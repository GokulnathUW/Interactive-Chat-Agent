#!/usr/bin/env python3
"""
Connection verification script.
Run from the project root:
    python tests/test_connection.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.session.snowflake_session import get_session, ensure_session_context


def main():
    print("Connecting to Snowflake...")
    session = get_session()
    print("  Connection successful.\n")

    ensure_session_context(session)
    print("Session context set.\n")

    tables = session.sql("SHOW TABLES").collect()
    print(f"Tables in schema: {len(tables)}")

    print("\nVerification complete.")
    session.close()


if __name__ == "__main__":
    main()
