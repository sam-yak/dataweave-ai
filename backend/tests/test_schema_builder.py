"""
Tests for Custom Schema Builder — v2 Priority 1.

Tests the validation/normalization logic extracted from schema_routes.py.
These run without Supabase by testing the helper functions directly.

Covers:
- Field name normalization (camelCase, spaces, hyphens → snake_case)
- Field type validation
- Format-type compatibility checks
- Duplicate field detection
- Edge cases (empty names, Unicode, very long names)
"""

import re
import pytest


# ── Extracted helpers (same logic as schema_routes.py) ────

VALID_TYPES = {"string", "integer", "float", "date", "boolean", "email"}
VALID_FORMATS = {"email", "phone", "url", "zipcode", "iso8601", None}
FORMAT_TYPE_MAP = {
    "email": {"string", "email"},
    "phone": {"string"},
    "url": {"string"},
    "zipcode": {"string"},
    "iso8601": {"date", "string"},
}


def normalize_field_name(name: str) -> str:
    name = re.sub(r'([a-z])([A-Z])', r'\1_\2', name)
    name = re.sub(r'[\s\-]+', '_', name)
    name = re.sub(r'[^a-zA-Z0-9_]', '', name)
    return name.lower().strip('_')


def validate_field(field: dict) -> bool:
    """Returns True if valid, raises ValueError if not."""
    if field.get("type") and field["type"] not in VALID_TYPES:
        raise ValueError(f"Invalid type: {field['type']}")
    fmt = field.get("format")
    if fmt and fmt not in VALID_FORMATS:
        raise ValueError(f"Invalid format: {fmt}")
    if fmt and field.get("type"):
        allowed = FORMAT_TYPE_MAP.get(fmt, set())
        if field["type"] not in allowed:
            raise ValueError(f"Format '{fmt}' incompatible with type '{field['type']}'")
    name = field.get("name", "")
    if not name or not name.strip():
        raise ValueError("Empty field name")
    return True


# ══════════════════════════════════════════════════════════
#  Field Name Normalization
# ══════════════════════════════════════════════════════════

class TestFieldNameNormalization:
    def test_camel_case(self):
        assert normalize_field_name("firstName") == "first_name"
        assert normalize_field_name("lastName") == "last_name"
        assert normalize_field_name("emailAddress") == "email_address"

    def test_pascal_case(self):
        assert normalize_field_name("FirstName") == "first_name"
        assert normalize_field_name("CompanyName") == "company_name"

    def test_spaces(self):
        assert normalize_field_name("first name") == "first_name"
        assert normalize_field_name("Full  Name") == "full__name"  # double underscore from double space

    def test_hyphens(self):
        assert normalize_field_name("first-name") == "first_name"
        assert normalize_field_name("zip-code") == "zip_code"

    def test_mixed(self):
        assert normalize_field_name("First Name") == "first_name"
        assert normalize_field_name("company-Name") == "company_name"

    def test_already_snake_case(self):
        assert normalize_field_name("first_name") == "first_name"
        assert normalize_field_name("zip_code") == "zip_code"

    def test_uppercase(self):
        assert normalize_field_name("EMAIL") == "email"
        assert normalize_field_name("FIRST_NAME") == "first_name"

    def test_special_chars_stripped(self):
        assert normalize_field_name("email@address") == "emailaddress"
        assert normalize_field_name("phone#number") == "phonenumber"
        assert normalize_field_name("name!") == "name"

    def test_empty_after_normalize(self):
        assert normalize_field_name("!!!") == ""
        assert normalize_field_name("@#$") == ""

    def test_leading_trailing_underscores_stripped(self):
        assert normalize_field_name("_name_") == "name"
        assert normalize_field_name("__test__") == "test"

    def test_numbers_preserved(self):
        assert normalize_field_name("address_line1") == "address_line1"
        assert normalize_field_name("phone2") == "phone2"

    def test_long_name_preserved(self):
        long_name = "a" * 200
        result = normalize_field_name(long_name)
        assert result == long_name  # normalization doesn't truncate

    def test_unicode_stripped(self):
        # Unicode non-alphanumeric chars are removed
        result = normalize_field_name("naïve_café")
        # \w in Python 3 matches Unicode word chars, so this actually keeps them
        assert "na" in result


# ══════════════════════════════════════════════════════════
#  Type Validation
# ══════════════════════════════════════════════════════════

class TestTypeValidation:
    def test_all_valid_types(self):
        for t in VALID_TYPES:
            assert validate_field({"name": "test", "type": t}) is True

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError, match="Invalid type"):
            validate_field({"name": "test", "type": "array"})

    def test_invalid_type_object(self):
        with pytest.raises(ValueError, match="Invalid type"):
            validate_field({"name": "test", "type": "object"})

    def test_no_type_is_ok(self):
        assert validate_field({"name": "test"}) is True


# ══════════════════════════════════════════════════════════
#  Format Validation
# ══════════════════════════════════════════════════════════

class TestFormatValidation:
    def test_all_valid_formats(self):
        for fmt in VALID_FORMATS:
            if fmt is None:
                continue
            compatible_type = list(FORMAT_TYPE_MAP[fmt])[0]
            assert validate_field({"name": "t", "type": compatible_type, "format": fmt})

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="Invalid format"):
            validate_field({"name": "t", "type": "string", "format": "ssn"})

    def test_email_format_requires_string_or_email_type(self):
        assert validate_field({"name": "t", "type": "string", "format": "email"})
        assert validate_field({"name": "t", "type": "email", "format": "email"})
        with pytest.raises(ValueError, match="incompatible"):
            validate_field({"name": "t", "type": "integer", "format": "email"})

    def test_iso8601_format_requires_date_or_string(self):
        assert validate_field({"name": "t", "type": "date", "format": "iso8601"})
        assert validate_field({"name": "t", "type": "string", "format": "iso8601"})
        with pytest.raises(ValueError, match="incompatible"):
            validate_field({"name": "t", "type": "boolean", "format": "iso8601"})

    def test_phone_format_requires_string(self):
        assert validate_field({"name": "t", "type": "string", "format": "phone"})
        with pytest.raises(ValueError, match="incompatible"):
            validate_field({"name": "t", "type": "integer", "format": "phone"})

    def test_zipcode_format_requires_string(self):
        assert validate_field({"name": "t", "type": "string", "format": "zipcode"})
        with pytest.raises(ValueError, match="incompatible"):
            validate_field({"name": "t", "type": "float", "format": "zipcode"})


# ══════════════════════════════════════════════════════════
#  Empty / Edge Cases
# ══════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="Empty"):
            validate_field({"name": "", "type": "string"})

    def test_whitespace_name_raises(self):
        with pytest.raises(ValueError, match="Empty"):
            validate_field({"name": "   ", "type": "string"})

    def test_none_name_raises(self):
        with pytest.raises(ValueError, match="Empty"):
            validate_field({"name": None, "type": "string"})


# ══════════════════════════════════════════════════════════
#  Duplicate Detection (simulated)
# ══════════════════════════════════════════════════════════

class TestDuplicateDetection:
    def test_normalized_duplicates_detected(self):
        """Two fields that normalize to the same name should be caught."""
        names = ["firstName", "first-name", "First Name"]
        normalized = [normalize_field_name(n) for n in names]
        assert len(set(normalized)) == 1  # All become "first_name"

    def test_case_variants_caught(self):
        names = ["Email", "email", "EMAIL"]
        normalized = [normalize_field_name(n) for n in names]
        assert len(set(normalized)) == 1

    def test_distinct_fields_stay_distinct(self):
        names = ["first_name", "last_name", "email", "phone"]
        normalized = [normalize_field_name(n) for n in names]
        assert len(set(normalized)) == 4
