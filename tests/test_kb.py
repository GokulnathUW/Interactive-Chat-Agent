#!/usr/bin/env python3
"""
Smoke-test the Cortex Search knowledge base by running a sample query
and printing the retrieved chunks with their metadata.

Run from the project root:
    python scripts/test_kb.py
    python scripts/test_kb.py "median household income"
"""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from snowflake.core import Root
from src.session.snowflake_session import (
    get_session,
    SNOWFLAKE_KB_DATABASE,
    SNOWFLAKE_KB_SCHEMA,
)
from src.knowledge_base.builder import CORTEX_SEARCH_SERVICE

# Columns to retrieve — must match those in the CREATE CORTEX SEARCH SERVICE query
RETURN_COLUMNS = ["CHUNK_TEXT", "COLUMN_NAME", "SNOWFLAKE_TABLE", "DATASET", "SOURCE_TYPE"]
TOP_K = 5

DEFAULT_QUERY = "total population by race"


def run_query(query: str) -> None:
    print(f"Connecting to Snowflake...")
    session = get_session()

    try:
        root = Root(session)
        service = (
            root
            .databases[SNOWFLAKE_KB_DATABASE]
            .schemas[SNOWFLAKE_KB_SCHEMA]
            .cortex_search_services[CORTEX_SEARCH_SERVICE]
        )

        print(f"\nQuery: \"{query}\"")
        print(f"Top {TOP_K} results from '{CORTEX_SEARCH_SERVICE}':\n")
        print("-" * 72)

        response = service.search(query=query, columns=RETURN_COLUMNS, limit=TOP_K)

        for i, result in enumerate(response.results, start=1):
            print(f"[{i}] Table:       {result.get('SNOWFLAKE_TABLE', '—')}")
            print(f"    Column:      {result.get('COLUMN_NAME', '—')}")
            print(f"    Dataset:     {result.get('DATASET', '—')}")
            print(f"    Source type: {result.get('SOURCE_TYPE', '—')}")
            print(f"    Chunk text:  {result.get('CHUNK_TEXT', '—')}")
            print()

        print("-" * 72)
        print(f"{len(response.results)} results returned.")

    finally:
        session.close()


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUERY
    run_query(query)
