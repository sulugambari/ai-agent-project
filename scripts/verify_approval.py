"""Step 10.3 evidence: the approval gate's outcomes, with no model call.

The agent leg is already established: EVAL-010 prepared a pending proposal on
3 of 3 agent runs today (github_issue -> sulugambari/ai-agent-project, state
pending_approval, nothing executed) - the case that never completed once on Groq.
What this exercises is the GATE those proposals hand off to.

Two design properties are measured rather than assumed, because a first version of
this script asserted the opposite of both and was wrong:

* `approve_and_execute` is IDEMPOTENT by design, not raising. Streamlit reruns the
  whole script on any interaction, and a double-executed action is not recoverable
  by re-rendering a page. So the property is "executed exactly once", which needs a
  counting executor to see - an exception check cannot tell a refusal from a no-op.
* Proposal ids are derived from CONTENT, so an identical re-proposal keeps its id.
  Distinct proposals therefore need distinct payloads.
"""
from dotenv import load_dotenv
load_dotenv("/home/sulu/Neuefisch_wsl/ai-agent-project/.env")
from company_assistant.approval import ApprovalError, ExecutionResult, simulated_executor
from company_assistant.models import ActionProposal
from company_assistant.service import EMPLOYEES, AssistantService
from company_assistant.tools.actions import propose_action

leo, maya = EMPLOYEES["leo"], EMPLOYEES["maya"]
service = AssistantService()
checks = []
executions: list[str] = []

def counting_executor(proposal: ActionProposal) -> ExecutionResult:
    executions.append(proposal.proposal_id)
    return simulated_executor(proposal)

def check(name, passed, detail=""):
    checks.append(passed)
    print(f"  {'PASS' if passed else 'FAIL'}  {name}" + (f"  -  {detail}" if detail else ""))

def make(tag: str) -> ActionProposal:
    """The same tool call the agent makes, invoked directly (step 6.2 style)."""
    result = propose_action(
        "github_issue",
        {"title": f"Request Finance validation of the Atlas reconciliation fix [{tag}]",
         "body": "GH-142 is open and DOC-ATLAS-403 lists Finance validation as unmet."},
        leo,
    )
    p = result.proposal
    p = p if isinstance(p, ActionProposal) else ActionProposal.model_validate(p)
    service.approvals.register(p)
    return p

p = make("a")
check("prepared PENDING, never executed", p.status == "pending_approval" and not executions,
      f"{p.action_type} -> {p.destination}")
check("payload and destination both visible before approval",
      bool(p.payload) and bool(p.destination), ", ".join(p.payload))
check("appears in the pending queue the interface renders",
      any(q.proposal_id == p.proposal_id for q in service.pending_proposals()))

executed, outcome = service.approve(p.proposal_id, leo, executor=counting_executor)
check("APPROVED -> executed exactly once",
      executed.status == "executed" and outcome.ok and executions.count(p.proposal_id) == 1)
check("the reference is visibly simulated, not a real URL",
      "simulated" in str(outcome.detail).lower(), str(outcome.detail)[:64])

service.approve(p.proposal_id, leo, executor=counting_executor)
service.approve(p.proposal_id, leo, executor=counting_executor)
check("re-approving twice more does NOT execute again",
      executions.count(p.proposal_id) == 1,
      f"executor invoked {executions.count(p.proposal_id)}x across 3 approvals")

p2 = make("b")
check("REJECTED -> not executed",
      service.reject(p2.proposal_id, leo, reason="not needed").status == "rejected"
      and p2.proposal_id not in executions)
try:
    service.approve(p2.proposal_id, leo, executor=counting_executor); revived = True
except ApprovalError:
    revived = False
check("a rejected proposal cannot later be approved",
      not revived and p2.proposal_id not in executions)

p3 = make("c")
replacement = service.edit_proposal(p3.proposal_id, leo, payload={**p3.payload, "title": "EDITED"})
check("EDITED -> a NEW proposal that still needs approval, original not executed",
      replacement.proposal_id != p3.proposal_id
      and replacement.status == "pending_approval"
      and p3.proposal_id not in executions,
      f"{p3.proposal_id[:18]} -> {replacement.proposal_id[:18]}")

p4 = make("d")
try:
    service.approve(p4.proposal_id, maya, executor=counting_executor); crossed, msg = True, ""
except ApprovalError as exc:
    crossed, msg = False, str(exc)
check("identity rechecked AT the gate: Maya cannot approve Leo's proposal",
      not crossed and p4.proposal_id not in executions, msg[:70])

from company_assistant.tools import build_toolset
names = build_toolset(leo, index=service.index()).names
check("no tool in the agent's toolset can execute anything",
      not any(w in n for n in names for w in ("execute", "approve", "create_", "write")),
      f"tools: {', '.join(names)}")

print(f"\n{sum(checks)}/{len(checks)} approval-boundary checks pass")
print(f"total executions across the whole run: {len(executions)} "
      f"(one, for the single approval that was authorised)")
