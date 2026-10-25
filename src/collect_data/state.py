"""collect_data subgraph state."""

from typing import NotRequired

from langgraph.graph import MessagesState


class CollectDataState(MessagesState):
    """SQL-agent transcript in `messages`; `sql` / `error` / `data` from later nodes."""

    sql: NotRequired[str]
    error: NotRequired[str]
    data: NotRequired[str]
