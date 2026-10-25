"""Deterministic collect_data tests. No LLM or Snowflake."""

from langchain.messages import AIMessage, HumanMessage
from langgraph.graph import END

from src.collect_data.dql import dql_error, last_ai_text, validate_query
from src.collect_data.routing import after_run, after_validate


def test_dql_select_ok():
    assert dql_error('SELECT 1 FROM "2020_CBG_B01"') is None


def test_dql_with_cte_ok():
    sql = "WITH x AS (SELECT 1 AS n) SELECT n FROM x"
    assert dql_error(sql) is None


def test_dql_rejects_drop():
    assert dql_error("DROP TABLE users") is not None


def test_dql_rejects_delete():
    assert dql_error("DELETE FROM users") is not None


def test_dql_rejects_insert():
    assert dql_error("INSERT INTO users VALUES (1)") is not None


def test_dql_rejects_two_statements():
    assert dql_error("SELECT 1; DROP TABLE users") is not None


def test_dql_rejects_empty():
    assert dql_error("") == "No SQL was produced."


def test_dql_unsupported_query():
    assert dql_error("UNSUPPORTED_QUERY") == "UNSUPPORTED_QUERY"


def test_last_ai_text_strips_fence_and_semicolon():
    state = {
        "messages": [
            AIMessage(content="```sql\nSELECT 1;\n```"),
        ]
    }
    assert last_ai_text(state) == "SELECT 1"


def test_validate_query_sets_sql():
    state = {"messages": [AIMessage(content="SELECT 1")]}
    update = validate_query(state)
    assert update["sql"] == "SELECT 1"
    assert update["error"] == ""


def test_validate_query_clears_sql_on_dml():
    state = {"messages": [AIMessage(content="DROP TABLE users")]}
    update = validate_query(state)
    assert update["sql"] == ""
    assert update["error"]
    assert isinstance(update["messages"][0], HumanMessage)


def test_after_validate_routes():
    assert after_validate({"error": ""}) == "run_query"
    assert after_validate({"error": "UNSUPPORTED_QUERY"}) == END
    assert after_validate({"error": "Only DQL is allowed."}) == "sql_agent"


def test_after_run_routes():
    assert after_run({"error": ""}) == END
    assert after_run({"error": "SQL compilation error"}) == "sql_agent"
