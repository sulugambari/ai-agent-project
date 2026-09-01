"""Retrieval contract shared by the lexical, semantic and hybrid retrievers.

This module is the seam frozen at handover H2 so Phase 6 tools can be written
against a stable interface while Phase 5 implements semantic and hybrid retrieval
behind it. It deliberately contains no embedding, vector-store or model
dependency, so importing it stays cheap and testable.

Why the return type is richer than `list[SearchResult]`
-------------------------------------------------------
Two of the project's own findings make a bare result list insufficient:

* **F-4 — a refusal is not evidence of pre-retrieval filtering.** Proving the
  permission boundary requires showing the *candidate set*, not just the answer.
  So an outcome carries the ids that survived permission filtering and were
  scored, separately from the top-k actually returned.
* **F-12 — live and fallback records occupy disjoint id spaces.** An answer built
  on a degraded source must be able to say so, so freshness travels with the
  retrieval rather than being looked up separately and possibly inconsistently.

`models.py` is frozen by team agreement, so nothing here modifies it:
`SearchResult`, `CompanyDocument` and `RetrievalMode` are reused as they are.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar, Literal, Protocol, runtime_checkable

from company_assistant.models import EmployeeContext, RetrievalMode, SearchResult

#: How a source's data reached the index. ``local`` means a committed fixture,
#: which is neither live nor a degraded substitute for something live.
Freshness = Literal["live", "fallback", "local"]

#: Default number of results handed to the agent. Kept small on purpose: fewer,
#: better candidates mean less context, lower latency and tighter grounding.
DEFAULT_LIMIT = 6


@dataclass(frozen=True, slots=True)
class SourceFreshness:
    """Freshness of one ingested source, as recorded at index time."""

    source: str
    freshness: Freshness
    detail: str = ""

    @property
    def is_degraded(self) -> bool:
        return self.freshness == "fallback"


@dataclass(frozen=True, slots=True)
class IndexStatus:
    """What the index currently holds, for display and for honest disclosure.

    Phase 7 shows this in the interface as the last-indexed status; the agent
    uses `degraded` to avoid presenting fallback data as live freshness.
    """

    last_indexed_at: datetime | None = None
    unit_count: int = 0
    sources: tuple[SourceFreshness, ...] = ()
    rebuild_required: bool = False

    @property
    def degraded(self) -> bool:
        """True when any source was served from a fallback rather than live."""
        return any(source.is_degraded for source in self.sources)

    def describe(self) -> str:
        """One line suitable for the interface and for an audit trace."""
        when = self.last_indexed_at.isoformat(timespec="seconds") if self.last_indexed_at else "never"
        state = "degraded" if self.degraded else "ok"
        return f"{self.unit_count} unit(s), indexed {when}, {state}"


@dataclass(frozen=True, slots=True)
class RetrievalOutcome:
    """Everything one retrieval produced, including what it *considered*.

    `results` is the top-k handed to the model. `candidate_ids` is every source id
    that survived permission filtering and was scored — the evidence that a
    forbidden record was never a candidate at all. The distinction matters: a
    record absent from `results` might merely have ranked low, whereas a record
    absent from `candidate_ids` was never visible to this employee.
    """

    results: tuple[SearchResult, ...] = ()
    mode: RetrievalMode = "lexical"
    latency_ms: float = 0.0
    candidate_ids: tuple[str, ...] = ()
    index_status: IndexStatus = field(default_factory=IndexStatus)
    notes: tuple[str, ...] = ()

    @property
    def result_ids(self) -> tuple[str, ...]:
        return tuple(result.document.source_id for result in self.results)

    def trace_lines(self) -> list[str]:
        """Human-readable trace lines for the interface and the audit record."""
        lines = [
            f"Retrieval mode: {self.mode}",
            f"Permitted candidates scored: {len(self.candidate_ids)}"
            + (f" ({', '.join(self.candidate_ids)})" if self.candidate_ids else ""),
            f"Returned: {len(self.results)}"
            + (f" ({', '.join(self.result_ids)})" if self.results else ""),
            f"Retrieval latency: {self.latency_ms:.1f} ms",
            f"Index: {self.index_status.describe()}",
        ]
        lines.extend(self.notes)
        return lines


@runtime_checkable
class Retriever(Protocol):
    """The seam. Phase 6 tools depend on this, never on a concrete retriever.

    `employee` is required and positional-or-keyword by design: there is no way
    to call a retriever without an identity, so a tool cannot accidentally
    retrieve without permission filtering (D-002).
    """

    #: Modes this implementation can actually serve. Asking for anything else
    #: must raise rather than silently downgrade, or an evaluation comparing
    #: three modes could unknowingly compare one mode three times.
    supported_modes: ClassVar[frozenset[RetrievalMode]]

    def search(
        self,
        query: str,
        employee: EmployeeContext,
        *,
        mode: RetrievalMode = "hybrid",
        limit: int = DEFAULT_LIMIT,
    ) -> RetrievalOutcome: ...

    def index_status(self) -> IndexStatus: ...


class UnsupportedRetrievalMode(ValueError):
    """Raised when a retriever is asked for a mode it cannot serve.

    Deliberately loud. Silently falling back to another mode would corrupt the
    Phase 8 three-way comparison, which is the evidence for choosing a default.
    """

    def __init__(self, mode: RetrievalMode, supported: frozenset[RetrievalMode]) -> None:
        self.mode = mode
        self.supported = supported
        super().__init__(f"mode {mode!r} not supported; this retriever serves {sorted(supported)}")
