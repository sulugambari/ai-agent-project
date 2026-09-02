"""Hybrid retriever: one retriever, three modes, one permitted candidate set.

Why one class serves all three modes
------------------------------------
Phase 8 must compare lexical, semantic and hybrid retrieval on the same
questions. If each mode came from a differently-constructed retriever, a mode
could appear better merely because it saw a different corpus or a differently
filtered candidate set. Serving all three from one index over one permitted set
removes that confound: only the *scoring* differs.

The documented scoring strategy (required by `04`)
--------------------------------------------------
For a query and an employee:

1. Read the **permitted set** for that role from the index. This is the same set
   for every mode, and is the F-4 evidence.
2. Compute a **lexical** score per record: query-token coverage, the supplied
   baseline's measure, preserved unchanged so the comparison stays honest.
3. Compute a **semantic** score per record: cosine similarity from Chroma, with
   the permission `where` clause applied inside the query (D-002).
4. **Min-max normalise each signal independently across the permitted set**, so
   one signal cannot dominate purely because of its natural range.
5. Combine: `score = w * lexical_norm + (1 - w) * semantic_norm`, default
   `w = 0.5`, chosen from the step 5.5 comparison rather than asserted here.
6. **Break ties on `source_id`, never on recency.** Step 5.1 found the supplied
   baseline breaks ties by `occurred_at` descending, which silently encodes the
   "latest source is authoritative" fallacy the threat model rejects (T-03). A
   lexicographic tie-break is arbitrary but *neutral* and reproducible, which is
   what a tie deserves: ties should be broken by nothing meaningful, not by a
   hidden editorial claim.

Rejected alternative: **reciprocal rank fusion.** More robust to scale
differences and needs no normalisation, but it discards score magnitude, so the
per-result contribution could not be shown or reasoned about. With a permitted
set of ~11 records the scale problem is small, and inspectability is worth more
here than robustness — the product has to explain itself.

Known limitation, recorded rather than hidden: min-max normalisation is
**per query**, so combined scores rank correctly *within* a query but are not
comparable *across* queries. Phase 8 therefore compares rank-based outcomes
(was the expected source retrieved) rather than absolute scores.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import ClassVar

from company_assistant.models import (
    CompanyDocument,
    EmployeeContext,
    RetrievalMode,
    SearchResult,
)
from company_assistant.rag.contract import (
    DEFAULT_LIMIT,
    IndexStatus,
    RetrievalOutcome,
    UnsupportedRetrievalMode,
)
from company_assistant.rag.index import COMPANY_KNOWLEDGE, Namespace, VectorIndex
from company_assistant.retrieval import _tokens

DEFAULT_LEXICAL_WEIGHT = 0.5


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    """Per-record contribution of each signal, for the trace and the figure."""

    source_id: str
    lexical_raw: float
    semantic_raw: float
    lexical_norm: float
    semantic_norm: float
    combined: float


def _min_max(values: dict[str, float]) -> dict[str, float]:
    """Normalise to [0, 1]. All-equal inputs map to 0.0, not 0.5 or 1.0.

    Mapping a flat signal to zero is deliberate: if a signal cannot distinguish
    any record it should contribute nothing to the ranking, rather than adding a
    constant that shifts every score equally and looks like information.
    """
    if not values:
        return {}
    low, high = min(values.values()), max(values.values())
    if high - low < 1e-12:
        return {key: 0.0 for key in values}
    return {key: (value - low) / (high - low) for key, value in values.items()}


class HybridRetriever:
    """Lexical, semantic and hybrid scoring over one permission-filtered set."""

    supported_modes: ClassVar[frozenset[RetrievalMode]] = frozenset(
        {"lexical", "semantic", "hybrid"}
    )

    def __init__(
        self,
        index: VectorIndex,
        *,
        namespace: Namespace = COMPANY_KNOWLEDGE,
        lexical_weight: float = DEFAULT_LEXICAL_WEIGHT,
    ) -> None:
        if not 0.0 <= lexical_weight <= 1.0:
            raise ValueError("lexical_weight must be between 0 and 1")
        self._index = index
        self._namespace = namespace
        self._weight = lexical_weight

    @property
    def lexical_weight(self) -> float:
        return self._weight

    def index_status(self) -> IndexStatus:
        return self._index.status((self._namespace,))

    def _lexical_scores(self, query: str, documents: tuple[CompanyDocument, ...]) -> dict[str, float]:
        """Query-token coverage - the supplied baseline's measure, unchanged."""
        query_tokens = _tokens(query)
        if not query_tokens:
            return {document.source_id: 0.0 for document in documents}
        scores: dict[str, float] = {}
        for document in documents:
            document_tokens = _tokens(f"{document.title} {document.content}")
            scores[document.source_id] = len(query_tokens & document_tokens) / len(query_tokens)
        return scores

    def _semantic_scores(
        self, query: str, employee: EmployeeContext, permitted_count: int
    ) -> dict[str, float]:
        """Cosine similarity over the whole permitted set, so normalisation is fair."""
        if permitted_count == 0:
            return {}
        hits = self._index.query(
            query, namespace=self._namespace, role=employee.role, limit=permitted_count
        )
        return {document.source_id: score for document, score in hits}

    def breakdown(
        self, query: str, employee: EmployeeContext, *, mode: RetrievalMode = "hybrid"
    ) -> list[ScoreBreakdown]:
        """Score every permitted record, showing both signals. Ranked."""
        permitted = self._index.permitted_documents(self._namespace, employee.role)
        lexical_raw = self._lexical_scores(query, permitted)
        semantic_raw = self._semantic_scores(query, employee, len(permitted))
        semantic_raw = {document.source_id: semantic_raw.get(document.source_id, 0.0)
                        for document in permitted}

        lexical_norm = _min_max(lexical_raw)
        semantic_norm = _min_max(semantic_raw)

        rows: list[ScoreBreakdown] = []
        for document in permitted:
            sid = document.source_id
            if mode == "lexical":
                combined = lexical_raw[sid]
            elif mode == "semantic":
                combined = semantic_raw[sid]
            else:
                combined = (
                    self._weight * lexical_norm[sid]
                    + (1.0 - self._weight) * semantic_norm[sid]
                )
            rows.append(ScoreBreakdown(
                source_id=sid,
                lexical_raw=lexical_raw[sid],
                semantic_raw=semantic_raw[sid],
                lexical_norm=lexical_norm[sid],
                semantic_norm=semantic_norm[sid],
                combined=combined,
            ))
        # Tie-break on source_id, NEVER on recency (see the module docstring).
        rows.sort(key=lambda row: (-row.combined, row.source_id))
        return rows

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
        permitted = self._index.permitted_documents(self._namespace, employee.role)
        by_id = {document.source_id: document for document in permitted}
        rows = self.breakdown(query, employee, mode=mode)

        # A record scoring zero on the selected signal is not evidence. Returning
        # it would pad the context with irrelevant permitted material, which is
        # exactly the baseline product failure recorded in step 3.3.
        ranked = [row for row in rows if row.combined > 0.0][:limit]
        latency_ms = (time.perf_counter() - started) * 1000

        results = tuple(
            SearchResult(document=by_id[row.source_id], score=round(row.combined, 6))
            for row in ranked
        )

        # Defence in depth: the Chroma `where` clause and the permitted set both
        # already guarantee this, but ACCESS_MATRIX.md commits to rechecking so
        # malformed or stale metadata cannot bypass the first filter.
        for result in results:
            if employee.role not in result.document.allowed_roles:
                raise AssertionError(
                    f"permission filter bypassed: {result.document.source_id} "
                    f"reached role '{employee.role}'"
                )

        note = (
            f"Namespace '{self._namespace}'; {len(permitted)} record(s) admitted for role "
            f"'{employee.role}'."
        )
        weighting = (
            f"Hybrid weighting: {self._weight:.2f} lexical + {1 - self._weight:.2f} semantic, "
            "each min-max normalised across the permitted set. Ties broken on source_id, "
            "never on recency."
            if mode == "hybrid" else f"Single-signal mode: {mode}."
        )
        return RetrievalOutcome(
            results=results,
            mode=mode,
            latency_ms=latency_ms,
            candidate_ids=tuple(row.source_id for row in rows if row.combined > 0.0),
            index_status=self.index_status(),
            notes=(note, weighting),
        )
