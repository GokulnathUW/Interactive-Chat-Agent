"""
Generator — converts raw query results into a natural language response.

Public interface:
    generate_response(query, data, history, session) -> str
"""
import os
from snowflake.snowpark import Session

from src.session.snowflake_session import quotes_literal
from src.prompt_templates import GENERATOR_PROMPT

GENERATOR_MODEL = os.getenv("GENERATOR_MODEL", "claude-sonnet-4-6")


def generate_response(
    query: str,
    data: str,
    history: list[dict],
    session: Session,
) -> str:
    """Produce a natural language answer from raw CSV data and the user's question.

    Args:
        query:   The original user question.
        data:    CSV-style string returned by data_engine.run_query().
        history: nl_history — list of {"role", "content"} dicts with prior
                 user questions and natural language answers (oldest first).
        session: Active Snowpark session.

    Returns:
        A natural language response grounded strictly in the provided data.
    """
    history_text = "\n".join(
        f"{'User' if h['role'] == 'user' else 'Assistant'}: {h['content']}"
        for h in history
    ) if history else "None"

    prompt = GENERATOR_PROMPT.format(
        data=data,
        history=history_text,
        query=query,
    )

    raw = session.sql(
        f"SELECT SNOWFLAKE.CORTEX.COMPLETE({quotes_literal(GENERATOR_MODEL)}, {quotes_literal(prompt)})"
    ).collect()[0][0]

    return raw.strip()
