"""
US Census Data Chat Agent — Streamlit UI

Maintains two parallel history lists per session:
  sql_history — user questions + generated SQL  (fed to the SQL model)
  nl_history  — user questions + NL answers     (fed to the generator)
"""
import os
import random
import sys
import threading
import time

# Ensure the repo root is on sys.path regardless of working directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import streamlit as st
from src.agent import run as agent_run
from src.session.snowflake_session import get_session

# Messages shown after 10 s, in shuffled order (no repeats until all are shown)
_PROGRESS_MESSAGES = [
    "Waking up 330 million Americans to count them…",
    "Bribing the SQL optimizer with coffee…",
    "Asking the Census Bureau very nicely…",
    "Teaching a snowflake to read demographic data…",
    "Consulting with the ghost of the 2020 census taker…",
    "Untangling 12-digit FIPS codes by hand…",
    "Negotiating with the data warehouse union…",
    "Yes, Texas really is that big. Still counting…",
    "This would've taken weeks in 1790. You're welcome.",
    "Snowflake is thinking very hard right now…",
    "The LLM is having an existential moment. Give it a sec.",
    "99 problems but a SQL syntax error ain't one (anymore)…",
    "Summoning the spirit of every census worker ever…",
    "Attempting to fit California into RAM…",
    "The query is fine. The data is just dramatically pausing.",
    "Converting population into vibes. Almost done.",
    "Somewhere, a government statistician is smiling.",
    "If this were a paper form, you'd still be on page 2.",
    "Fun fact: the 1890 census data was destroyed in a fire. Ours is fine. Probably.",
    "Teaching the AI what a 'county' is for the 47th time…",
    "Heroically joining two very large tables…",
    "Running at the speed of democracy…",
    "Your patience is noted and deeply appreciated by the data warehouse.",
    "Somewhere in Snowflake, a tiny elf is typing very fast.",
]
_SHUFFLED_MESSAGES = random.sample(_PROGRESS_MESSAGES, len(_PROGRESS_MESSAGES))

_FIRST_MSG_DELAY_S = 10   # seconds before first message
_MSG_INTERVAL_S    = 8    # seconds between messages

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="US Census Chat Agent",
    page_icon="🏛️",
    layout="centered",
)

# ── Snowflake session (one per server process) ────────────────────────────────
@st.cache_resource(show_spinner="Connecting to Snowflake…")
def _get_session():
    return get_session()

# ── Session state ─────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []       # rendered chat bubbles
if "sql_history" not in st.session_state:
    st.session_state.sql_history = []    # {role, content} — content is SQL
if "nl_history" not in st.session_state:
    st.session_state.nl_history = []     # {role, content} — content is NL answer

# ── Helpers ───────────────────────────────────────────────────────────────────
_CONFIDENCE_STYLE = {
    "STRONG": ("🟢", "green",  "High confidence — response directly answers the question"),
    "MEDIUM": ("🟡", "#b8860b", "Medium confidence — response is mostly complete"),
    "WEAK":   ("🟠", "darkorange", "Low confidence — data may be partial or approximate"),
}

def _render_confidence(confidence: str) -> None:
    icon, color, tooltip = _CONFIDENCE_STYLE.get(
        confidence, ("⚪", "gray", "Unknown confidence")
    )
    st.markdown(
        f"<span title='{tooltip}' style='color:{color}; font-size:0.78em; "
        f"font-weight:600'>{icon} {confidence}</span>",
        unsafe_allow_html=True,
    )

def _render_assistant_msg(msg: dict) -> None:
    st.markdown(msg["content"])
    if msg.get("sql"):
        with st.expander("View SQL query", expanded=False):
            st.code(msg["sql"], language="sql")
    if msg.get("confidence"):
        _render_confidence(msg["confidence"])

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🏛️ Census Chat Agent")
    st.markdown(
        "Ask natural-language questions about US Census data — demographics, "
        "housing, income, education, geography, and foot-traffic patterns "
        "at the Census Block Group level."
    )
    st.markdown("---")
    st.markdown("**Data sources**")
    st.markdown(
        "- 2020 ACS 5-Year Estimates (CBG level)\n"
        "- 2020 Decennial Redistricting Data\n"
        "- 2019 SafeGraph Foot-Traffic Patterns\n"
        "- 2020 CBG Geometries & FIPS Metadata"
    )
    st.markdown("---")
    if st.button("🗑️ Clear conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.sql_history = []
        st.session_state.nl_history = []
        st.rerun()

# ── Main header ───────────────────────────────────────────────────────────────
st.title("US Census Data Chat Agent")
st.caption(
    "Powered by Snowflake Cortex · Ask about demographics, housing, income, "
    "education, and more."
)

# ── Render existing messages ──────────────────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            _render_assistant_msg(msg)
        else:
            st.markdown(msg["content"])

# ── Chat input ────────────────────────────────────────────────────────────────
if prompt := st.chat_input("Ask about US Census data…"):

    # Show user bubble immediately
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Run pipeline
    with st.chat_message("assistant"):
        status = st.empty()   # single placeholder reused for all progress messages

        # Resolve everything that touches Streamlit state in the MAIN thread
        # before handing off to the background thread. st.cache_resource and
        # st.session_state are not safe to access from a non-main thread.
        session  = _get_session()
        sql_hist = list(st.session_state.sql_history)
        nl_hist  = list(st.session_state.nl_history)

        # Run the agent in a background thread so the main thread can update the UI
        result_box: dict = {}
        done_event = threading.Event()

        def _run_agent() -> None:
            try:
                result_box["result"] = agent_run(
                    query=prompt,
                    session=session,
                    sql_history=sql_hist,
                    nl_history=nl_hist,
                )
            except Exception as exc:
                result_box["error"] = exc
            finally:
                done_event.set()

        threading.Thread(target=_run_agent, daemon=True).start()

        # Poll in the main thread; show witty messages starting at 10 s
        start   = time.monotonic()
        msg_idx = 0
        while not done_event.wait(timeout=1.0):
            elapsed = time.monotonic() - start
            if elapsed >= _FIRST_MSG_DELAY_S + msg_idx * _MSG_INTERVAL_S:
                status.markdown(
                    f"*{_SHUFFLED_MESSAGES[msg_idx % len(_SHUFFLED_MESSAGES)]}*"
                )
                msg_idx += 1

        status.empty()   # clear the last progress message before rendering result

        # Handle outcome
        if "error" in result_box:
            exc = result_box["error"]
            if isinstance(exc, ValueError):
                msg_text = str(exc)
                st.warning(msg_text)
                st.session_state.messages.append({"role": "assistant", "content": f"⚠️ {msg_text}"})
            else:
                print(f"  [app] Unhandled exception: {exc}")
                msg_text = "Something went wrong connecting to the data source. Please try again."
                st.error(msg_text)
                st.session_state.messages.append({"role": "assistant", "content": f"❌ {msg_text}"})
                st.session_state.messages.pop(-2)   # remove orphaned user message
        else:
            result     = result_box["result"]
            answer     = result["answer"]
            sql        = result["sql"]
            confidence = result["confidence"]

            _render_assistant_msg({"content": answer, "sql": sql, "confidence": confidence})

            # Persist message and update both history lists
            st.session_state.messages.append({
                "role":       "assistant",
                "content":    answer,
                "sql":        sql,
                "confidence": confidence,
            })
            st.session_state.sql_history.extend([
                {"role": "user",      "content": prompt},
                {"role": "assistant", "content": sql},
            ])
            st.session_state.nl_history.extend([
                {"role": "user",      "content": prompt},
                {"role": "assistant", "content": answer},
            ])
