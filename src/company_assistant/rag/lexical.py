"""Lexical retriever adapting the supplied baseline to the H2 contract.

This is a real, working implementation rather than a stub: Phase 6 tools can be
built and tested against it today, then swapped to the hybrid retriever at
handover H3 with no tool changes, because both satisfy `Retriever`.

It wraps `retrieval.lexical_search` without modifying it. AGENTS.md requires the
lexical baseline be preserved for comparison, so the scoring is untouched and the
adapter only adds the contract's instrumentation.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import ClassVar

from company_assistant.models import CompanyDocument, EmployeeContext, RetrievalMode
from company_assistant.rag.contract import (
    DEFAULT_LIMIT,
    IndexStatus,
    RetrievalOutcome,
    SourceFreshness,
    UnsupportedRetrievalMode,
)
from company_assistant.retrieval import _tokens, lexical_search
from company_assistant.security import filter_permitted


class LexicalRetriever:
    """Permission-filtered token-overlap retrieval over in-memory documents."""

    supported_modes: ClassVar[frozenset[RetrievalMode]] = frozenset({"lexical"})

    def __init__(
        self,
        documents: Sequence[CompanyDocument],
        *,
        sources: Sequence[SourceFreshness] = (),
        indexed_at: datetime | None = None,
    ) -> None:
        self._documents = tuple(documents)
        self._sources = tuple(sources) or (
            SourceFreshness("local_fixtures", "local", "committed teaching fixtures"),
        )
        self._indexed_at = indexed_at or datetime.now(timezone.utc)

    def index_status(self) -> IndexStatus:
        return IndexStatus(
            last_indexed_at=self._indexed_at,
            unit_count=len(self._documents),
            sources=self._sources,
        )

    def search(
        self,
        query: str,
        employee: EmployeeContext,
        *,
        mode: RetrievalMode = "hybrid",
        limit: int = DEFAULT_LIMIT,
    ) -> RetrievalOutcome:
        # Default mode is "hybrid" across the whole contract so callers do not
        # have to know which implementation they hold. This retriever cannot
        # serve it, and says so rather than quietly returning lexical results
        # labelled as hybrid.
        if mode not in self.supported_modes:
            raise UnsupportedRetrievalMode(mode, self.supported_modes)

        started = time.perf_counter()

        # Permission filtering FIRST, before any scoring, per D-002. The candidate
        # set is recorded here so the trace can prove a forbidden record was never
        # considered - not merely that it failed to rank (F-4).
        permitted = filter_permitted(self._documents, employee)
        query_tokens = _tokens(query)
        candidate_ids = tuple(
            document.source_id
            for document in permitted
            if query_tokens & _tokens(f"{document.title} {document.content}")
        )

        results = tuple(lexical_search(query, self._documents, employee, limit=limit))
        latency_ms = (time.perf_counter() - started) * 1000

        return RetrievalOutcome(
            results=results,
            mode="lexical",
            latency_ms=latency_ms,
            candidate_ids=candidate_ids,
            index_status=self.index_status(),
            notes=(
                f"Permission filter applied before scoring for role "
                f"'{employee.role}': {len(permitted)} of {len(self._documents)} records visible.",
            ),
        )
