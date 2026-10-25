"""Deterministic DQL checks. No LLM or Snowflake."""

import sqlglot
from langchain.messages import HumanMessage
from sqlglot import exp

from src.collect_data.state import CollectDataState


def last_ai_text(state: CollectDataState) -> str:
    # Newest AIMessage, unwrap ``` fences, drop a trailing semicolon.
    for message in reversed(state["messages"]):
        if message.type == "ai" and message.content:
            text = message.content if isinstance(message.content, str) else str(message.content)
            text = text.strip()
            if text.startswith("```"):
                lines = text.splitlines()
                text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
            return text.strip().rstrip(";")
    return ""


def dql_error(sql: str) -> str | None:
    if not sql:
        return "No SQL was produced."
    if sql.upper() == "UNSUPPORTED_QUERY":
        return "UNSUPPORTED_QUERY"
    # Fail closed: unparsable or not exactly one Query (SELECT / WITH / UNION).
    try:
        statements = sqlglot.parse(sql, dialect="snowflake")
    except sqlglot.errors.ParseError as exc:
        return f"SQL could not be parsed as DQL: {exc}"
    if not statements or statements == [None] or len(statements) != 1:
        return "Only one DQL statement is allowed."
    statement = statements[0]
    if statement is None or not isinstance(statement, exp.Query):
        return "Only DQL (SELECT or WITH … SELECT) is allowed."
    return None


def validate_query(state: CollectDataState) -> dict:
    sql = last_ai_text(state)
    error = dql_error(sql)
    if error:
        # Clear sql; put the reason on error and in messages for a retry.
        return {
            "sql": "",
            "error": error,
            "messages": [HumanMessage(content=error)],
        }
    return {"sql": sql, "error": ""}
