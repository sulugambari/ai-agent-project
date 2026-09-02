"""Search of GitHub work items across the live board and the local export."""

from __future__ import annotations

from company_assistant.models import EmployeeContext, RetrievalMode
from company_assistant.rag import COMPANY_KNOWLEDGE, DEFAULT_LIMIT, PROJECT_BOARD, Retriever
from company_assistant.tools.knowledge import evidence_from_outcome
from company_assistant.tools.schemas import EvidenceItem, WorkItemSearchResult


def _batch_freshness(evidence: list[EvidenceItem]) -> tuple[str, bool]:
    """Summarise freshness from the records themselves, not from index status.

    Deliberately derived per record. `IndexStatus.last_indexed_at` and its
    per-namespace freshness live in process memory and are lost when the
    process restarts, so a freshly started agent would read every namespace as
    `local` - asserting "committed fixture" over data that is really live or a
    degraded fallback. Each record's own `source_freshness` is persisted in the
    store at index time, so it survives a restart and cannot drift from the
    record it describes (F-12, T-07).
    """
    kinds = {item.source_freshness for item in evidence}
    if "fallback" in kinds:
        return "fallback", True
    if kinds == {"live"}:
        return "live", False
    if "live" in kinds:
        return "mixed", False
    return "local", False


def search_work_items(
    query: str,
    employee: EmployeeContext,
    *,
    board_retriever: Retriever,
    export_retriever: Retriever | None = None,
    limit: int = DEFAULT_LIMIT,
    retrieval_mode: RetrievalMode = "hybrid",
) -> WorkItemSearchResult:
    """Search engineering work items, reporting namespace and freshness per hit.

    Two id spaces are searched and kept labelled rather than merged into one
    undifferentiated list: the live board (`GH-LIVE-*`, `project_board`) and the
    committed export (`GH-*`, inside `company_knowledge`). They are disjoint
    (F-12), so a caller must be able to tell which of the two an item came from
    before quoting its state as the current state of the work.

    Access is enforced per record, not per tool: live board issues are indexed
    `allowed_roles={engineering}`, so a non-engineering employee's permitted
    candidate set on that namespace is empty. API reachability is not employee
    authorization - the repository being public does not widen who may read it.
    """
    if not query or not query.strip():
        return WorkItemSearchResult(
            status="error",
            query=query,
            reason="A non-empty search query is required.",
        )

    evidence: list[EvidenceItem] = []
    candidate_ids: list[str] = []
    namespaces: list[str] = []
    details: list[str] = []

    try:
        board = board_retriever.search(query, employee, mode=retrieval_mode, limit=limit)
        candidate_ids.extend(board.candidate_ids)
        board_evidence = evidence_from_outcome(board, query)
        if board_evidence:
            namespaces.append(PROJECT_BOARD)
        evidence.extend(board_evidence)
        details.append(f"{PROJECT_BOARD}: {len(board.candidate_ids)} permitted candidate(s)")

        if export_retriever is not None:
            export = export_retriever.search(query, employee, mode=retrieval_mode, limit=limit)
            # Only the GitHub family from company knowledge: the rest of that
            # namespace is not work items and belongs to search_company_knowledge.
            export_evidence = [
                item for item in evidence_from_outcome(export, query) if item.source_type == "github"
            ]
            candidate_ids.extend(
                source_id for source_id in export.candidate_ids if source_id.startswith("GH-")
            )
            if export_evidence:
                namespaces.append(f"{COMPANY_KNOWLEDGE} (github export)")
            evidence.extend(export_evidence)
            details.append(
                f"{COMPANY_KNOWLEDGE}: {len(export_evidence)} github record(s) of "
                f"{len(export.candidate_ids)} permitted candidate(s)"
            )
    except Exception as exc:  # noqa: BLE001 - degrade visibly, never crash the turn
        return WorkItemSearchResult(
            status="error",
            query=query,
            reason=f"Work-item search failed ({type(exc).__name__}). Treat as unknown, not as absence.",
            detail="; ".join(details),
        )

    evidence.sort(key=lambda item: item.score, reverse=True)
    evidence = evidence[:limit]
    freshness, degraded = _batch_freshness(evidence)

    if not evidence:
        return WorkItemSearchResult(
            status="empty",
            query=query,
            candidate_ids=sorted(set(candidate_ids)),
            namespace=", ".join(namespaces),
            source_freshness=freshness,
            degraded=degraded,
            detail="; ".join(details),
            reason=(
                "No permitted work items matched. "
                f"{len(set(candidate_ids))} work item(s) were visible to this employee."
            ),
        )

    return WorkItemSearchResult(
        status="ok",
        query=query,
        evidence=evidence,
        candidate_ids=sorted(set(candidate_ids)),
        namespace=", ".join(namespaces),
        source_freshness=freshness,
        degraded=degraded,
        detail="; ".join(details),
    )
