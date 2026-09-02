"""Verify the Groq key works, without spending meaningful quota.

Run:  uv run python scripts/check_groq_key.py

Deliberately does two cheap things and nothing else:

1. lists the models available to this key - a GET that consumes no tokens, so it
   distinguishes "key is invalid" from "quota is exhausted";
2. sends one 5-token completion, the smallest call that proves tool-capable
   chat inference actually works.

Never prints the key. F-21 recorded that a 36-turn evaluation exhausted the free
tier, so anything that checks the key must not itself be expensive.
"""

from __future__ import annotations

import os
import sys

import httpx
from dotenv import load_dotenv

BASE = "https://api.groq.com/openai/v1"
WANTED = ("openai/gpt-oss-20b", "openai/gpt-oss-120b", "llama-3.3-70b-versatile")


def main() -> int:
    load_dotenv()
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        print("FAIL  GROQ_API_KEY is empty in .env")
        return 1
    # Shape check only - never echo the value.
    print(f"key present: {len(key)} chars, starts with {key[:4]!r}"
          f"{'  (expected gsk_)' if not key.startswith('gsk_') else ''}")

    headers = {"Authorization": f"Bearer {key}"}
    try:
        with httpx.Client(base_url=BASE, headers=headers, timeout=30.0) as client:
            models = client.get("/models")
            if models.status_code == 401:
                print("FAIL  401 Unauthorized - the key is not valid")
                return 1
            models.raise_for_status()
            available = {m["id"] for m in models.json().get("data", [])}
            print(f"OK    key authenticates; {len(available)} models available")
            for name in WANTED:
                print(f"        {'yes' if name in available else 'no '}  {name}")

            model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
            if model not in available:
                print(f"WARN  GROQ_MODEL={model} is not in this key's model list")

            chat = client.post("/chat/completions", json={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with the single word: ready"}],
                "max_tokens": 5,
                "temperature": 0,
            })
            if chat.status_code == 429:
                print("WARN  429 rate limited - the key is valid but quota is exhausted right now.")
                print("      Retry-After:", chat.headers.get("retry-after", "not stated"))
                return 2
            chat.raise_for_status()
            body = chat.json()
            reply = body["choices"][0]["message"]["content"].strip()
            used = body.get("usage", {})
            print(f"OK    inference works on {model}: {reply!r} "
                  f"({used.get('total_tokens', '?')} tokens)")
    except httpx.HTTPStatusError as exc:
        print(f"FAIL  HTTP {exc.response.status_code}: {exc.response.text[:160]}")
        return 1
    except httpx.RequestError as exc:
        print(f"FAIL  network error: {exc}")
        return 1

    print("\nready for Phase 8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
