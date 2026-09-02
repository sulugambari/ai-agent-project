"""One bounded, tool-using agent - independent of Streamlit and FastAPI."""

from company_assistant.agent.prompt import SYSTEM_PROMPT
from company_assistant.agent.runner import (DEFAULT_MODEL, MAX_TOOL_CALLS, TEMPERATURE,
                                            TurnRecord, ask, build_agent)

__all__ = [
    "DEFAULT_MODEL",
    "MAX_TOOL_CALLS",
    "SYSTEM_PROMPT",
    "TEMPERATURE",
    "TurnRecord",
    "ask",
    "build_agent",
]
