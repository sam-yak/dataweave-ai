"""
Validation Agent — Agent 5 of 5
The quality gate.

Checks the transformed DataFrame against the target schema rules:
- Required fields present
- Type conformance
- Format validation (email, phone, URL, zip)
- Duplicate detection
- Anomaly detection (statistical outliers)
- Generates a quality score

LLM Usage: None (fully deterministic)
"""

import re
import pandas as pd
from typing import Optional


class ValidationAgent:
    """Validate transformed data against target schema rules."""

    def process(self, df: pd.DataFrame, target_schema: dict) -> dict:
        """
        Main entry point. Validates the transformed DataFrame.

        Args:
            df: Transformed DataFrame from Transform Agent
            target_schema: Target schema with field definitions

        Returns:
            Validation report dict with errors, warnings, and quality score
        """
        schema_json = target_schema.get("schema_json", target_schema)
        if isinstance(schema_json, str):
            import json
            schema_json = json.loads(schema_json)

        fields = schema_json.get("fields", [])
        field_lookup = {f["name"]: f for f in fields}

        errors = []      # Hard failures — data is wrong
        warnings = []    # Soft issues — data might be wrong

        # Run all validation checks
        errors.extend(self._check_required_fields(df, fields))
        errors.extend(self._check_type_conformance(df, fields))
        errors.extend(self._check_format_validation(df, field_lookup))
        warnings.extend(self._check_duplicates(df, field_lookup))
        warnings.extend(self._check_anomalies(df, field_lookup))
        warnings.extend(self._check_completeness(df, fields))

        # Calculate quality score
        quality_score = self._calculate_quality_score(df, errors, warnings)

        # Build row-level error map
        row_errors = self._build_row_error_map(errors)

        # Summary stats
        rows_with_errors = len(set(e["row"] for e in errors if e.get("row") is not None))
        clean_rows = len(df) - rows_with_errors

        return {
            "quality_score": quality_score,
            "total_rows": len(df),
            "clean_rows": clean_rows,
            "rows_with_errors": rows_with_errors,
            "total_errors": len(errors),
            "total_warnings": len(warnings),
            "errors": errors,
            "warnings": warnings,
            "row_errors": row_errors,
            "summary": {
                "required_field_errors": sum(1 for e in errors if e["type"] == "required_field"),
                "type_errors": sum(1 for e in errors if e["type"] == "type_conformance"),
                "format_errors": sum(1 for e in errors if e["type"] == "format_validation"),
                "duplicate_warnings": sum(1 for w in warnings if w["type"] == "duplicate"),
                "anomaly_warnings": sum(1 for w in warnings if w["type"] == "anomaly"),
            },
        }

    # ── Required Field Checks ────────────────────────────────

    def _check_required_fields(self, df: pd.DataFrame, fields: list[dict]) -> list[dict]:
        """Check that all required fields have values."""
        errors = []
        for field in fields:
            if not field.get("required"):
                continue

            field_name = field["name"]
            if field_name not in df.columns:
                errors.append({
                    "type": "required_field",
                    "field": field_name,
                    "row": None,
                    "message": f"Required field '{field_name}' is missing from the data",
                    "severity": "error",
                })
                continue

            # Check for null/empty values in required field
            for idx, val in df[field_name].items():
                if pd.isna(val) or val is None or (isinstance(val, str) and val.strip() == ""):
                    errors.append({
                        "type": "required_field",
                        "field": field_name,
                        "row": int(idx),
                        "value": None,
                        "message": f"Required field '{field_name}' is empty at row {int(idx) + 1}",
                        "severity": "error",
                    })

        return errors

    # ── Type Conformance ─────────────────────────────────────

    def _check_type_conformance(self, df: pd.DataFrame, fields: list[dict]) -> list[dict]:
        """Check that values match expected types."""
        errors = []

        for field in fields:
            field_name = field["name"]
            expected_type = field.get("type", "string")

            if field_name not in df.columns:
                continue

            for idx, val in df[field_name].items():
                if pd.isna(val) or val is None:
                    continue  # Nulls are handled by required check

                if expected_type == "integer":
                    if not self._is_valid_integer(val):
                        errors.append({
                            "type": "type_conformance",
                            "field": field_name,
                            "row": int(idx),
                            "value": str(val),
                            "expected": "integer",
                            "message": f"'{val}' is not a valid integer at row {int(idx) + 1}",
                            "severity": "error",
                        })

                elif expected_type == "float":
                    if not self._is_valid_float(val):
                        errors.append({
                            "type": "type_conformance",
                            "field": field_name,
                            "row": int(idx),
                            "value": str(val),
                            "expected": "float",
                            "message": f"'{val}' is not a valid number at row {int(idx) + 1}",
                            "severity": "error",
                        })

                elif expected_type == "date":
                    if not self._is_valid_date(val):
                        errors.append({
                            "type": "type_conformance",
                            "field": field_name,
                            "row": int(idx),
                            "value": str(val),
                            "expected": "date (YYYY-MM-DD)",
                            "message": f"'{val}' is not a valid date at row {int(idx) + 1}",
                            "severity": "error",
                        })

        return errors

    # ── Format Validation ────────────────────────────────────

    def _check_format_validation(self, df: pd.DataFrame, field_lookup: dict) -> list[dict]:
        """Validate field formats (email, phone, URL, zipcode)."""
        errors = []

        for field_name, field_spec in field_lookup.items():
            fmt = field_spec.get("format")
            if not fmt or field_name not in df.columns:
                continue

            for idx, val in df[field_name].items():
                if pd.isna(val) or val is None:
                    continue

                val_str = str(val).strip()
                if val_str == "":
                    continue

                is_valid = True

                if fmt == "email":
                    is_valid = self._is_valid_email(val_str)
                elif fmt == "phone":
                    is_valid = self._is_valid_phone(val_str)
                elif fmt == "url":
                    is_valid = self._is_valid_url(val_str)
                elif fmt == "zipcode":
                    is_valid = self._is_valid_zipcode(val_str)

                if not is_valid:
                    errors.append({
                        "type": "format_validation",
                        "field": field_name,
                        "row": int(idx),
                        "value": val_str,
                        "expected_format": fmt,
                        "message": f"'{val_str}' is not a valid {fmt} at row {int(idx) + 1}",
                        "severity": "error",
                    })

        return errors

    # ── Duplicate Detection ──────────────────────────────────

    def _check_duplicates(self, df: pd.DataFrame, field_lookup: dict) -> list[dict]:
        """Detect duplicate values in fields marked as unique."""
        warnings = []

        for field_name, field_spec in field_lookup.items():
            if not field_spec.get("unique") or field_name not in df.columns:
                continue

            # Find duplicates (ignoring nulls)
            non_null = df[field_name].dropna()
            duplicated = non_null[non_null.duplicated(keep=False)]

            if duplicated.empty:
                continue

            # Group duplicate values
            dup_values = duplicated.unique()
            for dup_val in dup_values:
                dup_rows = df[df[field_name] == dup_val].index.tolist()
                warnings.append({
                    "type": "duplicate",
                    "field": field_name,
                    "row": dup_rows[0],
                    "value": str(dup_val),
                    "duplicate_rows": [int(r) for r in dup_rows],
                    "message": f"Duplicate {field_name} '{dup_val}' found in rows {[r + 1 for r in dup_rows]}",
                    "severity": "warning",
                })

        return warnings

    # ── Anomaly Detection ────────────────────────────────────

    def _check_anomalies(self, df: pd.DataFrame, field_lookup: dict) -> list[dict]:
        """Detect statistical anomalies using IQR method for numeric fields."""
        warnings = []

        for field_name, field_spec in field_lookup.items():
            if field_spec.get("type") not in ("integer", "float"):
                continue
            if field_name not in df.columns:
                continue

            # Convert to numeric
            numeric_col = pd.to_numeric(df[field_name], errors="coerce")
            non_null = numeric_col.dropna()

            if len(non_null) < 10:
                continue  # Not enough data for meaningful anomaly detection

            # IQR method
            q1 = non_null.quantile(0.25)
            q3 = non_null.quantile(0.75)
            iqr = q3 - q1

            if iqr == 0:
                continue  # All values are the same

            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr

            outliers = non_null[(non_null < lower_bound) | (non_null > upper_bound)]

            for idx, val in outliers.items():
                warnings.append({
                    "type": "anomaly",
                    "field": field_name,
                    "row": int(idx),
                    "value": float(val),
                    "bounds": {"lower": float(lower_bound), "upper": float(upper_bound)},
                    "message": f"Anomalous value {val} in '{field_name}' at row {int(idx) + 1} (expected {lower_bound:.1f}-{upper_bound:.1f})",
                    "severity": "warning",
                })

        return warnings

    # ── Completeness Check ───────────────────────────────────

    def _check_completeness(self, df: pd.DataFrame, fields: list[dict]) -> list[dict]:
        """Warn about columns with high null rates."""
        warnings = []

        for field in fields:
            field_name = field["name"]
            if field_name not in df.columns:
                continue

            total = len(df)
            null_count = df[field_name].isna().sum() + (df[field_name].apply(
                lambda x: isinstance(x, str) and x.strip() == ""
            )).sum()

            null_rate = null_count / total if total > 0 else 0

            if null_rate > 0.5 and not field.get("required"):
                warnings.append({
                    "type": "completeness",
                    "field": field_name,
                    "row": None,
                    "null_rate": round(null_rate, 2),
                    "null_count": int(null_count),
                    "total": total,
                    "message": f"Field '{field_name}' is {null_rate:.0%} empty ({int(null_count)}/{total} rows)",
                    "severity": "warning",
                })

        return warnings

    # ── Quality Score Calculation ─────────────────────────────

    def _calculate_quality_score(self, df: pd.DataFrame, errors: list, warnings: list) -> float:
        """
        Calculate overall data quality score (0-100).
        Formula: (rows_with_zero_errors / total_rows) × 100,
        with minor deductions for warnings.
        """
        if len(df) == 0:
            return 0.0

        # Count rows with errors
        error_rows = set()
        for e in errors:
            if e.get("row") is not None:
                error_rows.add(e["row"])

        clean_rows = len(df) - len(error_rows)
        base_score = (clean_rows / len(df)) * 100

        # Small deductions for warnings (max 10 points)
        warning_deduction = min(len(warnings) * 0.5, 10)

        score = max(base_score - warning_deduction, 0)
        return round(score, 1)

    # ── Row Error Map ────────────────────────────────────────

    def _build_row_error_map(self, errors: list) -> dict:
        """Build a map of row_index → list of errors for that row."""
        row_map = {}
        for e in errors:
            row = e.get("row")
            if row is not None:
                if row not in row_map:
                    row_map[row] = []
                row_map[row].append(e)
        return row_map

    # ── Validation Helpers ───────────────────────────────────

    @staticmethod
    def _is_valid_integer(val) -> bool:
        try:
            cleaned = str(val).replace(",", "").strip()
            float(cleaned)
            return float(cleaned) == int(float(cleaned))
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _is_valid_float(val) -> bool:
        try:
            float(str(val).replace(",", "").strip())
            return True
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _is_valid_date(val) -> bool:
        try:
            # Check if it matches YYYY-MM-DD format (output of Transform Agent)
            return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", str(val).strip()))
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _is_valid_email(val: str) -> bool:
        pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
        return bool(re.match(pattern, val))

    @staticmethod
    def _is_valid_phone(val: str) -> bool:
        digits = re.sub(r"[^\d]", "", val)
        return 7 <= len(digits) <= 15

    @staticmethod
    def _is_valid_url(val: str) -> bool:
        pattern = r"^https?://[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}(/.*)?$"
        return bool(re.match(pattern, val))

    @staticmethod
    def _is_valid_zipcode(val: str) -> bool:
        # US zip: 5 digits or 5+4
        # Also accept international postal codes (alphanumeric, 3-10 chars)
        us_pattern = r"^\d{5}(-\d{4})?$"
        intl_pattern = r"^[a-zA-Z0-9\s\-]{3,10}$"
        return bool(re.match(us_pattern, val) or re.match(intl_pattern, val))
