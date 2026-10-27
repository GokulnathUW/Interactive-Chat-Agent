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


def _chunk_text(message) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text") or "")
        return "".join(parts)
    return ""


def _from_generator(ns) -> bool:
    return any(str(part).startswith("generator") for part in (ns or ()))


def _result_from_state(state: dict) -> dict:
    scope = state.get("input_scope")
    score = state.get("output_score")
    return {
        "answer": _last_ai_text(state.get("messages") or []),
        "sql": state.get("sql") or "",
        "confidence": score.decision if score is not None else "",
        "rejected": scope is not None and scope.decision == "INVALID",
    }


def run(query: str, session: Session, thread_id: str):
    """Stream the parent graph. Yields token dicts, then one result dict."""
    config = {"configurable": {"thread_id": thread_id}}
    last_state = None
    for chunk in graph.stream(
        {"messages": [HumanMessage(content=query)]},
        context=AgentContext(session=session),
        config=config,
        stream_mode=["messages", "values"],
        subgraphs=True,
        version="v2",
    ):
        kind = chunk["type"]
        ns = chunk.get("ns") or ()
        if kind == "messages" and _from_generator(ns):
            token, _metadata = chunk["data"]
            if getattr(token, "tool_call_chunks", None):
                continue
            text = _chunk_text(token)
            if text:
                yield {"type": "token", "text": text}
        elif kind == "values" and not ns:
            last_state = chunk["data"]
    if last_state is None:
        last_state = graph.get_state(config).values
    yield {"type": "result", **_result_from_state(last_state)}
