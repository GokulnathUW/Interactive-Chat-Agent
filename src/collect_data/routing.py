"""collect_data conditional edges."""

from langgraph.graph import END

from src.collect_data.state import CollectDataState


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
