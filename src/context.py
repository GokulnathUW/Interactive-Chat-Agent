"""Invoke-time config shared by chat_agent and collect_data."""

from dataclasses import dataclass

from snowflake.snowpark import Session


@dataclass
class AgentContext:
    session: Session
