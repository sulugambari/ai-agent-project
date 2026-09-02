"""Semantic retriever satisfying the H2 `Retriever` contract.

Holds a `VectorIndex` and one namespace. Phase 6 tools depend only on the
Protocol, so swapping this for the hybrid retriever at H3 requires no tool
changes.
"""

from __future__ import annotations

import time
from typing import ClassVar

from company_assistant.models import EmployeeContext, RetrievalMode, SearchResult
from company_assistant.rag.contract import (
    DEFAULT_LIMIT,
    IndexStatus,
    RetrievalOutcome,
    UnsupportedRetrievalMode,
)
from company_assistant.rag.index import COMPANY_KNOWLEDGE, Namespace, VectorIndex


class SemanticRetriever:
    """Embedding similarity over one namespace, permission-filtered at query time."""

    supported_modes: ClassVar[frozenset[RetrievalMode]] = frozenset({"semantic"})

    def __init__(self, index: VectorIndex, *, namespace: Namespace = COMPANY_KNOWLEDGE) -> None:
        self._index = index
        self._namespace = namespace

    def index_status(self) -> IndexStatus:
        return self._index.status((self._namespace,))

    def search(
        self,
        query: str,
        employee: EmployeeContext,
        *,
        mode: RetrievalMode = "hybrid",
        limit: int = DEFAULT_LIMIT,
    ) -> RetrievalOutcome:
        if mode not in self.supported_modes:
            raise UnsupportedRetrievalMode(mode, self.supported_modes)

        started = time.perf_counter()

        # The admitted set, read from metadata rather than inferred from ranking.
        # This is the F-4 evidence: a record missing here was never visible to this
        # employee, as distinct from having merely ranked low.
        candidate_ids = self._index.permitted_ids(self._namespace, employee.role)

        hits = self._index.query(
            query, namespace=self._namespace, role=employee.role, limit=limit
        )
        latency_ms = (time.perf_counter() - started) * 1000

        results = tuple(SearchResult(document=document, score=score) for document, score in hits)

        # Defence in depth. The Chroma `where` clause already made this impossible,
        # but permissions are rechecked after retrieval because malformed or stale
        # metadata must not be able to bypass the first filter - ACCESS_MATRIX.md
        # commits to rechecking, and a silent failure here would be a leak.
        for result in results:
            if employee.role not in result.document.allowed_roles:
                raise AssertionError(
                    f"permission pre-filter bypassed: {result.document.source_id} "
                    f"reached role '{employee.role}'"
                )

        return RetrievalOutcome(
            results=results,
            mode="semantic",
            latency_ms=latency_ms,
            candidate_ids=candidate_ids,
            index_status=self.index_status(),
            notes=(
                f"Namespace '{self._namespace}'; permission pre-filter applied inside the "
                f"vector query for role '{employee.role}': {len(candidate_ids)} record(s) admitted.",
            ),
        )
