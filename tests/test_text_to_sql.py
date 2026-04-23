#!/usr/bin/env python3
"""
Smoke-test the Text-to-SQL engine for single-turn and multi-turn queries.

Prints the generated SQL for manual inspection — no assertions since SQL
correctness is subjective and LLM output is non-deterministic.

Run from the project root:
    python tests/test_text_to_sql.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.session.snowflake_session import get_session
from src.text_to_sql import generate_sql

DIVIDER = "-" * 72


def run(label: str, query: str, session, history: list[dict] | None = None) -> str:
    """Run generate_sql, print result, and return SQL for chaining into history."""
    print(f"\n[{label}]")
    print(f"Query:   {query}")
    if history:
        print(f"History: {len(history)} turn(s)")
    try:
        sql = generate_sql(query, session, history)
        print(f"SQL:\n{sql}")
        return sql
    except ValueError as e:
        print(f"Rejected: {e}")
        return ""


def main():
    print("Connecting to Snowflake...")
    session = get_session()
    print("Connected.\n")
    print(DIVIDER)

    # --- Single-turn tests ---
    run("1. Single-turn: population by race",
        "What is the total population broken down by race for each census block group?",
        session)

    print(DIVIDER)

    run("2. Single-turn: geographic filter",
        "Show me the median household income for census block groups in Travis County, Texas.",
        session)

    print(DIVIDER)

    run("3. Single-turn: unsupported",
        "What is the weather in Austin today?",
        session)

    print(DIVIDER)

    # --- Multi-turn test: follow-up resolves pronoun via history ---
    sql_history = []

    first_query = "What is the total population of census block groups in California?"
    sql1 = run("4. Multi-turn turn 1", first_query, session, sql_history)
    if sql1:
        sql_history.append({"role": "user",      "content": first_query})
        sql_history.append({"role": "assistant",  "content": sql1})

    print(DIVIDER)

    run("5. Multi-turn turn 2 (follow-up: should resolve 'Texas' as population query)",
        "What about Texas?",
        session,
        sql_history)

    print(DIVIDER)
    print("\nDone.")
    session.close()


if __name__ == "__main__":
    main()
