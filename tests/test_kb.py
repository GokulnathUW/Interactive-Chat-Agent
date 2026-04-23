#!/usr/bin/env python3
"""
Knowledge base retrieval tests.

Asserts that Cortex Search returns relevant, well-formed chunks
for a range of query types. Runs multiple queries to verify topic
coverage across demographics, economics, geography, and patterns.

Run from the project root:
    python tests/test_kb.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from snowflake.core import Root
from src.session.snowflake_session import (
    get_session,
    SNOWFLAKE_KB_DATABASE,
    SNOWFLAKE_KB_SCHEMA,
)
from src.knowledge_base.builder import CORTEX_SEARCH_SERVICE

RETURN_COLUMNS = ["CHUNK_TEXT", "COLUMN_NAME", "SNOWFLAKE_TABLE", "DATASET", "SOURCE_TYPE"]
TOP_K          = 5
DIVIDER        = "-" * 72

VALID_SOURCE_TYPES = {
    "field_descriptions",
    "redistricting_descriptions",
    "fips",
    "geographic",
    "geometry",
    "patterns",
}


def search(service, query: str, top_k: int = TOP_K) -> list[dict]:
    response = service.search(query=query, columns=RETURN_COLUMNS, limit=top_k)
    return response.results


def assert_results(label: str, results: list[dict], min_count: int = 1) -> None:
    print(f"\n[{label}] — {len(results)} result(s)")
    assert len(results) >= min_count, \
        f"'{label}': expected at least {min_count} result(s), got {len(results)}"

    for i, r in enumerate(results):
        # Every chunk must have CHUNK_TEXT
        assert r.get("CHUNK_TEXT"), \
            f"'{label}' result {i}: CHUNK_TEXT is empty"
        # Every chunk must have a known SNOWFLAKE_TABLE
        assert r.get("SNOWFLAKE_TABLE"), \
            f"'{label}' result {i}: SNOWFLAKE_TABLE is missing"
        # SOURCE_TYPE must be one of the registered handler types
        assert r.get("SOURCE_TYPE") in VALID_SOURCE_TYPES, \
            f"'{label}' result {i}: unexpected SOURCE_TYPE '{r.get('SOURCE_TYPE')}'"

        print(f"  [{i+1}] {r['SNOWFLAKE_TABLE']} | {r.get('COLUMN_NAME','—')} | {r['SOURCE_TYPE']}")


def test_kb():
    print("Connecting to Snowflake...")
    session = get_session()
    print("  Connected.\n")

    root    = Root(session)
    service = (
        root
        .databases[SNOWFLAKE_KB_DATABASE]
        .schemas[SNOWFLAKE_KB_SCHEMA]
        .cortex_search_services[CORTEX_SEARCH_SERVICE]
    )

    print(DIVIDER)

    # ── Demographics ──────────────────────────────────────────────────────────
    results = search(service, "total population by race")
    assert_results("Total population by race", results, min_count=3)
    tables = {r["SNOWFLAKE_TABLE"] for r in results}
    assert any("CBG" in t for t in tables), \
        "Expected at least one CBG data table for a population query"

    print(DIVIDER)

    # ── Economics ─────────────────────────────────────────────────────────────
    results = search(service, "median household income")
    assert_results("Median household income", results, min_count=3)
    chunk_texts = " ".join(r["CHUNK_TEXT"] for r in results).upper()
    assert "INCOME" in chunk_texts or "B19" in chunk_texts, \
        "Income query did not return income-related chunks"

    print(DIVIDER)

    # ── Education ────────────────────────────────────────────────────────────
    results = search(service, "bachelor's degree educational attainment")
    assert_results("Educational attainment", results, min_count=3)

    print(DIVIDER)

    # ── Housing ──────────────────────────────────────────────────────────────
    results = search(service, "housing occupancy renter owner")
    assert_results("Housing occupancy", results, min_count=3)

    print(DIVIDER)

    # ── Geography / FIPS ─────────────────────────────────────────────────────
    results = search(service, "state county geographic filter FIPS")
    assert_results("Geographic / FIPS", results, min_count=1)
    source_types = {r["SOURCE_TYPE"] for r in results}
    assert source_types & {"fips", "geographic"}, \
        "Expected at least one fips or geographic chunk for a geography query"

    print(DIVIDER)

    # ── Foot-traffic patterns ─────────────────────────────────────────────────
    results = search(service, "foot traffic visitor mobility patterns")
    assert_results("Foot-traffic patterns", results, min_count=1)
    assert any(r["SOURCE_TYPE"] == "patterns" for r in results), \
        "Expected at least one patterns chunk for a mobility query"

    print(DIVIDER)

    # ── Redistricting ─────────────────────────────────────────────────────────
    results = search(service, "redistricting census block group race total")
    assert_results("Redistricting data", results, min_count=1)

    print(DIVIDER)
    print("All KB tests passed.")
    session.close()


if __name__ == "__main__":
    test_kb()
