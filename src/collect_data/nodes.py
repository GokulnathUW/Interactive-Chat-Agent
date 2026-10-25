"""collect_data subgraph nodes."""

import os

import sqlglot
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain.messages import HumanMessage
from langgraph.runtime import Runtime
from sqlglot import exp

from src.collect_data.prompts import SQL_AGENT_SYSTEM_PROMPT
from src.collect_data.state import CollectDataState
from src.collect_data.tools import AgentContext, retrieve_context
from src.session.snowflake_session import ensure_session_context

SQL_MODEL = os.getenv("SQL_MODEL", "mistral-large2")

# SQL agent: retrieve_context then emit a SELECT / WITH.
sql_agent = create_agent(
    model=init_chat_model(SQL_MODEL, model_provider="snowflake"),
    tools=[retrieve_context],
    system_prompt=SQL_AGENT_SYSTEM_PROMPT,
    state_schema=CollectDataState,
    context_schema=AgentContext,
    name="sql_agent",
)

def _last_ai_text(state: CollectDataState) -> str:
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


def _dql_error(sql: str) -> str | None:
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
    sql = _last_ai_text(state)
    error = _dql_error(sql)
    if error:
        # Clear sql; put the reason on error and in messages for a retry.
        return {
            "sql": "",
            "error": error,
            "messages": [HumanMessage(content=error)],
        }
    return {"sql": sql, "error": ""}


def run_query(state: CollectDataState, runtime: Runtime[AgentContext]) -> dict:
    # Census tables, not the KB schema. Raw Snowflake error goes back to sql_agent.
    try:
        session = runtime.context.session
        ensure_session_context(session, use_kb=False)
        df = session.sql(state["sql"])
        rows = df.collect()
    except Exception as exc:
        error = str(exc)
        print(f"  [run_query] SQL error: {error}")
        return {"data": "", "error": error, "messages": [HumanMessage(content=error)]}

    if not rows:
        return {"data": "No data found.", "error": ""}

    headers = ",".join(df.columns)
    body = "\n".join(",".join(str(v) for v in row) for row in rows)
    return {"data": f"{headers}\n{body}", "error": ""}

