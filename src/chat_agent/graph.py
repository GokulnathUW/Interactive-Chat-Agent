"""chat_agent parent graph."""

from langgraph.graph import END, START, StateGraph

from src.chat_agent.nodes import generator, input_guardrail, output_guardrail, reject_input
from src.chat_agent.routing import after_input
from src.chat_agent.state import ConversationState
from src.context import AgentContext

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

graph = builder.compile()
