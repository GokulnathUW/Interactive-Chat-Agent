"""chat_agent conditional edges."""

from src.chat_agent.state import ConversationState


def after_input(state: ConversationState) -> str:
    scope = state.get("input_scope")
    if scope is not None and scope.decision == "VALID":
        return "generator"
    return "reject_input"
