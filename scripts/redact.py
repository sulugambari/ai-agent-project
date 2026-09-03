"""Credential redaction for anything generated from the session transcript.

Exists because a real key was pasted into a chat whose transcript this project
commits to a **public** repository. `AGENTS.md` forbids credentials reaching
prompts, traces, indexed content or generated deliverables, and a transcript is
a generated deliverable. Redaction has to live in code rather than in a habit:
the transcript is regenerated on every handover update, so one forgetful refresh
would publish a live secret.

Patterns are matched on shape, not on a list of known keys, so a provider we
have never used is still caught.
"""

from __future__ import annotations

import re

#: Shape-based, so an unfamiliar provider is still redacted.
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("OPENROUTER_KEY", re.compile(r"sk-or-v1-[A-Za-z0-9]{16,}")),
    ("OPENAI_KEY", re.compile(r"\bsk-(?!or-)[A-Za-z0-9_-]{20,}")),
    ("GROQ_KEY", re.compile(r"\bgsk_[A-Za-z0-9]{20,}")),
    ("GITHUB_PAT", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}")),
    ("GITHUB_FINE_GRAINED", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("HF_TOKEN", re.compile(r"\bhf_[A-Za-z0-9]{20,}")),
    ("AWS_KEY", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("SLACK_TOKEN", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    ("PRIVATE_KEY_BLOCK", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    # A KEY=value assignment where the value actually looks like a secret.
    #
    # An earlier, looser version of this matched `TOKEN_PATTERN = re.compile(`,
    # `query_tokens = _tokens(query)` and the placeholder `GROQ_MODEL=openai/...`
    # in .env.example. A redactor that reports six false positives gets ignored,
    # which is worse than not having one - so the value must be uppercase-key,
    # no-space, at least 20 characters, and free of the punctuation that marks
    # code or a model path.
    ("ENV_ASSIGNMENT", re.compile(
        r"\b([A-Z][A-Z0-9_]*(?:API_KEY|SECRET|TOKEN|PASSWORD)[A-Z0-9_]*)"
        r"=(?!\s)([^\s'\"()/\\]{20,})")),
)


def redact(text: str) -> tuple[str, dict[str, int]]:
    """Return the text with credentials replaced, plus a count per pattern."""
    counts: dict[str, int] = {}
    for name, pattern in PATTERNS:
        if name == "ENV_ASSIGNMENT":
            def _sub(m: re.Match[str]) -> str:
                return f"{m.group(1)}=[REDACTED]"
            text, n = pattern.subn(_sub, text)
        else:
            text, n = pattern.subn(f"[REDACTED:{name}]", text)
        if n:
            counts[name] = n
    return text, counts


def assert_clean(text: str, where: str) -> None:
    """Raise if anything credential-shaped survives. Used as a release gate."""
    _, counts = redact(text)
    if counts:
        raise AssertionError(f"credential-shaped content still present in {where}: {counts}")


if __name__ == "__main__":
    import sys
    from pathlib import Path

    total: dict[str, int] = {}
    for arg in sys.argv[1:]:
        path = Path(arg)
        if not path.exists():
            continue
        cleaned, counts = redact(path.read_text(encoding="utf-8", errors="replace"))
        if counts:
            path.write_text(cleaned, encoding="utf-8")
            for k, v in counts.items():
                total[k] = total.get(k, 0) + v
            print(f"{path}: redacted {counts}")
        else:
            print(f"{path}: clean")
    print("total:", total or "nothing redacted")
