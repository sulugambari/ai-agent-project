"""Detection of stale and conflicting evidence, shared by two tools.

The problem this module exists for (F-2)
----------------------------------------
On Maya's refund question the *archived* EUR 2,500 policy scores 0.875 and the
*current* EUR 1,000 policy scores 0.678. It is measured in all three retrieval
modes, hybrid is the worst of them, and chunking did not help. So the correct
answer is not recoverable from ranking, and status-aware reasoning has to happen
above retrieval.

Why grouping uses source ids rather than titles
-----------------------------------------------
The obvious grouping key is the title, and it does not work on this corpus:
`EMAIL-ACME-301` is "Atlas migration and invoice follow-up" while its own
correction `EMAIL-ACME-302` is "Correction: Atlas customer date". Nothing in the
prose links them. The *stable id scheme* does: both belong to family
`EMAIL-ACME`. Source ids are governed and required to survive parsing,
retrieval, tool output and citation, which makes them the most stable joining
key available - considerably more stable than editorial wording.

Why recency is a signal and supersession is a verdict
-----------------------------------------------------
An explicit `status: archived` is the company stating that a record is no longer
authoritative. A later date is not: minutes written after a policy do not
override it. Treating recency as a rule would swap one confident error for
another, so the two are reported differently and only one of them decides.
"""

from __future__ import annotations

from company_assistant.tools.schemas import ConflictHint, EvidenceItem

#: Values of `record_status` that mean "no longer authoritative". Matching is
#: exact and lower-cased: an unrecognised status must never be silently read as
#: current, so anything outside both sets is treated as unknown and reported.
SUPERSEDED_STATUSES = frozenset({"archived", "superseded", "obsolete", "deprecated"})
CURRENT_STATUSES = frozenset({"current", "active", "effective"})

#: Source families where a later record can genuinely supersede an earlier one.
#: Slack is excluded deliberately - a thread accumulates messages, it does not
#: publish versions, so `SLACK-ATLAS-101/102/103` are not competing revisions.
#: GitHub is excluded because its lifecycle lives in `state` (open/closed), not
#: in date order.
VERSIONED_SOURCE_TYPES = frozenset({"document", "email"})

#: Id segments that mark a revision rather than a distinct record, so
#: `DOC-POLICY-OLD-402` groups with `DOC-POLICY-401` instead of forming its own
#: family of one.
_VERSION_MARKERS = frozenset({"old", "archived", "previous", "v1", "v2", "draft"})


def id_family(source_id: str) -> str:
    """The stable-id prefix shared by revisions of the same record.

    `DOC-POLICY-OLD-402` and `DOC-POLICY-401` both yield `DOC-POLICY`;
    `EMAIL-ACME-301` and `EMAIL-ACME-302` both yield `EMAIL-ACME`.
    """
    segments = [s for s in source_id.split("-") if s]
    while segments and (segments[-1].isdigit() or segments[-1].lower() in _VERSION_MARKERS):
        segments.pop()
    return "-".join(segments) or source_id


def is_superseded(record_status: str) -> bool:
    return record_status.strip().lower() in SUPERSEDED_STATUSES


def is_current(record_status: str) -> bool:
    return record_status.strip().lower() in CURRENT_STATUSES


def detect_conflicts(evidence: list[EvidenceItem]) -> list[ConflictHint]:
    """Report disagreements a caller must resolve before quoting any of them.

    Runs over one result set and returns hints, not decisions. The search tools
    attach these so the agent is pushed toward `compare_sources` by the data
    itself; the prompt is a second line of defence, not the first.
    """
    hints: list[ConflictHint] = []

    stale = [item for item in evidence if is_superseded(item.record_status)]
    if stale:
        # Only replacements from the SAME id family count. Most records in a
        # result set carry `status: current` without being related to the stale
        # one at all - naming them here would hand the agent ids to compare that
        # have nothing to do with the question, and a comparison of unrelated
        # records produces a confident non-answer.
        stale_families = {id_family(item.source_id) for item in stale}
        live = [
            item
            for item in evidence
            if is_current(item.record_status) and id_family(item.source_id) in stale_families
        ]
        stale_ids = [item.source_id for item in stale]
        live_ids = [item.source_id for item in live]
        detail = (
            f"{', '.join(stale_ids)} carries a superseded status"
            + (
                f" while {', '.join(live_ids)} in the same record family is marked current"
                if live_ids
                else " and no current replacement is present in these results"
            )
            + ". Do not quote a superseded record as current; call compare_sources."
        )
        hints.append(
            ConflictHint(
                reason="status_supersession",
                source_ids=stale_ids + live_ids,
                detail=detail,
            )
        )

    families: dict[str, list[EvidenceItem]] = {}
    for item in evidence:
        if item.source_type in VERSIONED_SOURCE_TYPES:
            families.setdefault(id_family(item.source_id), []).append(item)
    for family, items in sorted(families.items()):
        dated = [item for item in items if item.occurred_at is not None]
        if len(dated) < 2:
            continue
        if len({item.occurred_at for item in dated}) < 2:
            continue
        ordered = sorted(dated, key=lambda item: item.occurred_at)  # type: ignore[arg-type,return-value]
        # Skip when an explicit status already decided it - one conflict, one hint.
        if any(is_superseded(item.record_status) for item in ordered):
            continue
        newest, oldest = ordered[-1], ordered[0]
        hints.append(
            ConflictHint(
                reason="recency",
                source_ids=[item.source_id for item in ordered],
                detail=(
                    f"Family {family} holds {len(ordered)} dated records: "
                    f"{oldest.source_id} ({oldest.occurred_at:%Y-%m-%d}) is the oldest and "
                    f"{newest.source_id} ({newest.occurred_at:%Y-%m-%d}) the newest. "
                    "A later date does not by itself override an earlier one - read both."
                ),
            )
        )
    return hints
