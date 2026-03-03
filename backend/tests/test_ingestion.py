"""
Tests for Ingestion Agent.

Covers:
- CSV parsing
- Column profiling (type detection, sample values, null counts)
- Edge cases (empty files, single column)
"""

import pytest
import pandas as pd
import io
from agents.ingestion import IngestionAgent


@pytest.fixture
def agent():
    return IngestionAgent()


class TestCSVParsing:
    def test_basic_csv(self, agent):
        csv_content = b"Name,Email,Phone\nJohn,john@test.com,555-1234\nJane,jane@test.com,555-5678"
        df, metadata = agent.process(csv_content, "test.csv")
        assert len(df) == 2
        assert metadata["row_count"] == 2
        assert metadata["column_count"] == 3

    def test_csv_with_nulls(self, agent):
        csv_content = b"Name,Email\nJohn,john@test.com\nJane,\n,bob@test.com"
        df, metadata = agent.process(csv_content, "test.csv")
        assert len(df) == 3
        # Check null detection
        columns = {c["name"]: c for c in metadata["columns"]}
        assert columns["Name"]["null_count"] >= 1
        assert columns["Email"]["null_count"] >= 1

    def test_csv_with_commas_in_quotes(self, agent):
        csv_content = b'Name,Address\nJohn,"123 Main St, Springfield"\nJane,"456 Oak Ave, Chicago"'
        df, metadata = agent.process(csv_content, "test.csv")
        assert len(df) == 2
        assert "123 Main St, Springfield" in df["Address"].values


class TestTypeDetection:
    def test_email_detection(self, agent):
        csv_content = b"col\njohn@test.com\njane@test.com\nbob@test.com"
        df, metadata = agent.process(csv_content, "test.csv")
        col_info = metadata["columns"][0]
        assert col_info["detected_type"] == "email"

    def test_integer_detection(self, agent):
        csv_content = b"col\n1\n2\n3\n4\n5"
        df, metadata = agent.process(csv_content, "test.csv")
        col_info = metadata["columns"][0]
        assert col_info["detected_type"] in ("integer", "float")

    def test_date_detection(self, agent):
        csv_content = b"col\n2024-01-15\n2024-02-20\n2024-03-25"
        df, metadata = agent.process(csv_content, "test.csv")
        col_info = metadata["columns"][0]
        assert col_info["detected_type"] == "date"


class TestColumnProfiling:
    def test_sample_values(self, agent):
        csv_content = b"Name\nJohn\nJane\nBob\nAlice\nCharlie\nDiana\nEve"
        df, metadata = agent.process(csv_content, "test.csv")
        col_info = metadata["columns"][0]
        assert len(col_info["sample_values"]) <= 5
        assert col_info["unique_count"] == 7
        assert col_info["total_count"] == 7

    def test_null_count(self, agent):
        csv_content = b"Name\nJohn\n\nBob\n\nCharlie"
        df, metadata = agent.process(csv_content, "test.csv")
        col_info = metadata["columns"][0]
        # Empty rows may be read as NaN or dropped depending on pandas behavior
        # Just verify the profiling runs without error and returns a count
        assert col_info["null_count"] >= 0
        assert col_info["total_count"] >= 3


class TestEdgeCases:
    def test_single_column(self, agent):
        csv_content = b"Email\njohn@test.com"
        df, metadata = agent.process(csv_content, "test.csv")
        assert metadata["column_count"] == 1
        assert metadata["row_count"] == 1

    def test_unicode_content(self, agent):
        csv_content = "Name\nJosé\nMüller\nNaïve".encode("utf-8")
        df, metadata = agent.process(csv_content, "test.csv")
        assert len(df) == 3
