"""Streamlit chat interface for the Northstar internal assistant.

Everything that matters here is a trust-boundary display decision, not layout.
The interface has to make four things visible that a plausible-sounding answer
would otherwise hide:

* **who is asking** - identity drives what was even retrievable;
* **what the answer is worth** - status, plus conflict and staleness warnings;
* **where every fact came from** - openable citations with stable source ids;
* **what the assistant actually did** - the tool trace and, crucially, the
  permitted candidate set, which is the only evidence that filtering happened
  before retrieval rather than after (F-4).

Streamlit reruns this entire script on every interaction. That single fact
shapes the state handling: the service is cached as a resource so the ~90 MB
embedding model is loaded once, proposals are held immutably in session state
keyed by `proposal_id`, and approval sits inside a form so a rerun cannot
re-trigger it.
"""

from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

from company_assistant.approval import ApprovalError
from company_assistant.models import Answer
from company_assistant.service import EMPLOYEES, AssistantService

load_dotenv()

#: Trace prefixes the agent uses to mark facts the employee must see, rather
#: than leaving them buried in the trace expander (see agent/runner.py).
WARNING_PREFIXES = ("CONFLICT:", "CAUTION:", "STALE:", "WARNING:", "DROPPED")

STATUS_HELP = {
    "answered": ("success", "Grounded in the sources listed below."),
    "evidence_found": ("info", "Baseline evidence only - no model reasoning was applied."),
    "insufficient_evidence": ("warning", "The assistant did not find enough permitted evidence, and said so."),
    "forbidden": ("error", "This employee is not cleared for the records that would answer this."),
    "error": ("error", "Something failed. Draw no conclusion from this answer."),
}


@st.cache_resource(show_spinner="Loading the retrieval index...")
def get_service() -> AssistantService:
    """One service for the session.

    `@st.cache_resource` rather than a module global: without it every keystroke
    would reload the embedding model, which step 5.2 measured at 7.3 s of cold
    start against 23 ms of warm retrieval - roughly 300x, and the difference
    between a product that feels instant and one that feels broken.
    """
    return AssistantService()


def render_warnings(answer: Answer) -> None:
    """Surface conflict and staleness notices above the answer text.

    Above, not inside an expander: a warning that the current refund limit may be
    superseded is worth nothing if the reader has to go looking for it.
    """
    for line in answer.trace:
        if not line.startswith(WARNING_PREFIXES):
            continue
        if line.startswith("STALE:"):
            st.warning(f"Freshness - {line.split(':', 1)[1].strip()}", icon="🕒")
        elif line.startswith("CONFLICT:"):
            st.warning(f"Sources disagree - {line.split(':', 1)[1].strip()}", icon="⚖️")
        elif line.startswith("CAUTION:"):
            st.info(line.split(":", 1)[1].strip(), icon="❓")
        else:
            st.error(line, icon="⚠️")


def render_citations(answer: Answer) -> None:
    """List every cited source with a resolvable path.

    Expanded by default. Citations are the product's core trust claim, so hiding
    them behind a click makes the untrustworthy case (no citations) visually
    identical to the trustworthy one.
    """
    if not answer.citations:
        if answer.status in {"answered", "evidence_found"}:
            st.caption("No sources cited - treat this answer with suspicion.")
        return
    with st.expander(f"Sources ({len(answer.citations)})", expanded=True):
        for citation in answer.citations:
            date = citation.occurred_at.date().isoformat() if citation.occurred_at else "no date"
            path = citation.source_path
            location = (
                f"[{path}]({path})" if path.startswith(("http://", "https://")) else f"`{path}`"
            )
            st.markdown(
                f"- **{citation.source_id}** — {citation.title} "
                f"(`{citation.source_type}`, {date})<br>{location}",
                unsafe_allow_html=True,
            )


def render_answer(answer: Answer, *, answer_id: str | None = None, latency_ms: float | None = None) -> None:
    """Render one complete answer, including everything needed to distrust it."""
    kind, explanation = STATUS_HELP.get(answer.status, ("info", ""))
    getattr(st, kind)(f"**{answer.status}** — {explanation}")
    meta = f"Retrieval: `{answer.retrieval_mode}`"
    if latency_ms is not None:
        meta += f" · {latency_ms / 1000:.1f} s"
    if answer_id:
        meta += f" · `{answer_id}`"
    st.caption(meta)

    render_warnings(answer)
    st.markdown(answer.text or "_The assistant returned no text._")
    render_citations(answer)

    with st.expander("What the assistant did (tool trace)"):
        st.caption(
            "`permitted candidates` is the set of records the employee may see that were "
            "scored. A record absent from it was never visible — which is the evidence that "
            "filtering happened before retrieval, not after."
        )
        for step in answer.trace:
            st.markdown(f"- {step}")

    if answer.action_proposal is not None:
        st.info(
            f"An action was prepared and is **awaiting approval**: "
            f"`{answer.action_proposal.action_type}` → `{answer.action_proposal.destination}`. "
            "Approve it in the **Pending actions** panel below the conversation.",
            icon="🔒",
        )


def render_feedback(answer_id: str, retrieval_mode: str) -> None:
    """Rating plus a closed reason list, submitted as a form.

    A form so the rating and the reason arrive together in one rerun; separate
    buttons would persist a rating with whatever reason happened to be selected.
    Only five fields are stored and the question text is not among them - a
    feedback file that accumulated questions would become a second copy of the
    company's private knowledge, outside the permission model protecting the first.
    """
    service = get_service()
    if st.session_state.get(f"rated-{answer_id}"):
        st.caption("Feedback recorded. Thank you.")
        return
    with st.form(f"feedback-{answer_id}", clear_on_submit=True):
        columns = st.columns([1, 3])
        rating = columns[0].radio("Was this useful?", ["up", "down"],
                                  format_func=lambda value: "👍" if value == "up" else "👎",
                                  horizontal=True, key=f"rating-{answer_id}")
        reason = columns[1].selectbox(
            "Reason", ["correct", "wrong_answer", "missing_source", "stale_source",
                       "should_have_refused", "too_slow", "unhelpful", "other"],
            key=f"reason-{answer_id}",
        )
        if st.form_submit_button("Send feedback"):
            service.record_feedback(answer_id, rating, reason=reason, retrieval_mode=retrieval_mode)
            st.session_state[f"rated-{answer_id}"] = True
            st.rerun()


def render_pending_actions(employee) -> None:
    """Approval controls, deliberately outside the chat input (step 7.4).

    Separated from the conversation on purpose. Approval must be its own user
    interaction: if it lived in the chat flow, then sending a message and
    authorising an action would be the same gesture, and 'a separate approval'
    would be a claim about layout rather than about behaviour (T-05).
    """
    service = get_service()
    pending = service.pending_proposals()
    st.divider()
    st.subheader("Pending actions")
    if not pending:
        st.caption("Nothing is awaiting approval. The assistant cannot execute anything on its own.")
        return

    for proposal in pending:
        with st.container(border=True):
            st.markdown(f"**{proposal.action_type}** → `{proposal.destination}`")
            st.caption(f"Proposal `{proposal.proposal_id}` · requested by `{proposal.requested_by}`")
            with st.form(f"approve-{proposal.proposal_id}"):
                st.caption("Review the exact payload. You may edit it before approving; "
                           "editing replaces this proposal with a new one that needs approval again.")
                edited = {
                    field: st.text_area(field, value=str(value), key=f"{proposal.proposal_id}-{field}")
                    for field, value in proposal.payload.items()
                }
                approve, reject = st.columns(2)
                approved = approve.form_submit_button("Approve and execute", type="primary")
                rejected = reject.form_submit_button("Reject")

                if approved:
                    changed = edited != {k: str(v) for k, v in proposal.payload.items()}
                    try:
                        if changed:
                            replacement = service.edit_proposal(
                                proposal.proposal_id, employee, payload=edited
                            )
                            st.warning(
                                f"The payload changed, so proposal `{replacement.proposal_id}` "
                                "replaced it and still needs approval. Nothing was executed.",
                                icon="✏️",
                            )
                        else:
                            executed, outcome = service.approve(proposal.proposal_id, employee)
                            if outcome.ok:
                                st.success(f"{executed.status}: {outcome.detail}")
                            else:
                                st.error(f"{executed.status}: {outcome.detail}")
                    except ApprovalError as exc:
                        st.error(str(exc))
                    st.rerun()

                if rejected:
                    try:
                        service.reject(proposal.proposal_id, employee, reason="rejected in the interface")
                        st.info("Rejected. Nothing was performed.")
                    except ApprovalError as exc:
                        st.error(str(exc))
                    st.rerun()


st.set_page_config(page_title="Northstar Release Coordinator", page_icon="🧭", layout="centered")
st.title("Northstar Release Coordinator")
st.caption("Answers from Northstar Labs' private knowledge — with sources, permissions, and refusals.")

service = get_service()
status = service.status()

with st.sidebar:
    st.header("Who is asking")
    employee_key = st.selectbox(
        "Employee profile",
        options=list(EMPLOYEES),
        format_func=lambda key: f"{EMPLOYEES[key].display_name} — {EMPLOYEES[key].role}",
    )
    employee = EMPLOYEES[employee_key]
    st.caption("Identity is bound into the tools before the model runs. "
               "The assistant has no way to change who it is asking as.")

    st.header("Index")
    st.metric("Indexed units", status.index_units)
    st.caption(f"Last indexed: `{status.index_last_indexed}`")
    if status.index_degraded:
        st.warning("At least one source is a degraded fallback, not live data.", icon="🕒")
    for name, freshness, detail in status.index_sources:
        st.caption(f"`{name}` — **{freshness}**" + (f" · {detail}" if detail else ""))

    st.header("Configuration")
    st.caption(
        f"Model `{status.model}` · retrieval `{status.retrieval_mode}` "
        f"(lexical weight {status.lexical_weight}) · at most {status.max_tool_calls} tool calls per question"
    )
    if not status.agent_available:
        st.error("GROQ_API_KEY is not set, so only the deterministic baseline can answer.", icon="🔑")
    use_baseline = st.toggle(
        "Use the deterministic baseline instead", value=not status.agent_available,
        help="The Phase 3 lexical baseline: no model, no index. Kept as the comparison point.",
    )

    counts = service.feedback_summary()
    st.header("Feedback")
    st.caption(f"👍 {counts['up']} · 👎 {counts['down']} · {counts['total']} total")

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message["role"] == "user":
            st.markdown(message["content"])
        else:
            render_answer(
                Answer.model_validate(message["answer"]),
                answer_id=message.get("answer_id"),
                latency_ms=message.get("latency_ms"),
            )
            render_feedback(message["answer_id"], message["answer"]["retrieval_mode"])

if question := st.chat_input("Ask about projects, customers, policies, or work items"):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"), st.spinner("Searching company knowledge..."):
        if use_baseline:
            result = service.ask_baseline(question, employee)
        else:
            result = service.ask(question, employee, conversation_id=f"ui-{employee_key}")
        render_answer(result.answer, answer_id=result.answer_id, latency_ms=result.latency_ms)

    st.session_state.messages.append({
        "role": "assistant",
        "answer": result.answer.model_dump(mode="json"),
        "answer_id": result.answer_id,
        "latency_ms": result.latency_ms,
    })
    st.rerun()

render_pending_actions(employee)
