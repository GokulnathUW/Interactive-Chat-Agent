"""Tools for the collect_data subgraph."""

import os

from langchain.tools import ToolRuntime, tool
from snowflake.core import Root

from src.context import AgentContext
from src.session.snowflake_session import SNOWFLAKE_KB_DATABASE, SNOWFLAKE_KB_SCHEMA

CORTEX_SEARCH_SERVICE = os.getenv("CORTEX_SEARCH_SERVICE", "CBG_FIELD_SEARCH")
_SEARCH_COLUMNS = ["CHUNK_TEXT", "COLUMN_NAME", "SNOWFLAKE_TABLE", "DATASET", "SOURCE_TYPE"]
_TOP_K = 10


@tool
def retrieve_context(search_query: str, runtime: ToolRuntime[AgentContext]) -> str:
    """Search the Census knowledge base for relevant table and column descriptions.

    Pass a self-contained query that includes the topic and any geography.
    Call again with a refined query if results are missing columns you need.
    """
    service = (
        Root(runtime.context.session)
        .databases[SNOWFLAKE_KB_DATABASE]
        .schemas[SNOWFLAKE_KB_SCHEMA]
        .cortex_search_services[CORTEX_SEARCH_SERVICE]
    )
    results = service.search(
        query=search_query,
        columns=_SEARCH_COLUMNS,
        limit=_TOP_K,
    ).results
    if not results:
        return "No matching knowledge-base chunks."
    return "\n".join(
        chunk["CHUNK_TEXT"] for chunk in results if chunk.get("CHUNK_TEXT")
    )
