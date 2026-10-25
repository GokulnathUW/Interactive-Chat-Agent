"""collect_data subgraph."""

from langgraph.graph import END, START, StateGraph

from src.collect_data.nodes import run_query, sql_agent, validate_query
from src.collect_data.state import CollectDataState
from src.collect_data.tools import AgentContext


def after_validate(state: CollectDataState) -> str:
    error = state.get("error") or ""
    if not error:
        return "run_query"
    if error == "UNSUPPORTED_QUERY":
        return END
    return "sql_agent"


def after_run(state: CollectDataState) -> str:
    if state.get("error"):
        return "sql_agent"
    return END

# Build the graph
builder = StateGraph(CollectDataState, context_schema=AgentContext)
builder.add_node("sql_agent", sql_agent)
builder.add_node("validate_query", validate_query)
builder.add_node("run_query", run_query)

# Define logic
builder.add_edge(START, "sql_agent")
builder.add_edge("sql_agent", "validate_query")
builder.add_conditional_edges(
    "validate_query",
    after_validate,
    {"run_query": "run_query", "sql_agent": "sql_agent", END: END},
)
builder.add_conditional_edges(
    "run_query",
    after_run,
    {"sql_agent": "sql_agent", END: END},
)

graph = builder.compile()
