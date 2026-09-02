"""The approval gate: pending -> approve / edit / reject -> execution -> audit.

Why this is not in `company_assistant.tools`
--------------------------------------------
Deliberate separation. The agent can reach everything in `tools`; it can reach
nothing here. `propose_action` returns a proposal and has no parameter that can
advance it, so the only way an action executes is for a caller outside the model
loop to invoke `approve()` with an identity. Retrieved document text therefore
cannot approve anything - not because a prompt forbids it, but because the code
path does not exist (T-05, T-01).

Why the store is keyed by `proposal_id` and holds proposals immutably
--------------------------------------------------------------------
Streamlit reruns the whole script on every interaction. A proposal rebuilt on
each rerun would drift away from the one the human is looking at, so approval
could land on a payload nobody read. `proposal_id` is a content hash over the
exact operation, destination, payload and requester, so the id *is* the promise:
if any of those change, it is a different proposal with a different id.

Why "edited" creates a new proposal rather than mutating one
------------------------------------------------------------
An edit changes the payload, and the payload is what was shown before approval.
Mutating in place would let a proposal approved at one payload execute at
another. So an edit rejects the original and returns a new pending proposal, and
the audit trail records both. `models.py` is frozen and its `ActionStatus` has no
"edited" member, which is consistent with this: "edited" is an event in the audit
log, not a state a proposal can be in.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from company_assistant.models import (ActionProposal, ActionStatus, EmployeeContext,
                                      EmployeeRole)

#: Where the audit trail is appended. Git-ignored: it is a runtime record, not a
#: fixture, and it names real employees and destinations.
DEFAULT_AUDIT_PATH = Path("data/generated/action_audit.jsonl")

AuditEvent = Literal["proposed", "approved", "edited", "rejected", "executed", "failed"]

#: Which roles may approve which action type. Separate from the allow-list in
#: `tools.actions`, which governs what may be *drafted*: drafting an escalation
#: and authorising one are different privileges, and collapsing them would let
#: the ability to ask become the ability to do.
ACTION_APPROVERS: dict[str, frozenset[EmployeeRole]] = {
    "github_issue": frozenset({"engineering"}),
    "escalation_note": frozenset({"customer_success", "engineering"}),
    "status_update": frozenset({"customer_success", "engineering", "finance"}),
}


class ApprovalError(Exception):
    """Raised when a transition is not permitted. Never swallowed silently."""


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """One immutable entry in the action audit trail."""

    at: datetime
    event: AuditEvent
    proposal_id: str
    action_type: str
    destination: str
    actor: str
    detail: str = ""
    payload_fingerprint: str = ""

    def to_json(self) -> str:
        return json.dumps(
            {
                "at": self.at.isoformat(timespec="seconds"),
                "event": self.event,
                "proposal_id": self.proposal_id,
                "action_type": self.action_type,
                "destination": self.destination,
                "actor": self.actor,
                "detail": self.detail,
                "payload_fingerprint": self.payload_fingerprint,
            },
            ensure_ascii=False,
        )


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Outcome of a controlled execution attempt."""

    ok: bool
    detail: str
    reference: str = ""


#: An executor performs the action. It receives the proposal only after identity
#: and permissions have been rechecked, and it is expected to raise on failure so
#: the gate can record `failed` rather than a silent non-event.
Executor = Callable[[ActionProposal], ExecutionResult]


def simulated_executor(proposal: ActionProposal) -> ExecutionResult:
    """Record the action without performing it - the core project's default.

    `04` permits local or simulated execution and asks that the *approval
    boundary* be real. Simulation is also the honest default here: a genuine
    GitHub write needs a collaborator-scoped token (D-003), and a product that
    silently did nothing while reporting success would be the exact failure the
    threat model calls "failure reported as fact" (T-07). This returns a
    reference that is visibly simulated so no reader can mistake it for a URL.
    """
    return ExecutionResult(
        ok=True,
        detail=f"Simulated {proposal.action_type} against {proposal.destination}; nothing was written.",
        reference=f"simulated://{proposal.action_type}/{proposal.proposal_id}",
    )


@dataclass
class ApprovalStore:
    """Holds proposals and their audit trail for one session.

    Not a database. Phase 7 keeps one of these in `st.session_state` so it
    survives Streamlit's reruns, and the audit trail is appended to disk so an
    executed action leaves a record even if the session is lost.
    """

    audit_path: Path | None = DEFAULT_AUDIT_PATH
    _proposals: dict[str, ActionProposal] = field(default_factory=dict)
    _results: dict[str, ExecutionResult] = field(default_factory=dict)
    _audit: list[AuditRecord] = field(default_factory=list)

    # -- reading -------------------------------------------------------------
    @property
    def audit(self) -> tuple[AuditRecord, ...]:
        return tuple(self._audit)

    def get(self, proposal_id: str) -> ActionProposal | None:
        return self._proposals.get(proposal_id)

    def pending(self) -> tuple[ActionProposal, ...]:
        return tuple(p for p in self._proposals.values() if p.status == "pending_approval")

    def outcome(self, proposal_id: str) -> ExecutionResult | None:
        return self._results.get(proposal_id)

    def _record(self, event: AuditEvent, proposal: ActionProposal, actor: str, detail: str = "") -> AuditRecord:
        record = AuditRecord(
            at=datetime.now(timezone.utc),
            event=event,
            proposal_id=proposal.proposal_id,
            action_type=proposal.action_type,
            destination=proposal.destination,
            actor=actor,
            detail=detail,
            # The payload's identity, not its content: the audit trail must be
            # safe to read and to keep, and a payload can quote company records.
            payload_fingerprint=proposal.proposal_id,
        )
        self._audit.append(record)
        if self.audit_path is not None:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_path.open("a", encoding="utf-8") as handle:
                handle.write(record.to_json() + "\n")
        return record

    def _replace_status(self, proposal: ActionProposal, status: ActionStatus) -> ActionProposal:
        """Store a new proposal object rather than mutating the stored one."""
        updated = proposal.model_copy(update={"status": status})
        self._proposals[updated.proposal_id] = updated
        return updated

    # -- transitions ---------------------------------------------------------
    def register(self, proposal: ActionProposal) -> ActionProposal:
        """Record a freshly prepared proposal, idempotently.

        Re-registering the same proposal is a no-op rather than a reset: the id
        is a content hash, so an identical re-proposal after a Streamlit rerun is
        the *same* proposal, and resetting it would silently discard an approval
        the human had already given.
        """
        existing = self._proposals.get(proposal.proposal_id)
        if existing is not None:
            return existing
        if proposal.status != "pending_approval":
            raise ApprovalError(
                f"a proposal may only be registered as pending_approval, got {proposal.status!r}"
            )
        self._proposals[proposal.proposal_id] = proposal
        self._record("proposed", proposal, actor=proposal.requested_by)
        return proposal

    def reject(self, proposal_id: str, employee: EmployeeContext, *, reason: str = "") -> ActionProposal:
        proposal = self._require(proposal_id)
        if proposal.status in {"executed", "failed"}:
            raise ApprovalError(f"{proposal_id} already reached a terminal state ({proposal.status})")
        rejected = self._replace_status(proposal, "rejected")
        self._record("rejected", rejected, actor=employee.employee_id, detail=reason)
        return rejected

    def edit(
        self,
        proposal_id: str,
        employee: EmployeeContext,
        *,
        payload: dict[str, str],
        destination: str | None = None,
    ) -> ActionProposal:
        """Reject the original and return a new pending proposal.

        The new proposal must go through approval on its own. That is the point:
        the human approved a payload they read, so an edited payload is not
        covered by that approval and has to be shown again.
        """
        from company_assistant.tools.actions import propose_action  # local: avoids a cycle

        original = self._require(proposal_id)
        if original.status in {"executed", "failed"}:
            raise ApprovalError(f"{proposal_id} already reached a terminal state ({original.status})")

        result = propose_action(
            original.action_type,
            payload,
            employee,
            destination=destination or original.destination,
        )
        if result.status != "ok" or result.proposal is None:
            raise ApprovalError(f"edited proposal is not valid: {result.reason}")

        superseded = self._replace_status(original, "rejected")
        self._record("edited", superseded, actor=employee.employee_id,
                     detail=f"superseded by {result.proposal.proposal_id}")
        return self.register(result.proposal)

    def approve_and_execute(
        self,
        proposal_id: str,
        employee: EmployeeContext,
        *,
        executor: Executor = simulated_executor,
    ) -> tuple[ActionProposal, ExecutionResult]:
        """Approve one proposal and execute it, rechecking identity first.

        Idempotent: a second call for an already-executed proposal returns the
        recorded outcome instead of executing again. Streamlit can rerun this
        code path on any interaction, and a double-executed action is not
        recoverable by re-rendering a page.
        """
        proposal = self._require(proposal_id)

        if proposal.status in {"executed", "failed"}:
            recorded = self._results.get(proposal_id)
            if recorded is not None:
                return proposal, recorded
            raise ApprovalError(f"{proposal_id} is {proposal.status} but no outcome was recorded")
        if proposal.status == "rejected":
            raise ApprovalError(f"{proposal_id} was rejected and cannot be approved")
        if proposal.status != "pending_approval":
            raise ApprovalError(f"{proposal_id} is not pending approval (status {proposal.status})")

        # --- the recheck, immediately before execution ----------------------
        # Re-derived from the identity passed to THIS call, not from anything
        # stored with the proposal. A proposal can outlive the state that
        # produced it - a rerun, a re-login, a role change between drafting and
        # approving - so the permission that matters is the one held now.
        if employee.employee_id != proposal.requested_by:
            raise ApprovalError(
                f"{employee.employee_id} cannot approve a proposal requested by {proposal.requested_by}"
            )
        permitted = ACTION_APPROVERS.get(proposal.action_type, frozenset())
        if employee.role not in permitted:
            failed = self._replace_status(proposal, "failed")
            self._record("failed", failed, actor=employee.employee_id,
                         detail=f"role {employee.role} may not approve {proposal.action_type}")
            result = ExecutionResult(
                ok=False, detail=f"Role {employee.role} is not authorised to approve {proposal.action_type}."
            )
            self._results[proposal_id] = result
            return failed, result

        approved = self._replace_status(proposal, "approved")
        self._record("approved", approved, actor=employee.employee_id)

        try:
            result = executor(approved)
        except Exception as exc:  # noqa: BLE001 - a failed action must be recorded, not raised away
            failed = self._replace_status(approved, "failed")
            self._record("failed", failed, actor=employee.employee_id,
                         detail=f"{type(exc).__name__}: {str(exc)[:160]}")
            result = ExecutionResult(ok=False, detail=f"Execution failed: {type(exc).__name__}.")
            self._results[proposal_id] = result
            return failed, result

        if not result.ok:
            failed = self._replace_status(approved, "failed")
            self._record("failed", failed, actor=employee.employee_id, detail=result.detail)
            self._results[proposal_id] = result
            return failed, result

        executed = self._replace_status(approved, "executed")
        self._record("executed", executed, actor=employee.employee_id, detail=result.reference or result.detail)
        self._results[proposal_id] = result
        return executed, result

    def _require(self, proposal_id: str) -> ActionProposal:
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            # An unknown id is never treated as approvable. Approval must refer to
            # a proposal that was actually shown to a human.
            raise ApprovalError(f"no proposal registered with id {proposal_id!r}")
        return proposal
