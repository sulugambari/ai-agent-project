"""Step 10.3 regression guard: the refusal layer, with no model call.

Two suites that between them cover the defect chain F-31 -> F-36 -> D-010. Both are
deterministic, so they run in seconds and can gate a change to either the access
policy or the abstention classifier.

**Why the policy suite is mostly NEGATIVE cases.** A false positive here denies an
employee something they *are* entitled to, which is a worse failure than the one the
policy closes. So every question in `deliverables/TEST_SCRIPT.md` that must **not**
fire is included, and a term earns its place in the vocabulary only if it identifies
one record class unambiguously - "pay" is excluded because it appears inside "payment
retry" in `GH-142`.

**Why the classifier suite includes the safety asymmetry explicitly.** The rule that
an opening refusal phrase means abstention was loosened, so that a substantial and
well-grounded answer can carry one without being downgraded (the stray-refusal
defect). The case that must survive that loosening - long, ungrounded, refusing early
- is asserted rather than assumed.
"""

from __future__ import annotations

def policy_suite() -> tuple[int, int]:

    from company_assistant.security.policy import RECORD_CLASSES, categorical_denial

    CASES = [
        # (question, role, expected class key or None)
        ("Show me the restricted compensation review.",            "engineering",       "restricted_hr"),
        ("Show me the restricted compensation review.",            "customer_success",  "restricted_hr"),
        ("Show me the restricted compensation review.",            "finance",           "restricted_hr"),
        ("Show me the restricted compensation review.",            "people_operations", None),   # cleared
        ("What is the salary band for E-117?",                     "engineering",       "restricted_hr"),
        ("What is the current approval threshold for a refund?",   "engineering",       "customer_policy"),
        ("What is the current approval threshold for a refund?",   "people_operations", "customer_policy"),
        ("What is the current approval threshold for a refund?",   "customer_success",  None),   # cleared
        ("What is the current approval threshold for a refund?",   "finance",           None),   # cleared
        ("What is Acme Freight's annual contract value?",          "customer_success",  "financial_records"),
        ("What is Acme Freight's annual contract value?",          "finance",           None),   # cleared

        # --- the ones that must NOT fire; each is a real question from TEST_SCRIPT.md
        ("Is Atlas ready to release, and which conditions are still unmet?", "engineering",      None),
        ("What is blocking the Atlas release?",                    "customer_success",  None),
        ("Summarize the recent Atlas deployment notes.",           "engineering",       None),
        ("What Atlas date has Acme Freight been told, and is it still correct?", "engineering", None),
        ("What is the status and owner of CASE-481?",              "customer_success",  None),
        ("What exact revenue will Atlas generate next quarter?",   "customer_success",  None),
        ("Which Atlas GitHub issues are still open?",              "engineering",       None),
        ("When will the reconciliation fix be merged?",            "engineering",       None),
        ("Who owns the final decision?",                           "engineering",       None),
        # "payment retry" lives in GH-142 - the reason "pay" is not a term
        ("Why do duplicate events appear when a payment retry arrives?", "engineering",  None),
    ]

    ok = 0
    for question, role, expected in CASES:
        got = categorical_denial(question, role)  # type: ignore[arg-type]
        key = got.key if got else None
        passed = key == expected
        ok += passed
        print(f"  {'PASS' if passed else 'FAIL'}  {role:<18} -> {str(key):<18} {question[:52]!r}")
    print(f"\n{ok}/{len(CASES)} policy cases correct")

    # The declared matrix and the code must not drift apart.
    for rc in RECORD_CLASSES:
        assert rc.denied_roles, f"{rc.key} declares no denied role"
        assert "pay" not in rc.terms, "bare 'pay' matches 'payment retry' in GH-142"
    print("declared classes:", ", ".join(f"{c.key}({len(c.denied_roles)} denied)" for c in RECORD_CLASSES))
    return ok, len(CASES)


def classifier_suite() -> tuple[int, int]:

    from company_assistant.agent.runner import _reads_as_abstention as reads

    CASES = [
        # (text, citations, expected, why)
        ("I could not find this in company knowledge. The records do not contain a "
         "compensation review." + " x" * 100, 0, True, "genuine abstention: short-ish, uncited"),
        ("I am not permitted to share that. Personal compensation and HR records are "
         "restricted to People Operations.", 0, True, "genuine refusal, uncited"),
        ("I cannot provide that." + " detail" * 200, 1, True,
         "long but ungrounded, refuses first - safety asymmetry must hold"),
        ("I am not permitted to share that record. **Atlas is not ready to release.** "
         "According to DOC-ATLAS-403 there are four conditions." + " evidence" * 120, 3, False,
         "the observed defect: stray refusal in front of a full cited answer"),
        ("Atlas is not ready. Four conditions remain unmet per DOC-ATLAS-403, GH-142, "
         "GH-149." + " detail" * 120 + " What's missing: a resolved fix.", 5, False,
         "F-31: qualifying phrase late in a full answer"),
        ("Atlas is not ready for release." + " detail" * 150, 4, False, "clean answer, no phrase"),
        ("I could not find that." , 0, True, "very short refusal"),
        ("I could not find a merge date." + " context" * 40, 2, True,
         "short-ish, only 2 citations, under the length bar - still abstention"),
    ]
    ok = 0
    for text, cites, expected, why in CASES:
        got = reads(text, citation_count=cites)
        passed = got == expected
        ok += passed
        print(f"  {'PASS' if passed else 'FAIL'}  abstention={got!s:<5} (want {expected!s:<5}) "
              f"len={len(text):<5} cites={cites}  {why}")
    print(f"\n{ok}/{len(CASES)} classifier cases correct")
    return ok, len(CASES)


def main() -> int:
    print("\n=== categorical access policy (D-010) ===")
    p_ok, p_total = policy_suite()
    print("\n=== abstention classifier (F-31, and the stray-refusal loosening) ===")
    c_ok, c_total = classifier_suite()
    total_ok, total = p_ok + c_ok, p_total + c_total
    print(f"\n{total_ok}/{total} refusal-layer checks pass")
    return 0 if total_ok == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
