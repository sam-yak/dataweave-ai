"""
Pattern Agent — Agent 5 of 5 (but used early in the pipeline)
The learning memory of the system.

Checks if a column name has been seen before and returns
the known mapping. Learns from human corrections over time.
This is the agent that saves money — every cache hit avoids an LLM call.

LLM Usage: None (pure database lookup)
"""

import re
import os
from typing import Optional
from supabase import create_client


class PatternAgent:
    """Look up known column mappings and learn from corrections."""

    # Minimum confidence to auto-apply a pattern without LLM verification
    AUTO_APPLY_THRESHOLD = 0.85

    # Minimum approval count before a pattern is considered reliable
    MIN_APPROVALS_FOR_AUTO = 5

    def __init__(self):
        self.supabase = create_client(
            os.getenv("SUPABASE_URL", ""),
            os.getenv("SUPABASE_SERVICE_KEY", "")
        )

    def lookup(self, column_name: str, target_schema_id: str) -> Optional[dict]:
        """
        Check if we have a known mapping for this column name.

        Args:
            column_name: The raw source column name (e.g., "First Name")
            target_schema_id: The target schema being mapped to

        Returns:
            dict with mapping info if found, None if no pattern exists
            {
                "target_field": "first_name",
                "confidence": 0.95,
                "transform_type": null,
                "transform_config": {},
                "source": "pattern"
            }
        """
        normalized = self.normalize(column_name)

        result = (
            self.supabase.table("patterns")
            .select("*")
            .eq("target_schema_id", target_schema_id)
            .eq("source_name_normalized", normalized)
            .order("confidence", desc=True)
            .limit(1)
            .execute()
        )

        if not result.data:
            return None

        pattern = result.data[0]

        # Only auto-apply if the pattern is reliable enough
        if (pattern["confidence"] >= self.AUTO_APPLY_THRESHOLD
                and pattern["approval_count"] >= self.MIN_APPROVALS_FOR_AUTO):
            # Update last_used_at
            self.supabase.table("patterns").update({
                "last_used_at": "now()"
            }).eq("id", pattern["id"]).execute()

            return {
                "target_field": pattern["target_field"],
                "confidence": pattern["confidence"],
                "transform_type": pattern.get("transform_type"),
                "transform_config": pattern.get("transform_config", {}),
                "source": "pattern",
                "pattern_id": pattern["id"],
            }

        # Pattern exists but confidence is too low — return it but flag it
        # so the Schema Agent can verify or override
        return {
            "target_field": pattern["target_field"],
            "confidence": pattern["confidence"],
            "transform_type": pattern.get("transform_type"),
            "transform_config": pattern.get("transform_config", {}),
            "source": "pattern_low_confidence",
            "pattern_id": pattern["id"],
        }

    def lookup_batch(self, columns: list[dict], target_schema_id: str) -> dict:
        """
        Look up patterns for multiple columns at once.

        Args:
            columns: List of {"name": "First Name", "normalized": "firstname"}
            target_schema_id: The target schema ID

        Returns:
            dict mapping column name → pattern result (or None if not found)
            {
                "First Name": {"target_field": "first_name", "confidence": 0.95, ...},
                "WeirdColumn": None,
            }
        """
        results = {}

        # Get all patterns for this schema in one query
        all_patterns = (
            self.supabase.table("patterns")
            .select("*")
            .eq("target_schema_id", target_schema_id)
            .execute()
        )

        # Build a lookup dict: normalized_name → best pattern
        pattern_lookup = {}
        for p in all_patterns.data:
            key = p["source_name_normalized"]
            if key not in pattern_lookup or p["confidence"] > pattern_lookup[key]["confidence"]:
                pattern_lookup[key] = p

        # Match each column
        for col in columns:
            normalized = col["normalized"]

            if normalized in pattern_lookup:
                pattern = pattern_lookup[normalized]

                if (pattern["confidence"] >= self.AUTO_APPLY_THRESHOLD
                        and pattern["approval_count"] >= self.MIN_APPROVALS_FOR_AUTO):
                    results[col["name"]] = {
                        "target_field": pattern["target_field"],
                        "confidence": pattern["confidence"],
                        "transform_type": pattern.get("transform_type"),
                        "transform_config": pattern.get("transform_config", {}),
                        "source": "pattern",
                        "pattern_id": pattern["id"],
                    }
                else:
                    results[col["name"]] = {
                        "target_field": pattern["target_field"],
                        "confidence": pattern["confidence"],
                        "transform_type": pattern.get("transform_type"),
                        "transform_config": pattern.get("transform_config", {}),
                        "source": "pattern_low_confidence",
                        "pattern_id": pattern["id"],
                    }
            else:
                results[col["name"]] = None

        return results

    def record_approval(self, target_schema_id: str, source_name: str, target_field: str,
                        transform_type: str = None, transform_config: dict = None):
        """
        Record that a user approved a mapping. Increases confidence.

        Called when a user clicks "Approve" on a mapping in the UI.
        """
        normalized = self.normalize(source_name)

        # Check if pattern already exists
        existing = (
            self.supabase.table("patterns")
            .select("*")
            .eq("target_schema_id", target_schema_id)
            .eq("source_name_normalized", normalized)
            .eq("target_field", target_field)
            .execute()
        )

        if existing.data:
            # Update existing pattern
            pattern = existing.data[0]
            new_approvals = pattern["approval_count"] + 1
            total = new_approvals + pattern["rejection_count"]
            new_confidence = new_approvals / total if total > 0 else 0.5

            self.supabase.table("patterns").update({
                "approval_count": new_approvals,
                "confidence": round(new_confidence, 4),
                "last_used_at": "now()",
            }).eq("id", pattern["id"]).execute()
        else:
            # Create new pattern
            self.supabase.table("patterns").insert({
                "target_schema_id": target_schema_id,
                "source_name_normalized": normalized,
                "target_field": target_field,
                "transform_type": transform_type,
                "transform_config": transform_config or {},
                "approval_count": 1,
                "rejection_count": 0,
                "confidence": 0.6,  # New patterns start at moderate confidence
            }).execute()

    def record_rejection(self, target_schema_id: str, source_name: str, target_field: str):
        """
        Record that a user rejected a mapping. Decreases confidence.

        Called when a user clicks "Reject" on a mapping in the UI.
        """
        normalized = self.normalize(source_name)

        existing = (
            self.supabase.table("patterns")
            .select("*")
            .eq("target_schema_id", target_schema_id)
            .eq("source_name_normalized", normalized)
            .eq("target_field", target_field)
            .execute()
        )

        if existing.data:
            pattern = existing.data[0]
            new_rejections = pattern["rejection_count"] + 1
            total = pattern["approval_count"] + new_rejections
            new_confidence = pattern["approval_count"] / total if total > 0 else 0

            self.supabase.table("patterns").update({
                "rejection_count": new_rejections,
                "confidence": round(new_confidence, 4),
            }).eq("id", pattern["id"]).execute()

    def record_correction(self, target_schema_id: str, source_name: str,
                          wrong_target: str, correct_target: str,
                          transform_type: str = None, transform_config: dict = None):
        """
        Record that a user corrected a mapping (changed the target field).

        This is the most valuable learning signal:
        - Decreases confidence in the wrong mapping
        - Increases confidence in the correct mapping
        """
        # Reject the wrong mapping
        self.record_rejection(target_schema_id, source_name, wrong_target)

        # Approve the correct mapping
        self.record_approval(target_schema_id, source_name, correct_target,
                            transform_type, transform_config)

    def get_stats(self, target_schema_id: str = None) -> dict:
        """Get pattern statistics — useful for monitoring and LinkedIn posts."""
        query = self.supabase.table("patterns").select("*")

        if target_schema_id:
            query = query.eq("target_schema_id", target_schema_id)

        result = query.execute()
        patterns = result.data

        if not patterns:
            return {"total": 0, "high_confidence": 0, "hit_rate": 0}

        total = len(patterns)
        high_confidence = sum(1 for p in patterns
                             if p["confidence"] >= self.AUTO_APPLY_THRESHOLD
                             and p["approval_count"] >= self.MIN_APPROVALS_FOR_AUTO)
        total_approvals = sum(p["approval_count"] for p in patterns)
        total_rejections = sum(p["rejection_count"] for p in patterns)
        total_decisions = total_approvals + total_rejections

        return {
            "total_patterns": total,
            "high_confidence_patterns": high_confidence,
            "auto_apply_rate": round(high_confidence / total, 2) if total > 0 else 0,
            "total_approvals": total_approvals,
            "total_rejections": total_rejections,
            "overall_accuracy": round(total_approvals / total_decisions, 4) if total_decisions > 0 else 0,
        }

    @staticmethod
    def normalize(name: str) -> str:
        """
        Normalize a column name for pattern matching.

        'First Name', 'first_name', 'firstName', 'FIRST_NAME',
        'First-Name', '  first name  ' → all become 'firstname'
        """
        # Convert camelCase to separate words: firstName → first Name
        name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
        # Remove ALL non-alphanumeric characters (spaces, underscores, hyphens, dots)
        name = re.sub(r'[^a-zA-Z0-9]', '', name)
        # Lowercase
        return name.lower()
