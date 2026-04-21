"""
Orchestrator — The brain that chains all 5 agents together.
 
State machine:
UPLOADED → INGESTING → PROFILING → MAPPING → AWAITING_REVIEW →
TRANSFORMING → VALIDATING → COMPLETE
 
The orchestrator holds the DataFrame in memory and passes it
between agents. Only metadata goes to the database.
 
v2: Handles 1-to-N (split) mappings. When a split_name or split_address
    mapping is approved, the orchestrator marks the secondary target fields
    as "covered" so the validation agent doesn't flag them as unmapped.
"""
 
import os
import io
import json
import pandas as pd
from typing import Optional
from supabase import create_client
from agents.ingestion import IngestionAgent
from agents.schema import SchemaAgent
from agents.pattern import PatternAgent
from agents.transform import TransformAgent
from agents.validation import ValidationAgent
from core.job_manager import job_manager
 
 
# Which target fields each split transform produces
SPLIT_TRANSFORM_OUTPUTS = {
    "split_name": {
        "primary": "first_name",
        "produces": ["first_name", "last_name"],
    },
    "split_address": {
        "primary": "address",
        "produces": ["address", "city", "state", "zip_code"],
    },
}
 
 
class Orchestrator:
    """Chain all agents together into a complete pipeline."""
 
    def __init__(self):
        self.supabase = create_client(
            os.getenv("SUPABASE_URL", ""),
            os.getenv("SUPABASE_SERVICE_KEY", "")
        )
        self.ingestion_agent = IngestionAgent()
        self.schema_agent = SchemaAgent()
        self.transform_agent = TransformAgent()
        self.validation_agent = ValidationAgent()
 
        # In-memory store for DataFrames during processing
        # Key: job_id, Value: DataFrame
        # This gets cleared when the job completes or the server restarts
        self._dataframes: dict[str, pd.DataFrame] = {}
 
        # In-memory store for raw file bytes (for re-ingestion after server restart)
        # Key: job_id, Value: (bytes, filename)
        self._file_cache: dict[str, tuple[bytes, str]] = {}
 
        # In-memory store for completed exports
        # Key: job_id, Value: CSV string
        # Persists after job completes so user can download later
        self._exports: dict[str, str] = {}
 
    # ── Phase 1: Upload → Ingest → Map → Await Review ───────
 
    def start_pipeline(self, file_bytes: bytes, filename: str, target_schema_id: str) -> dict:
        """
        Run Phase 1 of the pipeline:
        1. Create job
        2. Ingest file
        3. Profile and map columns (Pattern Agent + Schema Agent)
        4. Pause for human review
 
        Returns job info with mapping proposals.
        """
        # Validate target schema
        schema_result = self.supabase.table("target_schemas").select("*").eq("id", target_schema_id).execute()
        if not schema_result.data:
            raise ValueError(f"Target schema {target_schema_id} not found")
 
        # Create job
        job_result = self.supabase.table("jobs").insert({
            "status": "uploaded",
            "original_filename": filename,
            "file_type": filename.rsplit(".", 1)[-1].lower() if "." in filename else "unknown",
            "file_size_bytes": len(file_bytes),
            "target_schema_id": target_schema_id,
        }).execute()
 
        job = job_result.data[0]
        job_id = job["id"]
 
        self._log(job_id, "orchestrator", "job_created", f"Pipeline started for {filename}")
 
        # Track progress for async status polling
        job_manager.update(job_id, "ingesting", "Parsing and profiling your file...")
 
        # ── Stage 1: Ingestion ──
        try:
            self._update_status(job_id, "ingesting")
            self._log(job_id, "ingestion", "started", "Parsing file...")
 
            df, metadata = self.ingestion_agent.process(file_bytes, filename)
 
            # Store DataFrame in memory for later stages
            self._dataframes[job_id] = df
 
            # Cache raw file bytes for re-ingestion if server restarts before Phase 2
            self._file_cache[job_id] = (file_bytes, filename)
            self.supabase.table("jobs").update({
                "row_count": metadata["row_count"],
                "column_count": metadata["column_count"],
                "metadata": metadata,
            }).eq("id", job_id).execute()
 
            # Save column records
            for col_info in metadata["columns"]:
                normalized = PatternAgent.normalize(col_info["name"])
                self.supabase.table("columns").insert({
                    "job_id": job_id,
                    "source_name": col_info["name"],
                    "normalized_name": normalized,
                    "detected_type": col_info["detected_type"],
                    "sample_values": col_info["sample_values"],
                    "null_count": col_info["null_count"],
                    "total_count": col_info["total_count"],
                    "unique_count": col_info["unique_count"],
                    "profile_data": col_info,
                }).execute()
 
            self._log(job_id, "ingestion", "completed",
                     f"Parsed {metadata['row_count']} rows, {metadata['column_count']} columns")
 
        except Exception as e:
            self._update_status(job_id, "failed", str(e))
            self._log(job_id, "ingestion", "failed", str(e))
            job_manager.set_error(job_id, str(e))
            raise
 
        # ── Stage 2: Schema Agent (Pattern + LLM mapping) ──
        try:
            self._update_status(job_id, "mapping")
            self._log(job_id, "schema", "started", "Mapping columns to target schema...")
            job_manager.update(job_id, "mapping", "AI is mapping your columns to the target schema...")
 
            mappings = self.schema_agent.process(job_id, target_schema_id)
 
            self._update_status(job_id, "awaiting_review")
            self._log(job_id, "orchestrator", "awaiting_review",
                     "Mapping complete — awaiting human review")
            job_manager.update(job_id, "awaiting_review", "Mapping complete — ready for your review")
 
            # Build response
            pattern_count = sum(1 for m in mappings if m["agent_source"] == "pattern")
            llm_count = sum(1 for m in mappings if m["agent_source"] == "schema")
            mapped_count = sum(1 for m in mappings if m["target_field"] is not None)
 
            # v2: Count split transforms
            split_count = sum(1 for m in mappings if m.get("transform_type") in SPLIT_TRANSFORM_OUTPUTS)
 
            return {
                "job_id": job_id,
                "status": "awaiting_review",
                "metadata": metadata,
                "mapping_summary": {
                    "total_columns": len(mappings),
                    "mapped": mapped_count,
                    "unmapped": len(mappings) - mapped_count,
                    "pattern_agent_resolved": pattern_count,
                    "llm_resolved": llm_count,
                    "split_transforms": split_count,   # v2
                },
                "mappings": [
                    {
                        "id": m.get("id"),
                        "source_name": m["source_name"],
                        "target_field": m["target_field"],
                        "confidence": m["confidence"],
                        "agent_source": m["agent_source"],
                        "reasoning": m.get("reasoning", ""),
                        "transform_type": m.get("transform_type"),
                        "status": m["status"],
                    }
                    for m in mappings
                ],
            }
 
        except Exception as e:
            self._update_status(job_id, "failed", str(e))
            self._log(job_id, "schema", "failed", str(e))
            job_manager.set_error(job_id, str(e))
            raise
 
    # ── Phase 1 (Async): Same as start_pipeline but with pre-created job ──
 
    def start_pipeline_async(self, file_bytes: bytes, filename: str,
                              target_schema_id: str, job_id: str) -> dict:
        """
        Async version of start_pipeline. Uses a pre-created job_id
        (created by the upload endpoint before spawning this background task).
        This avoids a race condition where the frontend tries to poll status
        before the job record exists in the database.
        """
        # Validate target schema
        schema_result = self.supabase.table("target_schemas").select("*").eq(
            "id", target_schema_id).execute()
        if not schema_result.data:
            raise ValueError(f"Target schema {target_schema_id} not found")
 
        self._log(job_id, "orchestrator", "job_created",
                 f"Pipeline started for {filename}")
 
        # Track progress
        job_manager.update(job_id, "ingesting", "Parsing and profiling your file...")
 
        # ── Stage 1: Ingestion ──
        try:
            self._update_status(job_id, "ingesting")
            self._log(job_id, "ingestion", "started", "Parsing file...")
 
            df, metadata = self.ingestion_agent.process(file_bytes, filename)
 
            self._dataframes[job_id] = df
            self._file_cache[job_id] = (file_bytes, filename)
 
            self.supabase.table("jobs").update({
                "row_count": metadata["row_count"],
                "column_count": metadata["column_count"],
                "metadata": metadata,
            }).eq("id", job_id).execute()
 
            for col_info in metadata["columns"]:
                normalized = PatternAgent.normalize(col_info["name"])
                self.supabase.table("columns").insert({
                    "job_id": job_id,
                    "source_name": col_info["name"],
                    "normalized_name": normalized,
                    "detected_type": col_info["detected_type"],
                    "sample_values": col_info["sample_values"],
                    "null_count": col_info["null_count"],
                    "total_count": col_info["total_count"],
                    "unique_count": col_info["unique_count"],
                    "profile_data": col_info,
                }).execute()
 
            self._log(job_id, "ingestion", "completed",
                     f"Parsed {metadata['row_count']} rows, {metadata['column_count']} columns")
 
        except Exception as e:
            self._update_status(job_id, "failed", str(e))
            self._log(job_id, "ingestion", "failed", str(e))
            job_manager.set_error(job_id, str(e))
            raise
 
        # ── Stage 2: Schema Agent (Pattern + LLM mapping) ──
        try:
            self._update_status(job_id, "mapping")
            self._log(job_id, "schema", "started", "Mapping columns to target schema...")
            job_manager.update(job_id, "mapping",
                             "AI is mapping your columns to the target schema...")
 
            mappings = self.schema_agent.process(job_id, target_schema_id)
 
            self._update_status(job_id, "awaiting_review")
            self._log(job_id, "orchestrator", "awaiting_review",
                     "Mapping complete — awaiting human review")
            job_manager.update(job_id, "awaiting_review",
                             "Mapping complete — ready for your review")
 
            # Build response
            pattern_count = sum(1 for m in mappings if m["agent_source"] == "pattern")
            llm_count = sum(1 for m in mappings if m["agent_source"] == "schema")
            mapped_count = sum(1 for m in mappings if m["target_field"] is not None)
            split_count = sum(1 for m in mappings
                            if m.get("transform_type") in SPLIT_TRANSFORM_OUTPUTS)
 
            return {
                "job_id": job_id,
                "status": "awaiting_review",
                "metadata": metadata,
                "mapping_summary": {
                    "total_columns": len(mappings),
                    "mapped": mapped_count,
                    "unmapped": len(mappings) - mapped_count,
                    "pattern_agent_resolved": pattern_count,
                    "llm_resolved": llm_count,
                    "split_transforms": split_count,
                },
                "mappings": [
                    {
                        "id": m.get("id"),
                        "source_name": m["source_name"],
                        "target_field": m["target_field"],
                        "confidence": m["confidence"],
                        "agent_source": m["agent_source"],
                        "reasoning": m.get("reasoning", ""),
                        "transform_type": m.get("transform_type"),
                        "status": m["status"],
                    }
                    for m in mappings
                ],
            }
 
        except Exception as e:
            self._update_status(job_id, "failed", str(e))
            self._log(job_id, "schema", "failed", str(e))
            job_manager.set_error(job_id, str(e))
            raise
 
    # ── Phase 2: Transform → Validate → Complete ────────────
 
    def complete_pipeline(self, job_id: str) -> dict:
        """
        Run Phase 2 of the pipeline (after human review):
        1. Fetch approved mappings
        2. Transform data (including split transforms)
        3. Validate results
        4. Return quality report + transformed data
 
        Call this after the user has approved/corrected mappings.
        """
        # Get job info
        job = self._get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
 
        if job["status"] not in ("awaiting_review", "transforming"):
            raise ValueError(f"Job is in '{job['status']}' state. Expected 'awaiting_review'.")
 
        # Get the DataFrame from memory
        df = self._dataframes.get(job_id)
        if df is None:
            # Try re-ingesting from cached file bytes
            cached = self._file_cache.get(job_id)
            if cached:
                file_bytes, filename = cached
                self._log(job_id, "orchestrator", "re_ingesting",
                         "DataFrame expired — re-parsing from cached file bytes...")
                df, _ = self.ingestion_agent.process(file_bytes, filename)
                self._dataframes[job_id] = df
            else:
                raise ValueError(
                    "DataFrame not found in memory and no cached file bytes. "
                    "The file needs to be re-uploaded. "
                    "This happens if the server restarted between upload and review."
                )
 
        # Get target schema
        schema = self.supabase.table("target_schemas").select("*").eq(
            "id", job["target_schema_id"]).execute()
        if not schema.data:
            raise ValueError("Target schema not found")
        target_schema = schema.data[0]
 
        # Get mappings
        mappings_result = self.supabase.table("mappings").select("*").eq("job_id", job_id).execute()
        mappings = mappings_result.data
 
        # Check if any mappings are still "proposed" (not reviewed)
        proposed = [m for m in mappings if m["status"] == "proposed"]
        approved_or_corrected = [m for m in mappings if m["status"] in ("approved", "corrected")]
        rejected = [m for m in mappings if m["status"] == "rejected"]
 
        # Auto-approve any remaining proposed mappings with high confidence
        for m in proposed:
            if m["confidence"] >= 85:
                self.supabase.table("mappings").update(
                    {"status": "approved"}
                ).eq("id", m["id"]).execute()
                m["status"] = "approved"
                approved_or_corrected.append(m)
            else:
                # Low confidence proposed mappings are treated as rejected
                self.supabase.table("mappings").update(
                    {"status": "rejected"}
                ).eq("id", m["id"]).execute()
                m["status"] = "rejected"
                rejected.append(m)
 
        active_mappings = [m for m in mappings if m["status"] in ("approved", "corrected", "proposed")]
 
        # v2: Ensure split transforms have correct target field names
        active_mappings = self._enrich_split_configs(active_mappings, target_schema)
 
        # ── Stage 3: Transform ──
        try:
            self._update_status(job_id, "transforming")
            job_manager.update(job_id, "transforming", "Applying transforms to your data...")
 
            # v2: Log split transforms specifically
            split_count = sum(1 for m in active_mappings if m.get("transform_type") in SPLIT_TRANSFORM_OUTPUTS)
            if split_count > 0:
                self._log(job_id, "transform", "started",
                         f"Applying {len(active_mappings)} mappings ({split_count} split transforms)...")
            else:
                self._log(job_id, "transform", "started",
                         f"Applying {len(active_mappings)} mappings...")
 
            transformed_df = self.transform_agent.process(df, active_mappings, target_schema)
 
            self._log(job_id, "transform", "completed",
                     f"Transformed {len(transformed_df)} rows, {len(transformed_df.columns)} columns")
 
        except Exception as e:
            self._update_status(job_id, "failed", str(e))
            self._log(job_id, "transform", "failed", str(e))
            job_manager.set_error(job_id, str(e))
            raise
 
        # ── Stage 4: Validation ──
        try:
            self._update_status(job_id, "validating")
            self._log(job_id, "validation", "started", "Running quality checks...")
            job_manager.update(job_id, "validating", "Running quality checks on transformed data...")
 
            # v2/P3: Pass mappings so validator knows which fields have source data
            validation_report = self.validation_agent.process(
                transformed_df, target_schema, mappings=active_mappings
            )
 
            quality_score = validation_report["quality_score"]
 
            # Update job with final results
            self.supabase.table("jobs").update({
                "status": "complete",
                "quality_score": quality_score,
            }).eq("id", job_id).execute()
 
            info_count = validation_report.get("total_info", 0)
            info_msg = f", {info_count} info" if info_count > 0 else ""
 
            self._log(job_id, "validation", "completed",
                     f"Quality score: {quality_score}% — "
                     f"{validation_report['clean_rows']}/{validation_report['total_rows']} clean rows, "
                     f"{validation_report['total_errors']} errors, "
                     f"{validation_report['total_warnings']} warnings{info_msg}")
 
            self._log(job_id, "orchestrator", "complete", "Pipeline complete")
 
        except Exception as e:
            self._update_status(job_id, "failed", str(e))
            self._log(job_id, "validation", "failed", str(e))
            job_manager.set_error(job_id, str(e))
            raise
 
        # Convert transformed data to exportable formats
        export_data = self._prepare_export(transformed_df)
 
        # Cache the CSV export for later download
        self._exports[job_id] = export_data["csv"]
 
        # Clean up in-memory DataFrame and file cache (no longer needed)
        self._dataframes.pop(job_id, None)
        self._file_cache.pop(job_id, None)
 
        return {
            "job_id": job_id,
            "status": "complete",
            "quality_score": quality_score,
            "validation_report": {
                "total_rows": validation_report["total_rows"],
                "clean_rows": validation_report["clean_rows"],
                "rows_with_errors": validation_report["rows_with_errors"],
                "total_errors": validation_report["total_errors"],
                "total_warnings": validation_report["total_warnings"],
                "total_info": validation_report.get("total_info", 0),
                "summary": validation_report["summary"],
                "errors": validation_report["errors"][:50],  # Limit to first 50 for API response
                "warnings": validation_report["warnings"][:20],
                "info": validation_report.get("info", []),
            },
            "export": export_data,
            "mappings_applied": len(active_mappings),
            "mappings_rejected": len(rejected),
        }
 
    # ── v2: Enrich split transform configs ───────────────────
 
    def _enrich_split_configs(self, mappings: list[dict], target_schema: dict) -> list[dict]:
        """
        For split mappings, ensure the transform_config has the correct
        target field names from the schema.
 
        v2.1: If the Schema Agent already set a valid config (e.g.,
        consumer_first_name instead of first_name), respect it.
        Only build a new config if the existing one is empty or missing.
        """
        schema_json = target_schema.get("schema_json", target_schema)
        if isinstance(schema_json, str):
            schema_json = json.loads(schema_json)
 
        schema_field_names = {f["name"] for f in schema_json.get("fields", [])}
 
        enriched = []
        for m in mappings:
            m = dict(m)  # copy so we don't mutate the original
 
            transform_type = m.get("transform_type")
 
            if transform_type == "split_name":
                existing_config = m.get("transform_config") or {}
 
                # Check if Schema Agent already set valid field names
                # that actually exist in the target schema
                existing_first = existing_config.get("first_name_field", "")
                existing_last = existing_config.get("last_name_field", "")
 
                if existing_first in schema_field_names and existing_last in schema_field_names:
                    # Schema Agent's config is valid — keep it
                    m["transform_config"] = existing_config
                else:
                    # Need to find the right fields — use substring matching
                    first_field = None
                    last_field = None
 
                    for fname in schema_field_names:
                        lower = fname.lower()
                        if "first" in lower and "name" in lower:
                            first_field = fname
                        elif "last" in lower and "name" in lower:
                            last_field = fname
 
                    # Fallback to exact match if substring didn't work
                    if not first_field:
                        first_field = self._find_field_like(schema_field_names, [
                            "first_name", "firstname", "fname", "given_name", "givenname"
                        ])
                    if not last_field:
                        last_field = self._find_field_like(schema_field_names, [
                            "last_name", "lastname", "lname", "surname", "family_name", "familyname"
                        ])
 
                    m["transform_config"] = {
                        "first_name_field": first_field or "first_name",
                        "last_name_field": last_field or "last_name",
                    }
 
            elif transform_type == "split_address":
                existing_config = m.get("transform_config") or {}
 
                # Check if Schema Agent already set valid field names
                existing_street = existing_config.get("street_field", "")
                existing_city = existing_config.get("city_field", "")
 
                if existing_street in schema_field_names and existing_city in schema_field_names:
                    # Schema Agent's config is valid — keep it
                    m["transform_config"] = existing_config
                else:
                    # Need to find the right fields — use substring matching
                    street_field = None
                    city_field = None
                    state_field = None
                    zip_field = None
 
                    for fname in schema_field_names:
                        lower = fname.lower()
                        if lower in ("address", "street", "street_address", "mailing_address"):
                            street_field = fname
                        elif lower in ("city",):
                            city_field = fname
                        elif lower in ("state", "province", "state_province"):
                            state_field = fname
                        elif "zip" in lower or "postal" in lower:
                            zip_field = fname
 
                    # Fallback to exact match
                    if not street_field:
                        street_field = self._find_field_like(schema_field_names, [
                            "address", "street", "address_line1", "addressline1", "street_address"
                        ])
                    if not city_field:
                        city_field = self._find_field_like(schema_field_names, [
                            "city", "address_city", "town"
                        ])
                    if not state_field:
                        state_field = self._find_field_like(schema_field_names, [
                            "state", "address_state", "province", "state_province"
                        ])
                    if not zip_field:
                        zip_field = self._find_field_like(schema_field_names, [
                            "zip_code", "zipcode", "zip", "postal_code", "postalcode",
                            "address_postal_code"
                        ])
 
                    m["transform_config"] = {
                        "street_field": street_field or "address",
                        "city_field": city_field or "city",
                        "state_field": state_field or "state",
                        "zip_field": zip_field or "zip_code",
                    }
 
            enriched.append(m)
 
        return enriched
 
    @staticmethod
    def _find_field_like(schema_fields: set, candidates: list[str]) -> Optional[str]:
        """Find the first candidate that exists in the schema fields."""
        for candidate in candidates:
            if candidate in schema_fields:
                return candidate
        return None
 
    # ── Export ────────────────────────────────────────────────
 
    def _prepare_export(self, df: pd.DataFrame) -> dict:
        """Prepare transformed data for export in multiple formats."""
        # Replace all NaN/NaT with None for JSON compatibility
        clean_df = df.copy()
        clean_df = clean_df.astype(object)
        clean_df = clean_df.where(clean_df.notna(), None)
 
        # CSV string
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_string = csv_buffer.getvalue()
 
        # JSON array — convert to Python native types
        json_records = []
        for _, row in clean_df.iterrows():
            record = {}
            for col in clean_df.columns:
                val = row[col]
                # Force Python native types (not numpy)
                if val is None:
                    record[col] = None
                elif isinstance(val, (int, float, bool, str)):
                    record[col] = val
                else:
                    record[col] = str(val)
            json_records.append(record)
 
        # Preview (first 5 rows)
        preview = json_records[:5]
 
        return {
            "csv": csv_string,
            "json": json_records,
            "preview": preview,
            "columns": list(df.columns),
            "row_count": len(df),
        }
 
    # ── Helpers ──────────────────────────────────────────────
 
    def _get_job(self, job_id: str) -> Optional[dict]:
        result = self.supabase.table("jobs").select("*").eq("id", job_id).execute()
        return result.data[0] if result.data else None
 
    def _update_status(self, job_id: str, status: str, error: str = None):
        data = {"status": status}
        if error:
            data["error_message"] = error
        self.supabase.table("jobs").update(data).eq("id", job_id).execute()
 
    def _log(self, job_id: str, agent: str, event_type: str, message: str, metadata: dict = None):
        self.supabase.table("events").insert({
            "job_id": job_id,
            "agent": agent,
            "event_type": event_type,
            "message": message,
            "metadata": metadata or {},
        }).execute()
        
