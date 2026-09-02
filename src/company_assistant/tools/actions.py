"""Action proposal - prepares an operation that this package cannot perform.

There is no execution function anywhere in `company_assistant.tools`. That is
the design, not an omission: the only transition out of `pending_approval` is
step 6.4's approval gate, driven by a separate user interaction. A tool that
could both draft and run an action would make the approval boundary advisory,
and T-05 (unapproved action execution) is a hard release blocker.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from company_assistant.models import ActionProposal, EmployeeContext
from company_assistant.tools.schemas import ProposalResult

#: Action types the product supports, with the payload each one requires. An
#: allow-list rather than free-form text: an action whose shape is unknown
#: cannot have its destination and effect shown before approval, and an approval
#: given without seeing those is not informed consent.
ActionType = Literal["github_issue", "escalation_note", "status_update"]

REQUIRED_PAYLOAD: dict[str, tuple[str, ...]] = {
    "github_issue": ("title", "body"),
    "escalation_note": ("subject", "body", "recipient_role"),
    "status_update": ("subject", "body"),
}

EXPECTED_EFFECT: dict[str, str] = {
    "github_issue": "Creates one new issue in the destination repository. Nothing else is modified.",
    "escalation_note": "Records one escalation note addressed to the named internal role. No message is sent.",
    "status_update": "Records one proposed status update for human review. No source record is changed.",
}

#: Destinations the product may target. Anything else is refused: a destination
#: is where an irreversible effect lands, so it is decided by configuration and
#: by the human approving, never by whatever a model produced.
ALLOWED_DESTINATIONS: frozenset[str] = frozenset(
    {"sulugambari/ai-agent-project", "internal://escalations", "internal://status-updates"}
)

DEFAULT_DESTINATIONS: dict[str, str] = {
    "github_issue": "sulugambari/ai-agent-project",
    "escalation_note": "internal://escalations",
    "status_update": "internal://status-updates",
}

#: Payload values are shown to a human before approval, so they must be short
#: enough to actually be read. A wall of text is an approval that was not given.
MAX_FIELD_CHARS = 4000


def proposal_id_for(
    action_type: str, destination: str, payload: dict, requested_by: str
) -> str:
    """Stable id over the exact operation, so re-proposing does not multiply.

    Deterministic on purpose: it doubles as an idempotency key. Streamlit reruns
    the whole script on every interaction, so an id derived from time or a
    counter would produce a fresh "pending" proposal on each rerun and the
    approved one would drift away from the one on screen.
    """
    blob = json.dumps(
        {
            "action_type": action_type,
            "destination": destination,
            "payload": {key: payload[key] for key in sorted(payload)},
            "requested_by": requested_by,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return f"prop-{hashlib.sha256(blob.encode('utf-8')).hexdigest()[:12]}"


def render_preview(proposal: ActionProposal) -> str:
    """Exact operation, destination, payload and expected effect, in that order.

    Required before approval: the human has to be able to see what they are
    authorising without reading the trace or the code.
    """
    lines = [
        f"Operation:   {proposal.action_type}",
        f"Destination: {proposal.destination}",
        f"Requested by: {proposal.requested_by}",
        "Payload:",
    ]
    lines.extend(f"  {key}: {proposal.payload[key]!r}" for key in sorted(proposal.payload))
    lines.append(f"Expected effect: {EXPECTED_EFFECT.get(proposal.action_type, 'Unknown.')}")
    lines.append("Status: pending_approval - nothing has run.")
    return "\n".join(lines)


def propose_action(
    action_type: str,
    payload: dict[str, str],
    employee: EmployeeContext,
    *,
    destination: str | None = None,
) -> ProposalResult:
    """Prepare one action for human approval. Never performs it.

    The returned proposal is always `pending_approval`; this function has no
    parameter that can produce any other status. Retrieved document text
    therefore cannot approve anything, no matter how it is phrased - the
    approval path does not pass through here at all (T-01, T-05).
    """
    normalized_type = (action_type or "").strip()
    if normalized_type not in REQUIRED_PAYLOAD:
        return ProposalResult(
            status="error",
            reason=f"Unsupported action type {normalized_type!r}. Supported: {', '.join(sorted(REQUIRED_PAYLOAD))}.",
        )

    target = (destination or DEFAULT_DESTINATIONS[normalized_type]).strip()
    if target not in ALLOWED_DESTINATIONS:
        return ProposalResult(
            status="denied",
            reason=f"Destination {target!r} is not an approved target for this product.",
        )

    payload = payload or {}
    missing = [field for field in REQUIRED_PAYLOAD[normalized_type] if not str(payload.get(field, "")).strip()]
    if missing:
        return ProposalResult(
            status="error",
            reason=f"Action {normalized_type} requires non-empty {', '.join(missing)}.",
        )

    cleaned: dict[str, str | int | float | bool | None] = {}
    for field in REQUIRED_PAYLOAD[normalized_type]:
        value = str(payload[field]).strip()
        if len(value) > MAX_FIELD_CHARS:
            return ProposalResult(
                status="error",
                reason=f"Field {field!r} exceeds {MAX_FIELD_CHARS} characters; shorten it so a human can review it.",
            )
        cleaned[field] = value

    proposal = ActionProposal(
        proposal_id=proposal_id_for(normalized_type, target, dict(cleaned), employee.employee_id),
        action_type=normalized_type,
        destination=target,
        payload=cleaned,
        requested_by=employee.employee_id,
        status="pending_approval",
    )
    return ProposalResult(status="ok", proposal=proposal, preview=render_preview(proposal))
