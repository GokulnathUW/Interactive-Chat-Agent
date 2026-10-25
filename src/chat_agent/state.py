"""Graph state schema."""

from langgraph.graph import MessagesState


class ConversationState(MessagesState):
    """User questions and agent answers in `messages`."""
