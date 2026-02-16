"""
Ingestion Agent — Agent 1 of 5
Parses uploaded files into a standardized format.
Handles CSV, XLSX, JSON, TSV with encoding detection,
delimiter sniffing, and header row detection.

LLM Usage: None (fully deterministic)
"""

import io
import json
import chardet
import pandas as pd
from typing import Tuple


class IngestionAgent:
    """Parse any supported file into a clean DataFrame + metadata."""

    SUPPORTED_TYPES = {"csv", "xlsx", "xls", "json", "tsv"}

    # Values that should be treated as null
    NULL_VALUES = {
        "", "null", "none", "n/a", "na", "nan", "-", "--",
        "undefined", "nil", "#n/a", "#na", "missing", "not available"
    }

    def process(self, file_bytes: bytes, filename: str, sheet_name: str = None) -> Tuple[pd.DataFrame, dict]:
        """
        Main entry point. Takes raw file bytes and returns a clean DataFrame + metadata.

        Args:
            file_bytes: Raw bytes of the uploaded file
            filename: Original filename (used for type detection)
            sheet_name: Optional sheet name for Excel files

        Returns:
            Tuple of (DataFrame, metadata_dict)

        Raises:
            ValueError: If file type is unsupported or parsing fails
        """
        file_type = self._detect_file_type(filename)
        if file_type not in self.SUPPORTED_TYPES:
            raise ValueError(f"Unsupported file type: .{file_type}. Supported: {', '.join(self.SUPPORTED_TYPES)}")

        # Route to the correct parser
        if file_type in ("csv", "tsv"):
            df = self._parse_csv(file_bytes, file_type)
        elif file_type in ("xlsx", "xls"):
            df = self._parse_excel(file_bytes, sheet_name)
        elif file_type == "json":
            df = self._parse_json(file_bytes)
        else:
            raise ValueError(f"No parser for file type: {file_type}")

        # Clean the DataFrame
        df = self._clean_dataframe(df)

        # Detect and fix header row
        df = self._detect_header(df)

        # Build metadata
        metadata = self._build_metadata(df, filename, file_type, len(file_bytes))

        return df, metadata

    def get_excel_sheets(self, file_bytes: bytes) -> list:
        """Return list of sheet names in an Excel file."""
        try:
            excel_file = pd.ExcelFile(io.BytesIO(file_bytes))
            return excel_file.sheet_names
        except Exception as e:
            raise ValueError(f"Failed to read Excel sheets: {str(e)}")

    # ── File Type Detection ──────────────────────────────────────

    def _detect_file_type(self, filename: str) -> str:
        """Detect file type from extension."""
        if "." not in filename:
            raise ValueError("Filename has no extension. Cannot detect file type.")
        extension = filename.rsplit(".", 1)[-1].lower()
        return extension

    # ── CSV / TSV Parser ─────────────────────────────────────────

    def _parse_csv(self, file_bytes: bytes, file_type: str) -> pd.DataFrame:
        """Parse CSV or TSV with encoding detection and delimiter sniffing."""
        # Step 1: Detect encoding
        encoding = self._detect_encoding(file_bytes)

        # Step 2: Decode bytes to string
        try:
            text = file_bytes.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            # Fallback encodings
            for fallback in ["utf-8", "latin-1", "cp1252"]:
                try:
                    text = file_bytes.decode(fallback)
                    encoding = fallback
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise ValueError("Could not decode file with any supported encoding.")

        # Strip BOM if present
        if text.startswith("\ufeff"):
            text = text[1:]

        # Step 3: Detect delimiter
        if file_type == "tsv":
            delimiter = "\t"
        else:
            delimiter = self._sniff_delimiter(text)

        # Step 4: Parse with pandas
        try:
            df = pd.read_csv(
                io.StringIO(text),
                sep=delimiter,
                dtype=str,           # Read everything as string initially
                keep_default_na=False,  # We handle nulls ourselves
                on_bad_lines="skip"  # Skip malformed rows instead of crashing
            )
        except Exception as e:
            raise ValueError(f"CSV parse failed: {str(e)}")

        return df

    def _detect_encoding(self, file_bytes: bytes) -> str:
        """Detect file encoding using chardet."""
        # Check for BOM first
        if file_bytes[:3] == b"\xef\xbb\xbf":
            return "utf-8-sig"
        if file_bytes[:2] in (b"\xff\xfe", b"\xfe\xff"):
            return "utf-16"

        # Use chardet for detection
        result = chardet.detect(file_bytes[:10000])  # Sample first 10KB
        encoding = result.get("encoding", "utf-8")
        confidence = result.get("confidence", 0)

        # If confidence is low, default to utf-8
        if confidence < 0.7 or encoding is None:
            return "utf-8"

        return encoding.lower()

    def _sniff_delimiter(self, text: str) -> str:
        """Detect the most likely delimiter in a CSV file."""
        # Take first 5 lines for analysis
        lines = text.strip().split("\n")[:5]
        if not lines:
            return ","

        candidates = {",": 0, "\t": 0, ";": 0, "|": 0}

        for line in lines:
            for delim in candidates:
                candidates[delim] += line.count(delim)

        # Pick the delimiter that appears most consistently
        # But also check that it appears in every line
        best_delim = ","
        best_score = 0

        for delim, total_count in candidates.items():
            if total_count == 0:
                continue
            # Check consistency: delimiter should appear in every line
            lines_with_delim = sum(1 for line in lines if delim in line)
            consistency = lines_with_delim / len(lines)
            score = total_count * consistency

            if score > best_score:
                best_score = score
                best_delim = delim

        return best_delim

    # ── Excel Parser ─────────────────────────────────────────────

    def _parse_excel(self, file_bytes: bytes, sheet_name: str = None) -> pd.DataFrame:
        """Parse Excel file with optional sheet selection."""
        try:
            excel_file = pd.ExcelFile(io.BytesIO(file_bytes))

            # Use specified sheet or default to first
            if sheet_name and sheet_name in excel_file.sheet_names:
                target_sheet = sheet_name
            else:
                target_sheet = excel_file.sheet_names[0]

            df = pd.read_excel(
                excel_file,
                sheet_name=target_sheet,
                dtype=str,
                keep_default_na=False
            )
        except Exception as e:
            raise ValueError(f"Excel parse failed: {str(e)}")

        return df

    # ── JSON Parser ──────────────────────────────────────────────

    def _parse_json(self, file_bytes: bytes) -> pd.DataFrame:
        """Parse JSON file — handles array-of-objects and simple nested structures."""
        encoding = self._detect_encoding(file_bytes)

        try:
            text = file_bytes.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            text = file_bytes.decode("utf-8", errors="replace")

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON parse failed: {str(e)}")

        # Handle different JSON structures
        if isinstance(data, list):
            # Array of objects — most common format
            if len(data) == 0:
                raise ValueError("JSON array is empty.")
            if isinstance(data[0], dict):
                df = pd.json_normalize(data, max_level=1)
            else:
                raise ValueError("JSON array must contain objects, not primitives.")
        elif isinstance(data, dict):
            # Could be a single object or a wrapper like {"data": [...]}
            # Look for an array value inside
            array_key = None
            for key, value in data.items():
                if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
                    array_key = key
                    break

            if array_key:
                df = pd.json_normalize(data[array_key], max_level=1)
            else:
                # Single object — make it a one-row DataFrame
                df = pd.json_normalize([data], max_level=1)
        else:
            raise ValueError("JSON must be an array of objects or an object.")

        # Convert all columns to string for consistency
        df = df.astype(str)

        return df

    # ── Data Cleaning ────────────────────────────────────────────

    def _clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean the parsed DataFrame."""
        if df.empty:
            raise ValueError("File contains no data rows.")

        # Strip whitespace from column names
        df.columns = [str(col).strip() for col in df.columns]

        # Remove completely empty rows
        df = df.dropna(how="all")

        # Remove completely empty columns
        df = df.dropna(axis=1, how="all")

        # Strip whitespace from all string values
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype(str).str.strip()

        # Normalize null-like values to actual None
        for col in df.columns:
            df[col] = df[col].apply(
                lambda x: None if (isinstance(x, str) and x.lower() in self.NULL_VALUES) else x
            )

        # Remove unnamed columns (common in messy Excel files)
        unnamed_cols = [col for col in df.columns if col.lower().startswith("unnamed")]
        if unnamed_cols:
            # Only drop if they're actually empty
            for col in unnamed_cols:
                if df[col].isna().all():
                    df = df.drop(columns=[col])

        if df.empty:
            raise ValueError("File contains no data after cleaning.")

        if len(df.columns) == 0:
            raise ValueError("File contains no valid columns after cleaning.")

        return df

    def _detect_header(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Check if the first row might actually be data, not a header.
        This handles cases where the real header is row 2 or 3 (common in exports
        that have a title row or metadata rows before the actual data).
        """
        if len(df) < 2:
            return df

        # Heuristic: if column names look like data (all numeric, or look like
        # actual values), then the first row of data might be the real header.
        cols = [str(c) for c in df.columns]

        # Check if columns are just default integer indices
        all_numeric_headers = all(self._is_numeric_string(c) for c in cols)

        if all_numeric_headers:
            # Use first row as header
            new_headers = [str(v).strip() if pd.notna(v) else f"column_{i}"
                          for i, v in enumerate(df.iloc[0])]
            df.columns = new_headers
            df = df.iloc[1:].reset_index(drop=True)

        return df

    def _is_numeric_string(self, s: str) -> bool:
        """Check if a string looks like a number."""
        try:
            float(s)
            return True
        except (ValueError, TypeError):
            return False

    # ── Metadata ─────────────────────────────────────────────────

    def _build_metadata(self, df: pd.DataFrame, filename: str, file_type: str, file_size: int) -> dict:
        """Build metadata about the parsed file."""
        column_info = []
        for col in df.columns:
            series = df[col]
            non_null = series.dropna()

            # Detect likely data type
            detected_type = self._detect_column_type(non_null)

            # Get sample values (up to 5 non-null unique values)
            samples = non_null.unique()[:5].tolist()

            column_info.append({
                "name": col,
                "detected_type": detected_type,
                "sample_values": samples,
                "null_count": int(series.isna().sum()),
                "total_count": len(series),
                "unique_count": int(non_null.nunique()),
            })

        return {
            "filename": filename,
            "file_type": file_type,
            "file_size_bytes": file_size,
            "row_count": len(df),
            "column_count": len(df.columns),
            "columns": column_info,
        }

    def _detect_column_type(self, series: pd.Series) -> str:
        """Detect the most likely data type for a column."""
        if series.empty:
            return "unknown"

        # Sample up to 100 values for type detection
        sample = series.head(100)

        # Try numeric
        numeric_count = 0
        for val in sample:
            try:
                float(str(val).replace(",", ""))
                numeric_count += 1
            except (ValueError, TypeError):
                pass

        if numeric_count / len(sample) > 0.8:
            # Check if integers or floats
            int_count = 0
            for val in sample:
                try:
                    cleaned = str(val).replace(",", "")
                    if float(cleaned) == int(float(cleaned)):
                        int_count += 1
                except (ValueError, TypeError):
                    pass
            return "integer" if int_count / len(sample) > 0.8 else "float"

        # Try date
        date_count = 0
        from dateutil import parser as date_parser
        for val in sample:
            try:
                date_parser.parse(str(val), fuzzy=False)
                date_count += 1
            except (ValueError, TypeError, OverflowError):
                pass

        if date_count / len(sample) > 0.7:
            return "date"

        # Try boolean
        bool_values = {"true", "false", "yes", "no", "1", "0", "y", "n"}
        bool_count = sum(1 for val in sample if str(val).lower() in bool_values)
        if bool_count / len(sample) > 0.8:
            return "boolean"

        # Try email
        email_count = sum(1 for val in sample if "@" in str(val) and "." in str(val))
        if email_count / len(sample) > 0.7:
            return "email"

        # Default to string
        return "string"
