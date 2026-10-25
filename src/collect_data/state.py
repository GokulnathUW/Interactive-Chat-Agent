"""collect_data subgraph state."""

from langgraph.graph import MessagesState


class CollectDataState(MessagesState):
    """SQL-agent transcript in `messages`."""
