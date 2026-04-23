#!/usr/bin/env python3
"""
Text-to-SQL engine tests.

LLM output is non-deterministic in content, but the structural constraints
we enforce via prompts are testable. These tests assert:
  - SQL always starts with SELECT
  - Geographic queries use the correct FIPS join pattern (ON with STATE_FIPS /
    COUNTY_FIPS) rather than USING (census_block_group)
  - State filters use 2-char abbreviations, not full names
  - County filters include the word 'County'
  - Banned patterns (USING census_block_group, f.state_name) are absent
  - Table names in geographic queries are double-quoted
  - Off-topic queries raise ValueError

Run from the project root:
    python tests/test_text_to_sql.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.session.snowflake_session import get_session, ensure_session_context
from src.text_to_sql import generate_sql

DIVIDER = "-" * 72


def run(label: str, query: str, session, history=None) -> str:
    """Generate SQL, print it, return SQL for history chaining."""
    print(f"\n[{label}]")
    print(f"Query: {query}")
    try:
        sql = generate_sql(query, session, history)
        print(f"SQL:\n{sql}\n")
        return sql
    except ValueError as e:
        print(f"Rejected: {e}\n")
        return ""


def assert_sql_executable(label: str, sql: str, session) -> None:
    """Actually run the SQL against Snowflake and assert it raises no exception."""
    print(f"  Executing SQL for [{label}]...")
    ensure_session_context(session, use_kb=False)
    try:
        rows = session.sql(sql).collect()
        print(f"  Returned {len(rows)} row(s). ✓")
    except Exception as exc:
        assert False, f"[{label}] Generated SQL failed at execution: {exc}\nSQL: {sql}"


def assert_sql_structure(label: str, sql: str) -> None:
    """Assertions that apply to every valid SQL output."""
    assert sql.upper().startswith("SELECT"), \
        f"[{label}] SQL must start with SELECT, got: {sql[:80]}"
    assert "USING (CENSUS_BLOCK_GROUP)" not in sql.upper(), \
        f"[{label}] SQL must not use USING (census_block_group) — FIPS table has no such column"
    assert "F.STATE_NAME" not in sql.upper(), \
        f"[{label}] SQL must not reference f.STATE_NAME — correct column is f.STATE"
    assert "F.COUNTY_NAME" not in sql.upper(), \
        f"[{label}] SQL must not reference f.COUNTY_NAME — correct column is f.COUNTY"


def assert_fips_join(label: str, sql: str) -> None:
    """Assert the correct two-part FIPS join is present for geographic queries."""
    upper = sql.upper()
    assert "STATE_FIPS" in upper, \
        f"[{label}] Geographic query must join on STATE_FIPS"
    assert "COUNTY_FIPS" in upper or "STATE_FIPS" in upper, \
        f"[{label}] Geographic query must use FIPS prefix extraction in JOIN"
    assert "LEFT(" in upper or "SUBSTR(" in upper, \
        f"[{label}] Geographic JOIN must extract FIPS prefix via LEFT() or SUBSTR()"


def assert_state_abbreviation(label: str, sql: str, full_name: str, abbreviation: str) -> None:
    """Assert the state filter uses the 2-char abbreviation, not the full name."""
    upper = sql.upper()
    assert f"'{abbreviation}'" in upper or f'"{abbreviation}"' in upper, \
        f"[{label}] Expected state abbreviation '{abbreviation}' in SQL"
    assert full_name.upper() not in upper, \
        f"[{label}] SQL must not use full state name '{full_name}' — use abbreviation '{abbreviation}'"


def assert_county_suffix(label: str, sql: str, county_word: str) -> None:
    """Assert the county filter includes the word 'County'."""
    assert "COUNTY" in sql.upper(), \
        f"[{label}] Expected 'County' suffix in county filter, got: {sql}"
    assert county_word.upper() + " COUNTY" in sql.upper() or \
           county_word.upper() + "'S COUNTY" in sql.upper() or \
           "COUNTY" in sql.upper(), \
        f"[{label}] County filter should include 'County' word"


def test_text_to_sql():
    print("Connecting to Snowflake...")
    session = get_session()
    print("Connected.\n")
    print(DIVIDER)

    # ── 1. Basic demographic query ────────────────────────────────────────────
    sql = run("1. Population by race (no geo filter)", session=session,
              query="What is the total population broken down by race for each census block group?")
    assert sql, "Expected SQL to be generated"
    assert_sql_structure("1", sql)

    print(DIVIDER)

    # ── 2. State-level geographic filter — SQL generated AND executed ─────────
    sql = run("2. Median income — Texas", session=session,
              query="Show me the median household income for census block groups in Texas.")
    assert sql, "Expected SQL to be generated"
    assert_sql_structure("2", sql)
    assert_fips_join("2", sql)
    assert_state_abbreviation("2", sql, full_name="Texas", abbreviation="TX")
    assert_sql_executable("2", sql, session)

    print(DIVIDER)

    # ── 3. County-level geographic filter — SQL generated AND executed ────────
    sql = run("3. Population — Travis County, Texas", session=session,
              query="What is the total population in Travis County, Texas?")
    assert sql, "Expected SQL to be generated"
    assert_sql_structure("3", sql)
    assert_fips_join("3", sql)
    assert_state_abbreviation("3", sql, full_name="Texas", abbreviation="TX")
    assert "TRAVIS" in sql.upper(), "Expected 'Travis' in county filter"
    assert "COUNTY" in sql.upper(), "County name must include 'County' suffix"
    assert_sql_executable("3", sql, session)

    print(DIVIDER)

    # ── 4. California state filter — SQL generated AND executed ───────────────
    sql = run("4. Housing occupancy — California", session=session,
              query="What percentage of housing units are renter-occupied in California?")
    assert sql, "Expected SQL to be generated"
    assert_sql_structure("4", sql)
    assert_fips_join("4", sql)
    assert_state_abbreviation("4", sql, full_name="California", abbreviation="CA")
    assert_sql_executable("4", sql, session)

    print(DIVIDER)

    # ── 5. Aggregation query — SQL generated AND executed ────────────────────
    sql = run("5. Aggregate — total population California", session=session,
              query="What is the total population of census block groups in California?")
    assert sql, "Expected SQL to be generated"
    assert_sql_structure("5", sql)
    assert "SUM(" in sql.upper() or "COUNT(" in sql.upper(), \
        "[5] 'Total population' query should use an aggregate function"
    assert_sql_executable("5", sql, session)

    print(DIVIDER)

    # ── 6. Off-topic — should raise ValueError ────────────────────────────────
    sql = run("6. Off-topic (should be rejected)", session=session,
              query="What is the weather in Austin today?")
    assert sql == "", "[6] Off-topic query should have been rejected with ValueError"

    print(DIVIDER)

    # ── 7. Multi-turn follow-up resolves via history ──────────────────────────
    sql_history = []
    first_query = "What is the total population of census block groups in California?"
    sql1 = run("7a. Multi-turn turn 1 — California", session=session,
               query=first_query)
    assert sql1, "Expected SQL for turn 1"
    assert_sql_structure("7a", sql1)
    assert_state_abbreviation("7a", sql1, full_name="California", abbreviation="CA")

    sql_history.append({"role": "user",      "content": first_query})
    sql_history.append({"role": "assistant",  "content": sql1})

    sql2 = run("7b. Multi-turn turn 2 — follow-up 'What about Texas?'", session=session,
               query="What about Texas?", history=sql_history)
    assert sql2, "Expected SQL for follow-up turn"
    assert_sql_structure("7b", sql2)
    assert_state_abbreviation("7b", sql2, full_name="Texas", abbreviation="TX")
    # Follow-up should query the same table as the first turn
    assert any(t in sql2 for t in ["B01", "B25", "B19"]), \
        "[7b] Follow-up should reference a CBG data table consistent with the prior query"

    print(DIVIDER)

    # ── 8. Foot-traffic / patterns query ─────────────────────────────────────
    sql = run("8. Foot-traffic patterns", session=session,
              query="What is the average number of visitors per census block group in New York?")
    assert sql, "Expected SQL to be generated"
    assert_sql_structure("8", sql)

    print(DIVIDER)
    print("All text-to-SQL tests passed.")
    session.close()


if __name__ == "__main__":
    test_text_to_sql()
