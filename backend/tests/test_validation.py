"""
Tests for Validation Agent.

Covers:
- Required field errors (only for mapped fields)
- Type conformance checks
- Format validation (email, phone, zipcode)
- Duplicate detection
- Unmapped fields → info messages (not errors)
- Quality score calculation (unmapped fields don't tank score)
- Edge cases (empty DataFrame, all nulls)
"""

import pytest
import pandas as pd
from agents.validation import ValidationAgent
from tests.fixtures import (
    SIMPLE_SCHEMA, GENERIC_CRM_SCHEMA, FINANCIAL_SCHEMA,
)


@pytest.fixture
def agent():
    return ValidationAgent()


# ══════════════════════════════════════════════════════════
#  Required Field Checks
# ══════════════════════════════════════════════════════════

class TestRequiredFields:
    def test_all_required_present(self, agent):
        df = pd.DataFrame({
            "first_name": ["John", "Jane"],
            "last_name": ["Doe", "Smith"],
            "email": ["j@t.com", "js@t.com"],
            "phone": ["555-1234", None],
        })
        mappings = [
            {"target_field": "first_name", "status": "approved"},
            {"target_field": "last_name", "status": "approved"},
            {"target_field": "email", "status": "approved"},
            {"target_field": "phone", "status": "approved"},
        ]
        report = agent.process(df, SIMPLE_SCHEMA, mappings=mappings)
        required_errors = [e for e in report["errors"] if e["type"] == "required_field"]
        assert len(required_errors) == 0

    def test_missing_required_value(self, agent):
        df = pd.DataFrame({
            "first_name": ["John", None],
            "last_name": ["Doe", "Smith"],
            "email": ["j@t.com", "js@t.com"],
            "phone": [None, None],
        })
        mappings = [
            {"target_field": "first_name", "status": "approved"},
            {"target_field": "last_name", "status": "approved"},
            {"target_field": "email", "status": "approved"},
        ]
        report = agent.process(df, SIMPLE_SCHEMA, mappings=mappings)
        required_errors = [e for e in report["errors"] if e["type"] == "required_field"]
        assert len(required_errors) == 1
        assert required_errors[0]["field"] == "first_name"
        assert required_errors[0]["row"] == 1

    def test_unmapped_required_field_not_error(self, agent):
        """If a required field was never mapped, it should NOT generate per-row errors."""
        df = pd.DataFrame({
            "first_name": ["John"],
            "last_name": ["Doe"],
            "email": ["j@t.com"],
            "phone": [None],
        })
        # Only first_name and email are mapped — last_name is required but unmapped
        mappings = [
            {"target_field": "first_name", "status": "approved"},
            {"target_field": "email", "status": "approved"},
        ]
        report = agent.process(df, SIMPLE_SCHEMA, mappings=mappings)
        required_errors = [e for e in report["errors"] if e["type"] == "required_field"]
        # last_name is required but unmapped — should NOT be an error
        assert len(required_errors) == 0

    def test_empty_string_is_error(self, agent):
        df = pd.DataFrame({
            "first_name": ["John", "  "],
            "last_name": ["Doe", "Smith"],
            "email": ["j@t.com", "js@t.com"],
            "phone": [None, None],
        })
        mappings = [
            {"target_field": "first_name", "status": "approved"},
            {"target_field": "last_name", "status": "approved"},
            {"target_field": "email", "status": "approved"},
        ]
        report = agent.process(df, SIMPLE_SCHEMA, mappings=mappings)
        required_errors = [e for e in report["errors"] if e["type"] == "required_field"]
        assert len(required_errors) == 1


# ══════════════════════════════════════════════════════════
#  Format Validation
# ══════════════════════════════════════════════════════════

class TestFormatValidation:
    def test_valid_emails(self, agent):
        df = pd.DataFrame({
            "first_name": ["John"], "last_name": ["Doe"],
            "email": ["john@test.com"], "phone": [None],
        })
        mappings = [{"target_field": "email", "status": "approved"}]
        report = agent.process(df, SIMPLE_SCHEMA, mappings=mappings)
        format_errors = [e for e in report["errors"] if e["type"] == "format_validation"]
        assert len(format_errors) == 0

    def test_invalid_email(self, agent):
        df = pd.DataFrame({
            "first_name": ["John"], "last_name": ["Doe"],
            "email": ["not-an-email"], "phone": [None],
        })
        mappings = [
            {"target_field": "first_name", "status": "approved"},
            {"target_field": "last_name", "status": "approved"},
            {"target_field": "email", "status": "approved"},
        ]
        report = agent.process(df, SIMPLE_SCHEMA, mappings=mappings)
        format_errors = [e for e in report["errors"] if e["type"] == "format_validation"]
        assert len(format_errors) == 1
        assert format_errors[0]["field"] == "email"

    def test_unmapped_format_field_skipped(self, agent):
        """Format checks should be skipped for unmapped fields."""
        df = pd.DataFrame({
            "first_name": ["John"], "last_name": ["Doe"],
            "email": ["anything"], "phone": ["not-a-phone"],
        })
        # email and phone are NOT mapped
        mappings = [
            {"target_field": "first_name", "status": "approved"},
            {"target_field": "last_name", "status": "approved"},
        ]
        report = agent.process(df, SIMPLE_SCHEMA, mappings=mappings)
        format_errors = [e for e in report["errors"] if e["type"] == "format_validation"]
        assert len(format_errors) == 0


# ══════════════════════════════════════════════════════════
#  Duplicate Detection
# ══════════════════════════════════════════════════════════

class TestDuplicateDetection:
    def test_duplicate_unique_field(self, agent):
        df = pd.DataFrame({
            "first_name": ["John", "Jane", "John"],
            "last_name": ["Doe", "Smith", "Doe"],
            "email": ["j@t.com", "js@t.com", "j@t.com"],
            "phone": [None, None, None],
        })
        mappings = [{"target_field": "email", "status": "approved"}]
        report = agent.process(df, SIMPLE_SCHEMA, mappings=mappings)
        dup_warnings = [w for w in report["warnings"] if w["type"] == "duplicate"]
        assert len(dup_warnings) == 1
        assert dup_warnings[0]["field"] == "email"

    def test_no_duplicates(self, agent):
        df = pd.DataFrame({
            "first_name": ["John", "Jane"],
            "last_name": ["Doe", "Smith"],
            "email": ["j@t.com", "js@t.com"],
            "phone": [None, None],
        })
        mappings = [{"target_field": "email", "status": "approved"}]
        report = agent.process(df, SIMPLE_SCHEMA, mappings=mappings)
        dup_warnings = [w for w in report["warnings"] if w["type"] == "duplicate"]
        assert len(dup_warnings) == 0


# ══════════════════════════════════════════════════════════
#  Unmapped Fields → Info Messages
# ══════════════════════════════════════════════════════════

class TestUnmappedFields:
    def test_unmapped_fields_generate_info(self, agent):
        df = pd.DataFrame({
            "first_name": ["John"],
            "last_name": ["Doe"],
            "email": ["j@t.com"],
            "phone": [None],
            "company": [None],
            "job_title": [None],
            "address": [None],
            "city": [None],
            "state": [None],
            "zip_code": [None],
            "country": [None],
            "created_at": [None],
        })
        # Only 3 fields mapped
        mappings = [
            {"target_field": "first_name", "status": "approved"},
            {"target_field": "last_name", "status": "approved"},
            {"target_field": "email", "status": "approved"},
        ]
        report = agent.process(df, GENERIC_CRM_SCHEMA, mappings=mappings)
        info = report["info"]
        unmapped_info = [i for i in info if i["type"] == "unmapped_field"]
        # 12 fields - 3 mapped = 9 unmapped
        assert len(unmapped_info) == 9

    def test_unmapped_required_marked(self, agent):
        """Unmapped required fields should have is_required=True in info."""
        df = pd.DataFrame({
            "email": ["j@t.com"],
            "first_name": [None],
            "last_name": [None],
            "phone": [None],
        })
        mappings = [{"target_field": "email", "status": "approved"}]
        report = agent.process(df, SIMPLE_SCHEMA, mappings=mappings)
        info = report["info"]
        required_info = [i for i in info if i.get("is_required")]
        # first_name and last_name are required but unmapped
        assert len(required_info) == 2

    def test_unmapped_dont_affect_score(self, agent):
        """Quality score should be high when the only issues are unmapped fields."""
        df = pd.DataFrame({
            "first_name": ["John", "Jane", "Bob"],
            "last_name": ["Doe", "Smith", "Brown"],
            "email": ["j@t.com", "js@t.com", "b@t.com"],
            "phone": [None, None, None],
            "company": [None, None, None],
            "job_title": [None, None, None],
            "address": [None, None, None],
            "city": [None, None, None],
            "state": [None, None, None],
            "zip_code": [None, None, None],
            "country": [None, None, None],
            "created_at": [None, None, None],
        })
        mappings = [
            {"target_field": "first_name", "status": "approved"},
            {"target_field": "last_name", "status": "approved"},
            {"target_field": "email", "status": "approved"},
        ]
        report = agent.process(df, GENERIC_CRM_SCHEMA, mappings=mappings)
        # Score should be 100 or close — no real errors, just unmapped fields
        assert report["quality_score"] >= 95


# ══════════════════════════════════════════════════════════
#  Quality Score
# ══════════════════════════════════════════════════════════

class TestQualityScore:
    def test_perfect_score(self, agent):
        df = pd.DataFrame({
            "first_name": ["John", "Jane"],
            "last_name": ["Doe", "Smith"],
            "email": ["j@test.com", "js@test.com"],
            "phone": ["555-1234", "555-2345"],
        })
        mappings = [
            {"target_field": "first_name", "status": "approved"},
            {"target_field": "last_name", "status": "approved"},
            {"target_field": "email", "status": "approved"},
            {"target_field": "phone", "status": "approved"},
        ]
        report = agent.process(df, SIMPLE_SCHEMA, mappings=mappings)
        assert report["quality_score"] >= 95

    def test_some_errors_reduce_score(self, agent):
        df = pd.DataFrame({
            "first_name": ["John", None, "Bob"],
            "last_name": ["Doe", "Smith", "Brown"],
            "email": ["j@test.com", "bad", "b@test.com"],
            "phone": [None, None, None],
        })
        mappings = [
            {"target_field": "first_name", "status": "approved"},
            {"target_field": "last_name", "status": "approved"},
            {"target_field": "email", "status": "approved"},
        ]
        report = agent.process(df, SIMPLE_SCHEMA, mappings=mappings)
        # Row 1 has errors (null first_name, bad email)
        assert 30 < report["quality_score"] < 90

    def test_empty_dataframe(self, agent):
        df = pd.DataFrame(columns=["first_name", "last_name", "email", "phone"])
        report = agent.process(df, SIMPLE_SCHEMA, mappings=[])
        assert report["quality_score"] == 0
        assert report["total_rows"] == 0


# ══════════════════════════════════════════════════════════
#  Type Conformance
# ══════════════════════════════════════════════════════════

class TestTypeConformance:
    def test_valid_float(self, agent):
        df = pd.DataFrame({
            "name": ["John"],
            "amount": [1234.56],
            "date": ["2024-01-15"],
            "category": [None],
            "zip_code": [None],
        })
        mappings = [
            {"target_field": "name", "status": "approved"},
            {"target_field": "amount", "status": "approved"},
            {"target_field": "date", "status": "approved"},
        ]
        report = agent.process(df, FINANCIAL_SCHEMA, mappings=mappings)
        type_errors = [e for e in report["errors"] if e["type"] == "type_conformance"]
        assert len(type_errors) == 0

    def test_invalid_float(self, agent):
        df = pd.DataFrame({
            "name": ["John"],
            "amount": ["not a number"],
            "date": ["2024-01-15"],
            "category": [None],
            "zip_code": [None],
        })
        mappings = [
            {"target_field": "name", "status": "approved"},
            {"target_field": "amount", "status": "approved"},
            {"target_field": "date", "status": "approved"},
        ]
        report = agent.process(df, FINANCIAL_SCHEMA, mappings=mappings)
        type_errors = [e for e in report["errors"] if e["type"] == "type_conformance"]
        assert len(type_errors) == 1

    def test_unmapped_type_field_skipped(self, agent):
        """Type checks should be skipped for unmapped fields."""
        df = pd.DataFrame({
            "name": ["John"],
            "amount": ["not a number"],
            "date": ["2024-01-15"],
            "category": [None],
            "zip_code": [None],
        })
        # amount is NOT mapped
        mappings = [
            {"target_field": "name", "status": "approved"},
            {"target_field": "date", "status": "approved"},
        ]
        report = agent.process(df, FINANCIAL_SCHEMA, mappings=mappings)
        type_errors = [e for e in report["errors"] if e["type"] == "type_conformance"]
        assert len(type_errors) == 0


# ══════════════════════════════════════════════════════════
#  Report Structure
# ══════════════════════════════════════════════════════════

class TestReportStructure:
    def test_report_has_all_fields(self, agent):
        df = pd.DataFrame({
            "first_name": ["John"], "last_name": ["Doe"],
            "email": ["j@t.com"], "phone": [None],
        })
        report = agent.process(df, SIMPLE_SCHEMA, mappings=[])
        assert "quality_score" in report
        assert "total_rows" in report
        assert "clean_rows" in report
        assert "errors" in report
        assert "warnings" in report
        assert "info" in report
        assert "summary" in report
        assert "unmapped_fields" in report["summary"]

    def test_severity_tags(self, agent):
        """All errors should have severity='error', warnings 'warning', info 'info'."""
        df = pd.DataFrame({
            "first_name": [None], "last_name": ["Doe"],
            "email": ["bad"], "phone": [None],
        })
        mappings = [
            {"target_field": "first_name", "status": "approved"},
            {"target_field": "last_name", "status": "approved"},
            {"target_field": "email", "status": "approved"},
        ]
        report = agent.process(df, SIMPLE_SCHEMA, mappings=mappings)
        for e in report["errors"]:
            assert e["severity"] == "error"
        for w in report["warnings"]:
            assert w["severity"] == "warning"
        for i in report["info"]:
            assert i["severity"] == "info"
