# Learnings

## ToolRuntime, state, and context

- **The model** = the LLM (`create_agent` / `init_chat_model`). It sees `messages` plus each tool’s JSON schema (name, description, arguments). It does not see Python objects we inject.
- `@tool` builds that schema from function parameters. `runtime` is a **reserved** name: stripped from the schema, injected when the function actually runs.
- `ToolRuntime` is not storage. It is the handle the tool uses to read things the model must not fill in.

| Bucket | What it is | Session? |
| --- | --- | --- |
| **State** (`ConversationState`, `runtime.state`) | Mutable, checkpointed, changes during the run (`messages`, later `sql` / `data`) | No. A Snowpark `Session` is a live connection; the checkpointer would try to serialize it. |
| **Context** (`AgentContext`, `runtime.context`) | Immutable config passed at `invoke`. Same object for the whole run. | Yes. `context=AgentContext(session=session)`. |
| **Store** | Long-term memory across threads | No. |

- `runtime.state` is the state of **the graph currently running the tool**, as a dict (`runtime.state["messages"]`). It is not automatically the parent `ConversationState` unless we pass that `state_schema` or share subgraph state. `create_agent` defaults to `AgentState`.
- Define `AgentContext` next to the agent (`graph.py` or `context.py`). Create the session in the app (`get_session()`). Pass it at `invoke`. Do not define the dataclass in the Streamlit app; do not keep it in `tools.py` long-term.
- `get_session()` inside a tool works but opens a new connection per call. Context reuses the app’s cached session.
