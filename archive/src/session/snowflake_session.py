import os
from dotenv import load_dotenv
from snowflake.snowpark import Session

load_dotenv()

# Census source — the Snowflake Marketplace dataset (read queries run here)
SNOWFLAKE_DATA_DATABASE = os.getenv("SNOWFLAKE_DATA_DATABASE", "")
SNOWFLAKE_DATA_SCHEMA   = os.getenv("SNOWFLAKE_DATA_SCHEMA", "")

# Knowledge base — owns the Cortex Search service and staging tables
SNOWFLAKE_KB_DATABASE = os.getenv("SNOWFLAKE_KB_DATABASE", "")
SNOWFLAKE_KB_SCHEMA   = os.getenv("SNOWFLAKE_KB_SCHEMA", "")


def get_snowflake_session_parameters() -> dict:
    """Return connection parameters dict from environment variables.

    Uses the knowledge base database/schema as the session default so the
    Cortex Search service and staging tables are in scope on connect.
    """
    params = {
        "account":   os.getenv("SNOWFLAKE_ACCOUNT"),
        "user":      os.getenv("SNOWFLAKE_USER"),
        "password":  os.getenv("SNOWFLAKE_PASSWORD"),
        "role":      os.getenv("SNOWFLAKE_ROLE"),
        "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
        "database":  SNOWFLAKE_KB_DATABASE,
        "schema":    SNOWFLAKE_KB_SCHEMA,
    }
    missing = [k for k, v in params.items() if not v]
    if missing:
        raise EnvironmentError(
            f"Missing required Snowflake environment variables: {', '.join(missing)}"
        )
    return params


def get_session() -> Session:
    """Create and return a Snowpark session using environment credentials."""
    try:
        params = get_snowflake_session_parameters()
        return Session.builder.configs(params).create()
    except Exception as e:
        raise ConnectionError(
            f"I'm having trouble connecting to Snowflake: {e}"
        ) from e


def ensure_session_context(session: Session, use_kb: bool = True) -> None:
    """Set the active database and schema on an existing session.

    Pass use_kb=False to switch context to the census data source instead,
    e.g. when running SQL queries against the marketplace tables.
    """
    db     = SNOWFLAKE_KB_DATABASE   if use_kb else SNOWFLAKE_DATA_DATABASE
    schema = SNOWFLAKE_KB_SCHEMA     if use_kb else SNOWFLAKE_DATA_SCHEMA
    session.sql(f"USE DATABASE {quotes_identifier(db)}").collect()
    session.sql(f"USE SCHEMA {quotes_identifier(schema)}").collect()


def quotes_identifier(n: str) -> str:
    """Wrap an identifier in double-quotes, escaping any internal double-quotes."""
    return '"' + n.replace('"', '""') + '"'


def quotes_literal(s: str) -> str:
    """Wrap a value in single-quotes, escaping any internal single-quotes."""
    return "'" + s.replace("'", "''") + "'"


