"""Regenerate the committed session transcript, with credentials redacted.

Replaces the ad-hoc inline script used until now. The transcript is refreshed on
every handover update and the repository is public, so redaction cannot depend on
remembering: it runs here, and `assert_clean` gates the write. A key was pasted
into the chat once, which is exactly the failure this guards.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from redact import assert_clean, redact  # noqa: E402

SESSION_DIR = Path.home() / ".claude/projects/-home-sulu-Neuefisch-wsl-ai-agent-project"
READABLE = Path("docs/CHAT_HISTORY.md")
RAW = Path("docs/chat-history-raw.jsonl")


def blocks(message: dict) -> list[dict]:
    content = message.get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return content if isinstance(content, list) else []


def clip(value: object, limit: int) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[:limit] + " …"


def main() -> int:
    logs = sorted(SESSION_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    if not logs:
        print("no session log found")
        return 1
    src = logs[-1]

    lines = [
        "# Claude Code — Session Transcript", "",
        "Verbatim record of the working session behind this project, for handover",
        "continuity.", "",
        "**How to read this.** Human turns and Claude's replies are reproduced in full.",
        "Tool calls are summarised to one line each; full payloads are in",
        "`docs/chat-history-raw.jsonl`. Claude's internal reasoning blocks are not",
        "included; they were never part of the visible conversation.", "",
        "**Credentials are redacted** by `scripts/redact.py` before this file is written.",
        "The repository is public and this file is committed, so redaction is a gate",
        "rather than a habit.", "",
        "Curated conclusions live in `HANDOVER.md` — read that first.", "", "---", "",
    ]
    turn, pending = 0, []

    def flush() -> None:
        nonlocal pending
        if pending:
            lines.append(f"<details><summary>Tool calls ({len(pending)})</summary>\n")
            lines.extend(f"- `{item}`" for item in pending)
            lines.append("\n</details>\n")
            pending = []

    for raw_line in src.open(encoding="utf-8", errors="replace"):
        try:
            entry = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if entry.get("type") not in {"user", "assistant"}:
            continue
        message = entry.get("message") or {}
        if message.get("role") == "user":
            text = "\n".join(b.get("text", "") for b in blocks(message)
                             if b.get("type") == "text").strip()
            for pattern in (r"<system-reminder>.*?</system-reminder>",
                            r"<ide_(opened_file|selection)>.*?</ide_\1>",
                            r"\[SYSTEM NOTIFICATION.*?</task-notification>"):
                text = re.sub(pattern, "", text, flags=re.S).strip()
            if not text:
                continue
            flush()
            turn += 1
            lines += [f"## Turn {turn} · Sulu", "", text, ""]
        else:
            for block in blocks(message):
                if block.get("type") == "text" and block.get("text", "").strip():
                    flush()
                    lines += ["### Claude", "", block["text"].strip(), ""]
                elif block.get("type") == "tool_use":
                    args = block.get("input") or {}
                    detail = (args.get("description") or args.get("file_path")
                              or args.get("command") or args.get("prompt") or "")
                    pending.append(f"{block.get('name')}: {clip(detail, 110)}")
    flush()

    readable, counts = redact("\n".join(lines) + "\n")
    assert_clean(readable, "docs/CHAT_HISTORY.md")
    READABLE.write_text(readable, encoding="utf-8")

    raw, raw_counts = redact(src.read_text(encoding="utf-8", errors="replace"))
    assert_clean(raw, "docs/chat-history-raw.jsonl")
    RAW.write_text(raw, encoding="utf-8")

    print(f"{READABLE}: {turn} human turns, {READABLE.stat().st_size/1024:.0f} KB, "
          f"redacted {counts or 'nothing'}")
    print(f"{RAW}: {RAW.stat().st_size/1024/1024:.1f} MB, redacted {raw_counts or 'nothing'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
