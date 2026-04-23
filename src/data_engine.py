"""
Data engine — executes a SQL query and returns results as a plain string.

Public interface:
    run_query(sql, session) -> str
"""
from snowflake.snowpark import Session
from src.session.snowflake_session import ensure_session_context


def run_query(sql: str, session: Session) -> str:
    """Execute sql and return results as a CSV-style string for the generator.

    Returns:
        A newline-separated string of comma-separated rows (header + data).
        "No data found." if the query returns zero rows.

    Raises nothing — all exceptions are caught and returned as a user-friendly
    message so the caller never sees raw Snowflake error codes or stack traces.
    """
    try:
        ensure_session_context(session, use_kb=False)
        rows = session.sql(sql).collect()

        if not rows:
            return "No data found."

        # Header row from column names, then one line per data row
        headers = ",".join(rows[0].__fields__)
        data    = "\n".join(",".join(str(v) for v in row) for row in rows)
        return f"{headers}\n{data}"

    except Exception:
        return "I'm having trouble retrieving the data. The query may reference unavailable columns or tables."
