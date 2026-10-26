"""chat_agent parent graph."""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from src.chat_agent.nodes import generator, input_guardrail, output_guardrail, reject_input
from src.chat_agent.routing import after_input
from src.chat_agent.state import ConversationState
from src.context import AgentContext

if TYPE_CHECKING:
    from snowflake.snowpark import Session

builder = StateGraph(ConversationState, context_schema=AgentContext)
builder.add_node("input_guardrail", input_guardrail)
builder.add_node("reject_input", reject_input)
builder.add_node("generator", generator)
builder.add_node("output_guardrail", output_guardrail)

builder.add_edge(START, "input_guardrail")
builder.add_conditional_edges(
    "input_guardrail",
    after_input,
    {"generator": "generator", "reject_input": "reject_input"},
)
builder.add_edge("reject_input", END)
builder.add_edge("generator", "output_guardrail")
builder.add_edge("output_guardrail", END)

graph = builder.compile(checkpointer=InMemorySaver())


def _last_ai_text(messages) -> str:
    for message in reversed(messages):
        if message.type == "ai" and message.content:
            text = message.content if isinstance(message.content, str) else str(message.content)
            if text.strip():
                return text
    return ""


def run(query: str, session: Session, thread_id: str) -> dict:
    """Invoke the parent graph. thread_id selects the checkpointed conversation."""
    result = graph.invoke(
        {"messages": [HumanMessage(content=query)]},
        context=AgentContext(session=session),
        config={"configurable": {"thread_id": thread_id}},
    )
    scope = result.get("input_scope")
    score = result.get("output_score")
    return {
        "answer": _last_ai_text(result["messages"]),
        "sql": result.get("sql") or "",
        "confidence": score.decision if score is not None else "",
        "rejected": scope is not None and scope.decision == "INVALID",
    }
