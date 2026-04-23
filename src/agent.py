"""
Agent orchestrator — single entry point for the full query pipeline.

Public interface:
    run(query, session, sql_history, nl_history) -> dict

Returns:
    {"answer": str, "sql": str, "confidence": str}

The app layer is responsible for maintaining sql_history and nl_history across
turns and for displaying the returned dict to the user.
"""
from snowflake.snowpark import Session

from src.guardrail import classify_input, evaluate_output
from src.text_to_sql import generate_sql
from src.data_engine import run_query
from src.generator import generate_response

_MAX_RETRIES = 2


def run(
    query: str,
    session: Session,
    sql_history: list[dict] | None = None,
    nl_history:  list[dict] | None = None,
) -> dict:
    """Run the full pipeline for a single user query.

    Args:
        query:       Natural language question from the user.
        session:     Active Snowpark session.
        sql_history: Prior turns as {"role", "content"} with SQL as assistant content.
        nl_history:  Prior turns as {"role", "content"} with NL answers as assistant content.

    Returns:
        {"answer": str, "sql": str, "confidence": str}

    Raises:
        ValueError: if the input guardrail rejects the query (caller displays message).
    """
    sql_history = sql_history or []
    nl_history  = nl_history  or []

    # --- Step 1: Validate input ---
    if classify_input(query, session) == "INVALID":
        raise ValueError(
            "I can only answer questions about US Census demographics, housing, "
            "income, education, geography, and foot-traffic patterns. "
            "Please rephrase your question."
        )

    # --- Steps 2 & 3: Generate SQL → fetch data → generate response → validate ---
    # Retry the full pipeline on INVALID so a bad SQL pick can be corrected.
    # The SQL model is non-deterministic and may choose better columns on retry.
    for attempt in range(_MAX_RETRIES + 1):
        if attempt > 0:
            print(f"  [agent] Retry {attempt}/{_MAX_RETRIES} — output was INVALID, regenerating...")

        sql        = generate_sql(query, session, sql_history)
        data       = run_query(sql, session)
        answer     = generate_response(query, data, nl_history, session)
        confidence = evaluate_output(query, answer, session)

        if confidence != "INVALID":
            break

        if attempt == _MAX_RETRIES:
            answer     = (
                "I wasn't able to produce a satisfactory answer for your question. "
                "Please try rephrasing or ask a different question."
            )
            confidence = "WEAK"

    return {"answer": answer, "sql": sql, "confidence": confidence}
