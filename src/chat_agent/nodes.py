"""chat_agent graph nodes."""

import os

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain.messages import AIMessage, SystemMessage
from langgraph.runtime import Runtime

from src.chat_agent.prompts import (
    GENERATOR_SYSTEM_PROMPT,
    INPUT_GUARDRAIL_PROMPT,
    OUTPUT_GUARDRAIL_PROMPT,
    REJECT_INPUT_MESSAGE,
)
from src.chat_agent.state import ConversationState, InputScope, OutputScore
from src.chat_agent.tools import collect_data
from src.context import AgentContext
from src.session.snowflake_session import cortex_model, use_context_session

GUARDRAIL_MODEL = os.getenv("GUARDRAIL_MODEL", "claude-haiku-4-5")
_OUTPUT_HISTORY = 8  # last 4 human+ai exchanges; no ToolMessages

# Classifier only. Decision goes to input_scope, not messages.
def input_guardrail(state: ConversationState, runtime: Runtime[AgentContext]) -> dict:
    last_human = next(
        (m for m in reversed(state["messages"]) if m.type == "human"),
        None,
    )
    if last_human is None:
        return {"input_scope": InputScope(decision="INVALID")}

    result = (
        cortex_model(GUARDRAIL_MODEL, runtime.context.session)
        .with_structured_output(InputScope)
        .invoke([SystemMessage(content=INPUT_GUARDRAIL_PROMPT), last_human])
    )
    return {"input_scope": result}


def reject_input(state: ConversationState) -> dict:
    return {"messages": [AIMessage(content=REJECT_INPUT_MESSAGE)]}


def output_guardrail(state: ConversationState, runtime: Runtime[AgentContext]) -> dict:
    chat = [m for m in state["messages"] if m.type in ("human", "ai")][-_OUTPUT_HISTORY:]
    if not any(m.type == "human" for m in chat) or not any(m.type == "ai" for m in chat):
        return {"output_score": OutputScore(decision="INVALID")}

    result = (
        cortex_model(GUARDRAIL_MODEL, runtime.context.session)
        .with_structured_output(OutputScore)
        .invoke([SystemMessage(content=OUTPUT_GUARDRAIL_PROMPT), *chat])
    )
    return {"output_score": result}


GENERATOR_MODEL = os.getenv("GENERATOR_MODEL", "claude-sonnet-4-6")

# Generator: collect_data then answer in natural language.
generator = create_agent(
    model=init_chat_model(GENERATOR_MODEL, model_provider="snowflake"),
    tools=[collect_data],
    system_prompt=GENERATOR_SYSTEM_PROMPT,
    middleware=[use_context_session],
    state_schema=ConversationState,
    context_schema=AgentContext,
    name="generator",
)
