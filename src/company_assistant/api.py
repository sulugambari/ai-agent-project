"""FastAPI boundary for the internal assistant application layer.

The approval contract is deliberately NOT the answer contract
-------------------------------------------------------------
`/ask` returns an `Answer`, which may carry a proposal. `/approve` takes a
`proposal_id` and returns an `ApprovalResponse`. They are separate request
bodies, separate response models and separate endpoints on purpose: if approval
travelled inside the answer contract, then anything that could produce an answer
could also carry an approval, and "approval must come from a separate user
interaction" would depend on a client choosing not to set a field (T-05).

Nothing here holds business logic. Every route is a thin adapter over
`AssistantService`, which is also what the Streamlit app and the evaluation
harness call - so all three paths exercise the same behaviour.
"""

from __future__ import annotations

from functools import lru_cache

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from company_assistant.approval import ApprovalError
from company_assistant.models import Answer, EmployeeContext, EmployeeRole
from company_assistant.service import (EMPLOYEES, AssistantService, FeedbackRating,
                                       FeedbackReason)

load_dotenv()

app = FastAPI(title="Northstar Internal Assistant", version="0.2.0")

@lru_cache(maxsize=1)
def get_service() -> AssistantService:
    """One service per process.

    Cached because the embedding model is ~90 MB: building a service per request
    would make the first token of every answer cost seconds of model loading.
    """
    return AssistantService()


def _employee(employee_id: str) -> EmployeeContext:
    employee = EMPLOYEES.get(employee_id)
    if employee is None:
        # 403 rather than 404: whether a given employee id exists is not
        # something an unidentified caller is entitled to learn.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Unknown employee profile."
        )
    return employee


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    employee_id: str
    conversation_id: str | None = None
    #: Lets the evaluation harness and a degraded deployment reach the
    #: deterministic Phase 3 baseline, which needs neither model nor index.
    use_baseline: bool = False


class AskResponse(BaseModel):
    answer_id: str
    answer: Answer
    latency_ms: float


class ApproveRequest(BaseModel):
    """Separate from AskRequest by design - see the module docstring."""

    proposal_id: str = Field(min_length=1)
    employee_id: str
    decision: str = Field(default="approve", pattern="^(approve|reject)$")
    reason: str = ""


class ApprovalResponse(BaseModel):
    proposal_id: str
    status: str
    executed: bool
    detail: str
    reference: str = ""


class FeedbackRequest(BaseModel):
    answer_id: str = Field(min_length=1)
    rating: FeedbackRating
    reason: FeedbackReason = "other"
    retrieval_mode: str = "hybrid"


class HealthResponse(BaseModel):
    status: str
    employee_roles: list[EmployeeRole]


class StatusResponse(BaseModel):
    model: str
    retrieval_mode: str
    lexical_weight: float
    max_tool_calls: int
    index_units: int
    index_last_indexed: str
    index_degraded: bool
    index_sources: list[dict[str, str]]
    agent_available: bool
    #: The env var the ACTIVE provider needs. Exposed so an API consumer sees the
    #: same honest disclosure the portal does, rather than inferring Groq.
    credential_variable: str
    detail: str
    feedback: dict[str, int]


@app.get("/health")
def health() -> HealthResponse:
    """Readiness without a model, an index or a network call.

    Kept deliberately free of every heavy dependency: step 9.1 requires a
    model-free health endpoint, and a container health check that loaded a 90 MB
    embedding model would report "unhealthy" for the first minute of every
    deployment and time out restarting itself.
    """
    return HealthResponse(
        status="ok",
        employee_roles=[
            "customer_success",
            "engineering",
            "people_operations",
            "finance",
        ],
    )


@app.get("/status", response_model=StatusResponse)
def service_status() -> StatusResponse:
    """Report retrieval configuration and honest index freshness."""
    service = get_service()
    current = service.status()
    return StatusResponse(
        model=current.model,
        retrieval_mode=current.retrieval_mode,
        lexical_weight=current.lexical_weight,
        max_tool_calls=current.max_tool_calls,
        index_units=current.index_units,
        index_last_indexed=current.index_last_indexed,
        index_degraded=current.index_degraded,
        index_sources=[
            {"source": name, "freshness": freshness, "detail": detail}
            for name, freshness, detail in current.index_sources
        ],
        agent_available=current.agent_available,
        credential_variable=current.credential_variable,
        detail=current.detail,
        feedback=service.feedback_summary(),
    )


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    """Answer one question for one known fictional employee."""
    employee = _employee(request.employee_id)
    service = get_service()
    if request.use_baseline:
        result = service.ask_baseline(request.question, employee)
    else:
        result = service.ask(
            request.question, employee, conversation_id=request.conversation_id
        )
    return AskResponse(
        answer_id=result.answer_id, answer=result.answer, latency_ms=result.latency_ms
    )


@app.post("/approve", response_model=ApprovalResponse)
def approve(request: ApproveRequest) -> ApprovalResponse:
    """Approve or reject one prepared action.

    This is the separate user interaction the approval boundary requires. The
    identity is rechecked inside the gate immediately before execution, not here:
    a check performed by the transport layer would be bypassed by any other
    caller of the service.
    """
    employee = _employee(request.employee_id)
    service = get_service()

    try:
        if request.decision == "reject":
            proposal = service.reject(request.proposal_id, employee, reason=request.reason)
            return ApprovalResponse(
                proposal_id=proposal.proposal_id, status=proposal.status,
                executed=False, detail="Rejected; nothing was performed.",
            )
        proposal, outcome = service.approve(request.proposal_id, employee)
        return ApprovalResponse(
            proposal_id=proposal.proposal_id, status=proposal.status,
            executed=proposal.status == "executed", detail=outcome.detail,
            reference=outcome.reference,
        )
    except ApprovalError as exc:
        # 409: the request was understood and refused because the proposal is not
        # in a state that permits it. Not a 400 - the client did nothing wrong.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@app.post("/feedback")
def feedback(request: FeedbackRequest) -> dict[str, str]:
    """Store exactly five fields about one answer, and nothing more."""
    return get_service().record_feedback(
        request.answer_id, request.rating,
        reason=request.reason, retrieval_mode=request.retrieval_mode,
    )
