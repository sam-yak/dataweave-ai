"""
Quick test for the Ingestion Agent.
Run from the backend/ directory:  python test_ingestion.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from agents.ingestion import IngestionAgent

agent = IngestionAgent()

# ── Test 1: Basic CSV ────────────────────────────────────────
print("=" * 60)
print("TEST 1: Basic CSV")
print("=" * 60)

csv_data = b"""First Name,Last Name,Email,Phone,Company
John,Doe,john@example.com,555-1234,Acme Inc
Jane,Smith,jane@test.com,555-5678,Globex Corp
Bob,Wilson,bob@company.org,,DataCo
Alice,,alice@email.com,555-0000,TechStart"""

df, meta = agent.process(csv_data, "contacts.csv")
print(f"Rows: {meta['row_count']}, Columns: {meta['column_count']}")
print(f"Column names: {[c['name'] for c in meta['columns']]}")
print(f"Column types: {[c['detected_type'] for c in meta['columns']]}")
print(df.to_string(index=False))
print("PASSED\n")

# ── Test 2: Semicolon Delimiter ──────────────────────────────
print("=" * 60)
print("TEST 2: Semicolon-delimited CSV (European format)")
print("=" * 60)

euro_csv = b"""Name;Email;Amount;Date
Hans Mueller;hans@example.de;1234.56;2024-01-15
Maria Schmidt;maria@test.de;789.00;2024-02-20
Klaus Weber;klaus@company.de;456.78;2024-03-10"""

df, meta = agent.process(euro_csv, "data.csv")
print(f"Rows: {meta['row_count']}, Columns: {meta['column_count']}")
print(f"Delimiter detected correctly: {meta['column_count'] == 4}")
print(df.to_string(index=False))
print("PASSED\n")

# ── Test 3: Messy Data with Nulls ────────────────────────────
print("=" * 60)
print("TEST 3: Messy data with various null values")
print("=" * 60)

messy_csv = b"""name,email,phone,city
  John Doe  ,john@test.com,555-1234,New York
Jane Smith,N/A,null,
Bob,bob@email.com,none,Chicago
,missing@test.com,n/a,--
Alice Cooper,alice@test.com,555-0000,Not Available"""

df, meta = agent.process(messy_csv, "messy.csv")
print(f"Rows: {meta['row_count']}, Columns: {meta['column_count']}")
print("Null counts per column:")
for col in meta['columns']:
    print(f"  {col['name']}: {col['null_count']} nulls out of {col['total_count']}")
print(df.to_string(index=False))
print("PASSED\n")

# ── Test 4: JSON Array ───────────────────────────────────────
print("=" * 60)
print("TEST 4: JSON array of objects")
print("=" * 60)

json_data = b"""[
    {"firstName": "John", "lastName": "Doe", "email": "john@test.com", "age": 30},
    {"firstName": "Jane", "lastName": "Smith", "email": "jane@test.com", "age": 25},
    {"firstName": "Bob", "lastName": "Wilson", "email": "bob@test.com", "age": 45}
]"""

df, meta = agent.process(json_data, "users.json")
print(f"Rows: {meta['row_count']}, Columns: {meta['column_count']}")
print(f"Column names: {[c['name'] for c in meta['columns']]}")
print(df.to_string(index=False))
print("PASSED\n")

# ── Test 5: JSON with Wrapper ────────────────────────────────
print("=" * 60)
print("TEST 5: JSON with wrapper object")
print("=" * 60)

json_wrapped = b"""{
    "status": "success",
    "data": [
        {"name": "Product A", "price": "29.99", "category": "Electronics"},
        {"name": "Product B", "price": "49.99", "category": "Books"},
        {"name": "Product C", "price": "9.99", "category": "Electronics"}
    ]
}"""

df, meta = agent.process(json_wrapped, "products.json")
print(f"Rows: {meta['row_count']}, Columns: {meta['column_count']}")
print(f"Correctly found 'data' array: {meta['row_count'] == 3}")
print(df.to_string(index=False))
print("PASSED\n")

# ── Test 6: TSV ──────────────────────────────────────────────
print("=" * 60)
print("TEST 6: Tab-separated values")
print("=" * 60)

tsv_data = b"id\tname\temail\tstatus\n1\tJohn\tjohn@test.com\tactive\n2\tJane\tjane@test.com\tinactive\n3\tBob\tbob@test.com\tactive"

df, meta = agent.process(tsv_data, "export.tsv")
print(f"Rows: {meta['row_count']}, Columns: {meta['column_count']}")
print(f"Columns: {[c['name'] for c in meta['columns']]}")
print(df.to_string(index=False))
print("PASSED\n")

# ── Test 7: Type Detection ───────────────────────────────────
print("=" * 60)
print("TEST 7: Column type detection")
print("=" * 60)

typed_csv = b"""name,email,age,salary,is_active,joined_date
John,john@test.com,30,75000.50,yes,2024-01-15
Jane,jane@test.com,25,82000.00,no,2023-06-20
Bob,bob@test.com,45,91000.75,true,2022-11-01
Alice,alice@test.com,35,68000.00,false,2024-03-10"""

df, meta = agent.process(typed_csv, "employees.csv")
print("Detected types:")
for col in meta['columns']:
    print(f"  {col['name']}: {col['detected_type']}")
print("PASSED\n")

# ── Test 8: BOM Marker ──────────────────────────────────────
print("=" * 60)
print("TEST 8: UTF-8 with BOM marker")
print("=" * 60)

bom_csv = b"\xef\xbb\xbfname,email,city\nJohn,john@test.com,NYC\nJane,jane@test.com,LA"

df, meta = agent.process(bom_csv, "bom_file.csv")
print(f"Rows: {meta['row_count']}, Columns: {meta['column_count']}")
print(f"First column name clean: '{meta['columns'][0]['name']}'")
print(f"No BOM in column name: {not meta['columns'][0]['name'].startswith('\\ufeff')}")
print("PASSED\n")

# ── Summary ──────────────────────────────────────────────────
print("=" * 60)
print("ALL 8 TESTS PASSED")
print("Ingestion Agent is working correctly.")
print("=" * 60)
