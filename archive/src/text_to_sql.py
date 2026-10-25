"""
Text-to-SQL engine.

Public interface:
    generate_sql(query, session, history) -> str

Built in stages:
    1. retrieve_context  — Cortex Search → relevant field descriptions
    2. derive_tables     — column names → Snowflake table names
    3. build_prompt      — assemble system prompt + context + history
    4. generate_sql      — call Cortex LLM, validate, return SQL
"""
import os
from snowflake.snowpark import Session
from snowflake.core import Root

from src.session.snowflake_session import (
    SNOWFLAKE_KB_DATABASE,
    SNOWFLAKE_KB_SCHEMA,
    quotes_literal,
)
from src.prompt_templates import SQL_GENERATION_PROMPT

CORTEX_SEARCH_SERVICE = os.getenv("CORTEX_SEARCH_SERVICE", "CBG_SEARCH")
SQL_MODEL             = os.getenv("SQL_MODEL", "mistral-large2")

# Columns returned from Cortex Search for each retrieved chunk
_SEARCH_COLUMNS = ["CHUNK_TEXT", "COLUMN_NAME", "SNOWFLAKE_TABLE", "DATASET", "SOURCE_TYPE"]
# How many chunks to retrieve per query
_TOP_K = 10


def retrieve_context(query: str, session: Session, history: list[dict] | None = None) -> list[dict]:
    """Query Cortex Search and return the top-K most relevant chunks.

    For follow-up queries ("What about Texas?"), the current query alone lacks
    enough signal for semantic search. Prepending recent user turns makes the
    search query self-contained so Cortex retrieves the right columns.

    Example:
        history: "What is the population of California by race?"
        query:   "What about Texas?"
        → search: "What is the population of California by race? What about Texas?"

    Only user turns from history are used (not assistant SQL) — the topic words
    live in the user's questions, not in SQL syntax.
    """
    if history:
        prior_user_turns = " ".join(
            h["content"] for h in history if h["role"] == "user"
        )
        search_query = f"{prior_user_turns} {query}"
    else:
        search_query = query

    root = Root(session)
    service = (
        root
        .databases[SNOWFLAKE_KB_DATABASE]
        .schemas[SNOWFLAKE_KB_SCHEMA]
        .cortex_search_services[CORTEX_SEARCH_SERVICE]
    )
    response = service.search(query=search_query, columns=_SEARCH_COLUMNS, limit=_TOP_K)
    return response.results


def parse_context(chunks: list[dict]) -> dict:
    """Parse retrieved chunks into structured context for prompt building.

    Returns a dict with two keys:
        "tables"  — {table_name: [column_name, ...]} for column-level chunks
                    Table is included with an empty list if only schema chunks
                    were retrieved (geographic, geometry, patterns).
        "chunks"  — the raw chunk list, for injecting full CHUNK_TEXT into prompt

    All chunks now have a SNOWFLAKE_TABLE. Chunks with no COLUMN_NAME are
    schema-only (fips, geographic, geometry, patterns) — table registered, no columns.
    """
    tables: dict[str, list[str]] = {}

    for chunk in chunks:
        table  = chunk.get("SNOWFLAKE_TABLE")
        column = chunk.get("COLUMN_NAME")

        if not table:
            continue

        if table not in tables:
            tables[table] = []

        if column:
            # Column-level chunk (field_descriptions, redistricting_descriptions)
            if column not in tables[table]:
                tables[table].append(column)
        # else: schema-only chunk (geographic, geometry, patterns) — table
        # registered with no columns; signals the LLM the table exists

    return {"tables": tables, "chunks": chunks}


def build_prompt(query: str, chunks: list[dict], history: list[dict]) -> str:
    """Assemble the final prompt string from retrieved chunks and conversation history.

    history is a list of {"role": "user"|"assistant", "content": "..."} dicts,
    ordered oldest first. Each turn is formatted as "User: ..." / "Assistant: ..."
    so the LLM receives plain readable text rather than JSON.
    """
    field_context = "\n".join(c["CHUNK_TEXT"] for c in chunks)

    if history:
        history_text = "\n".join(
            f"{'User' if h['role'] == 'user' else 'Assistant'}: {h['content']}"
            for h in history
        )
    else:
        history_text = "None"

    return SQL_GENERATION_PROMPT.format(
        field_context=field_context,
        history=history_text,
        query=query,
    )


def generate_sql(query: str, session: Session, history: list[dict] | None = None) -> str:
    """Full Text-to-SQL pipeline: retrieve → parse → prompt → LLM → validate.

    Args:
        query:   Natural language question from the user.
        session: Active Snowpark session.
        history: Conversation history as list of {"role", "content"} dicts.

    Returns:
        A validated Snowflake SQL SELECT string.

    Raises:
        ValueError: If the LLM returns UNSUPPORTED_QUERY or a non-SELECT response.
    """
    chunks  = retrieve_context(query, session, history)
    prompt  = build_prompt(query, chunks, history or [])
    raw = session.sql(
        f"SELECT SNOWFLAKE.CORTEX.COMPLETE({quotes_literal(SQL_MODEL)}, {quotes_literal(prompt)})"
    ).collect()[0][0]
    # Prompt ends with "SELECT" to prime the model. Strip it from the response
    # if the model echoed it, then restore exactly one SELECT at the front.
    stripped = raw.strip()
    if stripped.upper().startswith("SELECT"):
        stripped = stripped[6:].lstrip()
    sql = "SELECT " + stripped

    if sql.upper().startswith("SELECT UNSUPPORTED_QUERY"):
        raise ValueError("I'm not able to answer that question with the available Census data.")

    if not sql.upper().startswith("SELECT"):
        raise ValueError(f"I received an unexpected response from the SQL model: {sql[:120]}")

    return sql
