"""
Transform Agent — Agent 4 of 5
The worker that actually changes the data.

Takes approved mappings and applies them to the raw DataFrame:
- Renames columns to target field names
- Casts types (string → int, string → float)
- Parses dates to ISO 8601
- Normalizes emails and phone numbers
- Merges/splits columns when needed
- Drops unmapped columns

LLM Usage: None (fully deterministic)
"""

import re
import pandas as pd
from dateutil import parser as date_parser
from typing import Optional


class TransformAgent:
    """Apply approved mappings to transform raw data into target schema format."""

    def process(self, df: pd.DataFrame, mappings: list[dict], target_schema: dict) -> pd.DataFrame:
        """
        Main entry point. Takes raw DataFrame and approved mappings,
        returns a transformed DataFrame matching the target schema.

        Args:
            df: Raw DataFrame from Ingestion Agent
            mappings: List of approved/proposed mappings with target_field and transform_type
            target_schema: Target schema definition with field specs

        Returns:
            Transformed DataFrame with columns renamed and data cleaned
        """
        # Work on a copy
        result = df.copy()

        # Build lookup: source_name → mapping info
        mapping_lookup = {}
        for m in mappings:
            if m.get("target_field") and m.get("status") != "rejected":
                mapping_lookup[m["source_name"]] = m

        # Build target field specs for validation context
        field_specs = {}
        schema_json = target_schema.get("schema_json", target_schema)
        if isinstance(schema_json, str):
            import json
            schema_json = json.loads(schema_json)
        for field in schema_json.get("fields", []):
            field_specs[field["name"]] = field

        # Step 1: Apply transforms to each mapped column
        transformed_columns = {}
        for source_name, mapping in mapping_lookup.items():
            if source_name not in result.columns:
                continue

            target_field = mapping["target_field"]
            transform_type = mapping.get("transform_type")
            transform_config = mapping.get("transform_config", {})
            field_spec = field_specs.get(target_field, {})

            # Get the column data
            col_data = result[source_name].copy()

            # Apply transform if specified
            if transform_type:
                col_data = self._apply_transform(col_data, transform_type, transform_config, field_spec)

            transformed_columns[target_field] = col_data

        # Step 2: Build the output DataFrame with only mapped columns
        output = pd.DataFrame(transformed_columns)

        # Step 3: Add missing required columns with None values
        for field in schema_json.get("fields", []):
            if field["name"] not in output.columns:
                if field.get("default") is not None:
                    output[field["name"]] = field["default"]
                else:
                    output[field["name"]] = None

        # Step 4: Reorder columns to match target schema field order
        schema_field_order = [f["name"] for f in schema_json.get("fields", [])]
        ordered_cols = [col for col in schema_field_order if col in output.columns]
        extra_cols = [col for col in output.columns if col not in schema_field_order]
        output = output[ordered_cols + extra_cols]

        return output

    def _apply_transform(self, series: pd.Series, transform_type: str,
                         config: dict, field_spec: dict) -> pd.Series:
        """Route to the correct transform function."""
        transforms = {
            "cast_integer": self._cast_integer,
            "cast_float": self._cast_float,
            "parse_date": self._parse_date,
            "cast_boolean": self._cast_boolean,
            "lowercase": self._lowercase,
            "uppercase": self._uppercase,
            "titlecase": self._titlecase,
            "phone_normalize": self._phone_normalize,
            "email_normalize": self._email_normalize,
        }

        transform_fn = transforms.get(transform_type)
        if transform_fn:
            return transform_fn(series, config)

        # Unknown transform — return as-is
        return series

    # ── Type Casting ─────────────────────────────────────────

    def _cast_integer(self, series: pd.Series, config: dict) -> pd.Series:
        """Convert to integer, handling commas and decimals."""
        def to_int(val):
            if pd.isna(val) or val is None:
                return None
            try:
                # Remove commas, dollar signs, spaces
                cleaned = str(val).replace(",", "").replace("$", "").replace(" ", "").strip()
                if cleaned == "" or cleaned.lower() in ("null", "none", "n/a", "nan"):
                    return None
                return int(float(cleaned))
            except (ValueError, TypeError):
                return None
        return series.apply(to_int)

    def _cast_float(self, series: pd.Series, config: dict) -> pd.Series:
        """Convert to float, handling commas and currency symbols."""
        def to_float(val):
            if pd.isna(val) or val is None:
                return None
            try:
                cleaned = str(val).replace(",", "").replace("$", "").replace(" ", "").strip()
                if cleaned == "" or cleaned.lower() in ("null", "none", "n/a", "nan"):
                    return None
                return round(float(cleaned), 2)
            except (ValueError, TypeError):
                return None
        return series.apply(to_float)

    # ── Date Parsing ─────────────────────────────────────────

    def _parse_date(self, series: pd.Series, config: dict) -> pd.Series:
        """Parse various date formats into ISO 8601 (YYYY-MM-DD)."""
        def to_iso_date(val):
            if pd.isna(val) or val is None:
                return None
            val_str = str(val).strip()
            if val_str == "" or val_str.lower() in ("null", "none", "n/a", "nan"):
                return None
            try:
                # Try dateutil parser (handles most formats)
                parsed = date_parser.parse(val_str, dayfirst=False, fuzzy=True)
                return parsed.strftime("%Y-%m-%d")
            except (ValueError, TypeError, OverflowError):
                pass

            # Try common patterns manually
            patterns = [
                "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d",
                "%m-%d-%Y", "%d-%m-%Y", "%B %d %Y", "%b %d %Y",
                "%d %B %Y", "%d %b %Y", "%m.%d.%Y", "%d.%m.%Y",
                "%Y%m%d",
            ]
            for pattern in patterns:
                try:
                    parsed = pd.to_datetime(val_str, format=pattern)
                    return parsed.strftime("%Y-%m-%d")
                except (ValueError, TypeError):
                    continue

            return val_str  # Return original if parsing fails

        return series.apply(to_iso_date)

    # ── Boolean Casting ──────────────────────────────────────

    def _cast_boolean(self, series: pd.Series, config: dict) -> pd.Series:
        """Convert yes/no, true/false, 1/0 to boolean."""
        true_values = {"true", "yes", "1", "y", "on", "active", "enabled"}
        false_values = {"false", "no", "0", "n", "off", "inactive", "disabled"}

        def to_bool(val):
            if pd.isna(val) or val is None:
                return None
            val_str = str(val).strip().lower()
            if val_str in true_values:
                return True
            if val_str in false_values:
                return False
            return None
        return series.apply(to_bool)

    # ── String Transforms ────────────────────────────────────

    def _lowercase(self, series: pd.Series, config: dict) -> pd.Series:
        """Convert to lowercase."""
        return series.apply(lambda x: str(x).lower().strip() if pd.notna(x) and x is not None else None)

    def _uppercase(self, series: pd.Series, config: dict) -> pd.Series:
        """Convert to uppercase."""
        return series.apply(lambda x: str(x).upper().strip() if pd.notna(x) and x is not None else None)

    def _titlecase(self, series: pd.Series, config: dict) -> pd.Series:
        """Convert to title case."""
        return series.apply(lambda x: str(x).strip().title() if pd.notna(x) and x is not None else None)

    # ── Phone Normalization ──────────────────────────────────

    def _phone_normalize(self, series: pd.Series, config: dict) -> pd.Series:
        """Normalize phone numbers to a consistent format."""
        def normalize_phone(val):
            if pd.isna(val) or val is None:
                return None
            val_str = str(val).strip()
            if val_str == "" or val_str.lower() in ("null", "none", "n/a", "nan"):
                return None

            # Extract only digits and leading +
            has_plus = val_str.startswith("+")
            digits = re.sub(r"[^\d]", "", val_str)

            if not digits or len(digits) < 7:
                return val_str  # Too short to normalize, return as-is

            # If it starts with + keep the international format
            if has_plus:
                return f"+{digits}"

            # US/Canada: 10 digits → +1XXXXXXXXXX
            if len(digits) == 10:
                return f"+1{digits}"

            # 11 digits starting with 1 → +1XXXXXXXXXX
            if len(digits) == 11 and digits.startswith("1"):
                return f"+{digits}"

            # Otherwise just return cleaned digits with +
            return f"+{digits}"

        return series.apply(normalize_phone)

    # ── Email Normalization ──────────────────────────────────

    def _email_normalize(self, series: pd.Series, config: dict) -> pd.Series:
        """Normalize email addresses — lowercase, strip whitespace."""
        def normalize_email(val):
            if pd.isna(val) or val is None:
                return None
            val_str = str(val).strip().lower()
            if val_str == "" or val_str in ("null", "none", "n/a", "nan"):
                return None
            # Basic email validation
            if "@" in val_str and "." in val_str:
                return val_str
            return None  # Not a valid email
        return series.apply(normalize_email)
