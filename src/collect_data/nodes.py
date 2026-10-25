"""collect_data subgraph nodes."""

import os

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain.messages import HumanMessage
from langgraph.runtime import Runtime

from src.collect_data.prompts import SQL_AGENT_SYSTEM_PROMPT
from src.collect_data.state import CollectDataState
from src.collect_data.tools import retrieve_context
from src.context import AgentContext
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

