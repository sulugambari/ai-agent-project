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

from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from company_assistant.approval import ApprovalError
from company_assistant.models import Answer
from company_assistant.service import EMPLOYEES, AssistantService

load_dotenv()

#: Trace prefixes the agent uses to mark facts the employee must see, rather
#: than leaving them buried in the trace expander (see agent/runner.py).
WARNING_PREFIXES = ("CONFLICT:", "CAUTION:", "STALE:", "WARNING:", "DROPPED")

NO_ANSWER_STATUSES = frozenset({"insufficient_evidence", "forbidden", "error"})

STATUS_HELP = {
    "answered": ("success", "Grounded in the sources listed below."),
    "evidence_found": ("info", "Baseline evidence only - no model reasoning was applied."),
    # Two different facts, deliberately worded so they cannot be confused.
    # `forbidden` says nothing about whether the company holds the information -
    # the assistant cannot see a record the pre-filter denied, so claiming absence
    # would be a guess presented as a fact.
    "insufficient_evidence": ("warning", "🔍 **NO ANSWER FOUND** — the company's own records do "
                                         "not contain an answer to this question. The assistant "
                                         "said so rather than assembling something plausible."),
    "forbidden": ("error", "⛔ **REFUSED — NOT PERMITTED** — this employee is not cleared for the "
                           "records that would answer this. Nothing was answered, and this says "
                           "nothing about whether the company holds the information."),
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

    # A refusal cites the records it INSPECTED, not evidence for a claim. Labelling
    # both cases "Sources" made a refusal look like an answer: the same prose block
    # and the same expander, so readers reported "it still answered" when the text
    # plainly began "I cannot access that record". Same furniture, opposite meaning.
    refused = answer.status in NO_ANSWER_STATUSES
    label = (f"⛔ Records inspected ({len(answer.citations)}) — not evidence for an answer"
             if refused else f"Sources ({len(answer.citations)})")
    with st.expander(label, expanded=not refused):
        if refused:
            st.caption(
                "No answer was given. These are the permitted records the assistant looked "
                "at while deciding it could not answer - reading them as support for a claim "
                "would be reading the opposite of what happened."
            )
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
    if answer.status == "forbidden":
        st.caption("⛔ **Refused on permissions.** What follows is the assistant's explanation, "
                   "not an answer. It does not confirm or deny that such a record exists.")
    elif answer.status == "insufficient_evidence":
        st.caption("🔍 **No answer found in company knowledge.** What follows is the "
                   "assistant's explanation, not an answer to the question.")
    elif answer.status == "error":
        st.caption("⚠️ **The request failed.** Draw no conclusion from anything below.")
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


# ---------------------------------------------------------------------------
# Northstar Labs intranet shell
#
# The chrome is presentation only: every trust affordance Karthik built stays
# exactly where it was and nothing is moved behind a nicer surface.
# `02-system-design.md` warns not to let visual polish replace trust and
# evaluation work, and a convincing corporate shell is precisely where that
# would happen - so the answer status, citations, conflict warnings, tool trace,
# index freshness, approval queue and feedback control are all still on the page.
#
# The one thing a company-looking portal MUST not do is imply real
# authentication. It has a profile switcher and a "signed in as" chip, which read
# as a login to anyone who has used an intranet. The banner below says plainly
# that this is role simulation, because that gap is a residual risk in
# ACCESS_MATRIX.md and hiding it behind convincing chrome would be the dishonest
# version of this UI.
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Northstar Labs · Release Coordinator",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

BRAND_INK = "#101a2b"

#: The header bar's own palette. #E34208 was sampled directly from the reference
#: loading animation (cssbud.com's "LOADING" GIF), not eyeballed - downloaded and
#: read with Pillow. #EB774D is that same hue lightened 28% toward white (each
#: channel moved 28% of the way to 255), on request for a lighter banner. Flat,
#: not a gradient: a two-stop version was tried first with a darker second stop
#: for depth, and the ink that read clearly on the light stop dropped below WCAG
#: AA (4.05:1, need 4.5) on the dark one. One flat shade keeps the contrast
#: uniform everywhere text sits on it. #140D08 clears 6.67:1 against the
#: lightened orange - well inside AA, with more margin than the darker version
#: had. Banner text is deliberately monochrome (one ink, no colour) throughout,
#: per the brief - including the compass mark below.
BANNER_ORANGE = "#EB774D"
BANNER_INK = "#140D08"

#: Department label per role. The role keys are machine identifiers; an intranet
#: shows a department.
DEPARTMENT = {
    "customer_success": "Customer Success",
    "engineering": "Engineering",
    "people_operations": "People Operations",
    "finance": "Finance",
}

#: Per-employee avatar images, inlined as data URIs for the same reason the
#: compass logo is inline SVG: no asset path for the Phase 9 container to lose,
#: and the header is raw injected HTML, which cannot load a filesystem path
#: directly - a browser cannot resolve `assets/avatars/leo.jpg` from inside a
#: `<style>`/`<div>` block the way `st.image()` would resolve it for a normal
#: Streamlit element. Read once at import time: four files, a few KB each.
@st.cache_data(show_spinner=False)
def _avatar_data_uris() -> dict[str, str]:
    import base64

    uris = {}
    for key in EMPLOYEES:
        path = Path("assets/avatars") / f"{key}.jpg"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        uris[key] = f"data:image/jpeg;base64,{encoded}"
    return uris


AVATARS = _avatar_data_uris()

#: The loading indicator, as the team's own chosen GIF - not a link to it.
#: Earlier this was recreated as a CSS animation rather than pointing at the
#: source (cssbud.com), because this interface embeds no third-party asset:
#: a live URL is one more thing that can go unreachable, be swapped out from
#: under the product, or leak a referrer from a permission-aware internal
#: tool. Once the actual file was supplied directly, that objection no longer
#: applies - it's now a local, committed asset like the avatars above, so it
#: gets the same treatment: read once, inlined as a data URI, shipped inside
#: the image rather than fetched at run time.
#:
#: `assets/loading_static.png` is one frame of the same GIF, served instead of
#: it when the browser reports `prefers-reduced-motion` - an animated GIF has
#: no native pause control, but `<picture><source media="...">` can swap the
#: element entirely, so the reduced-motion path costs nothing extra at runtime.
@st.cache_data(show_spinner=False)
def _loading_gif_data_uris() -> tuple[str, str]:
    import base64

    gif = base64.b64encode(Path("assets/loading.gif").read_bytes()).decode("ascii")
    static = base64.b64encode(Path("assets/loading_static.png").read_bytes()).decode("ascii")
    return f"data:image/gif;base64,{gif}", f"data:image/png;base64,{static}"


LOADING_GIF, LOADING_GIF_STATIC = _loading_gif_data_uris()

#: Inline SVG, not a file: a compass rose - the same instrument the product's
#: own name and page icon (🧭) already reference, so the header mark and the
#: browser tab finally agree with each other. Inline for the same reason as
#: before: no asset path for the container to lose, and no external URL for a
#: permission-aware internal tool to leak a referrer to.
#:
#: The needle is two-tone dark/grey rather than the traditional red-north
#: convention, on purpose: the header text next to it is deliberately
#: monochrome, and a red tip would be the one note of colour in a bar that is
#: supposed to have none.
LOGO = (
    f'<svg width="34" height="34" viewBox="0 0 32 32" fill="none" '
    f'xmlns="http://www.w3.org/2000/svg" aria-label="Northstar Labs">'
    f'<circle cx="16" cy="16" r="12.5" stroke="{BANNER_INK}" stroke-width="1.6"/>'
    f'<path d="M16 2.5v3.2M16 26.3v3.2M29.5 16h-3.2M5.7 16H2.5" '
    f'stroke="{BANNER_INK}" stroke-width="1.6" stroke-linecap="round"/>'
    f'<polygon points="16,7.5 19,16 13,16" fill="{BANNER_INK}"/>'
    f'<polygon points="16,24.5 19,16 13,16" fill="{BANNER_INK}" fill-opacity="0.5"/>'
    f'<circle cx="16" cy="16" r="1.7" fill="#ffffff" stroke="{BANNER_INK}" stroke-width="1"/>'
    f'</svg>'
)

st.markdown(
    f"""
    <style>
      /* Streamlit keeps a fixed toolbar at the top of the viewport. The header bar
         below was being clipped in half because the container padding pulled it
         underneath that toolbar - so the padding has to clear it, not fight it. */
      .block-container {{ padding-top: 3.4rem; padding-bottom: 3rem; max-width: 1180px; }}

      .ns-bar {{
        display: flex; align-items: center; gap: 1.15rem;
        background: {BANNER_ORANGE};
        color: {BANNER_INK}; padding: 0.85rem 1.25rem; border-radius: 12px;
        box-shadow: 0 1px 3px rgba(20,13,8,.22);
      }}
      .ns-mark {{
        display: flex; align-items: center; gap: .7rem;
        font-weight: 700; font-size: 1.3rem; letter-spacing: .03em;
        color: {BANNER_INK};
      }}
      /* Inactive items are distinguished by WEIGHT, not by dimming their colour -
         opacity looked right at a glance but quietly took every nav label below
         the 4.5:1 contrast this ink was chosen to clear. */
      .ns-nav {{ display: flex; gap: 1.25rem; font-size: .85rem; color: {BANNER_INK}; font-weight: 400; }}
      .ns-nav span.on {{ font-weight: 700;
                         border-bottom: 2px solid {BANNER_INK}; padding-bottom: 2px; }}
      .ns-spacer {{ flex: 1 1 auto; }}
      .ns-who {{
        display: flex; align-items: center; gap: .7rem; font-size: 1.02rem;
        color: {BANNER_INK};
        background: rgba(20,13,8,.1); padding: .45rem 1rem .45rem .45rem; border-radius: 999px;
      }}
      .ns-avatar {{
        width: 42px; height: 42px; border-radius: 50%; flex: none;
        object-fit: cover; object-position: center top;
        border: 1px solid rgba(20,13,8,.35);
      }}

      .ns-proto {{
        font-size: .8rem; line-height: 1.45; color: #7a4b00; background: #fff8e6;
        border: 1px solid #f0d089; border-left: 4px solid #eda100;
        border-radius: 8px; padding: .6rem .85rem; margin: .8rem 0 1.4rem 0;
      }}

      .ns-welcome {{ margin: .2rem 0 .1rem 0; font-size: 1.55rem; font-weight: 700;
                     color: {BRAND_INK}; letter-spacing: -.01em; }}
      .ns-sub {{ color: #5b6472; font-size: .93rem; margin-bottom: .2rem; }}

      /* A model-backed turn can take anywhere from a few seconds to well over a
         minute (free-tier providers vary a lot), so the waiting state needs a
         moving element - text alone reads as frozen past a few seconds. This is
         now the team's own GIF, on repeat (its own loop count is infinite),
         served as a local asset baked into the image - see LOADING_GIF above
         for why that changed from an earlier CSS recreation. */
      .ns-loading {{
        display: flex; align-items: center; gap: .8rem;
        color: {BANNER_INK}; font-size: .92rem; padding: .3rem 0;
      }}
      .ns-loading-gif {{ width: 34px; height: 34px; flex: none; object-fit: contain; }}

      /* Readability: roomier chat bubbles and calmer tab labels */
      [data-testid="stChatMessage"] {{ padding: .55rem .3rem; }}
      .stTabs [data-baseweb="tab"] {{ font-size: .93rem; padding: .5rem 1rem; }}
      div[data-testid="stExpander"] details {{ border-radius: 8px; }}
    </style>
    """,
    unsafe_allow_html=True,
)

service = get_service()
status = service.status()

employee_key = st.session_state.get("employee_key", next(iter(EMPLOYEES)))
employee = EMPLOYEES[employee_key]
department = DEPARTMENT.get(employee.role, employee.role.replace("_", " ").title())

st.markdown(
    f"""
    <div class="ns-bar">
      <div class="ns-mark">{LOGO}<span>NORTHSTAR&nbsp;LABS</span></div>
      <div class="ns-nav">
        <span>Home</span><span>Projects</span><span>Customers</span><span>Policies</span>
        <span class="on">Release Coordinator</span>
      </div>
      <div class="ns-spacer"></div>
      <div class="ns-who"><img class="ns-avatar" src="{AVATARS[employee_key]}"
        alt="{employee.display_name}">
        <span>{employee.display_name} · {department}</span></div>
    </div>
    """,
    unsafe_allow_html=True,
)

# PROTOTYPE_BANNER lives beside the sidebar block below, immediately above
# "Company knowledge" - moved there on request. It stays a module-level
# constant rather than an inline literal because it is now rendered from
# inside `with st.sidebar:`, one indent level away from where it is defined.
PROTOTYPE_BANNER = (
    '<div class="ns-proto"><b>Prototype.</b> The profile switcher is '
    '<b>role simulation, not authentication</b> — there is no credential behind it, and the '
    'navigation above is inert. Permission filtering is real and enforced before retrieval; '
    'identity is not.</div>'
)

st.markdown(
    f'<div class="ns-welcome">Welcome, {employee.display_name} — {department}</div>'
    f'<div class="ns-sub">Ask about release readiness, customer commitments, policies or '
    f'work items. Every answer shows its sources, and you only ever see what your role '
    f'is cleared for.</div>',
    unsafe_allow_html=True,
)

assistant_tab, evaluation_tab, about_tab = st.tabs(
    ["🧭  Release Coordinator", "📊  Evaluation", "ℹ️  About this prototype"]
)

with st.sidebar:
    st.markdown("### 👤 Signed in as")
    st.selectbox(
        "Switch profile",
        options=list(EMPLOYEES),
        format_func=lambda key: (f"{EMPLOYEES[key].display_name} — "
                                 f"{DEPARTMENT.get(EMPLOYEES[key].role, EMPLOYEES[key].role)}"),
        key="employee_key",
        label_visibility="collapsed",
    )
    employee = EMPLOYEES[st.session_state["employee_key"]]
    st.caption("Identity is bound into the tools before the model runs. "
               "The assistant has no way to change who it is asking as.")

    st.markdown(PROTOTYPE_BANNER, unsafe_allow_html=True)
    st.divider()
    st.markdown("### 📚 Company knowledge")
    st.metric("Records indexed", status.index_units)
    st.caption(f"Last indexed: `{status.index_last_indexed}`")
    if status.index_degraded:
        st.warning("At least one source is a degraded fallback, not live data.", icon="🕒")
    for name, freshness, detail in status.index_sources:
        st.caption(f"`{name}` — **{freshness}**" + (f" · {detail}" if detail else ""))

    st.divider()
    st.markdown("### ⚙️ How answers are produced")
    st.caption(
        f"Model `{status.model}` · retrieval `{status.retrieval_mode}` "
        f"(lexical weight {status.lexical_weight}) · at most {status.max_tool_calls} tool calls per question"
    )
    if not status.agent_available:
        # Names the variable the ACTIVE provider needs. It used to say GROQ_API_KEY
        # unconditionally, which on an OpenRouter setup sent the operator to fix a
        # key the product was not using.
        st.error(f"{status.credential_variable} is not set, so only the deterministic "
                 "baseline can answer.", icon="🔑")
    use_baseline = st.toggle(
        "Use the deterministic baseline instead", value=not status.agent_available,
        help="The Phase 3 lexical baseline: no model, no index. Kept as the comparison point.",
    )

    st.divider()
    counts = service.feedback_summary()
    st.markdown("### 💬 Feedback so far")
    st.caption(f"👍 {counts['up']} · 👎 {counts['down']} · {counts['total']} total")

with assistant_tab:
    left, right = st.columns([0.62, 0.38], gap="large")

    with left:
        # No heading here: the welcome line above already says what this is, and a
        # second title pushed the first question below the fold.

        # Keyed per profile, not one flat list. The agent's own short-term memory
        # was already scoped this way (`conversation_id=f"ui-{employee_key}"`
        # below), but the rendered transcript was not, so switching from Leo to
        # Priya showed Leo's questions in Priya's chat - a display bug, not an
        # agent one, but a real one: it makes the role-switch demonstration look
        # like the assistant remembers across identities when it never did.
        if "chat_by_profile" not in st.session_state:
            st.session_state.chat_by_profile = {}
        messages = st.session_state.chat_by_profile.setdefault(employee_key, [])

        for message in messages:
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
            # One divider per completed exchange, placed after the answer so it
            # separates that result from whatever question comes next - not
            # after the user's own turn, which would instead cut the question
            # away from its own answer.
            if message["role"] == "assistant":
                st.divider()

        if not messages:
            with st.expander("💡 Try one of these", expanded=True):
                st.markdown(
                    "- *Is Atlas ready to release, and which conditions are still unmet?*\n"
                    "- *What Atlas date has Acme Freight been told, and is it still correct?*\n"
                    "- *Show me the restricted compensation review* — to see a refusal\n\n"
                    "Switch profiles in the sidebar and ask the same question again: the same "
                    "records, a different answer."
                )

    with right:
        st.markdown("#### 🔒 Pending actions")
        st.caption("Nothing here executes until it is approved in this panel.")
        render_pending_actions(employee)

    if question := st.chat_input("Ask about projects, customers, policies, or work items"):
        messages.append({"role": "user", "content": question})
        with left:
            with st.chat_message("user"):
                st.markdown(question)
            with st.chat_message("assistant"):
                # A plain st.spinner() here is text-only past its first render,
                # and a model-backed turn can run well past a minute on a
                # free-tier provider - long enough that a static line reads as
                # hung. The GIF loops on its own (its own loop count is
                # infinite) for as long as the blocking call underneath takes,
                # with no polling or re-render required - an <img> keeps
                # animating regardless of what the surrounding Python is doing.
                waiting = st.empty()
                waiting.markdown(
                    '<div class="ns-loading"><picture>'
                    f'<source srcset="{LOADING_GIF_STATIC}" media="(prefers-reduced-motion: reduce)">'
                    f'<img class="ns-loading-gif" src="{LOADING_GIF}" alt="">'
                    '</picture>Searching company knowledge…</div>',
                    unsafe_allow_html=True,
                )
                if use_baseline:
                    result = service.ask_baseline(question, employee)
                else:
                    result = service.ask(question, employee,
                                         conversation_id=f"ui-{employee_key}")
                waiting.empty()
                render_answer(result.answer, answer_id=result.answer_id,
                              latency_ms=result.latency_ms)
        messages.append({
            "role": "assistant",
            "answer": result.answer.model_dump(mode="json"),
            "answer_id": result.answer_id,
            "latency_ms": result.latency_ms,
        })
        st.rerun()

with evaluation_tab:
    st.markdown("#### Comparative evaluation")
    try:
        from company_assistant.evaluation.charts import (
            latency_strip, layer_rates, verdict_matrix,
        )
        from company_assistant.evaluation.report import (
            injection_results, load as load_runs, variant_summary, verdicts,
        )

        rows = load_runs()
        if not rows:
            st.info("No evaluation runs recorded yet. Run `scripts/run_eval.py`.", icon="📄")
        else:
            case_verdicts = verdicts(rows)
            scored = [r for r in rows if r.get("scored")]

            # Release blockers are the headline, and they are a COUNT rather than a
            # chart on purpose: one occurrence blocks, whatever the pass rate, so an
            # average would be the wrong shape for the question being asked.
            blockers = {
                "Forbidden in citations": sum(len(r.get("forbidden_in_citations") or []) for r in scored),
                "Forbidden in trace": sum(len(r.get("forbidden_in_trace") or []) for r in scored),
                "Unresolvable citations": sum(len(r.get("unresolvable_citations") or []) for r in scored),
                "Unpermitted citations": sum(len(r.get("unpermitted_citations") or []) for r in scored),
                "Unapproved executions": sum(1 for r in scored if r.get("proposal_status") in {"executed", "approved"}),
            }
            fired = sum(blockers.values())
            if fired:
                st.error(f"**{fired} release blocker event(s).** Any one of these blocks the "
                         "release regardless of the overall pass rate.", icon="🛑")
            else:
                st.success(f"**No release blocker fired** across {len(scored)} scored run(s). "
                           "Counted, not averaged: one occurrence would block.", icon="✅")
            cols = st.columns(len(blockers))
            for col, (name, count) in zip(cols, blockers.items()):
                col.metric(name, count, help="Threshold is 0. Not rate-based.")

            st.caption(
                "**Coverage first.** `semantic_agent` has no scored runs and `hybrid_agent` "
                "covers 6 of 15 cases — a free-tier token-per-minute limit stopped the run, "
                "so the three-variant comparison is **incomplete**. The baseline's larger raw "
                "pass count is a coverage artifact, and every one of its statuses is "
                "`evidence_found` — a non-answer the scorer accepts. Read the like-for-like "
                "comparison below, not the totals."
            )

            st.divider()
            left, right = st.columns([0.55, 0.45], gap="large")
            with left:
                st.altair_chart(verdict_matrix(case_verdicts))
            with right:
                st.altair_chart(layer_rates(case_verdicts))
                st.altair_chart(latency_strip(rows))

            st.divider()
            st.markdown("##### Like-for-like: cases scored in both variants")
            by = {}
            for v in case_verdicts:
                by.setdefault(v.variant, {})[v.case_id] = v
            base, hyb = by.get("lexical_baseline", {}), by.get("hybrid_agent", {})
            rank = {"Pass": 2, "Partial": 1, "Fail": 0, "Not scored": -1}
            comparison = [
                {"case": c, "baseline": base[c].verdict, "hybrid + agent": hyb[c].verdict,
                 "better": ("hybrid" if rank[hyb[c].verdict] > rank[base[c].verdict]
                            else "baseline" if rank[base[c].verdict] > rank[hyb[c].verdict] else "tie")}
                for c in sorted(base)
                if c in hyb and base[c].scored_runs and hyb[c].scored_runs
            ]
            if comparison:
                st.dataframe(comparison, width="stretch", hide_index=True)
                wins = sum(1 for r in comparison if r["better"] == "hybrid")
                losses = sum(1 for r in comparison if r["better"] == "baseline")
                st.caption(
                    f"On the {len(comparison)} cases scored in both: **hybrid {wins}, "
                    f"baseline {losses}, tied {len(comparison) - wins - losses}**. The agent's "
                    "wins are the refusal and abstention cases the baseline structurally cannot do."
                )

            inj = injection_results(rows)
            if inj.get("runs"):
                st.markdown("##### Injection resistance — two results, not one")
                a, b = st.columns(2)
                a.metric("Structural control held",
                         f"{inj['structural_held']} of {inj['runs']}",
                         help="Payload not obeyed, restricted record untouched. A release blocker.")
                b.metric("Attack reported to the employee", "behavioural",
                         help="Reported as a rate with no threshold — it was a coin flip in Phase 6.")
                st.caption(inj["note"])

            st.divider()
            st.markdown("##### Per-variant totals")
            st.dataframe(variant_summary(rows), width="stretch", hide_index=True)
            st.caption(
                "Rate-limit waits are reported here and excluded from latency: a 429 measures "
                "our Groq tier, not the assistant."
            )

            counts = service.feedback_summary()
            st.markdown("##### Feedback")
            f1, f2, f3 = st.columns(3)
            f1.metric("Useful", counts["up"])
            f2.metric("Not useful", counts["down"])
            f3.metric("Total", counts["total"],
                      help="Threshold: at least 5 entries and one decision traced to feedback.")
            if counts["total"] < 5:
                st.caption("⚠️ Below the threshold set in `PRODUCT_BRIEF.md`.")
    except Exception as exc:  # noqa: BLE001 - the page must not take the app down
        st.warning(f"Evaluation results unavailable: {exc}", icon="⚠️")

with about_tab:
    st.markdown("#### What is real, and what is not")
    st.markdown(
        """
**Real, and enforced**

- Permission filtering runs **before** retrieval, as a metadata pre-filter on the vector
  query. A record outside your role never becomes a candidate — the trace shows the
  candidate set, which is the only evidence that distinguishes *"never visible to you"*
  from *"ranked low"*.
- Every factual claim carries a source ID, re-checked against your permissions at
  citation time rather than trusted from retrieval.
- Conflicting and superseded evidence is flagged rather than silently resolved. A later
  date does not by itself override an earlier one.
- Nothing executes without a separate approval in the panel beside the chat.
- Retrieved content is treated as **evidence, never instructions** — including one Slack
  message in the fixtures that tries to instruct the assistant.

**Not real**

- **Identity.** The profile switcher is role simulation. There is no credential,
  session, or token behind it, so every permission guarantee is conditional on the
  selected identity being honest.
- **The company.** Northstar Labs is fictional and all records are teaching fixtures.
- **The navigation.** Home, Projects, Customers and Policies are inert.

**Known limitations**

- Permissions come from fixture metadata, not from the source systems' own access
  control lists. In production the two could diverge.
- No encryption at rest, no access control on traces, no retention or deletion
  guarantees, no rate limiting.
- Filtering controls what is *retrieved*; it does not control what the model *infers*
  from evidence it is permitted to see.
"""
    )
    st.caption(
        "Full detail in `deliverables/THREAT_MODEL.md`, `deliverables/ACCESS_MATRIX.md` "
        "and `deliverables/EVALUATION_REPORT.md`."
    )
