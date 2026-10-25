"""
Guardrail — classifies user input and generator output using a fast Cortex LLM.

Public interface:
    classify_input(query, session)              -> str   ("VALID" | "INVALID")
    evaluate_output(query, response, session)   -> str   ("STRONG" | "MEDIUM" | "WEAK" | "INVALID")

Both functions are pure classifiers — all branching logic (error raising,
retry loops, user-facing messages) belongs in the agent layer.
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


def classify_input(query: str, session: Session) -> str:
    """Classify the user query as in-scope or out-of-scope.

    Returns "VALID" or "INVALID". All downstream logic is the caller's responsibility.
    """
    prompt   = INPUT_GUARDRAIL_PROMPT.format(query=query)
    decision = _classify(prompt, session)
    return "VALID" if decision.startswith("VALID") else "INVALID"


_VALID_SCORES = {"STRONG", "MEDIUM", "WEAK"}


def evaluate_output(query: str, response: str, session: Session) -> str:
    """Score the generator response against the user query.

    Returns one of: "STRONG", "MEDIUM", "WEAK", "INVALID".
    The agent retries on "INVALID"; passes the score through as confidence otherwise.
    The app is responsible for retry limits and graceful failure.
    """
    prompt   = OUTPUT_GUARDRAIL_PROMPT.format(query=query, response=response)
    decision = _classify(prompt, session)

    # Normalise — extract the first recognised token in case of trailing punctuation
    for token in ("STRONG", "MEDIUM", "WEAK", "INVALID"):
        if decision.startswith(token):
            return token

    return "INVALID"  # unrecognised response → treat as invalid, trigger retry
