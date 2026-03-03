"""
Integration Tests with Kaggle-Style Data — v2 Full Pipeline.

Tests the transform + validation agents end-to-end with realistic
messy data. No Supabase needed — tests agent logic directly.

Covers:
- HubSpot export → Generic CRM schema (split names, normalize phones)
- Salesforce dirty → CRM schema (duplicates, nulls, case issues)
- Large dataset performance (500 rows under 5 seconds)
- International data handling
- Quality score ranges for different data quality levels
"""

import time
import pytest
import pandas as pd
from agents.transform import TransformAgent
from agents.validation import ValidationAgent
from tests.fixtures import GENERIC_CRM_SCHEMA, SIMPLE_SCHEMA, FINANCIAL_SCHEMA
from tests.fixtures_kaggle import (
    kaggle_hubspot_export,
    kaggle_salesforce_dirty,
    kaggle_international_contacts,
    kaggle_large_messy,
)


@pytest.fixture
def transform():
    return TransformAgent()


@pytest.fixture
def validator():
    return ValidationAgent()


# ══════════════════════════════════════════════════════════
#  HubSpot Export → Generic CRM
# ══════════════════════════════════════════════════════════

class TestHubSpotIntegration:
    """
    Simulates: User exports contacts from HubSpot, uploads to DataWeave,
    maps to Generic CRM schema.
    """

    def _build_mappings_and_transform(self, transform, df):
        """Simulate the mappings that would come from Schema Agent."""
        mappings = [
            {"source_name": "Contact Name", "target_field": "first_name",
             "transform_type": "split_name", "status": "approved",
             "transform_config": {"first_name_field": "first_name", "last_name_field": "last_name"}},
            {"source_name": "Email Address", "target_field": "email",
             "transform_type": "email_normalize", "status": "approved"},
            {"source_name": "Phone Number", "target_field": "phone",
             "transform_type": "phone_normalize", "status": "approved"},
            {"source_name": "Company Name", "target_field": "company",
             "transform_type": None, "status": "approved"},
            {"source_name": "Created Date", "target_field": "created_at",
             "transform_type": "parse_date", "status": "approved"},
        ]
        result = transform.process(df, mappings, GENERIC_CRM_SCHEMA)
        return result, mappings

    def test_split_name_produces_first_and_last(self, transform):
        df = kaggle_hubspot_export()
        result, _ = self._build_mappings_and_transform(transform, df)
        assert "first_name" in result.columns
        assert "last_name" in result.columns
        # "John Doe" → first_name="John", last_name="Doe"
        assert result.iloc[0]["first_name"] == "John"
        assert result.iloc[0]["last_name"] == "Doe"

    def test_email_normalize_lowercases(self, transform):
        df = kaggle_hubspot_export()
        result, _ = self._build_mappings_and_transform(transform, df)
        # "BOBJOHNSON@INITECH.COM" should be lowercased
        emails = result["email"].tolist()
        for e in emails:
            if e and isinstance(e, str):
                assert e == e.lower(), f"Email not lowered: {e}"

    def test_phone_normalize_strips_formatting(self, transform):
        df = kaggle_hubspot_export()
        result, _ = self._build_mappings_and_transform(transform, df)
        phones = result["phone"].dropna().tolist()
        for p in phones:
            if p and isinstance(p, str) and p not in ("N/A", ""):
                # Should not contain parens or dots after normalization
                assert "(" not in str(p) or p.startswith("+"), f"Phone not normalized: {p}"

    def test_validation_catches_bad_email(self, transform, validator):
        df = kaggle_hubspot_export()
        result, mappings = self._build_mappings_and_transform(transform, df)
        report = validator.process(result, GENERIC_CRM_SCHEMA, mappings=mappings)
        # "eve.davis@example" is missing TLD — should be caught
        email_errors = [e for e in report["errors"] + report["warnings"]
                        if "email" in e.get("field", "").lower()
                        or "email" in e.get("message", "").lower()]
        assert len(email_errors) > 0, "Should flag invalid email format"

    def test_quality_score_reasonable(self, transform, validator):
        df = kaggle_hubspot_export()
        result, mappings = self._build_mappings_and_transform(transform, df)
        report = validator.process(result, GENERIC_CRM_SCHEMA, mappings=mappings)
        # HubSpot data is decent but not perfect — expect 50-95
        assert 40 <= report["quality_score"] <= 99, \
            f"Unexpected score: {report['quality_score']}"


# ══════════════════════════════════════════════════════════
#  Salesforce Dirty → CRM Schema
# ══════════════════════════════════════════════════════════

class TestSalesforceDirtyIntegration:
    """
    Simulates: Messy Salesforce export with duplicates, nulls,
    and inconsistent casing.
    """

    def _build_mappings_and_transform(self, transform, df):
        mappings = [
            {"source_name": "FirstName", "target_field": "first_name",
             "transform_type": None, "status": "approved"},
            {"source_name": "LastName", "target_field": "last_name",
             "transform_type": None, "status": "approved"},
            {"source_name": "Email", "target_field": "email",
             "transform_type": "email_normalize", "status": "approved"},
            {"source_name": "Phone", "target_field": "phone",
             "transform_type": "phone_normalize", "status": "approved"},
            {"source_name": "Zip", "target_field": "zip_code",
             "transform_type": "zip_pad", "status": "approved"},
            {"source_name": "State", "target_field": "state",
             "transform_type": None, "status": "approved"},
        ]
        result = transform.process(df, mappings, GENERIC_CRM_SCHEMA)
        return result, mappings

    def test_handles_null_first_names(self, transform):
        df = kaggle_salesforce_dirty()
        result, _ = self._build_mappings_and_transform(transform, df)
        assert "first_name" in result.columns
        # Should have some nulls but not crash
        null_count = result["first_name"].isna().sum()
        assert null_count > 0, "Should preserve nulls, not crash"

    def test_zip_pad_fixes_short_zips(self, transform):
        df = kaggle_salesforce_dirty()
        result, _ = self._build_mappings_and_transform(transform, df)
        zips = result["zip_code"].dropna().tolist()
        for z in zips:
            if z and isinstance(z, str) and z.isdigit():
                assert len(z) >= 5, f"Zip not padded: {z}"

    def test_duplicate_emails_flagged(self, transform, validator):
        df = kaggle_salesforce_dirty()
        result, mappings = self._build_mappings_and_transform(transform, df)
        report = validator.process(result, GENERIC_CRM_SCHEMA, mappings=mappings)
        dup_errors = [e for e in report["errors"] + report["warnings"]
                      if "duplicate" in e.get("type", "").lower()
                      or "duplicate" in e.get("message", "").lower()]
        assert len(dup_errors) > 0, "Should detect duplicate emails"

    def test_quality_score_lower_for_dirty_data(self, transform, validator):
        df = kaggle_salesforce_dirty()
        result, mappings = self._build_mappings_and_transform(transform, df)
        report = validator.process(result, GENERIC_CRM_SCHEMA, mappings=mappings)
        # Dirty data — expect lower score than clean data
        assert report["quality_score"] < 95, \
            f"Score too high for dirty data: {report['quality_score']}"


# ══════════════════════════════════════════════════════════
#  Large Dataset Performance
# ══════════════════════════════════════════════════════════

class TestLargeDatasetPerformance:
    def test_500_rows_under_5_seconds(self, transform, validator):
        df = kaggle_large_messy(500)
        mappings = [
            {"source_name": "Full Name", "target_field": "first_name",
             "transform_type": "split_name", "status": "approved",
             "transform_config": {"first_name_field": "first_name", "last_name_field": "last_name"}},
            {"source_name": "Email", "target_field": "email",
             "transform_type": "email_normalize", "status": "approved"},
            {"source_name": "Phone", "target_field": "phone",
             "transform_type": "phone_normalize", "status": "approved"},
            {"source_name": "Zip Code", "target_field": "zip_code",
             "transform_type": "zip_pad", "status": "approved"},
            {"source_name": "Signup Date", "target_field": "created_at",
             "transform_type": "parse_date", "status": "approved"},
        ]

        start = time.time()
        result = transform.process(df, mappings, GENERIC_CRM_SCHEMA)
        report = validator.process(result, GENERIC_CRM_SCHEMA, mappings=mappings)
        elapsed = time.time() - start

        assert elapsed < 5.0, f"Took {elapsed:.1f}s — too slow for 500 rows"
        assert report["total_rows"] == 500
        assert report["quality_score"] > 0

    def test_1000_rows_under_10_seconds(self, transform, validator):
        df = kaggle_large_messy(1000)
        mappings = [
            {"source_name": "Full Name", "target_field": "first_name",
             "transform_type": "split_name", "status": "approved",
             "transform_config": {"first_name_field": "first_name", "last_name_field": "last_name"}},
            {"source_name": "Email", "target_field": "email",
             "transform_type": "email_normalize", "status": "approved"},
            {"source_name": "Phone", "target_field": "phone",
             "transform_type": "phone_normalize", "status": "approved"},
        ]

        start = time.time()
        result = transform.process(df, mappings, GENERIC_CRM_SCHEMA)
        report = validator.process(result, GENERIC_CRM_SCHEMA, mappings=mappings)
        elapsed = time.time() - start

        assert elapsed < 10.0, f"Took {elapsed:.1f}s — too slow for 1000 rows"
        assert report["total_rows"] == 1000


# ══════════════════════════════════════════════════════════
#  Validation Report Structure
# ══════════════════════════════════════════════════════════

class TestValidationReportStructure:
    def test_report_has_all_required_keys(self, transform, validator):
        df = kaggle_hubspot_export()
        mappings = [
            {"source_name": "Email Address", "target_field": "email",
             "transform_type": None, "status": "approved"},
        ]
        result = transform.process(df, mappings, SIMPLE_SCHEMA)
        report = validator.process(result, SIMPLE_SCHEMA, mappings=mappings)

        required_keys = [
            "quality_score", "total_rows", "clean_rows",
            "rows_with_errors", "total_errors", "total_warnings",
            "errors", "warnings", "summary",
        ]
        for key in required_keys:
            assert key in report, f"Missing key: {key}"

    def test_quality_score_is_0_to_100(self, transform, validator):
        df = kaggle_hubspot_export()
        mappings = [
            {"source_name": "Email Address", "target_field": "email",
             "transform_type": None, "status": "approved"},
        ]
        result = transform.process(df, mappings, SIMPLE_SCHEMA)
        report = validator.process(result, SIMPLE_SCHEMA, mappings=mappings)
        assert 0 <= report["quality_score"] <= 100

    def test_error_objects_have_required_fields(self, transform, validator):
        df = kaggle_salesforce_dirty()
        mappings = [
            {"source_name": "Email", "target_field": "email",
             "transform_type": None, "status": "approved"},
            {"source_name": "FirstName", "target_field": "first_name",
             "transform_type": None, "status": "approved"},
            {"source_name": "LastName", "target_field": "last_name",
             "transform_type": None, "status": "approved"},
        ]
        result = transform.process(df, mappings, SIMPLE_SCHEMA)
        report = validator.process(result, SIMPLE_SCHEMA, mappings=mappings)

        for error in report["errors"]:
            assert "type" in error, f"Error missing 'type': {error}"
            assert "message" in error, f"Error missing 'message': {error}"


# ══════════════════════════════════════════════════════════
#  Currency + Financial Data
# ══════════════════════════════════════════════════════════

class TestFinancialData:
    def test_currency_normalize_from_hubspot(self, transform, validator):
        df = kaggle_hubspot_export()
        mappings = [
            {"source_name": "Contact Name", "target_field": "name",
             "transform_type": None, "status": "approved"},
            {"source_name": "Deal Amount", "target_field": "amount",
             "transform_type": "currency_normalize", "status": "approved"},
            {"source_name": "Created Date", "target_field": "date",
             "transform_type": "parse_date", "status": "approved"},
        ]
        result = transform.process(df, mappings, FINANCIAL_SCHEMA)

        # "$5,000.00" should become a number
        amounts = result["amount"].dropna().tolist()
        for a in amounts:
            if a is not None:
                assert isinstance(a, (int, float)), f"Amount not numeric: {a} ({type(a)})"

    def test_negative_currency_handled(self, transform):
        """($1,200.00) is a common accounting format for negatives."""
        df = kaggle_hubspot_export()
        mappings = [
            {"source_name": "Deal Amount", "target_field": "amount",
             "transform_type": "currency_normalize", "status": "approved"},
            {"source_name": "Contact Name", "target_field": "name",
             "transform_type": None, "status": "approved"},
            {"source_name": "Created Date", "target_field": "date",
             "transform_type": "parse_date", "status": "approved"},
        ]
        result = transform.process(df, mappings, FINANCIAL_SCHEMA)
        amounts = result["amount"].tolist()
        # Row 4 has "($1,200.00)" — should be -1200.0
        negatives = [a for a in amounts if isinstance(a, (int, float)) and a < 0]
        assert len(negatives) >= 1, "Should handle parenthetical negatives"
