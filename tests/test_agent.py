#!/usr/bin/env python3
"""
End-to-end smoke test for the full agent pipeline.

Runs a set of queries through agent.run() and prints the result dict.
No assertions — correctness of natural language output is subjective;
this test verifies the pipeline completes without errors and produces
sensible structure.

Run from the project root:
    python tests/test_agent.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.session.snowflake_session import get_session
import src.agent as agent

DIVIDER = "-" * 72


def run(label: str, query: str, session, sql_history=None, nl_history=None):
    print(f"\n[{label}]")
    print(f"Query: {query}")
    try:
        result = agent.run(query, session, sql_history, nl_history)
        print(f"Confidence: {result['confidence']}")
        print(f"SQL:\n{result['sql']}")
        print(f"Answer:\n{result['answer']}")
        return result
    except ValueError as e:
        print(f"Rejected: {e}")
        return None


def main():
    print("Connecting to Snowflake...")
    session = get_session()
    print("Connected.\n")

    # --- 1. Standard census query ---
    print(DIVIDER)
    run("1. Population by race",
        "What is the total population broken down by race for census block groups in Travis County, Texas?",
        session)

    # --- 2. Economic query ---
    print(DIVIDER)
    run("2. Median household income",
        "Show me the median household income for census block groups in California.",
        session)

    # --- 3. Input guardrail — off-topic ---
    print(DIVIDER)
    run("3. Off-topic (should be rejected)",
        "What is the weather like in Austin today?",
        session)

    # --- 4. Multi-turn: follow-up resolves via sql_history ---
    print(DIVIDER)
    sql_history, nl_history = [], []

    first_query = "What is the total population of census block groups in California?"
    result = run("4. Multi-turn turn 1", first_query, session, sql_history, nl_history)

    if result:
        sql_history.append({"role": "user",      "content": first_query})
        sql_history.append({"role": "assistant",  "content": result["sql"]})
        nl_history.append({"role": "user",       "content": first_query})
        nl_history.append({"role": "assistant",   "content": result["answer"]})

        print(DIVIDER)
        run("5. Multi-turn turn 2 (follow-up)",
            "What about Texas?",
            session, sql_history, nl_history)

    # --- 6. Stress test: multi-table join + county-level aggregation across a whole state ---
    # Tests: simultaneous retrieval of columns from 3+ ACS tables, percentage calculations,
    # county-level GROUP BY, ORDER BY on an aggregate, and a large geographic scope (all of Texas).
    print(DIVIDER)
    import time
    stress_query = (
        "For each county in Texas, give me the total population, the percentage of households "
        "earning under $25,000 per year, the percentage of adults with at least a bachelor's "
        "degree, and the average number of people per household. Sort by total population descending."
    )
    stress_start = time.monotonic()
    result = run("6. Stress test (multi-table, county aggregation, Texas)", stress_query, session)
    stress_elapsed = time.monotonic() - stress_start
    print(f"Elapsed: {stress_elapsed:.1f}s")

    print(DIVIDER)
    print("\nDone.")
    session.close()


if __name__ == "__main__":
    main()
