# Todos

- [ ] Add a chat-model provider package when `init_chat_model` is first used.
- [ ] Parent graph (`src/chat_agent`): input_guardrail → generator → output_guardrail.
- [ ] Generator tool: `collect_data(question: str) -> str` (returns CSV or error). Defined in `src/chat_agent`; invokes the collect_data subgraph.
- [ ] `collect_data` subgraph (`src/collect_data`):
  - [x] tool `retrieve_context(search_query: str)`
  - [ ] node `run_query` (SELECT check inside; loop back to the SQL agent on error)
- [ ] Pass Snowflake session via `AgentContext` / `context_schema` at invoke.
- [ ] Move `AgentContext` out of `src/collect_data/tools.py` when the subgraph is created.
- [ ] Not tools: `write_query` (the SQL model), `validate_query` (inside `run_query`), `fetch_data` (same as `run_query`).

## Maybe

- [ ] Let `retrieve_context` take `top_k` so the SQL agent can request more or fewer chunks. Keep `_TOP_K` as the default until then; a second search with a refined query is the current way to get more signal.
