"""
Kaggle-Style Test Data — Realistic messy datasets for integration testing.

These simulate the kinds of files real users upload:
- Exported CSVs from CRMs with inconsistent formatting
- Spreadsheets with merged headers and mixed types
- International data with various date/phone/address formats
- Datasets with high null rates and dirty values
"""

import pandas as pd
import random
import string


def kaggle_hubspot_export() -> pd.DataFrame:
    """
    Simulates a HubSpot CRM export — common Kaggle-style dataset.
    Typical issues: Full names, mixed date formats, company domains
    mixed in with emails, phone numbers in various formats.
    """
    return pd.DataFrame({
        "Contact Name": [
            "John Doe", "Jane M. Smith", "Bob Johnson III",
            "Alice Williams-Brown", "Charlie O'Brien",
            "Diana Prince", "  Eve   Davis  ", "Frank Lee",
            "Grace Hopper", "Hank Patel",
        ],
        "Email Address": [
            "john.doe@acme.com", "jane.smith@globex.net", "BOBJOHNSON@INITECH.COM",
            "alice@umbrella.co", "charlie.obrien@stark.io",
            "diana@wayneenterprises.com", "eve.davis@example", "frank@lee.org",
            "grace@navy.mil", "hank.patel@tcs.in",
        ],
        "Phone Number": [
            "(555) 123-4567", "555.234.5678", "+1-555-345-6789",
            "5554567890", "555 567 8901",
            "+44 20 7946 0958", "N/A", "",
            "(555)789-0123", "555-012-3456",
        ],
        "Company Name": [
            "Acme Corp", "Globex Corporation", "INITECH",
            "Umbrella Corp.", "Stark Industries",
            "Wayne Enterprises", "Example LLC", "Lee & Associates",
            "US Navy", "TCS",
        ],
        "Deal Amount": [
            "$5,000.00", "$12,500", "€8.500,00",
            "$750", "($1,200.00)",
            "£3,000", "$0", "$45,000.99",
            "USD 25000", "$100.50",
        ],
        "Created Date": [
            "2024-01-15", "01/20/2024", "Jan 25, 2024",
            "2024-02-01", "02/10/2024",
            "15-03-2024", "2024/04/01", "May 5 2024",
            "2024-06-15T10:30:00Z", "07/20/24",
        ],
        "Lifecycle Stage": [
            "Customer", "Lead", "MQL",
            "customer", "LEAD",
            "Opportunity", "lead", "Customer",
            "MQL", "Lead",
        ],
        "Mailing Address": [
            "123 Main St, Springfield, IL 62704",
            "456 Oak Ave, Apt 2B, Chicago, IL 60601",
            "789 Elm St, New York, NY 10001",
            "321 Pine Rd, Austin, TX 78701",
            "555 Maple Dr, Seattle, WA 98101",
            "10 Downing Street, London, UK",
            "", 
            "999 Broadway, Suite 100, Denver, CO 80202",
            "1 Navy Yard, Washington, DC 20374",
            "42 Tech Park, Bangalore, KA 560001",
        ],
    })


def kaggle_salesforce_dirty() -> pd.DataFrame:
    """
    Simulates a messy Salesforce export with common data quality issues:
    - Duplicate emails
    - Null-heavy columns
    - Inconsistent casing
    - Numeric strings mixed with text
    """
    return pd.DataFrame({
        "FirstName": ["John", "JANE", "bob", None, "Alice", "john", "Diana", "Eve", None, "Frank"],
        "LastName": ["Doe", "SMITH", "johnson", "Williams", None, "Doe", "Prince", "Davis", "Hopper", None],
        "Email": [
            "john@test.com", "jane@test.com", "bob@test.com",
            "williams@test.com", "alice@test.com",
            "john@test.com",  # duplicate
            "diana@test.com", "eve@test.com",
            "grace@test.com", "frank@test.com",
        ],
        "Phone": [
            "5551234567", None, "555-345-6789",
            None, None,
            "5551234567", "+1 555 789 0123", None,
            "555.012.3456", "abc-not-a-phone",
        ],
        "Title": [
            "CEO", "CTO", "engineer",
            "VP Sales", None,
            "ceo",  # duplicate + different case
            "CFO", None,
            "Admiral", "Manager",
        ],
        "Annual Revenue": [
            "1000000", "5000000", "not_a_number",
            "250000", "750000",
            "1000000", "3000000", "",
            "0", "-500",
        ],
        "State": [
            "IL", "California", "ny",
            "TX", "WA",
            "Illinois", "CA", "CO",
            "DC", None,
        ],
        "Zip": [
            "62704", "90210", "10001",
            "78701", "98101",
            "62704", "94102", "80202",
            "20374", "1234",  # too short
        ],
    })


def kaggle_international_contacts() -> pd.DataFrame:
    """
    International dataset with varied formats — tests edge cases
    in phone, address, date parsing across locales.
    """
    return pd.DataFrame({
        "Nom Complet": [  # French header
            "Jean Dupont", "María García López", "田中太郎",
            "Ahmed Al-Rashid", "Müller, Hans", "Σωκράτης Παπαδόπουλος",
        ],
        "Courriel": [  # French for email
            "jean@example.fr", "maria@ejemplo.es", "tanaka@example.jp",
            "ahmed@example.sa", "hans@example.de", "sokrates@example.gr",
        ],
        "Téléphone": [
            "+33 1 23 45 67 89", "+34 912 345 678", "+81 3-1234-5678",
            "+966 11 234 5678", "+49 30 12345678", "+30 21 0 123 4567",
        ],
        "Date de création": [
            "15/01/2024", "20-01-2024", "2024年1月25日",
            "01/02/2024", "10.02.2024", "15/03/2024",
        ],
    })


def kaggle_large_messy(n: int = 500) -> pd.DataFrame:
    """
    Generate a large dataset with controlled messiness for stress testing.
    ~20% null rate, ~10% bad formats, ~5% duplicates.
    """
    random.seed(42)
    first_names = ["John", "Jane", "Bob", "Alice", "Charlie", "Diana",
                   "Eve", "Frank", "Grace", "Hank", "Ivy", "Jack"]
    last_names = ["Doe", "Smith", "Johnson", "Williams", "Brown",
                  "Jones", "Davis", "Miller", "Wilson", "Moore"]
    domains = ["test.com", "example.com", "demo.org", "sample.net", "company.io"]
    states = ["IL", "CA", "NY", "TX", "WA", "CO", "FL", "PA", "OH", "GA"]

    rows = []
    for i in range(n):
        fn = random.choice(first_names)
        ln = random.choice(last_names)

        # 20% chance of null for each optional field
        def maybe_null(val, rate=0.2):
            return None if random.random() < rate else val

        # 10% chance of bad format
        def maybe_bad_email(email):
            if random.random() < 0.1:
                return random.choice(["not-email", "", "@@bad", email.replace("@", "")])
            return email

        def maybe_bad_phone(phone):
            if random.random() < 0.1:
                return random.choice(["abc", "123", "N/A", ""])
            return phone

        email = f"{fn.lower()}.{ln.lower()}{i}@{random.choice(domains)}"

        # 5% duplicates — reuse an earlier email
        if i > 10 and random.random() < 0.05:
            dup_idx = random.randint(0, len(rows) - 1)
            email = rows[dup_idx]["Email"]

        phone_raw = f"({random.randint(200,999)}) {random.randint(100,999)}-{random.randint(1000,9999)}"
        zip_raw = f"{random.randint(10000, 99999)}"

        rows.append({
            "Full Name": maybe_null(f"{fn} {ln}"),
            "Email": maybe_bad_email(email),
            "Phone": maybe_bad_phone(maybe_null(phone_raw)),
            "Company": maybe_null(f"Company {random.choice(string.ascii_uppercase)}{random.randint(1,99)}"),
            "Job Title": maybe_null(random.choice(["CEO", "Engineer", "Manager", "VP", "Analyst", "Director"])),
            "State": maybe_null(random.choice(states)),
            "Zip Code": maybe_null(zip_raw),
            "Signup Date": maybe_null(f"2024-{random.randint(1,12):02d}-{random.randint(1,28):02d}"),
            "Amount": maybe_null(f"${random.randint(100, 50000):,}.{random.randint(0,99):02d}"),
        })

    return pd.DataFrame(rows)
