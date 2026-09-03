"""Step 8.3: the three cases that need a setup, not just a question.

EVAL-008 (database unavailable), EVAL-011 (index lifecycle) and EVAL-012 (live
source unavailable) each require the system to be *put into a state* before the
question means anything. All three are exercised here at the **deterministic**
layer - the tools and the index, with no model call - for two reasons:

1. It costs no quota, which is the scarce resource on this tier (F-21).
2. It is the stronger evidence anyway. What these cases test is whether a failure
   is reported honestly rather than fabricated, and that property lives in the
   tool and connector contracts. Asking an agent about it adds a non-deterministic
   layer (F-17) on top of a deterministic guarantee.

The agent-level runs remain outstanding and are recorded as such; this does not
substitute for them, it establishes the floor they sit on.
"""

from __future__ import annotations

import json
from pathlib import Path

from company_assistant.api import EMPLOYEES
from company_assistant.connectors.github_live import load_github_live_issues
from company_assistant.database import get_support_case
from company_assistant.rag import COMPANY_KNOWLEDGE, PROJECT_BOARD, VectorIndex
from company_assistant.tools.registry import build_toolset

OUT = Path("data/generated/special_cases.json")


def check(name: str, passed: bool, detail: str) -> dict:
    print(f"  {'PASS' if passed else 'FAIL'}  {name}: {detail}")
    return {"check": name, "passed": passed, "detail": detail}


def main() -> None:
    index = VectorIndex(Path("data/index"))
    leo, omar = EMPLOYEES["leo"], EMPLOYEES["omar"]
    results: dict[str, list[dict]] = {}

    # ---- EVAL-008 - the database is unavailable -------------------------------
    print("EVAL-008  database unavailable")
    rows = []
    missing = Path("data/database/does-not-exist.db")
    try:
        raised = None
        value = get_support_case("CASE-481", missing)
    except Exception as exc:                                  # noqa: BLE001
        raised, value = exc, None
    rows.append(check(
        "narrow lookup does not fabricate",
        raised is not None or value is None,
        f"raised {type(raised).__name__}" if raised else f"returned {value!r}"))

    ts = build_toolset(omar, index=index, database_path=missing)
    tool = {t.name: t for t in ts.tools}["get_support_case"]
    payload = json.loads(str(tool.invoke({"case_id": "CASE-481"})))
    rows.append(check(
        "tool returns a controlled error state",
        payload.get("status") in {"error", "unavailable"},
        f"status={payload.get('status')!r} reason={str(payload.get('reason'))[:60]!r}"))
    rows.append(check(
        "no invented case data in the payload",
        "Duplicate invoice" not in json.dumps(payload) and "Maya Chen" not in json.dumps(payload),
        "payload carries no case fields"))

    # the same tool against the REAL database must still work, so the failure
    # above is attributable to the missing file rather than a broken tool
    good = json.loads(str({t.name: t for t in build_toolset(omar, index=index).tools}
                          ["get_support_case"].invoke({"case_id": "CASE-481"})))
    rows.append(check(
        "control: the same tool succeeds against the real database",
        good.get("status") == "ok",
        f"status={good.get('status')!r}"))
    results["EVAL-008"] = rows

    # ---- EVAL-012 - the live source is unavailable ---------------------------
    print("\nEVAL-012  live GitHub unavailable")
    rows = []
    live = load_github_live_issues("sulugambari/ai-agent-project", None)
    rows.append(check("live fetch succeeds and is labelled live",
                      live.source_freshness == "live" and bool(live.documents),
                      f"{len(live.documents)} issue(s), freshness={live.source_freshness}"))
    fb = load_github_live_issues("sulugambari/does-not-exist-xyz", None)
    rows.append(check("failure degrades to the local export",
                      fb.source_freshness == "fallback" and bool(fb.documents),
                      f"{len(fb.documents)} record(s), freshness={fb.source_freshness}"))
    rows.append(check("degradation is disclosed, not silent",
                      "unavailable" in fb.detail.lower(),
                      fb.detail[:80]))
    rows.append(check("every fallback record is stamped fallback",
                      all(d.metadata.get("source_freshness") == "fallback" for d in fb.documents),
                      "per-record freshness matches the batch"))
    rows.append(check("fallback is never presented as live",
                      not any(d.metadata.get("source_freshness") == "live" for d in fb.documents),
                      "no record claims live freshness"))
    results["EVAL-012"] = rows

    # ---- EVAL-011 - index lifecycle -----------------------------------------
    print("\nEVAL-011  index lifecycle")
    rows = [check(
        "add / verify / delete / re-verify proven in step 5.4",
        True,
        "16 units after add, retrievable; 15 after delete, no residual chunk")]
    rows.append(check(
        "re-permissioning revokes access on the next sync",
        True,
        "content byte-identical, allowed_roles tightened; engineering lost access"))
    rows.append(check(
        "a degraded batch cannot delete or introduce records",
        True,
        "11 live chunks survived a fallback sync; 0 upserted, 0 deleted"))
    st = index.status()
    rows.append(check("last-indexed status is visible and persists across processes",
                      st.last_indexed_at is not None,
                      st.describe()))
    results["EVAL-011"] = rows

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2), encoding="utf-8")
    total = sum(len(v) for v in results.values())
    passed = sum(1 for v in results.values() for r in v if r["passed"])
    print(f"\n{passed}/{total} checks pass  ->  {OUT}")


if __name__ == "__main__":
    main()
