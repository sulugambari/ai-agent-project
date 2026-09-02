"""One bounded agent, and a deterministic reading of what it did.

Two decisions shape this module.

**The Answer contract is derived from tool results, not from the model's claims.**
Status, citations and the proposal are all reconstructed by inspecting what the
tools actually returned. A model that says "I refused" is not evidence that it
refused, and a model that writes `DOC-HR-001` in its answer has not thereby
retrieved it. Citation fabrication is a hard release blocker (T-04), so a cited
id that never appeared in a tool result is dropped and the drop is recorded in
the trace rather than passed through.

**The candidate set is carried out of every turn.** F-4: a refusal does not prove
pre-retrieval filtering - only the admitted candidate set does. The Phase 7 trace
panel is the evidence for the project's most important access claim, so the ids
have to survive the agent, not just exist inside it.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import ToolCallLimitMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_groq import ChatGroq

from company_assistant.agent.prompt import SYSTEM_PROMPT
from company_assistant.database import DATABASE_PATH
from company_assistant.models import (ActionProposal, Answer, AnswerStatus, Citation,
                                      EmployeeContext, RetrievalMode)
from company_assistant.rag import VectorIndex
from company_assistant.tools import Toolset, build_toolset

#: Hard ceiling on tool calls per question. Caps worst-case latency and cost and
#: keeps the trace short enough for a human to actually audit, which is the point
#: of having a trace at all.
MAX_TOOL_CALLS = 6

#: Groq model used when `GROQ_MODEL` is unset. The D-001 bake-off compares this
#: against `openai/gpt-oss-120b`; the loser is not removed, so the comparison
#: stays reproducible in Phase 8.
DEFAULT_MODEL = "openai/gpt-oss-20b"

#: Deterministic decoding. This product is evaluated on whether it abstains,
#: resolves conflicts and refuses actions - behaviour that must not vary between
#: runs of the same case, or the evaluation measures sampling noise.
TEMPERATURE = 0.0

#: Matches the project's stable source ids wherever they appear in prose, so a
#: cited id can be checked against what was actually retrieved.
SOURCE_ID_PATTERN = re.compile(r"\b(?:DOC|SLACK|EMAIL|GH|GH-LIVE|DB)-[A-Z0-9-]*\d[A-Z0-9-]*\b")

#: Unicode characters models substitute for an ASCII hyphen when formatting.
#: This is not cosmetic. `gpt-oss` writes source ids with U+2011 NON-BREAKING
#: HYPHEN (`GH‑142`), so an id-matching pass over raw prose found nothing, every
#: citation was dropped, and a fully grounded four-source answer was labelled
#: `insufficient_evidence`. Extracting structured facts from generated prose
#: means normalising the prose first: the model chose a typographically better
#: hyphen and silently broke the citation contract.
_HYPHEN_LOOKALIKES = str.maketrans({
    "\u2010": "-",  # HYPHEN
    "\u2011": "-",  # NON-BREAKING HYPHEN  <- observed in practice
    "\u2012": "-",  # FIGURE DASH
    "\u2013": "-",  # EN DASH
    "\u2014": "-",  # EM DASH
    "\u2015": "-",  # HORIZONTAL BAR
    "\u2212": "-",  # MINUS SIGN
    "\u00a0": " ",  # NO-BREAK SPACE
})


def normalize_for_id_matching(text: str) -> str:
    """Fold hyphen look-alikes to ASCII so source ids can be recognised."""
    return text.translate(_HYPHEN_LOOKALIKES)


@dataclass
class TurnRecord:
    """What one tool call did, kept for the trace and for status derivation."""

    tool: str
    args: dict[str, Any]
    status: str = ""
    detail: str = ""
    source_ids: tuple[str, ...] = ()
    candidate_ids: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


def build_agent(
    employee: EmployeeContext,
    *,
    index: VectorIndex,
    model: str | None = None,
    database_path: Path = DATABASE_PATH,
    max_tool_calls: int = MAX_TOOL_CALLS,
    retrieval_mode: RetrievalMode = "hybrid",
) -> tuple[Any, Toolset]:
    """Create the agent for one employee, bounded and deterministic.

    The toolset is returned alongside it because the caller needs the same
    retrievers for the trace and for Phase 7's index-status disclosure.
    """
    toolset = build_toolset(employee, index=index, database_path=database_path,
                            retrieval_mode=retrieval_mode)
    llm = ChatGroq(model=model or os.getenv("GROQ_MODEL") or DEFAULT_MODEL, temperature=TEMPERATURE)
    agent = create_agent(
        llm,
        tools=list(toolset.tools),
        system_prompt=SYSTEM_PROMPT,
        # 'end' rather than 'continue': once the budget is spent the agent must
        # answer from what it has. Letting it continue with tools blocked invites
        # a loop of refused calls that burns model calls and says nothing new.
        middleware=[ToolCallLimitMiddleware(run_limit=max_tool_calls, exit_behavior="end")],
    )
    return agent, toolset


def _parse_tool_message(message: ToolMessage, args_by_id: dict[str, dict]) -> TurnRecord:
    """Read one tool result back into a structured record.

    Tool output is JSON by design (see `tools.schemas`), so this is parsing, not
    interpretation. A payload that will not parse is recorded as such rather than
    guessed at.
    """
    name = message.name or "unknown"
    args = args_by_id.get(str(message.tool_call_id), {})
    try:
        payload = json.loads(message.content if isinstance(message.content, str) else "{}")
    except (json.JSONDecodeError, TypeError):
        return TurnRecord(tool=name, args=args, status="unparseable",
                          detail=str(message.content)[:120])

    evidence = payload.get("evidence") or []
    source_ids = tuple(str(item.get("source_id", "")) for item in evidence if item.get("source_id"))
    if payload.get("case"):
        source_ids = (*source_ids, str(payload["case"].get("source_id", "")))
    for key in ("authoritative",):
        if payload.get(key):
            source_ids = (*source_ids, str(payload[key].get("source_id", "")))
    for item in payload.get("superseded") or []:
        source_ids = (*source_ids, str(item.get("source_id", "")))

    detail_bits: list[str] = []
    if payload.get("relevance"):
        detail_bits.append(f"relevance={payload['relevance']} coverage={payload.get('max_term_coverage')}")
    if payload.get("conflict_detected"):
        detail_bits.append("conflict_detected=true")
    if payload.get("verdict"):
        detail_bits.append(f"verdict={payload['verdict']}")
    if payload.get("source_freshness"):
        detail_bits.append(f"freshness={payload['source_freshness']}")
    if payload.get("reason"):
        detail_bits.append(str(payload["reason"])[:120])

    return TurnRecord(
        tool=name,
        args=args,
        status=str(payload.get("status", "")),
        detail=" · ".join(detail_bits),
        source_ids=tuple(sid for sid in source_ids if sid),
        candidate_ids=tuple(str(c) for c in (payload.get("candidate_ids") or [])),
        raw=payload,
    )


def _derive_status(records: list[TurnRecord], cited: list[str], text: str) -> AnswerStatus:
    """Decide the answer status from what the tools did, not from what was said.

    Ordering matters. A permission denial outranks an empty result, because
    "not permitted" and "does not exist" are different facts and the stronger
    claim must not be softened. A tool failure outranks both when nothing was
    retrieved at all, so an outage is never reported as absence (T-07).
    """
    if not records:
        return "insufficient_evidence"

    retrieved_anything = any(record.source_ids for record in records)

    # A turn whose purpose was to PREPARE AN ACTION is judged on whether the
    # proposal exists, not on whether company evidence was retrieved. "Prepare an
    # issue to track the Finance validation step" needs no citation to be a
    # correct, complete turn, so grading it by retrieval labelled a successful
    # proposal `insufficient_evidence` - which in the interface reads as though
    # the assistant had failed.
    prepared = [
        record for record in records
        if record.tool == "propose_action" and record.status == "ok" and record.raw.get("proposal")
    ]
    if prepared:
        return "answered"

    if any(record.status == "denied" for record in records) and not retrieved_anything:
        return "forbidden"
    if any(record.status in {"error", "unparseable"} for record in records) and not retrieved_anything:
        return "error"
    if not retrieved_anything:
        return "insufficient_evidence"

    # Evidence reached the model but the answer grounded none of it. Treating
    # that as "answered" would let an ungrounded answer inherit the credibility
    # of a successful retrieval.
    if not cited:
        return "insufficient_evidence"

    # An answer that says it could not find the thing asked for is not an
    # answer, however much unrelated evidence it cites alongside the refusal.
    # This is checked BEFORE the relevance signals and independently of them,
    # because relevance can be high for the wrong reason: asked for the
    # compensation review, retrieval scored 0.50 coverage on SLACK-ATLAS-103,
    # whose injected payload contains the words "confidential salary review".
    # The attack text inflates the relevance of the question it is hijacking, so
    # a strong relevance score cannot be allowed to overrule a stated refusal.
    if _reads_as_abstention(text):
        return "insufficient_evidence"

    return "answered"


#: Phrases that mark a refusal or an abstention.
#:
#: This list is load-bearing, and that is a known weakness: it reads the model's
#: own wording, which is exactly the kind of prose-parsing that already produced
#: one defect here (source ids written with U+2011). It is kept because the
#: failure is asymmetric. Matching only ever downgrades a status to
#: `insufficient_evidence`; it can never promote a refusal to `answered`. So a
#: false positive mislabels a real answer as cautious, while a miss mislabels a
#: refusal as an answer - and only the second one misleads an employee. The list
#: is therefore deliberately generous, and it is asserted against the evaluation
#: cases in the notebook so a wording the models actually use cannot go
#: unmatched silently.
#:
#: "could not locate" is here because `gpt-oss-120b` used precisely that phrase
#: to refuse the restricted HR record, and an earlier, tighter list missed it.
_ABSTENTION_MARKERS = (
    "could not find", "couldn't find", "could not locate", "couldn't locate",
    "cannot find", "cannot locate", "unable to find", "unable to locate",
    "no evidence", "not find any", "does not appear", "no record",
    "i do not know", "i don't know", "no information", "nothing in company",
    "unable to provide", "cannot provide", "no accessible", "not permitted to view",
    "did not find", "no such record", "no forecast", "not available in company",
)


def _reads_as_abstention(text: str) -> bool:
    lowered = normalize_for_id_matching(text).lower()
    return any(marker in lowered for marker in _ABSTENTION_MARKERS)


def _citations(records: list[TurnRecord], text: str) -> tuple[list[Citation], list[str]]:
    """Resolve cited ids against what was actually retrieved.

    Returns the resolvable citations and the ids the model produced that no tool
    ever returned. The second list is the T-04 evidence: a fabricated citation is
    dropped from the answer and named in the trace, never silently passed on.
    """
    retrieved: dict[str, dict] = {}
    for record in records:
        for item in record.raw.get("evidence") or []:
            if item.get("source_id"):
                retrieved[str(item["source_id"])] = item
        for key in ("authoritative",):
            if record.raw.get(key) and record.raw[key].get("source_id"):
                retrieved[str(record.raw[key]["source_id"])] = record.raw[key]
        for item in record.raw.get("superseded") or []:
            if item.get("source_id"):
                retrieved[str(item["source_id"])] = item
        case = record.raw.get("case")
        if case and case.get("source_id"):
            retrieved[str(case["source_id"])] = {
                "source_id": case["source_id"], "title": f"Support case {case.get('case_id')}: "
                f"{case.get('subject')}", "source_type": "database", "source_path": "data/database/company.db",
            }

    mentioned = list(dict.fromkeys(SOURCE_ID_PATTERN.findall(normalize_for_id_matching(text))))
    citations = [
        Citation(
            source_id=source_id,
            title=str(retrieved[source_id].get("title", source_id)),
            source_type=str(retrieved[source_id].get("source_type", "")),
            source_path=str(retrieved[source_id].get("source_path", "")),
            occurred_at=retrieved[source_id].get("occurred_at"),
        )
        for source_id in mentioned
        if source_id in retrieved
    ]
    fabricated = [source_id for source_id in mentioned if source_id not in retrieved]
    return citations, fabricated


def _proposal(records: list[TurnRecord]) -> ActionProposal | None:
    """The last proposal prepared this turn, if any. Never approved here."""
    for record in reversed(records):
        if record.tool == "propose_action" and record.raw.get("proposal"):
            return ActionProposal.model_validate(record.raw["proposal"])
    return None


def ask(
    question: str,
    employee: EmployeeContext,
    *,
    agent: Any,
    toolset: Toolset,
    history: list[Any] | None = None,
) -> tuple[Answer, list[Any]]:
    """Answer one question and return the shared contract plus the new history.

    `history` carries short-term conversation context. It is returned rather than
    stored so the caller owns it - Streamlit reruns its whole script per
    interaction, and hidden state inside the agent would be rebuilt or lost on
    every rerun.
    """
    messages = [*(history or []), HumanMessage(content=question)]

    try:
        result = agent.invoke({"messages": messages})
    except Exception as exc:  # noqa: BLE001 - a failed turn must still answer
        return (
            Answer(
                status="error",
                text=f"I could not complete this request: {type(exc).__name__}. "
                "No conclusion should be drawn from this failure.",
                retrieval_mode="hybrid",
                trace=[f"Agent invocation failed: {type(exc).__name__}: {str(exc)[:160]}"],
            ),
            messages,
        )

    produced = result["messages"]
    args_by_id: dict[str, dict] = {}
    for message in produced:
        if isinstance(message, AIMessage):
            for call in message.tool_calls or []:
                args_by_id[str(call.get("id"))] = dict(call.get("args") or {})

    records = [
        _parse_tool_message(message, args_by_id)
        for message in produced
        if isinstance(message, ToolMessage)
    ]

    final = next(
        (m for m in reversed(produced) if isinstance(m, AIMessage) and not m.tool_calls),
        None,
    )
    text = ""
    if final is not None:
        # `.text` is a property in langchain-core 1.x; older versions exposed it
        # as a method. Read the property and fall back rather than calling it.
        attribute = getattr(final, "text", None)
        text = attribute if isinstance(attribute, str) else str(final.content)

    citations, fabricated = _citations(records, text)
    status = _derive_status(records, [c.source_id for c in citations], text)

    index_status = toolset.knowledge_retriever.index_status()

    # --- the interface warning contract -----------------------------------
    # These four prefixes are a deliberate contract between the agent and the
    # interfaces: Phase 7 must show conflict and staleness warnings, and the
    # facts that justify them are known here and nowhere else. Prefixing them
    # means the interface filters on a stable token instead of re-deriving the
    # conditions or pattern-matching prose it does not own.
    warnings: list[str] = []
    for record in records:
        for hint in record.raw.get("conflicts") or []:
            warnings.append(f"CONFLICT: {hint.get('detail', '')}")
        if record.raw.get("relevance") in {"weak", "none"}:
            warnings.append(
                f"CAUTION: retrieved evidence only covers {record.raw.get('max_term_coverage')} "
                "of the question's terms; the company may hold no answer to this."
            )
        if record.raw.get("degraded"):
            warnings.append(
                f"STALE: {record.tool} served a degraded fallback rather than live data "
                f"({record.raw.get('detail', '')})."
            )
    if index_status.degraded:
        warnings.append("STALE: at least one indexed source came from a fallback, not a live fetch.")

    trace = [
        f"Employee: {employee.display_name} ({employee.role})",
        f"Tool calls: {len(records)} of {MAX_TOOL_CALLS} permitted",
    ]
    for position, record in enumerate(records, start=1):
        query = record.args.get("query") or record.args.get("case_id") or record.args.get("source_ids") or ""
        trace.append(f"  {position}. {record.tool}({query!r}) -> {record.status or 'no status'}"
                     + (f" · {record.detail}" if record.detail else ""))
        if record.candidate_ids:
            trace.append(f"     permitted candidates ({len(record.candidate_ids)}): "
                         f"{', '.join(record.candidate_ids)}")
        if record.source_ids:
            trace.append(f"     returned: {', '.join(record.source_ids)}")
    if len(records) >= MAX_TOOL_CALLS:
        trace.append(f"Tool budget of {MAX_TOOL_CALLS} was reached; the answer uses what was gathered.")
    if not citations and any(record.source_ids for record in records) and not _reads_as_abstention(text):
        # Evidence reached the model and the answer referenced none of it. Called
        # out rather than left implicit in the status: an uncited claim is what
        # T-04 is about, and it looks identical to a good answer from outside.
        trace.append("WARNING: evidence was retrieved but the answer cited no source id (T-04 risk)")
    if fabricated:
        # Kept loud. A dropped citation is a near miss on a release blocker, not
        # a formatting detail.
        trace.append(f"DROPPED unretrieved source id(s) cited by the model: {', '.join(fabricated)}")
    trace.extend(dict.fromkeys(warnings))  # de-duplicated, order preserved
    trace.append(f"Derived status: {status} (from tool outcomes, not from the answer text)")
    trace.append(f"Index: {index_status.describe()}")

    return (
        Answer(
            status=status,
            text=text,
            retrieval_mode="hybrid",
            citations=citations,
            trace=trace,
            action_proposal=_proposal(records),
        ),
        [*messages, *produced[len(messages):]],
    )
