"""
Tests for Transform Agent.

Covers:
- split_name (full names → first + last)
- split_address (compound addresses → components)
- currency_normalize ($1,234.56 → 1234.56)
- zip_pad (2134 → 02134)
- Existing transforms (cast_integer, parse_date, email_normalize, etc.)
- 1-to-N mapping flow (single source → multiple targets)
- Edge cases (nulls, empty strings, single names)
"""

import pytest
import pandas as pd
from agents.transform import TransformAgent
from tests.fixtures import (
    full_name_data, full_address_data, currency_data,
    clean_crm_data, messy_crm_data, SIMPLE_SCHEMA, GENERIC_CRM_SCHEMA,
    FINANCIAL_SCHEMA,
)


@pytest.fixture
def agent():
    return TransformAgent()


# ══════════════════════════════════════════════════════════
#  split_name
# ══════════════════════════════════════════════════════════

class TestSplitName:
    def test_basic_split(self, agent):
        series = pd.Series(["John Doe", "Jane Smith"])
        result = agent._split_name(series, {})
        assert result["first_name"].tolist() == ["John", "Jane"]
        assert result["last_name"].tolist() == ["Doe", "Smith"]

    def test_three_part_name(self, agent):
        series = pd.Series(["John Michael Doe"])
        result = agent._split_name(series, {})
        assert result["first_name"].tolist() == ["John"]
        assert result["last_name"].tolist() == ["Michael Doe"]

    def test_single_name(self, agent):
        series = pd.Series(["Madonna"])
        result = agent._split_name(series, {})
        assert result["first_name"].tolist() == ["Madonna"]
        assert result["last_name"].tolist() == [None]

    def test_comma_format(self, agent):
        series = pd.Series(["Doe, John"])
        result = agent._split_name(series, {})
        assert result["first_name"].tolist() == ["John"]
        assert result["last_name"].tolist() == ["Doe"]

    def test_null_handling(self, agent):
        series = pd.Series([None, "", "  "])
        result = agent._split_name(series, {})
        assert result["first_name"].tolist() == [None, None, None]
        assert result["last_name"].tolist() == [None, None, None]

    def test_custom_field_names(self, agent):
        series = pd.Series(["John Doe"])
        config = {"first_name_field": "fname", "last_name_field": "lname"}
        result = agent._split_name(series, config)
        assert "fname" in result
        assert "lname" in result
        assert result["fname"].tolist() == ["John"]

    def test_whitespace_handling(self, agent):
        series = pd.Series(["  Bob  Johnson  "])
        result = agent._split_name(series, {})
        assert result["first_name"].tolist() == ["Bob"]
        assert result["last_name"].tolist() == ["Johnson"]

    def test_full_name_fixture(self, agent):
        df = full_name_data()
        result = agent._split_name(df["Full Name"], {})
        assert len(result["first_name"]) == 5
        assert result["first_name"].iloc[0] == "John"
        assert result["last_name"].iloc[0] == "Doe"
        # Comma format
        assert result["first_name"].iloc[3] == "John"
        assert result["last_name"].iloc[3] == "Doe"


# ══════════════════════════════════════════════════════════
#  split_address
# ══════════════════════════════════════════════════════════

class TestSplitAddress:
    def test_three_part_address(self, agent):
        series = pd.Series(["123 Main St, Springfield, IL 62704"])
        result = agent._split_address(series, {})
        assert result["address"].iloc[0] == "123 Main St"
        assert result["city"].iloc[0] == "Springfield"
        assert result["state"].iloc[0] == "IL"
        assert result["zip_code"].iloc[0] == "62704"

    def test_four_part_address(self, agent):
        series = pd.Series(["456 Oak Ave, Apt 2B, Chicago, IL 60601"])
        result = agent._split_address(series, {})
        assert "456 Oak Ave" in result["address"].iloc[0]
        assert result["city"].iloc[0] == "Chicago"
        assert result["state"].iloc[0] == "IL"
        assert result["zip_code"].iloc[0] == "60601"

    def test_no_zip(self, agent):
        series = pd.Series(["789 Elm St, New York, NY"])
        result = agent._split_address(series, {})
        assert result["address"].iloc[0] == "789 Elm St"
        assert result["state"].iloc[0] == "NY"

    def test_null_handling(self, agent):
        series = pd.Series([None, ""])
        result = agent._split_address(series, {})
        assert result["address"].tolist() == [None, None]

    def test_custom_field_names(self, agent):
        series = pd.Series(["123 Main St, Springfield, IL 62704"])
        config = {"street_field": "addr", "city_field": "town"}
        result = agent._split_address(series, config)
        assert "addr" in result
        assert "town" in result

    def test_full_address_fixture(self, agent):
        df = full_address_data()
        result = agent._split_address(df["Full Address"], {})
        assert len(result["address"]) == 4
        assert result["state"].iloc[0] == "IL"
        assert result["zip_code"].iloc[3] == "78701"


# ══════════════════════════════════════════════════════════
#  currency_normalize
# ══════════════════════════════════════════════════════════

class TestCurrencyNormalize:
    def test_usd_with_commas(self, agent):
        series = pd.Series(["$1,234.56"])
        result = agent._currency_normalize(series, {})
        assert result.iloc[0] == 1234.56

    def test_european_format(self, agent):
        series = pd.Series(["€2.345,67"])
        result = agent._currency_normalize(series, {})
        assert result.iloc[0] == 2345.67

    def test_plain_dollar(self, agent):
        series = pd.Series(["$500"])
        result = agent._currency_normalize(series, {})
        assert result.iloc[0] == 500.0

    def test_negative_parens(self, agent):
        series = pd.Series(["($50.00)"])
        result = agent._currency_normalize(series, {})
        assert result.iloc[0] == -50.0

    def test_currency_code(self, agent):
        series = pd.Series(["USD 1000"])
        result = agent._currency_normalize(series, {})
        assert result.iloc[0] == 1000.0

    def test_null_handling(self, agent):
        series = pd.Series([None, "", "N/A"])
        result = agent._currency_normalize(series, {})
        assert result.tolist() == [None, None, None]

    def test_negative_sign(self, agent):
        series = pd.Series(["$-50.00"])
        result = agent._currency_normalize(series, {})
        assert result.iloc[0] == -50.0

    def test_fixture_data(self, agent):
        df = currency_data()
        result = agent._currency_normalize(df["Amount"], {})
        assert result.iloc[0] == 1234.56
        assert result.iloc[2] == 500.0


# ══════════════════════════════════════════════════════════
#  zip_pad
# ══════════════════════════════════════════════════════════

class TestZipPad:
    def test_short_zip(self, agent):
        series = pd.Series(["2134"])
        result = agent._zip_pad(series, {})
        assert result.iloc[0] == "02134"

    def test_correct_zip(self, agent):
        series = pd.Series(["90210"])
        result = agent._zip_pad(series, {})
        assert result.iloc[0] == "90210"

    def test_zip_plus_four(self, agent):
        series = pd.Series(["12345-6789"])
        result = agent._zip_pad(series, {})
        assert result.iloc[0] == "12345-6789"

    def test_float_zip(self, agent):
        """Excel sometimes converts zips to floats like 2134.0"""
        series = pd.Series(["2134.0"])
        result = agent._zip_pad(series, {})
        assert result.iloc[0] == "02134"

    def test_null_handling(self, agent):
        series = pd.Series([None, "", "N/A"])
        result = agent._zip_pad(series, {})
        assert result.iloc[0] is None
        assert result.iloc[1] is None
        assert result.iloc[2] is None

    def test_fixture_data(self, agent):
        df = currency_data()
        result = agent._zip_pad(df["Zip"], {})
        assert result.iloc[0] == "02134"
        assert result.iloc[1] == "02134"
        assert result.iloc[2] == "90210"
        assert result.iloc[3] == "07201"
        assert result.iloc[4] == "12345-6789"


# ══════════════════════════════════════════════════════════
#  Existing Transforms
# ══════════════════════════════════════════════════════════

class TestExistingTransforms:
    def test_cast_integer(self, agent):
        series = pd.Series(["1,234", "$500", "42.0", None, "abc"])
        result = agent._cast_integer(series, {})
        assert result.iloc[0] == 1234
        assert result.iloc[1] == 500
        assert result.iloc[2] == 42
        assert result.iloc[3] is None
        assert result.iloc[4] is None

    def test_cast_float(self, agent):
        series = pd.Series(["1,234.56", "$500", None])
        result = agent._cast_float(series, {})
        assert result.iloc[0] == 1234.56
        assert result.iloc[1] == 500.0
        assert result.iloc[2] is None

    def test_parse_date(self, agent):
        series = pd.Series(["2024-01-15", "01/20/2024", "Jan 25, 2024", None, "garbage"])
        result = agent._parse_date(series, {})
        assert result.iloc[0] == "2024-01-15"
        assert result.iloc[1] == "2024-01-20"
        assert result.iloc[2] == "2024-01-25"
        assert result.iloc[3] is None

    def test_cast_boolean(self, agent):
        series = pd.Series(["yes", "no", "true", "false", "1", "0", None, "maybe"])
        result = agent._cast_boolean(series, {})
        assert result.iloc[0] is True
        assert result.iloc[1] is False
        assert result.iloc[2] is True
        assert result.iloc[3] is False
        assert result.iloc[4] is True
        assert result.iloc[5] is False
        assert result.iloc[6] is None
        assert result.iloc[7] is None

    def test_email_normalize(self, agent):
        series = pd.Series(["  John@Test.COM  ", "invalid", None])
        result = agent._email_normalize(series, {})
        assert result.iloc[0] == "john@test.com"
        assert result.iloc[1] is None
        assert result.iloc[2] is None

    def test_phone_normalize(self, agent):
        series = pd.Series(["(555) 123-4567", "+44 20 7946 0958"])
        result = agent._phone_normalize(series, {})
        assert result.iloc[0] == "+15551234567"
        assert result.iloc[1] == "+442079460958"


# ══════════════════════════════════════════════════════════
#  Full Pipeline (process method)
# ══════════════════════════════════════════════════════════

class TestTransformProcess:
    def test_simple_rename(self, agent):
        """Test basic column renaming without transforms."""
        df = pd.DataFrame({"First Name": ["John"], "Last Name": ["Doe"], "Email": ["j@t.com"]})
        mappings = [
            {"source_name": "First Name", "target_field": "first_name", "transform_type": None, "status": "approved"},
            {"source_name": "Last Name", "target_field": "last_name", "transform_type": None, "status": "approved"},
            {"source_name": "Email", "target_field": "email", "transform_type": "email_normalize", "status": "approved"},
        ]
        result = agent.process(df, mappings, SIMPLE_SCHEMA)
        assert "first_name" in result.columns
        assert "last_name" in result.columns
        assert "email" in result.columns
        assert result["first_name"].iloc[0] == "John"

    def test_split_name_in_pipeline(self, agent):
        """Test that split_name works through the full process() method."""
        df = pd.DataFrame({
            "Full Name": ["John Doe", "Jane Smith"],
            "Email": ["j@t.com", "js@t.com"],
        })
        mappings = [
            {
                "source_name": "Full Name",
                "target_field": "first_name",
                "transform_type": "split_name",
                "transform_config": {"first_name_field": "first_name", "last_name_field": "last_name"},
                "status": "approved",
            },
            {
                "source_name": "Email",
                "target_field": "email",
                "transform_type": "email_normalize",
                "status": "approved",
            },
        ]
        result = agent.process(df, mappings, SIMPLE_SCHEMA)
        assert "first_name" in result.columns
        assert "last_name" in result.columns
        assert result["first_name"].iloc[0] == "John"
        assert result["last_name"].iloc[0] == "Doe"
        assert result["first_name"].iloc[1] == "Jane"
        assert result["last_name"].iloc[1] == "Smith"

    def test_split_address_in_pipeline(self, agent):
        """Test that split_address works through the full process() method."""
        df = full_address_data()
        mappings = [
            {"source_name": "Name", "target_field": "first_name", "transform_type": None, "status": "approved"},
            {
                "source_name": "Full Address",
                "target_field": "address",
                "transform_type": "split_address",
                "transform_config": {
                    "street_field": "address", "city_field": "city",
                    "state_field": "state", "zip_field": "zip_code",
                },
                "status": "approved",
            },
            {"source_name": "Email", "target_field": "email", "transform_type": "email_normalize", "status": "approved"},
        ]
        result = agent.process(df, mappings, GENERIC_CRM_SCHEMA)
        assert "address" in result.columns
        assert "city" in result.columns
        assert "state" in result.columns
        assert "zip_code" in result.columns
        assert result["state"].iloc[0] == "IL"

    def test_missing_columns_get_none(self, agent):
        """Unmapped schema fields should be added as None columns."""
        df = pd.DataFrame({"Email": ["j@t.com"]})
        mappings = [
            {"source_name": "Email", "target_field": "email", "transform_type": None, "status": "approved"},
        ]
        result = agent.process(df, mappings, SIMPLE_SCHEMA)
        assert "first_name" in result.columns
        assert result["first_name"].iloc[0] is None

    def test_rejected_mappings_ignored(self, agent):
        """Rejected mappings should not produce output columns."""
        df = pd.DataFrame({"Name": ["John"], "Email": ["j@t.com"]})
        mappings = [
            {"source_name": "Name", "target_field": "first_name", "transform_type": None, "status": "rejected"},
            {"source_name": "Email", "target_field": "email", "transform_type": None, "status": "approved"},
        ]
        result = agent.process(df, mappings, SIMPLE_SCHEMA)
        assert result["email"].iloc[0] == "j@t.com"
        # first_name should exist but be None (added as missing column)
        assert result["first_name"].iloc[0] is None
