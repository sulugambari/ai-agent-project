"""Find which free OpenRouter models this key can ACTUALLY run an agent on.

The catalogue is not the answer. A model can carry the `:free` suffix, declare
`tools` in `supported_parameters`, and still return **402 Payment Required** on
this key - which is exactly what happened after picking one from the listing. So
each candidate is probed for real, and probed for the thing that matters:
whether it emits a **tool call**, not merely whether it replies.

Same lesson as F-23, where a model the plan nominated turned out not to exist on
the tier: verify availability at the moment you need it, never infer it.

Cost is kept low deliberately - one tiny tool-call request per model.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

BASE = "https://openrouter.ai/api/v1"

# A trivial tool. If a model cannot call this, it cannot run the agent.
PROBE_TOOL = [{
    "type": "function",
    "function": {
        "name": "get_release_status",
        "description": "Return the status of a named project.",
        "parameters": {
            "type": "object",
            "properties": {"project": {"type": "string", "description": "Project name"}},
            "required": ["project"],
        },
    },
}]
PROBE_MESSAGES = [{"role": "user", "content": "Use the tool to get the status of project Atlas."}]


def main() -> int:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        print("OPENROUTER_API_KEY is empty in .env")
        return 1

    headers = {"Authorization": f"Bearer {key}",
               "X-Title": os.getenv("OPENROUTER_APP_TITLE", "Northstar Release Coordinator")}
    with httpx.Client(base_url=BASE, headers=headers, timeout=90.0) as client:
        catalogue = client.get("/models").json().get("data", [])
        candidates = sorted(
            m["id"] for m in catalogue
            if m["id"].endswith(":free")
            and ("tools" in (m.get("supported_parameters") or [])
                 or "tool_choice" in (m.get("supported_parameters") or []))
        )
        print(f"{len(candidates)} free model(s) declare tool calling. Probing each for real.\n")
        print(f"{'model':<52}{'result':<26}{'tool call?':<12}served by")
        print("-" * 104)

        usable: list[tuple[str, str]] = []
        for model in candidates:
            try:
                response = client.post("/chat/completions", json={
                    "model": model, "messages": PROBE_MESSAGES, "tools": PROBE_TOOL,
                    # generous: gpt-oss-class models spend tokens reasoning before
                    # emitting anything (F-22), and a tight cap returns empty content
                    "max_tokens": 256, "temperature": 0,
                })
            except httpx.RequestError as exc:
                print(f"{model:<52}{'network error':<26}{'-':<12}{type(exc).__name__}")
                continue

            if response.status_code != 200:
                try:
                    reason = response.json().get("error", {}).get("message", "")[:22]
                except Exception:
                    reason = response.text[:22]
                print(f"{model:<52}{f'HTTP {response.status_code} {reason}':<26}{'-':<12}")
                continue

            body = response.json()
            choice = (body.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            calls = message.get("tool_calls") or []
            served = body.get("provider") or "?"
            called = bool(calls) and calls[0].get("function", {}).get("name") == "get_release_status"
            print(f"{model:<52}{'ok':<26}{('YES' if called else 'no'):<12}{served}")
            if called:
                usable.append((model, served))

        print("\n" + "=" * 104)
        if not usable:
            print("No free model on this key both responded and emitted a tool call.")
            print("The agent cannot run on OpenRouter's free tier; keep Groq as the provider.")
            return 1
        print(f"{len(usable)} model(s) usable for this agent:\n")
        for model, served in usable:
            print(f"  {model:<52} served by {served}")
        print(f"\nsuggested .env line:\n  OPENROUTER_MODEL={usable[0][0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
