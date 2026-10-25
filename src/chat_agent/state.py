"""Graph state schema."""

from typing import Literal, NotRequired

from langgraph.graph import MessagesState
from pydantic import BaseModel


class InputScope(BaseModel):
    decision: Literal["VALID", "INVALID"]


class OutputScore(BaseModel):
    decision: Literal["HIGH", "MEDIUM", "LOW", "INVALID"]


class ConversationState(MessagesState):
    """User questions and agent answers in `messages`."""

    input_scope: NotRequired[InputScope]
    output_score: NotRequired[OutputScore]
