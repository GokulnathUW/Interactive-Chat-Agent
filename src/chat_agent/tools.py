"""Tools for the chat_agent generator."""

from langchain.messages import HumanMessage, ToolMessage
from langchain.tools import ToolRuntime, tool
from langgraph.types import Command

from src.collect_data.graph import graph as collect_data_graph
from src.context import AgentContext


@tool
def collect_data(question: str, runtime: ToolRuntime[AgentContext]) -> Command:
    """Fetch Census data that answers the question.

    Pass a self-contained question (topic and geography). Do not pass a
    pronoun-only follow-up — this tool does not see the parent chat.
    """
    result = collect_data_graph.invoke(
        {"messages": [HumanMessage(content=question)]},
        context=runtime.context,
    )
    data = result.get("data") or result.get("error") or "No data found."
    return Command(
        update={
            "sql": result.get("sql") or "",
            "messages": [
                ToolMessage(content=data, tool_call_id=runtime.tool_call_id or "")
            ],
        }
    )
