# Reflection

## 1. Development process and key architectural decisions

### Exploring the dataset

The first step was the dataset. I spent the next three hours exploring the dataset. The census data first made no sense with incomprehensibile column names. After discovering the METADATA file detailing each column, things started taking shape. I wanted to keep this knowledge base apart from the census data. This maintained the clean schema. So, I created a new database to hold the knowledge base. Huge portion of my inital time spent in exploring the dataset went in identifying what to store in the knowledge base and what not to. I made some unwise decisions initially. I assumed all files with 'METADATA' in it's name must logically be a METADATA file but that was not to be as it turned out with the geographic and FIPS code data. Finally, currently the entire knowledge base sits on a single table. This can be split in the future if the change reaped benefits.

### First architectural decision: how to give the LLM schema knowledge

I thought about what the system should be like, quickly drawing a block diagram. The important components I noticed were:

- Knowledge Base
- Guardrail (to validate both the user's query and the agent's response)
- Text-To-SQL converter
- Information Extractor (to run the generated SQL query)
- Generator (To generate a response in natural language grounded on the result from the SQL query)

1. The information extractor (called data engine in my codebase) was the easiest to figure out. It simply had to connect toa Snowpark session, execute the query and merge each row to a single string.
2. The generator was the next easiest to design. If a prompt is available, CORTEX's AI functions like AI_COMPLETE can generate response in natural language. Cortex already offers very powerful LLMs that I didn't have to use APIs, relieving me of the duty to maintain secrets like API keys. This also meant I incur zero cost in hosting this app. One final advantage was that this makes it possible to contain the entire project within Snowflake. I use claude-sonnet-4-6 LLM for repsonse generation for it's superior reasoning capability.
3. The guardrail was a little tricky at but it is only a very simple generator with very limited vocabulary to respond with. AI_COMPLETE achieves this function too.
4. Text-To-SQL was the trickiest. Not only did the component know to write SQL queries, it also had to know what tables to query from. The former sounded like a GENERATION problem and the latter a RETRIEVAL problem. Text-To-SQL has to be a RAG. From thinking a RAG would be the entire take-home assignment, here I am discovering it is only a single component of it.

I had already familiarized myself with Snowflake offerings and so was fully aware about Cortex Analyst and Cortex Search. My inital thought was to use Cortex Analyst. But I had to reject it for two reasons. One, it requires a clear schema definition of all the tables, columns and relationships between the tables. This thought alone made me want to give up with there being 7500 census attributes. But the overwhelming reason was that using Cortex Analyst felt like cheating. It abstracted the entire project, requiring me to only code the web interface.

Cortex Search on the other hand seemed like a very attractive option. It abstracts some part of the project, making my life easier and letting me focus on the more important problems and at the same time contributed to only a portion of the projet's components. Afterall, it was only one subcomponent of the Text-To-SQL converter.

That left me with a final question: What goes into the knowledge base. The Text-To-SQL converter must know what all the columns mean and what tables they belong to. That's a topic in itself (No, really, scroll down a little)!

### Deciding what goes in the knowledge base

Eventually I came to this conclusion:

- All rows in CBG and REDISTRIBUTING FILE_DESCRIPTION METADATA file must be stored in the knowledge base. Currently, each row is its own chunk. However with 7500 attributes in CBG data alone, this might not be the best approach. The responses look good and with limited time, I chose this to be the current strategy. A possible optimization is listed below [1].
- For other tables like the FIPS code, the table can be joined with the census data whenever needed. Also the philosopohy with the census data was to store column information in the knowledge base. So, for these tables, the columns alone was read, labeled and stored in the knowledge base.

Initially, I made the mistake of joining each FIPS code to the knowledge base. So when a query arrives, it's FIPS code can be retrieved and this information can be used to generate the SQL query. However, if a user query wants statistic from multiple states/counties, the FIPS code alone would dominate the retrieved chunks with little information to create a meaningful SQL query.

An assumption had to be made: 2019 and 2020 census were going to be procedurally very similar. Storing both metadata could be redundant and crowd the retrieved chunks. For this reason, only 2020's column descriptions are stored. However, this strategy could be optimized further [2].

### Choosing the pipeline shape

This is the complete flow from start to finish:

1. User submits a query in natural language
2. The interface validates the query by passing it to the guardrail
3. Valid queries are sent to the Text-To-SQL converter. Crotex Search Service first retrieves the most relevant chunks. Sortex Search takes care of hybrid search and reranking so I don't have to.
4. A complete prompt is built, combining the information the chunks has to offer and the conversation history.
5. The SQL Model generates a SQL query grouned on the prompt and context.
6. The data engine runs the SQL query, creates a string that represents a csv file of the query's result (with header).
7. This data forms the context for the final generator model. A final prompt is built combining the results from the query, the conversation history and few rules.
8. The generator model generates a response in natural language that answers (hopefully) the user's question. This is sent to the guardrail.
9. The guardrail validates this response. If valid, it also gives a confidence score, which can be STRONG, MEDIUM or WEAK. This keeps things transparent and honest with the user.
10. If the guardrail is satisfied with the response, it reaches the user to see. Otherwise, the agent retries from Step 3 for a finite time. If the agent repeatedly fails, a white flag is hoisted, accepting defeat to the user.

### Text-to-SQL: from Cortex Search to SQL

As mentioned, Cortex Search abstracts the chunking, embedding and retrieval part of this component. Cortex Search doesn't allow configuring the topK parameter. But to avoid overloading the prompt with context, this effect is achieved by limiting the number of rows retrieved from Cortex Search. So eventually, only K chunks are added to prompt. Cortex Search uses Snowflake's own Arctic model to create embeddings. Cortex Search will not only store the embeddings but also the table name and column name in independent fields to avoid parsing the column description during query generation.

An assumption is made here: Cortex Search returns chunks in the order of relevance from highest to lowest.

For the LLM, snowflake-arctic was planned to be used for SQL generation. But because it will be deprecated within a week, mistral-large2 was chosen to generate SQL queries for its strong ability ro follow strict formatting rules and its performance in writing code. One stark observation was the prompt quality had an outsized effect. Every ambiguity in the prompt produced a class of SQL errors. 

Examples:

- Not specifying double quotes for digit-prefixed table names → syntax errors
- Not specifying the exact FIPS join pattern → wrong joins
- Not specifying state abbreviations (TX vs Texas) → zero-row results
- Not specifying column quoting for mixed-case ACS names → column-not-found errors

### The FIPS table discovery and its domino effect

Although I had correctly stored FIPS table information in the knowledge base, I assumed FIPS table had a census_block_group column and could be joined with USING (census_block_group). It does not. The table is county-level with five columns. I didn't originally know how to resolve this. There clearly aren't common columns connecting FIPS table to the census tables. So instead, I asked Cortex Code to write me a query to answer "What is the total population of Texas. Do not substitute state_code in query but join with the FIPS data"

This forced three prompt changes at once:

1. The join pattern became LEFT(cbg, 2) = STATE_FIPS AND SUBSTR(cbg, 3, 3) = COUNTY_FIPS
2. State filter changed from full name ('Texas') to abbreviation ('TX')
3. County filter must include the word 'County' ('Travis County', not 'Travis')

Chose to hardcode this join pattern in the prompt rather than describe it in the KB, because the model must follow it on every geographic query without exception. A KB chunk could be absent from a retrieval; a prompt rule cannot.

This resulted in another question: If the prompt has explicit information about how to handle FIPS code, why even store it in the knowledge base. But because it is one row in the knowledge base among 8000+ more and it cannot degrade the retrieved chunks quality, I let it be.

### Guardrail design: from binary to confidence scoring

I started with a binary VALID/INVALID output guardrail. Later, I upgraded to four levels (STRONG / MEDIUM / WEAK / INVALID) because binary was losing useful signal — a response that partially answers a question is different from one that is completely wrong.

Because the guardrail is supposed to be a simple classifier, I chose to use a lightweight LLM for both latency and cost purposes. I settled with claude-haiku-4-5.

Second backtrack: the original output guardrail raised a ValueError directly when the response was invalid. I changed it to a pure classifier that returns a string. All retry logic and error raising was moved to the agent layer, primarily for separation of concerns — a classifier should classify, not decide what to do with the result.

An important observation was that the stateless guardrail scores follow-up questions (e.g. "What about Texas?") as MEDIUM or WEAK even when the answer is correct, because it cannot see the prior context. This is currently a known limitation rather than trying to fix it with a complex stateful guardrail. But this can be optimized further [3].

NOTE: STRONG indicates the response directly answers the question with specific data values. MEDIUM indicates the response is plausible but may reference imprecise columns or aggregations. WEAK indicates the response is technically valid but the guardrail has low confidence it fully addresses the question. I added these to keep the user informed rather than silently serving a uncertain answer

### Retry strategy

My initial plan was to retry with a transformed user query. If the original query didn't do the trick, an LLM can enrich it so that it adds more signal than noise. This was left as a future optimization [4].

Later when I stuck to simply retrying the same user query, only the generator was retried when the output was INVALID. But this was wrong. If the SQL model picked the wrong columns, regenerating the prose will not fix it. Hence, I  changed to retry the full pipeline (SQL generation → data fetch → response generation → output validation) on INVALID. Max 2 retries.
The SQL model is non-deterministic and will sometimes pick better columns on a second attempt.

### Dual conversation history

A single history list would mix SQL and natural language, which is confusing for both models. So, I separated this into sql_history (user questions + SQL) and nl_history (user questions + NL answers). The SQL model gets sql_history so it can write consistent follow-up queries. The generator gets nl_history so it can reference prior results. The Streamlit app owns both lists in session state and passes them on every call.

Also, for Cortex Search, I prepend recent user turns to the search query so that ambiguous follow-ups ("What about Texas?") retrieve the right columns. Here, only user query history is prepended and no LLM generated text is.

### The Streamlit application and UX decisions

I took some conscious UX decisions:

1. I wanted the web interface to be very utilitarian. I didn't want to spend too much time building the web interface, that I risk not finishing my minimum goals for the agent. I felt Streamlit was the right call for a 24-hour assignment. It handles session state, chat UI, secrets management, and one-click public deployment out of the box. Building a React/Flask stack would have taken most of the time budget and added no value to the AI engineering being evaluated.
2. User not only gets the response but also a confidence score produced by the output guardrail. As mentioned before, The output guardrail produces STRONG / MEDIUM / WEAK for every response. Surfacing this to the user is an honest signal,  it tells them how much to trust the answer without hiding the uncertainty behind a confident-sounding response. Hiding the score would make the agent look more polished but less trustworthy. With evaluations not setup, I felt this to be a bare minimum to guarantee reliability.
3. User also sees the generated SQL in an expander. Two reasons. First, a power user or engineer can verify the SQL against the data model and spot if the model picked the wrong table or column. Second, it is a transparency signal — showing the SQL proves the answer is grounded in a real query against real data, not hallucinated. The expander keeps it out of the way for users who do not care. Also, Some may not be masters in coding in SQL but they can be profiecient enough to understand and validate a query (I took this motivation from RLHF - humans are good at criticing, not generating).
4. The stream progress messages every few seconds instead of a spinner. The full pipeline (guardrail → Cortex Search → SQL LLM → Snowflake query →

generator LLM → output guardrail) might sometimes take 15–40 seconds depending on the query complexity. A static spinner for that long creates anxiety — users do not know if the app has frozen. Rotating messages serve two purposes: they confirm the app is alive, and they reduce perceived wait time (not backed by research but a simple self reflection). The wait messages were made to be funny, motivated by excessive Qwen usage.

1. The app currently has a 2-minute hard timeout. Without it a hung Snowflake query or LLM call would block the thread indefinitely. The timeout gives a clean error and frees the UI.

### Technical issues discovered during testing

- snowflake.core.Root: assumed Root was bundled with snowflake-snowpark-python. It is not. Fixed by adding snowflake-core as an explicit dependency.
- Row.**fields**: assumed Snowpark Row objects expose column names via **fields**. They do not. Fixed by reading df.columns from the DataFrame before .collect().
- SELECT SELECT bug: the SQL prompt ends with "SELECT" to prime the model, and the model sometimes echoed it back. Fixed by stripping the leading SELECT from the raw LLM response before prepending a canonical SELECT.
- pyproject.toml vs requirements.txt: Streamlit Community Cloud found the pyproject.toml next to the app file and used it instead of the root requirements.txt. Fixed by putting all dependencies in pyproject.toml.
- Threading: Streamlit is single-threaded. Running the agent synchronously blocked the UI with no feedback. Fixed by running the agent in a daemon thread and polling from the main thread to show progress messages.

---

## 2. What I would improve or do differently with more time

This includes both optimizations and unimplemented features.

The unimplemented features are few:

- The agent is currently unmonitored. There's no evaluation suite monitoring the agent and validating its performance. I plan to evaluate Text-To-SQL using RAGAS as Text-To-SQL is simply a RAG. Guardrails can be evaluated on precision and recall (invalid requests and responses are going to be far fewer than valid ones) and the generator on faithfulness, answer relevance etc (likely also RAGAS).
- Also, overall metrics like latency, LLM cost could be also be tracked and visualized in a dashboard.
- The current app also doesn't track retries. This is important in investigating where the LLM costs are spent
- Few simple features like getting feedback from the user on responses
- The current tests are smoke tests. Would add unit tests for the prompt-building logic, the FIPS join extraction, and the chunk parsing
- Capture few known-good (query, SQL, answer) triplets and alert (me) when a prompt change causes a regression

Some optimizations could be:

[1] Although there are 7500 attributes, mant track the same thing and so can be clubbed into a single chunk (Ex.: "Total population", "Mean population", "Population under age 18" ...). This can reduce retrieval latency.

[2] Instead of completely neglecting 2019 COLUMN_DESCRIPTION METADATA, it can be deduplicated (only store information about columns that do not appear in 2020 or vice versa).

[3] Instead of stateless guardrails, pass the last user turn to the guardrail so follow-up questions are scored fairly.

[4] Instead of retrying with the same query hoping LLMs' non-determinism to somehow fix the issue, the user query can be enriched that includes removing vague words, replacing words to more defined words etc..

[5] This is less important but knowledge base building part is very rigid at the moment. This must be made more flexible in the future.

[6] Identical queries within a session could be answered from cache instead of re-running through the full pipeline

---

## 3. Edge cases and failure modes identified but not fully addressed

- Queries spanning many states: if the user asks for data on too many states, the 10-chunk retrieval limit may not return FIPS chunks for every state. Worked around by moving FIPS join logic into the prompt, but a user asking for aggregated national data could still get incomplete results.
- Ambiguous column selection: ACS has multiple tables for similar topics (B02001 and C02003 both cover race) and so, the model sometimes picks the wrong one. The output guardrail catches the worst cases, but MEDIUM-confidence answers may be using the wrong table.
- Prompt injection: I added sandwich-technique defences (XML tags, post-query reminders) but did not do adversarial red-teaming. A determined attacker could still craft inputs that slip past the guardrail.
- Timeout with partial data: if the SQL runs but returns a huge result set, the generator prompt can exceed the LLM's context window. Currently the data engine caps results at 1000 rows, which helps (1000 is a lot) but is not a complete fix.
- Session expiry: the Snowflake session is cached for the lifetime of the Streamlit server process. A very long-lived deployment will eventually hit session expiry, resulting in a connection error that requires a server reboot.

---

## 4. Testing approach and what I would add

There are four test files:

- test_connection.py  — verifies credentials and basic connectivity. Useful as a pre-flight check before deploying.
- test_kb.py          — queries Cortex Search directly to confirm the knowledge base was built correctly and retrieval returns sensible chunks.
- test_text_to_sql.py — checks that the SQL generation stage produces valid, executable SQL for a handful of known questions.
- test_agent.py       — end-to-end smoke test for the full pipeline, including multi-turn context and the stress test query.

As pointed earlier in things I'd add with more time, the tests print results for manual inspection rather than asserting exact strings. The output guardrail confidence score is the closest thing to an automated quality assertion. This can be upgraded to a complete evaluation and monitoring suite.

## 5. AI Usage Declaration

I used AI for faster iteration and research. Specifically, I used:

- Claude for general research to answer questions like:
  -- What is a Census Block Group? (They are mini neighbourhoods)
  -- Understanding the dataset
  -- Making architectural decisions
- Cursor
  -- Coding
  -- Rewriting my README.md (fix grammar, paraphrase to professional sentences)

Note: This file (REFLECTION.md) is untouched by AI to stay true to its name and be a complete reflection of my thoughts, ideas, mistakes and learnings.