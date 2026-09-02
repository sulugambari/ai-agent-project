"""Run the Phase 8 harness for one or more variants. Resumable.

    uv run python scripts/run_eval.py hybrid_agent
    uv run python scripts/run_eval.py semantic_agent
    uv run python scripts/run_eval.py lexical_baseline hybrid_agent semantic_agent

Safe to re-run: completed (case, variant, run) rows are skipped, so a run killed
by an exhausted quota resumes where it stopped rather than costing the quota
twice (F-21).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from company_assistant.evaluation.harness import (  # noqa: E402
    VARIANTS, Harness, load_cases, repeats_for, tier_of,
)


def main(argv: list[str]) -> int:
    variants = tuple(argv[1:]) or ("hybrid_agent",)
    unknown = [v for v in variants if v not in VARIANTS]
    if unknown:
        print(f"unknown variant(s): {unknown}; choose from {VARIANTS}")
        return 1

    cases = load_cases()
    harness = Harness()
    done = harness.store.completed()
    planned = sum(repeats_for(c.case_id, v) for v in variants for c in cases)
    remaining = sum(
        1
        for v in variants
        for c in cases
        for i in range(1, repeats_for(c.case_id, v) + 1)
        if harness.store.key(c.case_id, v, i) not in done
    )
    print(f"variants : {', '.join(variants)}")
    print(f"planned  : {planned} runs   already done: {planned - remaining}   to run: {remaining}")
    print(f"order    : Tier A first ({', '.join(sorted(c.case_id for c in cases if tier_of(c.case_id) == 'A'))})")
    print(f"results  : {harness.store.path}\n", flush=True)

    started = time.perf_counter()
    rows = harness.run(cases, variants=variants)
    elapsed = time.perf_counter() - started

    scored = [r for r in rows if r.get("scored")]
    waits = sum(r.get("rate_limit_waits", 0) for r in rows)
    wait_s = sum(r.get("rate_limit_wait_s", 0.0) for r in rows)
    print(f"\ncompleted {len(rows)} run(s) in {elapsed / 60:.1f} min")
    print(f"  scored              : {len(scored)}")
    print(f"  infra failures      : {len(rows) - len(scored)}")
    print(f"  rate-limit waits    : {waits} ({wait_s / 60:.1f} min waiting, excluded from latency)")
    if scored:
        blockers = {
            "forbidden in citations": sum(len(r.get("forbidden_in_citations") or []) for r in scored),
            "forbidden in trace": sum(len(r.get("forbidden_in_trace") or []) for r in scored),
            "unresolvable citations": sum(len(r.get("unresolvable_citations") or []) for r in scored),
            "unpermitted citations": sum(len(r.get("unpermitted_citations") or []) for r in scored),
        }
        print("  blocker checks      :", ", ".join(f"{k}={v}" for k, v in blockers.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
