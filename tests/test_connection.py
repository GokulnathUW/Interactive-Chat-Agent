#!/usr/bin/env python3
"""
Connection and environment verification tests.

Asserts that credentials are valid, both databases are reachable,
and the required tables exist in the data source.

Run from the project root:
    python tests/test_connection.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.session.snowflake_session import (
    get_session,
    ensure_session_context,
    SNOWFLAKE_DATA_DATABASE,
    SNOWFLAKE_DATA_SCHEMA,
    SNOWFLAKE_KB_DATABASE,
    SNOWFLAKE_KB_SCHEMA,
)

# Tables that must exist in the data source for the agent to function
REQUIRED_TABLES = [
    "2020_CBG_B01",
    "2020_CBG_B19",
    "2020_CBG_B25",
    "2020_METADATA_CBG_FIPS_CODES",
    "2020_METADATA_CBG_FIELD_DESCRIPTIONS",
    "2020_REDISTRICTING_CBG_DATA",
    "2020_REDISTRICTING_METADATA_CBG_FIELD_DESCRIPTIONS",
    "2019_CBG_PATTERNS",
]

DIVIDER = "-" * 72


def test_connection():
    print("Connecting to Snowflake...")
    session = get_session()
    print("  Connected.\n")

    # ── KB database reachable ─────────────────────────────────────────────────
    print(f"Checking KB database: {SNOWFLAKE_KB_DATABASE}.{SNOWFLAKE_KB_SCHEMA}")
    ensure_session_context(session, use_kb=True)
    kb_tables = {row["name"].upper() for row in session.sql("SHOW TABLES").collect()}
    print(f"  {len(kb_tables)} table(s) found in KB schema.")

    # ── Data database reachable ───────────────────────────────────────────────
    print(f"\nChecking data database: {SNOWFLAKE_DATA_DATABASE}.{SNOWFLAKE_DATA_SCHEMA}")
    ensure_session_context(session, use_kb=False)
    data_tables = {row["name"].upper() for row in session.sql("SHOW TABLES").collect()}
    print(f"  {len(data_tables)} table(s) found in data schema.")

    assert len(data_tables) > 0, "Data schema is empty — check SNOWFLAKE_DATA_DATABASE and SNOWFLAKE_DATA_SCHEMA"

    # ── Required tables present ───────────────────────────────────────────────
    print("\nChecking required tables:")
    for table in REQUIRED_TABLES:
        present = table.upper() in data_tables
        status  = "✓" if present else "✗ MISSING"
        print(f"  {status}  {table}")
        assert present, f"Required table missing from data source: {table}"

    # ── FIPS table has the right columns ─────────────────────────────────────
    print("\nVerifying FIPS table schema...")
    fips_cols = {
        row["name"].upper()
        for row in session.sql(
            'DESCRIBE TABLE "2020_METADATA_CBG_FIPS_CODES"'
        ).collect()
    }
    for expected_col in ("STATE", "STATE_FIPS", "COUNTY", "COUNTY_FIPS", "CLASS_CODE"):
        assert expected_col in fips_cols, \
            f"Expected column {expected_col} missing from FIPS table (found: {fips_cols})"
    assert "CENSUS_BLOCK_GROUP" not in fips_cols, \
        "FIPS table unexpectedly has CENSUS_BLOCK_GROUP — join logic may be wrong"
    print("  FIPS schema looks correct.")

    print(DIVIDER)
    print("All connection tests passed.")
    session.close()


if __name__ == "__main__":
    test_connection()
