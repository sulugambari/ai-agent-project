"""Permission-aware search over company knowledge - the agent's primary tool."""

from __future__ import annotations

from textwrap import shorten

from company_assistant.models import EmployeeContext, RetrievalMode
from company_assistant.rag import COMPANY_KNOWLEDGE, DEFAULT_LIMIT, Retriever
from company_assistant.rag.contract import RetrievalOutcome
from company_assistant.tools.conflicts import detect_conflicts
from company_assistant.tools.relevance import classify, relevance_note, term_coverage
from company_assistant.tools.schemas import EvidenceItem, KnowledgeSearchResult

#: Excerpt width per result. Six results at this width keeps one turn's evidence
#: well inside the context budget while leaving each passage long enough to carry
#: a threshold, a date or a decision - the three things this corpus is asked for.
EXCERPT_WIDTH = 600


def _excerpt(content: str, width: int = EXCERPT_WIDTH) -> str:
    return shorten(" ".join(content.split()), width=width, placeholder=" ...")


def to_evidence(document, score: float, *, query: str = "") -> EvidenceItem:
    """Project a retrieved document onto the evidence envelope.

    Metadata the system asserts is kept structurally apart from `excerpt`, which
    is company content and therefore untrusted (T-01).

    `term_coverage` is measured over the FULL record, not the truncated excerpt:
    a relevance measure that changed with the excerpt width would be a measure of
    formatting, not of relevance.
    """
    return EvidenceItem(
        source_id=document.source_id,
        title=document.title,
        source_type=document.source_type,
        source_path=document.source_path,
        occurred_at=document.occurred_at,
        record_status=str(document.metadata.get("status", "")),
        source_freshness=str(document.metadata.get("source_freshness", "local")),
        namespace=str(document.metadata.get("namespace", "")),
        score=round(score, 4),
        term_coverage=round(term_coverage(query, f"{document.title} {document.content}"), 4)
        if query
        else 0.0,
        excerpt=_excerpt(document.content),
    )


def evidence_from_outcome(outcome: RetrievalOutcome, query: str = "") -> list[EvidenceItem]:
    return [to_evidence(result.document, result.score, query=query) for result in outcome.results]


def search_company_knowledge(
    query: str,
    employee: EmployeeContext,
    *,
    retriever: Retriever,
    limit: int = DEFAULT_LIMIT,
    retrieval_mode: RetrievalMode = "hybrid",
) -> KnowledgeSearchResult:
    """Search Slack, email, documents and the local GitHub export.

    `employee` is required, so there is no code path that retrieves without an
    identity (D-002). Permission filtering happens inside the retriever, before
    scoring, which is why `candidate_ids` is reported: it is the only artefact
    that distinguishes "never visible to you" from "ranked low" (F-4).
    """
    if not query or not query.strip():
        return KnowledgeSearchResult(
            status="error",
            query=query,
            reason="A non-empty search query is required.",
        )

    try:
        outcome = retriever.search(query, employee, mode=retrieval_mode, limit=limit)
    except Exception as exc:  # noqa: BLE001 - a tool must degrade, never crash the turn
        # Reported as a controlled failure rather than an empty result: T-07 -
        # an infrastructure failure must never be presented as "nothing exists".
        return KnowledgeSearchResult(
            status="error",
            query=query,
            reason=f"Retrieval failed ({type(exc).__name__}). Treat this as unknown, not as absence of evidence.",
        )

    evidence = evidence_from_outcome(outcome, query)

    # Defence in depth for F-13. The retriever is namespace-scoped so live board
    # issues cannot reach here; if that ever changes, contamination must surface
    # as a visible note rather than as quietly mixed-in evidence.
    contaminants = [item.source_id for item in evidence if item.source_id.startswith("GH-LIVE-")]
    if contaminants:
        evidence = [item for item in evidence if not item.source_id.startswith("GH-LIVE-")]
    notes = list(outcome.notes)
    if contaminants:
        notes.append(
            f"Dropped {len(contaminants)} live board record(s) that must not appear in "
            f"company knowledge: {', '.join(contaminants)} (F-13)."
        )

    if not evidence:
        return KnowledgeSearchResult(
            status="empty",
            query=query,
            candidate_ids=list(outcome.candidate_ids),
            retrieval_mode=outcome.mode,
            latency_ms=round(outcome.latency_ms, 1),
            index_status=outcome.index_status.describe(),
            notes=notes,
            reason=(
                "No permitted evidence matched. "
                f"{len(outcome.candidate_ids)} record(s) were visible to this employee and none matched."
            ),
        )

    conflicts = detect_conflicts(evidence)

    # The retriever cannot report irrelevance: min-max normalisation gives the
    # best permitted record a score of 1.0 whatever the question, so a result set
    # always looks confident. The absolute measure is added here instead.
    max_coverage = max((item.term_coverage for item in evidence), default=0.0)
    relevance = classify(max_coverage)
    notes.append(relevance_note(relevance, max_coverage))

    return KnowledgeSearchResult(
        status="ok",
        query=query,
        evidence=evidence,
        candidate_ids=list(outcome.candidate_ids),
        conflict_detected=bool(conflicts),
        conflicts=conflicts,
        relevance=relevance,
        max_term_coverage=round(max_coverage, 4),
        retrieval_mode=outcome.mode,
        latency_ms=round(outcome.latency_ms, 1),
        index_status=outcome.index_status.describe(),
        notes=notes,
    )
