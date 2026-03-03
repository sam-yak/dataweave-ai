"""
Transform Agent — Agent 4 of 5
The worker that actually changes the data.

Takes approved mappings and applies them to the raw DataFrame:
- Renames columns to target field names
- Casts types (string → int, string → float)
- Parses dates to ISO 8601
- Normalizes emails and phone numbers
- Splits columns (name → first + last, address → components)  [v2]
- Normalizes currency values                                    [v2]
- Pads zip codes                                                [v2]
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

        # Step 1: Separate 1-to-1 mappings from 1-to-N (split) mappings
        simple_mappings = {}     # source → single target
        split_mappings = {}      # source → split transform producing multiple targets

        for source_name, mapping in mapping_lookup.items():
            if source_name not in result.columns:
                continue

            transform_type = mapping.get("transform_type")

            # Check if this is a split transform (1-to-N)
            if transform_type in ("split_name", "split_address"):
                split_mappings[source_name] = mapping
            else:
                simple_mappings[source_name] = mapping

        # Step 2: Apply split transforms first (they produce multiple columns)
        transformed_columns = {}

        for source_name, mapping in split_mappings.items():
            transform_type = mapping["transform_type"]
            transform_config = mapping.get("transform_config", {})
            col_data = result[source_name].copy()

            split_results = self._apply_split_transform(
                col_data, transform_type, transform_config, field_specs
            )

            # split_results is a dict: {"first_name": Series, "last_name": Series}
            for target_field, series in split_results.items():
                transformed_columns[target_field] = series

        # Step 3: Apply simple 1-to-1 transforms
        for source_name, mapping in simple_mappings.items():
            target_field = mapping["target_field"]

            # Don't overwrite a field already produced by a split transform
            if target_field in transformed_columns:
                continue

            transform_type = mapping.get("transform_type")
            transform_config = mapping.get("transform_config", {})
            field_spec = field_specs.get(target_field, {})

            col_data = result[source_name].copy()

            if transform_type:
                col_data = self._apply_transform(col_data, transform_type, transform_config, field_spec)

            transformed_columns[target_field] = col_data

        # Step 4: Build the output DataFrame with only mapped columns
        output = pd.DataFrame(transformed_columns)

        # Step 5: Add missing required columns with None values
        for field in schema_json.get("fields", []):
            if field["name"] not in output.columns:
                if field.get("default") is not None:
                    output[field["name"]] = field["default"]
                else:
                    output[field["name"]] = None

        # Step 6: Reorder columns to match target schema field order
        schema_field_order = [f["name"] for f in schema_json.get("fields", [])]
        ordered_cols = [col for col in schema_field_order if col in output.columns]
        extra_cols = [col for col in output.columns if col not in schema_field_order]
        output = output[ordered_cols + extra_cols]

        return output

    # ── Transform Router ─────────────────────────────────────

    def _apply_transform(self, series: pd.Series, transform_type: str,
                         config: dict, field_spec: dict) -> pd.Series:
        """Route to the correct transform function for 1-to-1 transforms."""
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
            "currency_normalize": self._currency_normalize,   # v2
            "zip_pad": self._zip_pad,                         # v2
        }

        transform_fn = transforms.get(transform_type)
        if transform_fn:
            return transform_fn(series, config)

        # Unknown transform — return as-is
        return series

    def _apply_split_transform(self, series: pd.Series, transform_type: str,
                                config: dict, field_specs: dict) -> dict[str, pd.Series]:
        """
        Route to the correct split transform function for 1-to-N transforms.

        Returns a dict mapping target_field_name → Series.
        """
        split_transforms = {
            "split_name": self._split_name,
            "split_address": self._split_address,
        }

        split_fn = split_transforms.get(transform_type)
        if split_fn:
            return split_fn(series, config)

        # Unknown split transform — return empty
        return {}

    # ══════════════════════════════════════════════════════════
    #  v2: SPLIT TRANSFORMS (1-to-N)
    # ══════════════════════════════════════════════════════════

    def _split_name(self, series: pd.Series, config: dict) -> dict[str, pd.Series]:
        """
        Split a full name column into first_name and last_name.

        Handles:
          - "John Doe" → first_name="John", last_name="Doe"
          - "John Michael Doe" → first_name="John", last_name="Michael Doe"
          - "Madonna" → first_name="Madonna", last_name=None
          - "Doe, John" → first_name="John", last_name="Doe"  (comma format)
          - None / empty → None, None

        Config options:
          - first_name_field: target field name (default: "first_name")
          - last_name_field: target field name (default: "last_name")
        """
        first_field = config.get("first_name_field", "first_name")
        last_field = config.get("last_name_field", "last_name")

        first_names = []
        last_names = []

        for val in series:
            if pd.isna(val) or val is None:
                first_names.append(None)
                last_names.append(None)
                continue

            name = str(val).strip()
            if not name:
                first_names.append(None)
                last_names.append(None)
                continue

            # Handle "Last, First" format
            if "," in name:
                parts = [p.strip() for p in name.split(",", 1)]
                if len(parts) == 2 and parts[0] and parts[1]:
                    first_names.append(parts[1].strip().title())
                    last_names.append(parts[0].strip().title())
                    continue

            # Standard "First Last" or "First Middle Last" format
            parts = name.split()

            if len(parts) == 0:
                first_names.append(None)
                last_names.append(None)
            elif len(parts) == 1:
                # Single name — put it in first_name
                first_names.append(parts[0].strip().title())
                last_names.append(None)
            elif len(parts) == 2:
                first_names.append(parts[0].strip().title())
                last_names.append(parts[1].strip().title())
            else:
                # 3+ parts: first word is first name, rest is last name
                first_names.append(parts[0].strip().title())
                last_names.append(" ".join(parts[1:]).strip().title())

        return {
            first_field: pd.Series(first_names, index=series.index),
            last_field: pd.Series(last_names, index=series.index),
        }

    def _split_address(self, series: pd.Series, config: dict) -> dict[str, pd.Series]:
        """
        Split a compound address into components.

        Handles common formats:
          - "123 Main St, Springfield, IL 62704"
          - "456 Oak Ave, Apt 2B, Chicago, IL 60601"
          - "789 Elm St, New York, NY"

        Config options:
          - street_field: target field name (default: "address")
          - city_field: target field name (default: "city")
          - state_field: target field name (default: "state")
          - zip_field: target field name (default: "zip_code")

        Note: Address parsing is inherently fuzzy. This handles the most
        common US formats. International addresses may not split cleanly.
        """
        street_field = config.get("street_field", "address")
        city_field = config.get("city_field", "city")
        state_field = config.get("state_field", "state")
        zip_field = config.get("zip_field", "zip_code")

        streets = []
        cities = []
        states = []
        zips = []

        # Common US state abbreviations for detection
        us_states = {
            "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
            "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
            "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
            "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
            "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
            "DC",
        }

        for val in series:
            if pd.isna(val) or val is None:
                streets.append(None)
                cities.append(None)
                states.append(None)
                zips.append(None)
                continue

            addr = str(val).strip()
            if not addr:
                streets.append(None)
                cities.append(None)
                states.append(None)
                zips.append(None)
                continue

            # Split by commas
            parts = [p.strip() for p in addr.split(",")]

            street = None
            city = None
            state = None
            zip_code = None

            if len(parts) == 1:
                # No commas — just put it all in street
                street = parts[0]

            elif len(parts) == 2:
                # "123 Main St, Springfield IL 62704" or "123 Main St, Springfield"
                street = parts[0]
                state_zip = self._parse_state_zip(parts[1], us_states)
                city = state_zip.get("city")
                state = state_zip.get("state")
                zip_code = state_zip.get("zip")

            elif len(parts) == 3:
                # "123 Main St, Springfield, IL 62704"
                street = parts[0]
                city = parts[1].strip()
                state_zip = self._parse_state_zip(parts[2], us_states)
                if state_zip.get("city") and not state:
                    # "city" from state_zip is actually just leftover text
                    pass
                state = state_zip.get("state")
                zip_code = state_zip.get("zip")

            elif len(parts) >= 4:
                # "123 Main St, Apt 2B, Springfield, IL 62704"
                # First part is street, second could be apt/suite, etc.
                street = ", ".join(parts[:-2])  # Everything before last 2
                city = parts[-2].strip()
                state_zip = self._parse_state_zip(parts[-1], us_states)
                state = state_zip.get("state")
                zip_code = state_zip.get("zip")

            streets.append(street)
            cities.append(city)
            states.append(state)
            zips.append(zip_code)

        return {
            street_field: pd.Series(streets, index=series.index),
            city_field: pd.Series(cities, index=series.index),
            state_field: pd.Series(states, index=series.index),
            zip_field: pd.Series(zips, index=series.index),
        }

    def _parse_state_zip(self, text: str, us_states: set) -> dict:
        """Parse a string like 'IL 62704' or 'Springfield IL 62704' into components."""
        text = text.strip()
        result = {"city": None, "state": None, "zip": None}

        if not text:
            return result

        # Try to extract zip code from the end
        zip_match = re.search(r'\b(\d{5}(?:-\d{4})?)\s*$', text)
        if zip_match:
            result["zip"] = zip_match.group(1)
            text = text[:zip_match.start()].strip()

        # Now try to extract state
        words = text.split()
        if words:
            # Check if last word is a state abbreviation
            last_word = words[-1].upper().rstrip(".,")
            if last_word in us_states:
                result["state"] = last_word
                remaining = " ".join(words[:-1]).strip()
                if remaining:
                    result["city"] = remaining
            else:
                # No state found — treat the whole thing as city
                result["city"] = text if text else None

        return result

    # ══════════════════════════════════════════════════════════
    #  v2: NEW 1-TO-1 TRANSFORMS
    # ══════════════════════════════════════════════════════════

    def _currency_normalize(self, series: pd.Series, config: dict) -> pd.Series:
        """
        Normalize currency strings to plain numbers.

        Handles:
          - "$1,234.56" → 1234.56
          - "€1.234,56" → 1234.56  (European format)
          - "1,234" → 1234.0
          - "USD 500" → 500.0
          - "$-50.00" → -50.0
        """
        def normalize_currency(val):
            if pd.isna(val) or val is None:
                return None
            val_str = str(val).strip()
            if not val_str or val_str.lower() in ("null", "none", "n/a", "nan"):
                return None

            # Remove currency symbols and codes
            cleaned = re.sub(r'[A-Za-z$€£¥₹₽₩]', '', val_str).strip()

            # Handle negative: could be in parens like (500) or with minus
            is_negative = False
            if cleaned.startswith('(') and cleaned.endswith(')'):
                is_negative = True
                cleaned = cleaned[1:-1]
            elif cleaned.startswith('-'):
                is_negative = True
                cleaned = cleaned[1:]

            # Detect European format: "1.234,56" (dot as thousands, comma as decimal)
            # vs US format: "1,234.56" (comma as thousands, dot as decimal)
            if re.match(r'^\d{1,3}\.\d{3}[,]\d{1,2}$', cleaned):
                # European: 1.234,56
                cleaned = cleaned.replace('.', '').replace(',', '.')
            else:
                # US/standard: remove commas, keep dots
                cleaned = cleaned.replace(',', '')

            # Remove any remaining whitespace
            cleaned = cleaned.strip()

            if not cleaned:
                return None

            try:
                result = round(float(cleaned), 2)
                return -result if is_negative else result
            except (ValueError, TypeError):
                return None

        return series.apply(normalize_currency)

    def _zip_pad(self, series: pd.Series, config: dict) -> pd.Series:
        """
        Pad zip codes to standard width.

        Handles:
          - "2134" → "02134"  (US 5-digit, left-pad with zero)
          - "02134" → "02134" (already correct)
          - "12345-6789" → "12345-6789" (ZIP+4 preserved)
          - "SW1A 1AA" → "SW1A 1AA" (non-US preserved as-is)

        Config options:
          - width: target width (default: 5)
          - pad_char: character to pad with (default: "0")
        """
        width = config.get("width", 5)
        pad_char = config.get("pad_char", "0")

        def pad_zip(val):
            if pd.isna(val) or val is None:
                return None
            val_str = str(val).strip()
            if not val_str or val_str.lower() in ("null", "none", "n/a", "nan"):
                return None

            # If it's a ZIP+4 format (12345-6789), don't pad
            if re.match(r'^\d{5}-\d{4}$', val_str):
                return val_str

            # If it's purely numeric and shorter than target width, pad it
            if val_str.isdigit() and len(val_str) < width:
                return val_str.zfill(width)

            # If it looks like a truncated float (e.g., "2134.0"), clean it
            if re.match(r'^\d+\.0$', val_str):
                int_part = val_str.split('.')[0]
                if len(int_part) < width:
                    return int_part.zfill(width)
                return int_part

            return val_str

        return series.apply(pad_zip)

    # ══════════════════════════════════════════════════════════
    #  EXISTING TRANSFORMS (unchanged from v1)
    # ══════════════════════════════════════════════════════════

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
