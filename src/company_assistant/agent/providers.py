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

#: Chosen by running the REAL workload, not by reading the catalogue.
#:
#: Of 424 models, 17 are free and declare tool calling. Eleven of those pass a
#: small tool-call probe. But a 256-token probe says nothing about this agent: a
#: turn here is roughly 6,100 tokens because the system prompt, five tool schemas
#: and the tool output all travel in context. Probed small, several models
#: answered; given the real workload the same models returned
#: `PaymentRequiredResponseError` (402) or `NotFoundResponseError` (F-30).
#:
#: So `:free` in the model id, `tools` in `supported_parameters`, and a successful
#: small probe are all necessary and none of them are sufficient. Verify at the
#: moment and the size you actually need, never infer.
#:
#: **Why this is nemotron and not laguna.** F-32 selected `poolside/laguna-xs-2.1`
#: on the case that discriminated: asked for a restricted record, nemotron ANSWERED
#: at length while laguna refused. That reasoning was correct for the design at the
#: time, and **D-010 removed the premise.** The permission refusal no longer comes
#: from the model at all - a categorical `Deny` in the access matrix is enforced by
#: the tool before any search runs, and `forbidden` is derived from that tool
#: outcome rather than from prose. A model's disposition to refuse is therefore no
#: longer load-bearing, which is the whole point of moving a control from
#: behavioural to structural. Nemotron already answered the flagship question 3/3
#: (F-32), and the team selected it on cost.
#:
#: **UNVERIFIED at the time of writing.** `OPENROUTER_API_KEY` returns 401, so the
#: claim above - that the boundary holds on a model that would not have refused on
#: its own - has not been measured on this model since D-010 landed. It is a
#: prediction about the design, and predictions in this project have been wrong
#: before. Close it with one command as soon as a working key exists:
#:
#:     uv run python scripts/verify_behaviours.py
#:
#: If the permission case fails there, the structural control is not doing what
#: D-010 claims and that is a finding about the DESIGN, not a reason to quietly
#: switch models back.
OPENROUTER_DEFAULT_MODEL = "nvidia/nemotron-3.5-lightning:free"

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


#: Which environment variable holds the key for each provider. One mapping, so a
#: caller asking "can the agent run?" cannot answer it against the wrong provider.
API_KEY_VARIABLE: dict[Provider, str] = {
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def credentials_present(provider: Provider | None = None) -> tuple[bool, str]:
    """Whether the ACTIVE provider has a key, and which variable that is.

    `ServiceStatus.agent_available` previously read `GROQ_API_KEY` directly,
    whatever `LLM_PROVIDER` said. On an OpenRouter-only setup the interface would
    therefore announce "GROQ_API_KEY is not set, so only the deterministic
    baseline can answer" and pre-select the baseline toggle - while the agent was
    perfectly able to run. A disclosure wrong by construction, and the same family
    as F-15.2 and F-25: a status that asserts a configuration instead of asking
    for it. The variable name is returned alongside so the interface can name the
    one the operator actually has to set.
    """
    variable = API_KEY_VARIABLE[provider or active_provider()]
    return bool((os.getenv(variable) or "").strip()), variable


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
