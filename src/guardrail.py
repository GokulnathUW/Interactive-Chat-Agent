"""
Guardrail — validates user input and generator output using a fast Cortex LLM.

Public interface:
    validate_input(query, session)            -> None  (raises ValueError if invalid)
    is_output_valid(query, response, session) -> bool

Both functions are stateless classifiers — retry logic and attempt limits are
the responsibility of the app layer.
"""
import os
from snowflake.snowpark import Session

from src.session.snowflake_session import quotes_literal
from src.prompt_templates import INPUT_GUARDRAIL_PROMPT, OUTPUT_GUARDRAIL_PROMPT

GUARDRAIL_MODEL = os.getenv("GUARDRAIL_MODEL", "claude-haiku-4-5")


def _classify(prompt: str, session: Session) -> str:
    """Call the guardrail LLM and return its response as an uppercased string."""
    raw = session.sql(
        f"SELECT SNOWFLAKE.CORTEX.COMPLETE({quotes_literal(GUARDRAIL_MODEL)}, {quotes_literal(prompt)})"
    ).collect()[0][0]
    return raw.strip().upper()


def validate_input(query: str, session: Session) -> None:
    """Classify the user query as in-scope or out-of-scope.

    Raises:
        ValueError: with a user-friendly message if the query is out of scope.
                    The caller should display this message directly to the user.
    """
    prompt   = INPUT_GUARDRAIL_PROMPT.format(query=query)
    decision = _classify(prompt, session)

    # startswith guards against "VALID." or "VALID\n" from the model
    if not decision.startswith("VALID"):
        raise ValueError(
            "I can only answer questions about US Census demographics, housing, "
            "income, education, geography, and foot-traffic patterns. "
            "Please rephrase your question."
        )


def is_output_valid(query: str, response: str, session: Session) -> bool:
    """Return True if the generator response genuinely answers the query.

    The app is responsible for deciding how many times to retry on False,
    and for raising a user-friendly error when retries are exhausted.
    """
    prompt   = OUTPUT_GUARDRAIL_PROMPT.format(query=query, response=response)
    decision = _classify(prompt, session)
    return decision.startswith("VALID")
