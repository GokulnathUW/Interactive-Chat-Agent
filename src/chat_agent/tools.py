"""Tools for the chat_agent generator."""

from langchain.messages import HumanMessage
from langchain.tools import ToolRuntime, tool

from src.collect_data.graph import graph as collect_data_graph
from src.context import AgentContext


@tool
def collect_data(question: str, runtime: ToolRuntime[AgentContext]) -> str:
    """Fetch Census data that answers the question.

    Pass a self-contained question (topic and geography). Do not pass a
    pronoun-only follow-up — this tool does not see the parent chat.
    """
    result = collect_data_graph.invoke(
        {"messages": [HumanMessage(content=question)]},
        context=runtime.context,
    )
    return result.get("data") or result.get("error") or "No data found."
