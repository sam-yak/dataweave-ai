"""
Schema Agent — Agent 2 of 5
The intelligence layer.

Profiles every column, checks the Pattern Agent first,
then sends unknown columns to the LLM Router.
Blends heuristic confidence with LLM confidence for final scores.

LLM Usage: Only for columns not found in Pattern Agent cache

v2: Handles split transform proposals from the LLM (split_name, split_address).
    When a split transform is proposed, the agent stores it as a single mapping
    with transform_type set. The orchestrator + transform agent handle the rest.
"""

import os
import re
from typing import Tuple
from agents.pattern import PatternAgent
from core.llm_router import LLMRouter
from supabase import create_client


# Split transforms that produce multiple output fields
SPLIT_TRANSFORMS = {"split_name", "split_address"}


class SchemaAgent:
    """Profile columns and propose intelligent mappings to target schema."""

    def __init__(self):
        self.pattern_agent = PatternAgent()
        self.llm_router = LLMRouter()
        self.supabase = create_client(
            os.getenv("SUPABASE_URL", ""),
            os.getenv("SUPABASE_SERVICE_KEY", "")
        )

    def process(self, job_id: str, target_schema_id: str) -> list[dict]:
        """
        Main entry point. Takes a job ID, reads its columns from the database,
        and produces mapping proposals for each column.

        Args:
            job_id: The job to process
            target_schema_id: The target schema to map to

        Returns:
            List of mapping proposals saved to the database
        """
        # 1. Fetch column data from database
        columns = self._get_columns(job_id)
        if not columns:
            raise ValueError(f"No columns found for job {job_id}")

        # 2. Fetch target schema
        target_schema = self._get_target_schema(target_schema_id)
        if not target_schema:
            raise ValueError(f"Target schema {target_schema_id} not found")

        schema_json = target_schema["schema_json"]
        if isinstance(schema_json, str):
            import json
            schema_json = json.loads(schema_json)

        # 3. Run Pattern Agent on all columns (batch lookup — one DB query)
        column_inputs = [
            {"name": col["source_name"], "normalized": col["normalized_name"]}
            for col in columns
        ]
        pattern_results = self.pattern_agent.lookup_batch(column_inputs, target_schema_id)

        # 4. Separate into matched (by pattern) and unmatched (need LLM)
        pattern_matched = []   # Columns resolved by Pattern Agent
        needs_llm = []         # Columns that need LLM mapping
        all_mappings = []      # Final results

        for col in columns:
            pattern_result = pattern_results.get(col["source_name"])

            if pattern_result and pattern_result["source"] == "pattern":
                # High-confidence pattern match — use it directly
                mapping = {
                    "job_id": job_id,
                    "column_id": col["id"],
                    "source_name": col["source_name"],
                    "target_field": pattern_result["target_field"],
                    "confidence": self._boost_confidence(pattern_result["confidence"], col, schema_json),
                    "transform_type": pattern_result.get("transform_type"),
                    "transform_config": pattern_result.get("transform_config", {}),
                    "status": "proposed",
                    "agent_source": "pattern",
                    "reasoning": f"Pattern Agent: known mapping with {pattern_result['confidence']:.0%} confidence",
                }
                pattern_matched.append(mapping)
                all_mappings.append(mapping)

            elif pattern_result and pattern_result["source"] == "pattern_low_confidence":
                # Low-confidence pattern — send to LLM for verification but include as hint
                needs_llm.append({
                    "name": col["source_name"],
                    "normalized": col["normalized_name"],
                    "detected_type": col.get("detected_type", "string"),
                    "sample_values": col.get("sample_values", []),
                    "null_count": col.get("null_count", 0),
                    "total_count": col.get("total_count", 0),
                    "unique_count": col.get("unique_count", 0),
                    "column_id": col["id"],
                    "pattern_hint": pattern_result["target_field"],
                })

            else:
                # No pattern at all — definitely needs LLM
                needs_llm.append({
                    "name": col["source_name"],
                    "normalized": col["normalized_name"],
                    "detected_type": col.get("detected_type", "string"),
                    "sample_values": col.get("sample_values", []),
                    "null_count": col.get("null_count", 0),
                    "total_count": col.get("total_count", 0),
                    "unique_count": col.get("unique_count", 0),
                    "column_id": col["id"],
                    "pattern_hint": None,
                })

        # 5. Call LLM for unmapped columns (if any)
        if needs_llm:
            already_mapped = [
                {"source": m["source_name"], "target_field": m["target_field"]}
                for m in pattern_matched
            ]

            llm_results = self.llm_router.map_columns(
                unmapped_columns=needs_llm,
                target_schema=schema_json,
                already_mapped=already_mapped
            )

            # Match LLM results back to columns
            llm_by_source = {r["source"]: r for r in llm_results}

            for col_info in needs_llm:
                llm_result = llm_by_source.get(col_info["name"], {})

                # Find the original column record to get the column_id
                col_record = next(
                    (c for c in columns if c["source_name"] == col_info["name"]),
                    None
                )
                if not col_record:
                    continue

                # Blend LLM confidence with heuristic boosts
                raw_confidence = llm_result.get("confidence", 0)
                target_field = llm_result.get("target_field")
                transform_type = llm_result.get("transform_type")

                boosted_confidence = self._apply_heuristic_boosts(
                    raw_confidence, col_info, target_field, schema_json
                )

                # v2: Build reasoning that mentions split transforms
                reasoning = llm_result.get("reasoning", "Mapped by Schema Agent via LLM")
                if transform_type in SPLIT_TRANSFORMS:
                    reasoning = f"[Split] {reasoning}"

                mapping = {
                    "job_id": job_id,
                    "column_id": col_record["id"],
                    "source_name": col_info["name"],
                    "target_field": target_field,
                    "confidence": boosted_confidence,
                    "transform_type": transform_type,
                    "transform_config": {},
                    "status": "proposed",
                    "agent_source": "schema",
                    "reasoning": reasoning,
                }
                all_mappings.append(mapping)

        # 6. Save all mappings to database
        for mapping in all_mappings:
            self.supabase.table("mappings").insert(mapping).execute()

        # 7. Log summary event
        pattern_count = len(pattern_matched)
        llm_count = len(needs_llm)
        total = len(all_mappings)
        mapped_count = sum(1 for m in all_mappings if m["target_field"] is not None)
        split_count = sum(1 for m in all_mappings if m.get("transform_type") in SPLIT_TRANSFORMS)

        summary_msg = (
            f"Mapped {mapped_count}/{total} columns. "
            f"Pattern Agent resolved {pattern_count}, LLM resolved {llm_count}."
        )
        if split_count > 0:
            summary_msg += f" {split_count} split transform(s) proposed."

        self._log_event(
            job_id, "schema", "completed",
            summary_msg,
            metadata={
                "pattern_matches": pattern_count,
                "llm_matches": llm_count,
                "total_mapped": mapped_count,
                "total_columns": total,
                "split_transforms": split_count,
                "llm_stats": self.llm_router.get_stats(),
            }
        )

        return all_mappings

    def _boost_confidence(self, base_confidence: float, column: dict, schema_json: dict) -> float:
        """Apply heuristic boosts to pattern-matched confidence."""
        confidence = base_confidence * 100  # Convert to 0-100 scale

        # Boost if the detected type matches the target field's expected type
        target_field_name = None
        for field in schema_json.get("fields", []):
            normalized_target = PatternAgent.normalize(field["name"])
            if normalized_target == column.get("normalized_name"):
                target_field_name = field
                break

        if target_field_name:
            expected_type = target_field_name.get("type", "string")
            detected_type = column.get("detected_type", "string")
            if expected_type == detected_type:
                confidence = min(confidence + 5, 99)

        return min(round(confidence, 1), 99)

    def _apply_heuristic_boosts(self, raw_confidence: float, column_info: dict,
                                 target_field: str, schema_json: dict) -> float:
        """Apply heuristic boosts/penalties to LLM confidence."""
        if target_field is None:
            return 0

        confidence = float(raw_confidence)

        # Boost: exact name match (after normalization)
        col_normalized = PatternAgent.normalize(column_info["name"])
        target_normalized = PatternAgent.normalize(target_field)
        if col_normalized == target_normalized:
            confidence = min(confidence + 15, 99)

        # Boost: partial name overlap
        elif (target_normalized in col_normalized) or (col_normalized in target_normalized):
            confidence = min(confidence + 8, 99)

        # Boost: detected type matches expected type
        target_field_def = None
        for field in schema_json.get("fields", []):
            if field["name"] == target_field:
                target_field_def = field
                break

        if target_field_def:
            expected_type = target_field_def.get("type", "string")
            detected_type = column_info.get("detected_type", "string")

            type_compatibility = {
                ("email", "string"): 10,
                ("integer", "integer"): 10,
                ("float", "float"): 10,
                ("date", "date"): 10,
                ("boolean", "boolean"): 10,
                ("string", "string"): 3,
            }
            boost = type_compatibility.get((detected_type, expected_type), 0)
            confidence = min(confidence + boost, 99)

            # Boost: email format column → email field
            if column_info.get("detected_type") == "email" and target_field_def.get("format") == "email":
                confidence = min(confidence + 10, 99)

        # Penalty: pattern hint disagreement
        if column_info.get("pattern_hint") and column_info["pattern_hint"] != target_field:
            confidence = max(confidence - 10, 0)

        return round(confidence, 1)

    def _get_columns(self, job_id: str) -> list[dict]:
        """Fetch columns for a job from database."""
        result = self.supabase.table("columns").select("*").eq("job_id", job_id).execute()
        return result.data

    def _get_target_schema(self, schema_id: str) -> dict:
        """Fetch a target schema from database."""
        result = self.supabase.table("target_schemas").select("*").eq("id", schema_id).execute()
        return result.data[0] if result.data else None

    def _log_event(self, job_id: str, agent: str, event_type: str,
                   message: str, metadata: dict = None):
        """Log an agent event."""
        self.supabase.table("events").insert({
            "job_id": job_id,
            "agent": agent,
            "event_type": event_type,
            "message": message,
            "metadata": metadata or {},
        }).execute()
