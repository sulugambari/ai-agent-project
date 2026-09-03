"""The single application layer. Both interfaces call this and nothing else.

Why this module imports neither Streamlit nor FastAPI
----------------------------------------------------
AGENTS.md requires agent logic to stay independent of both interfaces, and the
requirement has teeth: if answering a question needed `st.session_state`, then
the FastAPI path could not answer at all, and the evaluation harness in Phase 8
would have to drive a web app to measure anything. So conversation history,
proposals and feedback are all passed in and out explicitly. The interfaces own
their own state; this layer owns the behaviour.

The lexical baseline below is preserved on purpose (`answer_with_baseline`). It
is the Phase 3 comparison point that every later variant is measured against,
and it is the only path that runs with no model and no index at all - which
makes it the fallback when a health check has to answer without either.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from textwrap import shorten
from typing import Any, Literal

from company_assistant.agent import DEFAULT_MODEL, MAX_TOOL_CALLS, ask as agent_ask, build_agent
from company_assistant.approval import (ApprovalError, ApprovalStore, ExecutionResult,
                                        Executor, simulated_executor)
from company_assistant.connectors import load_all_documents
from company_assistant.database import DATABASE_PATH
from company_assistant.models import (ActionProposal, Answer, Citation,
                                       EmployeeContext, RetrievalMode)
from company_assistant.rag import DEFAULT_INDEX_DIR, VectorIndex
from company_assistant.retrieval import lexical_search
from company_assistant.tools import DECIDED_LEXICAL_WEIGHT

#: Where feedback is appended. Git-ignored: it is runtime data about real use.
DEFAULT_FEEDBACK_PATH = Path("data/feedback/feedback.jsonl")

#: The four fictional employee profiles.
#:
#: These live here rather than in `api.py`, where the starter put them, because
#: both interfaces and the evaluation harness need them - and importing them from
#: the FastAPI module meant the Streamlit app pulled in FastAPI purely to learn
#: who Leo is. `api.py` re-exports this mapping, so the starter's import path
#: still works.
EMPLOYEES: dict[str, EmployeeContext] = {
    "maya": EmployeeContext(
        employee_id="maya", display_name="Maya Chen", role="customer_success"
    ),
    "leo": EmployeeContext(
        employee_id="leo", display_name="Leo Martins", role="engineering"
    ),
    "priya": EmployeeContext(
        employee_id="priya", display_name="Priya Shah", role="people_operations"
    ),
    "omar": EmployeeContext(
        employee_id="omar", display_name="Omar Haddad", role="finance"
    ),
}

#: The only reasons a rating may carry. A closed list rather than free text, so
#: nothing an employee types can drag a company record, a customer name or a
#: personal detail into a file we then keep (step 7.4: "nothing more").
FeedbackReason = Literal[
    "wrong_answer", "missing_source", "stale_source", "should_have_refused",
    "too_slow", "unhelpful", "correct", "other",
]
FeedbackRating = Literal["up", "down"]


def _excerpt(content: str, width: int = 240) -> str:
    """Create a compact readable preview without cutting a word in half."""

    normalized = " ".join(content.split())
    return shorten(normalized, width=width, placeholder="...")


def answer_with_baseline(
    question: str,
    employee: EmployeeContext,
    data_root: Path = Path("data/raw"),
) -> Answer:
    """Return extractive evidence from the deterministic starter retriever.

    Preserved unchanged from the starter: it is the Phase 3 baseline and the
    comparison point for every variant, so altering it would invalidate the
    evaluation report's fixed reference point.
    """
    documents = load_all_documents(data_root)
    results = lexical_search(question, documents, employee)
    if not results:
        return Answer(
            status="insufficient_evidence",
            text="I could not find permitted evidence for this question.",
            trace=["Loaded local exports", "Applied role filter", "Ran lexical search"],
        )

    evidence_lines = [
        f"- {result.document.title}: {_excerpt(result.document.content)}"
        for result in results
    ]
    citations = [
        Citation(
            source_id=result.document.source_id,
            title=result.document.title,
            source_type=result.document.source_type,
            source_path=result.document.source_path,
            occurred_at=result.document.occurred_at,
        )
        for result in results
    ]
    return Answer(
        status="evidence_found",
        text="Baseline evidence found:\n" + "\n".join(evidence_lines),
        citations=citations,
        trace=[
            "Loaded local exports",
            f"Applied role filter for {employee.role}",
            f"Returned {len(results)} lexical results",
            "No language model or agent was used",
        ],
    )


@dataclass(frozen=True, slots=True)
class AskResult:
    """One answered question, with the id feedback will later refer to.

    `models.py` is frozen by team agreement and `Answer` has no id field, so the
    id lives here rather than being bolted onto the shared contract. It has to
    exist somewhere: feedback that cannot name the answer it is about is not
    traceable to a retrieval mode or a case.
    """

    answer_id: str
    answer: Answer
    employee_id: str
    latency_ms: float


@dataclass(frozen=True, slots=True)
class ServiceStatus:
    """What the product can currently do, for /status and the sidebar."""

    model: str
    retrieval_mode: str
    lexical_weight: float
    max_tool_calls: int
    index_units: int
    index_last_indexed: str
    index_degraded: bool
    index_sources: tuple[tuple[str, str, str], ...] = ()
    agent_available: bool = True
    #: The env var the ACTIVE provider needs, so an interface can name the one an
    #: operator must actually set rather than a hardcoded provider's.
    credential_variable: str = "GROQ_API_KEY"
    detail: str = ""


@dataclass
class AssistantService:
    """Interface-independent entry point for asking, approving and rating.

    Heavy state - the embedding model, the Chroma client, one agent per employee -
    is built lazily and cached, because the embedding model is ~90 MB and
    Streamlit reruns the whole script on every interaction. The interface is
    expected to hold ONE of these behind `@st.cache_resource`.
    """

    index_dir: Path = DEFAULT_INDEX_DIR
    database_path: Path = DATABASE_PATH
    model: str | None = None
    #: Which retrieval mode the tools use. Kept configurable ONLY so Phase 8 can run
    #: the three-variant comparison 05 requires through the same service the product
    #: uses, rather than a parallel wiring that might not be the code path shipped.
    #: The product default is hybrid (D-006).
    retrieval_mode: RetrievalMode = "hybrid"
    feedback_path: Path | None = DEFAULT_FEEDBACK_PATH
    approvals: ApprovalStore = field(default_factory=ApprovalStore)
    _index: VectorIndex | None = field(default=None, init=False, repr=False)
    _agents: dict[str, tuple[Any, Any]] = field(default_factory=dict, init=False, repr=False)
    _histories: dict[str, list[Any]] = field(default_factory=dict, init=False, repr=False)

    # -- lazy resources ------------------------------------------------------
    @property
    def model_name(self) -> str:
        """What is actually serving turns, including the gateway when there is one.

        Previously this read GROQ_MODEL directly, so with LLM_PROVIDER=openrouter
        the interface reported a Groq model while OpenRouter served the request -
        a status wrong by construction, the same family of defect as F-15.2 and
        F-25. It now asks the provider boundary, so the disclosure follows the
        configuration rather than a hardcoded assumption.
        """
        from company_assistant.agent.providers import resolve

        return resolve(self.model).describe()

    @property
    def model_id(self) -> str:
        """The model id to SEND, as distinct from the label to SHOW.

        These must not be the same string, and conflating them was a live defect:
        `_agent_for` passed `model_name` - which is `ModelChoice.describe()`, i.e.
        "<model> via <provider>" - straight into `build_agent`, so every request
        went out with a model id of `nvidia/nemotron-3.5-lightning:free via
        openrouter`. OpenRouter cannot resolve that to a free model, routes it to
        something billable, and returns 402 Payment Required against a zero
        balance - which reads exactly like an exhausted free tier and is not one.

        Introduced in the commit that made the status report the truth: the
        display string was correct, and it was then reused as an identifier. A
        label and an id are different kinds of thing even when they contain the
        same words.
        """
        from company_assistant.agent.providers import resolve

        return resolve(self.model).model

    def index(self) -> VectorIndex:
        if self._index is None:
            self._index = VectorIndex(self.index_dir)
        return self._index

    def _agent_for(self, employee: EmployeeContext) -> tuple[Any, Any]:
        """One agent per employee, cached.

        Cached per employee rather than shared, because identity is bound into
        the toolset as a closure. Reusing one agent across employees is exactly
        the bug that binding was designed to prevent.
        """
        if f'{employee.employee_id}:{self.retrieval_mode}' not in self._agents:
            self._agents[f'{employee.employee_id}:{self.retrieval_mode}'] = build_agent(
                employee, index=self.index(), model=self.model_id,
                database_path=self.database_path,
                retrieval_mode=self.retrieval_mode,
            )
        return self._agents[f'{employee.employee_id}:{self.retrieval_mode}']

    # -- asking --------------------------------------------------------------
    def ask(
        self,
        question: str,
        employee: EmployeeContext,
        *,
        conversation_id: str | None = None,
    ) -> AskResult:
        """Answer one question with the tool-using agent.

        `conversation_id` selects the short-term history. Absent one, the turn is
        stateless - which is what the evaluation harness wants, so that a case's
        result cannot depend on a case that ran before it.
        """
        import time

        agent, toolset = self._agent_for(employee)
        history = self._histories.get(conversation_id, []) if conversation_id else []

        started = time.perf_counter()
        answer, new_history = agent_ask(
            question, employee, agent=agent, toolset=toolset, history=history
        )
        latency_ms = (time.perf_counter() - started) * 1000.0

        if conversation_id:
            self._histories[conversation_id] = new_history

        # A proposal is registered as pending the moment it exists, so approval
        # can only ever refer to a proposal that was actually shown to a human.
        if answer.action_proposal is not None:
            try:
                self.approvals.register(answer.action_proposal)
            except ApprovalError:
                # Already registered - an identical re-proposal keeps its id.
                pass

        return AskResult(
            answer_id=f"ans-{uuid.uuid4().hex[:12]}",
            answer=answer,
            employee_id=employee.employee_id,
            latency_ms=round(latency_ms, 1),
        )

    def ask_baseline(self, question: str, employee: EmployeeContext) -> AskResult:
        """Answer with the deterministic lexical baseline - no model, no index."""
        import time

        started = time.perf_counter()
        answer = answer_with_baseline(question, employee)
        return AskResult(
            answer_id=f"base-{uuid.uuid4().hex[:12]}",
            answer=answer,
            employee_id=employee.employee_id,
            latency_ms=round((time.perf_counter() - started) * 1000.0, 1),
        )

    # -- the approval boundary ------------------------------------------------
    def pending_proposals(self) -> tuple[ActionProposal, ...]:
        return self.approvals.pending()

    def approve(
        self,
        proposal_id: str,
        employee: EmployeeContext,
        *,
        executor: Executor = simulated_executor,
    ) -> tuple[ActionProposal, ExecutionResult]:
        """Approve and execute. Identity is rechecked inside the gate."""
        return self.approvals.approve_and_execute(proposal_id, employee, executor=executor)

    def reject(self, proposal_id: str, employee: EmployeeContext, *, reason: str = "") -> ActionProposal:
        return self.approvals.reject(proposal_id, employee, reason=reason)

    def edit_proposal(
        self,
        proposal_id: str,
        employee: EmployeeContext,
        *,
        payload: dict[str, str],
        destination: str | None = None,
    ) -> ActionProposal:
        return self.approvals.edit(proposal_id, employee, payload=payload, destination=destination)

    # -- feedback -------------------------------------------------------------
    def record_feedback(
        self,
        answer_id: str,
        rating: FeedbackRating,
        *,
        reason: FeedbackReason = "other",
        retrieval_mode: str = "hybrid",
    ) -> dict[str, str]:
        """Persist exactly five fields, and deliberately nothing more.

        Step 7.4 says "answer ID, rating, reason category, retrieval mode,
        timestamp - nothing more". The question text is NOT stored, and neither
        is the answer or the employee: a feedback file that accumulated
        questions would quietly become a second copy of the company's private
        knowledge, sitting outside the permission model that protects the first.
        """
        record = {
            "answer_id": answer_id,
            "rating": rating,
            "reason": reason,
            "retrieval_mode": retrieval_mode,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        if self.feedback_path is not None:
            self.feedback_path.parent.mkdir(parents=True, exist_ok=True)
            with self.feedback_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def feedback_summary(self) -> dict[str, int]:
        """Counts only. Used by the sidebar and by the Phase 8 dashboard."""
        if self.feedback_path is None or not self.feedback_path.exists():
            return {"up": 0, "down": 0, "total": 0}
        up = down = 0
        for line in self.feedback_path.read_text(encoding="utf-8").splitlines():
            try:
                rating = json.loads(line).get("rating")
            except json.JSONDecodeError:
                continue
            if rating == "up":
                up += 1
            elif rating == "down":
                down += 1
        return {"up": up, "down": down, "total": up + down}

    # -- status ---------------------------------------------------------------
    def status(self) -> ServiceStatus:
        """Report what the product can do, including honest index freshness."""
        from company_assistant.agent.providers import credentials_present

        agent_ready, credential_variable = credentials_present()
        try:
            index_status = self.index().status()
            return ServiceStatus(
                model=self.model_name,
                retrieval_mode=self.retrieval_mode,
                lexical_weight=DECIDED_LEXICAL_WEIGHT,
                max_tool_calls=MAX_TOOL_CALLS,
                index_units=index_status.unit_count,
                index_last_indexed=(
                    index_status.last_indexed_at.isoformat(timespec="seconds")
                    if index_status.last_indexed_at else "never"
                ),
                index_degraded=index_status.degraded,
                index_sources=tuple(
                    (source.source, source.freshness, source.detail)
                    for source in index_status.sources
                ),
                agent_available=agent_ready,
                credential_variable=credential_variable,
                detail=index_status.describe(),
            )
        except Exception as exc:  # noqa: BLE001 - status must answer even when broken
            return ServiceStatus(
                model=self.model_name, retrieval_mode=self.retrieval_mode,
                lexical_weight=DECIDED_LEXICAL_WEIGHT, max_tool_calls=MAX_TOOL_CALLS,
                index_units=0, index_last_indexed="unknown", index_degraded=True,
                agent_available=False, credential_variable=credential_variable,
                detail=f"index unavailable ({type(exc).__name__}); rebuild it before asking questions",
            )
