"""The model boundary: one place that decides which provider serves a turn.

`05-evaluation-and-release.md` asks for the chat model to sit behind "one small
application boundary" so a provider can be compared with prompts, tools,
retrieval results, parameters and evaluation cases all held fixed. This is that
boundary, and it is the only file that imports a provider SDK.

Groq is retained rather than replaced (`AGENTS.md` keeps it as the core path).
OpenRouter is the sanctioned optional extension, and because OpenRouter is a
**gateway** rather than a model host, `05` requires recording both the model
selected *and* the provider that actually served it - so `describe()` returns
both.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

Provider = Literal["groq", "openrouter"]

GROQ_DEFAULT_MODEL = "openai/gpt-oss-20b"

#: Chosen from the live model list on 3 September: free, declares tool calling,
#: and general-purpose rather than code-specialised. The agent has to route among
#: five tools, reconcile conflicting sources and abstain, so a code model is the
#: wrong shape for it even when it is the first free option alphabetically.
#: Provisional until a real agent turn confirms tool routing works - which is the
#: D-007 bake-off we could not run on Groq's free tier.
OPENROUTER_DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"

#: Deterministic sampling, so run-to-run variation is the model's own and not
#: ours. F-17 showed this is necessary but not sufficient: the agent still varied
#: at temperature 0.
TEMPERATURE = 0.0


@dataclass(frozen=True, slots=True)
class ModelChoice:
    """What was asked for, and what to report about it."""

    provider: Provider
    model: str

    def describe(self) -> str:
        return f"{self.model} via {self.provider}"


def active_provider() -> Provider:
    value = (os.getenv("LLM_PROVIDER") or "groq").strip().lower()
    if value not in ("groq", "openrouter"):
        raise ValueError(
            f"LLM_PROVIDER must be 'groq' or 'openrouter', got {value!r}. "
            "Refusing to guess, because silently falling back to another provider "
            "would make an evaluation compare two systems while reporting one."
        )
    return value  # type: ignore[return-value]


def resolve(model: str | None = None, provider: Provider | None = None) -> ModelChoice:
    """Decide provider and model without constructing anything."""
    chosen = provider or active_provider()
    if chosen == "openrouter":
        return ModelChoice("openrouter",
                           model or os.getenv("OPENROUTER_MODEL") or OPENROUTER_DEFAULT_MODEL)
    return ModelChoice("groq", model or os.getenv("GROQ_MODEL") or GROQ_DEFAULT_MODEL)


def build_chat_model(model: str | None = None, provider: Provider | None = None) -> tuple[Any, ModelChoice]:
    """Return a LangChain chat model plus the choice it represents.

    Imports are local so that using one provider does not require the other's
    SDK to be installed, and so a missing key fails with a message that names the
    variable rather than a stack trace from inside an SDK.
    """
    choice = resolve(model, provider)

    if choice.provider == "openrouter":
        if not (os.getenv("OPENROUTER_API_KEY") or "").strip():
            raise RuntimeError(
                "LLM_PROVIDER=openrouter but OPENROUTER_API_KEY is empty in .env"
            )
        from langchain_openrouter import ChatOpenRouter

        return (
            ChatOpenRouter(
                model=choice.model,
                temperature=TEMPERATURE,
                # Attribution in the OpenRouter dashboard, so usage from this
                # project is separable from anything else on the key.
                default_headers={
                    "X-Title": os.getenv("OPENROUTER_APP_TITLE",
                                         "Northstar Release Coordinator"),
                },
            ),
            choice,
        )

    if not (os.getenv("GROQ_API_KEY") or "").strip():
        raise RuntimeError("LLM_PROVIDER=groq but GROQ_API_KEY is empty in .env")
    from langchain_groq import ChatGroq

    return ChatGroq(model=choice.model, temperature=TEMPERATURE), choice
