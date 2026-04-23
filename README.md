# US Census Data Chat Agent

A conversational AI agent that answers natural-language questions about US Census demographics using Snowflake Cortex. You type a question; it writes and runs a SQL query against the real Census dataset and explains the result in plain English.

**Live demo:** [Click here to open the app](https://interactive-chat-agent.streamlit.app)

No login or account is needed — the app is publicly accessible.

---

## What it can answer

Anything at the Census Block Group (CBG) level from the 2020 American Community Survey and 2020 Decennial Redistricting data, plus 2019 SafeGraph foot-traffic patterns:

- Population counts broken down by race, age, sex, or household type
- Housing occupancy, tenure, vacancy, and unit counts
- Median household income and poverty rates by geography
- Education attainment and employment statistics
- Geographic filtering by state or county
- Foot-traffic and mobility patterns per block group

Multi-turn conversations work. "What about Texas?" after asking about California will correctly carry the context forward.

---

## Architecture

The agent is a sequential pipeline. Each query passes through five stages:

```text
User question
    │
    ▼
1. Input Guardrail       — classifies whether the question is within scope
    │
    ▼
2. Text-to-SQL           — retrieves relevant column descriptions from the
                           knowledge base, then asks a Cortex LLM to write
                           the SQL that answers the question
    │
    ▼
3. Data Engine           — executes the SQL against the Census dataset and
                           returns results as a CSV-style string
    │
    ▼
4. Generator             — asks a second Cortex LLM to turn the raw data
                           into a plain-English answer
    │
    ▼
5. Output Guardrail      — scores the answer as STRONG / MEDIUM / WEAK / INVALID;
                           INVALID triggers a full retry (up to 2 retries)
    │
    ▼
Answer displayed with confidence badge and collapsible SQL
```

### Knowledge base and retrieval

The Text-to-SQL stage does not see the full schema upfront. Instead, the relevant column descriptions are retrieved at query time from a **Cortex Search** service — a managed vector store built on top of Snowflake. The knowledge base contains one chunk per ACS column, describing its name, the table it belongs to, the Census topic it covers, and a human-readable label. Retrieving only the relevant chunks keeps the SQL prompt short and focused.

The knowledge base is not built automatically — it requires running `scripts/build_kb.py` once before the app can function. This script reads every enabled metadata table, converts rows into searchable text chunks, writes them to a staging table in Snowflake, and creates the Cortex Search service on top. It takes about two minutes and only needs to be re-run if the schema changes.

For other METADATA columns like FIPS Code, Geographic Data and Geometry, rows of the table are not read. They hold no contextual information about the Census data. Instead, their column names are retrieved, enriched with descriptive labels and stored in the knowledge base (includes the table name these columns pertain to too).

For follow-up questions ("What about Texas?"), the last few user turns are prepended to the search query so Cortex Search can find the right columns even when the current question lacks context.

### Two conversation histories

The agent maintains two separate histories across turns:

- `sql_history` — every user question paired with the SQL the model wrote. This goes to the SQL generation model so it can write consistent follow-up queries.
- `nl_history` — every user question paired with the natural-language answer. This goes to the generator so it can reference prior results when answering follow-ups.

The Streamlit app owns these lists in `st.session_state` and passes them into the agent on every call.

### Models

All inference runs inside Snowflake Cortex — no external API keys required.

| Role | Default model | Why |
| --- | --- | --- |
| SQL generation | `mistral-large2` | Strong at structured output and following strict formatting rules |
| Response generation | `claude-sonnet-4-6` | Better at natural, conversational prose |
| Guardrails (both) | `claude-haiku-4-5` | Fast and cheap; classification only needs a single word |

Models are configurable via environment variables.

---

## Project structure

``` text
src/
  agent.py                  — orchestrates the pipeline and handles retries
  text_to_sql.py            — Cortex Search retrieval + SQL generation
  data_engine.py            — SQL execution and result formatting
  generator.py              — natural language response generation
  guardrail.py              — input and output classifiers
  prompt_templates.py       — all LLM prompts in one place
  session/
    snowflake_session.py    — Snowflake connection, context switching, helpers
  knowledge_base/
    builder.py              — builds and uploads KB chunks, creates Cortex Search service
    sources.py              — registry of all source tables and their handlers
  app/
    streamlit_app.py        — the chat UI
    pyproject.toml          — dependencies for Streamlit Community Cloud
scripts/
  build_kb.py               — entry point for the one-time KB build
tests/
  test_connection.py        — asserts credentials, both databases, and all required tables are present
  test_kb.py                — asserts Cortex Search returns relevant, well-formed chunks across topics
  test_text_to_sql.py       — asserts SQL structure, FIPS join correctness, and executability
  test_agent.py             — end-to-end tests: result structure, guardrails, multi-turn, and graceful degradation
```

---

## Assumptions and design decisions

These are the places where I made a judgment call or worked around something I discovered empirically.

### 1. 2019 ACS metadata is redundant to 2020

The Snowflake Marketplace dataset ships with metadata tables for both 2019 and 2020. Census Block Group geography, FIPS codes, and ACS column definitions are stable across these two years. I index only the 2020 metadata in the knowledge base. The 2019 foot-traffic patterns table is kept because it is the only vintage of SafeGraph mobility data available in the dataset.

### 2. FIPS data stays out of the knowledge base

An earlier version stored FIPS rows (state and county names) in Cortex Search for semantic lookup. I removed it after realising two things: the FIPS table is joinable at query time without any per-row indexing, and storing thousands of FIPS rows would crowd out the column-description chunks that the SQL model actually needs. The knowledge base now contains only a single schema-description chunk for the FIPS table.

### 3. The output guardrail is stateless

The output guardrail sees only the current question and the current answer — not the conversation history. This means follow-up questions like "What about Texas?" score as `MEDIUM` or `WEAK` even when the answer is correct, because the guardrail cannot verify that "The total population of Texas is 28 million" is a complete answer to a question it has never seen. This is a known limitation. The confidence badge reflects this accurately, and the answer itself is still correct. This is a place I can optimize by feeding in user query history alone.

### 4. Retries cover the full pipeline, not just the generator

When the output guardrail returns `INVALID`, the agent reruns everything from SQL generation forward — not just the response generation step. The SQL model is non-deterministic: if it chose the wrong columns on the first attempt, regenerating only the prose won't fix it. Retrying the full pipeline gives the SQL model a chance to recover.

### 5. TOP_K = 10 for Cortex Search

Each query retrieves 10 chunks from the knowledge base. This was chosen as a balance between context length (more chunks = longer prompt = slower and more expensive) and coverage (fewer chunks = risk of missing the right table or column). For queries spanning many states, FIPS filtering does not compete for these slots because FIPS lookups happen via SQL JOIN, not via retrieval. Cortex Search doesn't allow to configure TopK chunk retrieval parameter. This effect is thus achieved by limiting the number of rows read from Cortex Search result. I assume Cortex Search sorts chunks by relevance before returning.

### 6. The Streamlit app runs the agent in a background thread

Streamlit's execution model is single-threaded. Because the full pipeline takes 15–30 seconds for simple queries, running it synchronously would block the UI entirely. The agent runs in a daemon thread while the main Streamlit thread polls for completion and updates a status message every few seconds. Anything that touches Streamlit state (`st.cache_resource`, `st.session_state`) is resolved in the main thread before the background thread starts, to avoid thread-safety issues.

Complex multi-table queries (like the stress test — county-level aggregation across all of Texas with four metrics) can take well over 60 seconds. This is a known limitation: `SNOWFLAKE.CORTEX.COMPLETE` is a blocking call with no streaming support via the SQL API, so the app must wait for the full LLM response before doing anything. A future improvement would be to use Cortex's REST API, which supports streaming, so partial responses could be shown incrementally rather than waiting for the full answer.

---

## Known limitations

- Complex multi-table queries can take over 60 seconds end-to-end. `SNOWFLAKE.CORTEX.COMPLETE` is a blocking call — there is no streaming via the SQL API, so the full LLM response must arrive before the next pipeline stage begins.
- The output guardrail does not have conversation history, so follow-up questions may score MEDIUM or WEAK even when the answer is correct.
- Queries spanning many geographic areas (e.g. "all 50 states") may not retrieve all the right columns within the 10-chunk retrieval limit.
- The knowledge base covers 2020 ACS data. Questions requiring comparisons to 2019 values will be answered with 2020 figures unless the question specifically references foot-traffic patterns, which are from 2019.
- If a Cortex-hosted model is unavailable in your Snowflake region, the relevant pipeline stage will fail. Supported models vary by region; check Snowflake's Cortex model availability documentation.
