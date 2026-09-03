"""Verify the OpenRouter key and find a model that can actually run this agent.

    uv run python scripts/check_openrouter_key.py

Checks three things in increasing cost, and stops at the first failure:

1. the key authenticates, and what credit/limits it reports (no tokens spent);
2. which available models declare **tool calling** - this agent cannot work
   without it, and many free models do not have it, so it is worth knowing
   before a run rather than after 18 failed turns;
3. one tiny completion, to prove inference works.

Never prints the key. Free tiers are rate limited too, so a key check must not
itself be expensive - F-27 measured one Groq turn at roughly 6,100 tokens
against an 8,000-per-minute ceiling.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

BASE = "https://openrouter.ai/api/v1"


def main() -> int:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        print("FAIL  OPENROUTER_API_KEY is empty in .env")
        return 1
    print(f"key present: {len(key)} chars, starts with {key[:9]!r}"
          f"{'' if key.startswith('sk-or-v1-') else '  (expected sk-or-v1-)'}")

    headers = {
        "Authorization": f"Bearer {key}",
        "X-Title": os.getenv("OPENROUTER_APP_TITLE", "Northstar Release Coordinator"),
    }
    try:
        with httpx.Client(base_url=BASE, headers=headers, timeout=45.0) as client:
            auth = client.get("/auth/key")
            if auth.status_code in (401, 403):
                print(f"FAIL  {auth.status_code} - the key is not valid")
                return 1
            if auth.status_code == 200:
                data = auth.json().get("data", {})
                print(f"OK    key authenticates")
                for field in ("label", "usage", "limit", "limit_remaining", "is_free_tier",
                              "rate_limit"):
                    if field in data:
                        print(f"        {field}: {data[field]}")

            models = client.get("/models")
            models.raise_for_status()
            catalogue = models.json().get("data", [])
            print(f"OK    {len(catalogue)} model(s) listed")

            def supports_tools(m: dict) -> bool:
                params = m.get("supported_parameters") or []
                return "tools" in params or "tool_choice" in params

            free_tool_models = sorted(
                (m["id"] for m in catalogue
                 if m["id"].endswith(":free") and supports_tools(m)),
            )
            print(f"\n  FREE models that declare tool calling: {len(free_tool_models)}")
            for name in free_tool_models[:12]:
                print(f"        {name}")
            if not free_tool_models:
                print("        none - this agent needs tool calling, so a paid model")
                print("        would be required, or Groq stays the provider")

            chosen = os.getenv("OPENROUTER_MODEL", "").strip() or (
                free_tool_models[0] if free_tool_models else "")
            if not chosen:
                print("\nFAIL  no usable model found")
                return 1
            print(f"\n  testing: {chosen}")

            chat = client.post("/chat/completions", json={
                "model": chosen,
                "messages": [{"role": "user", "content": "Reply with the single word: ready"}],
                "max_tokens": 64, "temperature": 0,
            })
            if chat.status_code == 429:
                print("WARN  429 rate limited - the key is valid but throttled right now")
                return 2
            chat.raise_for_status()
            body = chat.json()
            reply = (body["choices"][0]["message"].get("content") or "").strip()
            usage = body.get("usage", {})
            served = body.get("provider") or body.get("model")
            print(f"OK    inference works: {reply!r} ({usage.get('total_tokens', '?')} tokens)")
            print(f"        served by: {served}   <- 05 requires recording the underlying provider")
            print(f"\nsuggested .env line:\n  OPENROUTER_MODEL={chosen}")
    except httpx.HTTPStatusError as exc:
        print(f"FAIL  HTTP {exc.response.status_code}: {exc.response.text[:200]}")
        return 1
    except httpx.RequestError as exc:
        print(f"FAIL  network error: {exc}")
        return 1
    print("\nready - tell Claude and it will wire the provider boundary")
    return 0


if __name__ == "__main__":
    sys.exit(main())
