"""US Census Data Chat Agent — Streamlit UI.

LangGraph owns the pipeline. This app owns the transcript: prior Human/AI
turns go back into `run()` so follow-ups work without a checkpointer.
"""
import os
import random
import sys
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import streamlit as st
from langchain.messages import AIMessage, HumanMessage

from src.chat_agent.graph import run as agent_run
from src.session.snowflake_session import get_session

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

_FIRST_MSG_DELAY_S = 10
_MSG_INTERVAL_S = 6
_TIMEOUT_S = 120

st.set_page_config(
    page_title="US Census Chat Agent",
    page_icon="🏛️",
    layout="centered",
)

if "messages" not in st.session_state:
    st.session_state.messages = []

_CONFIDENCE_STYLE = {
    "HIGH": ("🟢", "green", "High confidence — response directly answers the question"),
    "MEDIUM": ("🟡", "#b8860b", "Medium confidence — response is mostly complete"),
    "LOW": ("🟠", "darkorange", "Low confidence — data may be partial or approximate"),
    "INVALID": ("🔴", "crimson", "Invalid — response does not answer the question"),
}


def _history_messages(stored: list[dict]) -> list:
    history = []
    for msg in stored:
        if msg["role"] == "user":
            history.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            history.append(AIMessage(content=msg["content"]))
    return history


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
    if msg.get("rejected"):
        st.warning(msg["content"])
        return
    st.markdown(msg["content"])
    if msg.get("sql"):
        with st.expander("View SQL query", expanded=False):
            st.code(msg["sql"], language="sql")
    if msg.get("confidence"):
        _render_confidence(msg["confidence"])


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
        st.rerun()

st.title("US Census Data Chat Agent")
st.caption(
    "Powered by Snowflake Cortex · Ask about demographics, housing, income, "
    "education, and more."
)

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            _render_assistant_msg(msg)
        else:
            st.markdown(msg["content"])

if prompt := st.chat_input("Ask about US Census data…"):
    with st.chat_message("user"):
        st.markdown(prompt)

    history = _history_messages(st.session_state.messages)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        status = st.empty()

        session = get_session()

        result_box: dict = {}
        done_event = threading.Event()

        def _run_agent() -> None:
            try:
                result_box["result"] = agent_run(
                    query=prompt,
                    session=session,
                    history=history,
                )
            except Exception as exc:
                result_box["error"] = exc
            finally:
                done_event.set()

        threading.Thread(target=_run_agent, daemon=True).start()

        start = time.monotonic()
        msg_idx = 0
        timed_out = False
        while not done_event.wait(timeout=1.0):
            elapsed = time.monotonic() - start
            if elapsed >= _TIMEOUT_S:
                timed_out = True
                break
            if elapsed >= _FIRST_MSG_DELAY_S + msg_idx * _MSG_INTERVAL_S:
                status.markdown(
                    f"*{_SHUFFLED_MESSAGES[msg_idx % len(_SHUFFLED_MESSAGES)]}*"
                )
                msg_idx += 1

        status.empty()

        if timed_out:
            msg_text = (
                "The query timed out after 2 minutes. Try asking a more specific "
                "question or narrowing the geography."
            )
            st.warning(msg_text)
            st.session_state.messages.append(
                {"role": "assistant", "content": msg_text, "rejected": True}
            )
        elif "error" in result_box:
            exc = result_box["error"]
            print(f"  [app] Unhandled exception: {exc}")
            msg_text = "Something went wrong connecting to the data source. Please try again."
            st.error(msg_text)
            st.session_state.messages.pop()
        else:
            result = result_box["result"]
            stored = {
                "role": "assistant",
                "content": result["answer"],
                "sql": result["sql"],
                "confidence": result["confidence"],
                "rejected": result["rejected"],
            }
            _render_assistant_msg(stored)
            st.session_state.messages.append(stored)
