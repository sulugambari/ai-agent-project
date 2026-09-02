"""Status- and recency-aware reconciliation of conflicting evidence.

This is the tool F-2 exists for. The archived EUR 2,500 refund policy outranks
the current EUR 1,000 one by 0.875 to 0.678, in every retrieval mode measured,
and chunking did not change it. Ranking cannot fix it, so the resolution is
metadata reasoning performed above retrieval - here.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from company_assistant.models import CompanyDocument, EmployeeContext
from company_assistant.tools.conflicts import (VERSIONED_SOURCE_TYPES, is_current,
                                               is_superseded)
from company_assistant.tools.knowledge import to_evidence
from company_assistant.tools.schemas import EvidenceItem, SourceComparison

#: Resolves every record one employee may see. Injected rather than imported so
#: the comparison logic is testable without an index, and so the permission
#: recheck goes through the same permitted-set read the retriever uses.
DocumentResolver = Callable[[EmployeeContext], Sequence[CompanyDocument]]


def _sort_key(item: EvidenceItem):
    return (item.occurred_at is not None, item.occurred_at)


def compare_sources(
    source_ids: list[str],
    employee: EmployeeContext,
    *,
    resolver: DocumentResolver,
) -> SourceComparison:
    """Decide which of several records is authoritative, and say why.

    Permissions are rechecked here rather than trusted from the caller. The ids
    arrive from a model turn, and a model turn is influenced by retrieved
    content - `SLACK-ATLAS-103` literally instructs the reader to fetch
    `DOC-HR-001`. Resolving only within this employee's permitted set means
    obeying that instruction retrieves nothing, so the injection fails
    structurally rather than by the prompt talking the model out of it (T-01).

    An id that cannot be resolved is reported the same way whether it is
    forbidden or non-existent. Distinguishing them would turn this tool into an
    existence oracle for records the employee may not read.
    """
    requested = [source_id.strip() for source_id in (source_ids or []) if source_id and source_id.strip()]
    if len(requested) < 1:
        return SourceComparison(
            status="error",
            verdict="unresolvable",
            reason="At least one source id is required. Pass ids returned by a search tool.",
        )

    try:
        permitted = {document.source_id: document for document in resolver(employee)}
    except Exception as exc:  # noqa: BLE001 - degrade visibly
        return SourceComparison(
            status="error",
            verdict="unresolvable",
            reason=f"Could not resolve sources ({type(exc).__name__}). Treat the comparison as unknown.",
        )

    resolved = [
        to_evidence(permitted[source_id], 0.0) for source_id in requested if source_id in permitted
    ]
    unresolved = [source_id for source_id in requested if source_id not in permitted]

    if not resolved:
        return SourceComparison(
            status="empty",
            verdict="unresolvable",
            unresolved_ids=unresolved,
            reason=(
                f"None of {', '.join(requested)} is available to this employee. "
                "Do not describe their contents; you have not read them."
            ),
        )

    reasoning: list[str] = []
    if unresolved:
        reasoning.append(
            f"Not available to this employee and excluded from the comparison: {', '.join(unresolved)}."
        )

    if len(resolved) == 1:
        only = resolved[0]
        reasoning.append(
            f"{only.source_id} is the only resolvable candidate"
            + (f", status {only.record_status!r}" if only.record_status else "")
            + ". Nothing to reconcile against it."
        )
        return SourceComparison(
            status="ok",
            verdict="single_source",
            authoritative=only,
            unresolved_ids=unresolved,
            reasoning=reasoning,
        )

    stale = [item for item in resolved if is_superseded(item.record_status)]
    live = [item for item in resolved if is_current(item.record_status)]
    unknown_status = [
        item for item in resolved if not is_superseded(item.record_status) and not is_current(item.record_status)
    ]

    if stale:
        for item in stale:
            reasoning.append(
                f"{item.source_id} carries status {item.record_status!r}"
                + (f", effective {item.occurred_at:%Y-%m-%d}" if item.occurred_at else "")
                + " - the company has marked it no longer authoritative. Its figures must not be quoted as current."
            )
        if live:
            authoritative = sorted(live, key=_sort_key)[-1]
            for item in live:
                reasoning.append(
                    f"{item.source_id} carries status {item.record_status!r}"
                    + (f", effective {item.occurred_at:%Y-%m-%d}" if item.occurred_at else "")
                    + "."
                )
            reasoning.append(
                f"Authoritative: {authoritative.source_id}. Answer from it, and say that "
                f"{', '.join(item.source_id for item in stale)} is superseded if the difference matters."
            )
            return SourceComparison(
                status="ok",
                verdict="superseded",
                authoritative=authoritative,
                superseded=stale,
                unresolved_ids=unresolved,
                reasoning=reasoning,
            )
        reasoning.append(
            "Every resolvable candidate is superseded and no current replacement was supplied. "
            "State that no current record was found rather than quoting a superseded one."
        )
        return SourceComparison(
            status="ok",
            verdict="superseded",
            authoritative=None,
            superseded=stale,
            unresolved_ids=unresolved,
            reasoning=reasoning,
        )

    dated = [item for item in resolved if item.occurred_at is not None]
    versioned = [item for item in dated if item.source_type in VERSIONED_SOURCE_TYPES]
    if len(versioned) >= 2 and len({item.occurred_at for item in versioned}) >= 2:
        ordered = sorted(versioned, key=_sort_key)
        for item in ordered:
            reasoning.append(f"{item.source_id} is dated {item.occurred_at:%Y-%m-%d}.")
        reasoning.append(
            f"No record carries a superseding status, so this is not decided by metadata. "
            f"{ordered[-1].source_id} is the most recent and {ordered[0].source_id} the oldest; "
            "read both and let their content decide which commitment stands. Do not treat "
            "'later' as 'correct' on its own."
        )
        # authoritative deliberately unset: recency is a signal about company
        # records, not a rule of authority. Naming a winner here would replace a
        # stale-evidence error with an equally confident date-ordering error.
        return SourceComparison(
            status="ok",
            verdict="recency_conflict",
            authoritative=None,
            superseded=[],
            unresolved_ids=unresolved,
            reasoning=reasoning,
        )

    if unknown_status:
        reasoning.append(
            "Candidates without a lifecycle status: "
            + ", ".join(item.source_id for item in unknown_status)
            + ". Their source families do not publish revisions, so none supersedes another."
        )
    reasoning.append("No superseding status and no competing dates were found among these candidates.")
    return SourceComparison(
        status="ok",
        verdict="no_conflict",
        authoritative=None,
        superseded=[],
        unresolved_ids=unresolved,
        reasoning=reasoning,
    )
