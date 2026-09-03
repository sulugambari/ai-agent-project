"""Generate the step 8.5 scenario table from the recorded runs.

Generated rather than hand-written so the report cannot drift from the data, and
so it can be regenerated when a later quota window adds coverage. Every cell is
traceable to `data/generated/eval_runs.jsonl`.
"""

from __future__ import annotations

import json
from pathlib import Path

from company_assistant.evaluation.report import load, verdicts

REPORT = Path("deliverables/EVALUATION_REPORT.md")
SPECIAL = Path("data/generated/special_cases.json")
START = "## Scenario Results"
END = "## Product and Operational Evidence"

LAYER_MARK = {True: "Pass", False: "Fail"}


def cell(rate: float | None, scored: int) -> str:
    if not scored:
        return "—"
    if rate == 1.0:
        return "Pass"
    if rate == 0.0:
        return "Fail"
    return f"Partial ({rate:.0%})"


def main() -> None:
    rows = load()
    all_verdicts = verdicts(rows)
    by = {}
    for v in all_verdicts:
        by.setdefault(v.case_id, {})[v.variant] = v

    lines = [
        START,
        "",
        "Generated from `data/generated/eval_runs.jsonl` by",
        "`scripts/write_scenario_table.py`, so the table cannot drift from the data.",
        "",
        "**Read the coverage column first.** A Tier-A case has three agent runs and passes",
        "on a majority; a Tier-B case has one. `—` means the case was never scored for that",
        "variant, which on this free tier means a token-per-minute limit stopped the run —",
        "not that the case was skipped as inconvenient.",
        "",
        "| Case | Tier | Variant | Runs | Retrieval | Permissions | Citations | Behaviour | Verdict | Note |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    order = sorted(by, key=lambda c: (not c.startswith("EVAL"), c))
    for case_id in order:
        for variant in ("lexical_baseline", "semantic_agent", "hybrid_agent"):
            v = by[case_id].get(variant)
            if v is None:
                lines.append(f"| {case_id} | {'A' if case_id in ('EVAL-001','EVAL-005','EVAL-006','EVAL-007','EVAL-010','P1') else 'B'} "
                             f"| {variant} | 0 | — | — | — | — | Not run | no runs recorded |")
                continue
            r = v.layer_rates
            lines.append(
                f"| {v.case_id} | {v.tier} | {v.variant} | {v.scored_runs}/{v.runs} "
                f"| {cell(r['retrieval_pass'], v.scored_runs)} "
                f"| {cell(r['permissions_pass'], v.scored_runs)} "
                f"| {cell(r['citations_pass'], v.scored_runs)} "
                f"| {cell(r['status_acceptable'], v.scored_runs)} "
                f"| **{v.verdict}** | {v.note or '-'} |")

    # blockers, stated as counts because they are not rate-based
    scored = [r for r in rows if r.get("scored")]
    blockers = {
        "Forbidden evidence in a citation": sum(len(r.get("forbidden_in_citations") or []) for r in scored),
        "Forbidden evidence in a trace": sum(len(r.get("forbidden_in_trace") or []) for r in scored),
        "Unresolvable citation": sum(len(r.get("unresolvable_citations") or []) for r in scored),
        "Citation outside the employee's permissions": sum(len(r.get("unpermitted_citations") or []) for r in scored),
        "Action executed without approval": sum(1 for r in scored if r.get("proposal_status") in {"executed", "approved"}),
    }
    lines += [
        "",
        "### Release blockers",
        "",
        f"Counted across **all {len(scored)} scored runs**, not averaged. One occurrence blocks,",
        "whatever the pass rate: a boundary that holds two times in three is broken.",
        "",
        "| Blocker | Threshold | Observed |",
        "| --- | --- | --- |",
    ]
    for name, count in blockers.items():
        mark = "**0** ✓" if count == 0 else f"**{count}** ✗"
        lines.append(f"| {name} | 0 | {mark} |")

    if SPECIAL.exists():
        special = json.loads(SPECIAL.read_text())
        total = sum(len(v) for v in special.values())
        passed = sum(1 for v in special.values() for c in v if c["passed"])
        lines += [
            "",
            "### Special-setup cases — step 8.3",
            "",
            f"Exercised at the **deterministic** layer: {passed} of {total} checks pass. These test",
            "whether a failure is reported honestly rather than fabricated, and that property lives",
            "in the tool and connector contracts, so asking an agent about it would add a",
            "non-deterministic layer on top of a deterministic guarantee. Agent-level runs for",
            "these cases remain outstanding.",
            "",
            "| Case | Check | Result |",
            "| --- | --- | --- |",
        ]
        for case_id, checks in special.items():
            for c in checks:
                lines.append(f"| {case_id} | {c['check']} | {'Pass' if c['passed'] else 'Fail'} |")

    lines += ["", ""]
    text = REPORT.read_text(encoding="utf-8")
    start, end = text.index(START), text.index(END)
    REPORT.write_text(text[:start] + "\n".join(lines) + text[end:], encoding="utf-8")
    print(f"scenario table written: {len(order)} cases, {len(scored)} scored runs")
    print("blockers:", blockers)


if __name__ == "__main__":
    main()
