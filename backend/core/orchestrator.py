"""
Orchestrator — The brain that chains all 5 agents together.

State machine:
UPLOADED → INGESTING → PROFILING → MAPPING → AWAITING_REVIEW →
TRANSFORMING → VALIDATING → COMPLETE

The orchestrator holds the DataFrame in memory and passes it
between agents. Only metadata goes to the database.
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

        # ── Stage 1: Ingestion ──
        try:
            self._update_status(job_id, "ingesting")
            self._log(job_id, "ingestion", "started", "Parsing file...")

            df, metadata = self.ingestion_agent.process(file_bytes, filename)

            # Store DataFrame in memory for later stages
            self._dataframes[job_id] = df

            # Save metadata to database
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
            raise

        # ── Stage 2: Schema Agent (Pattern + LLM mapping) ──
        try:
            self._update_status(job_id, "mapping")
            self._log(job_id, "schema", "started", "Mapping columns to target schema...")

            mappings = self.schema_agent.process(job_id, target_schema_id)

            self._update_status(job_id, "awaiting_review")
            self._log(job_id, "orchestrator", "awaiting_review",
                     "Mapping complete — awaiting human review")

            # Build response
            pattern_count = sum(1 for m in mappings if m["agent_source"] == "pattern")
            llm_count = sum(1 for m in mappings if m["agent_source"] == "schema")
            mapped_count = sum(1 for m in mappings if m["target_field"] is not None)

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
            raise

    # ── Phase 2: Transform → Validate → Complete ────────────

    def complete_pipeline(self, job_id: str) -> dict:
        """
        Run Phase 2 of the pipeline (after human review):
        1. Fetch approved mappings
        2. Transform data
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
            raise ValueError(
                "DataFrame not found in memory. The file may need to be re-uploaded. "
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

        # ── Stage 3: Transform ──
        try:
            self._update_status(job_id, "transforming")
            self._log(job_id, "transform", "started",
                     f"Applying {len(active_mappings)} mappings...")

            transformed_df = self.transform_agent.process(df, active_mappings, target_schema)

            self._log(job_id, "transform", "completed",
                     f"Transformed {len(transformed_df)} rows, {len(transformed_df.columns)} columns")

        except Exception as e:
            self._update_status(job_id, "failed", str(e))
            self._log(job_id, "transform", "failed", str(e))
            raise

        # ── Stage 4: Validation ──
        try:
            self._update_status(job_id, "validating")
            self._log(job_id, "validation", "started", "Running quality checks...")

            validation_report = self.validation_agent.process(transformed_df, target_schema)

            quality_score = validation_report["quality_score"]

            # Update job with final results
            self.supabase.table("jobs").update({
                "status": "complete",
                "quality_score": quality_score,
            }).eq("id", job_id).execute()

            self._log(job_id, "validation", "completed",
                     f"Quality score: {quality_score}% — "
                     f"{validation_report['clean_rows']}/{validation_report['total_rows']} clean rows, "
                     f"{validation_report['total_errors']} errors, "
                     f"{validation_report['total_warnings']} warnings")

            self._log(job_id, "orchestrator", "complete", "Pipeline complete")

        except Exception as e:
            self._update_status(job_id, "failed", str(e))
            self._log(job_id, "validation", "failed", str(e))
            raise

        # Convert transformed data to exportable formats
        export_data = self._prepare_export(transformed_df)

        # Clean up in-memory DataFrame
        del self._dataframes[job_id]

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
                "summary": validation_report["summary"],
                "errors": validation_report["errors"][:50],  # Limit to first 50 for API response
                "warnings": validation_report["warnings"][:20],
            },
            "export": export_data,
            "mappings_applied": len(active_mappings),
            "mappings_rejected": len(rejected),
        }

    def _prepare_export(self, df: pd.DataFrame) -> dict:
        """Prepare transformed data for export in multiple formats."""
        # CSV string
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_string = csv_buffer.getvalue()

        # JSON array
        json_records = df.where(df.notna(), None).to_dict(orient="records")

        # Preview (first 5 rows)
        preview = df.head(5).where(df.head(5).notna(), None).to_dict(orient="records")

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
