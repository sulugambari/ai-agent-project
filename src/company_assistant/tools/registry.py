"""Binding of the tool set to one employee identity.

Why identity is a closure and not a tool argument
-------------------------------------------------
`EmployeeContext` never appears in any tool's `args_schema`. If it did, the
identity under which retrieval runs would be a value the model produces - and
the model's output is influenced by retrieved content, which on this corpus
includes `SLACK-ATLAS-103` telling the reader to fetch the confidential salary
review. A model-supplied role would make privilege escalation a matter of the
model being persuaded. Binding identity at construction time means the agent has
no vocabulary for changing who it is (D-002).

Every callable here is also exported unbound, taking `employee` explicitly, so
step 6.2 can call each one directly with normal, denied, empty and failure inputs
before the agent is allowed anywhere near them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from company_assistant.database import DATABASE_PATH
from company_assistant.models import EmployeeContext, RetrievalMode
from company_assistant.rag import (COMPANY_KNOWLEDGE, DEFAULT_LIMIT, PROJECT_BOARD,
                                   HybridRetriever, Retriever, VectorIndex)
from company_assistant.tools.actions import REQUIRED_PAYLOAD, propose_action
from company_assistant.tools.comparison import compare_sources
from company_assistant.tools.knowledge import search_company_knowledge
from company_assistant.tools.support import get_support_case
from company_assistant.tools.work_items import search_work_items
from company_assistant.rag.hybrid import (
    DEFAULT_LEXICAL_WEIGHT as rag_default_weight,
)

#: D-006 selected hybrid with a lexical weight of 0.6 as the product default,
#: after re-measuring ten questions; `rag.hybrid.DEFAULT_LEXICAL_WEIGHT` is still
#: 0.5. Passed explicitly so the tools run the configuration the team actually
#: chose rather than the library default that happens to be in the code.
#: Kept as a named constant so the decided value is greppable from the tool layer,
#: but asserted equal to the retrieval default so the two cannot drift apart again.
#: F-15.1 was exactly that drift, and a comment would not have caught it.
DECIDED_LEXICAL_WEIGHT = 0.6
assert DECIDED_LEXICAL_WEIGHT == rag_default_weight, (
    f"tool layer expects lexical weight {DECIDED_LEXICAL_WEIGHT} but "
    f"rag.hybrid defaults to {rag_default_weight}; D-006 selected 0.6"
)


class KnowledgeSearchArgs(BaseModel):
    query: str = Field(description="What to look for in company knowledge, in natural language.")


class WorkItemSearchArgs(BaseModel):
    query: str = Field(description="What to look for among GitHub work items, in natural language.")


class SupportCaseArgs(BaseModel):
    case_id: str = Field(description="Exact support case id, for example 'CASE-4471'. No other input is accepted.")


class CompareSourcesArgs(BaseModel):
    source_ids: list[str] = Field(
        description="Two or more source ids returned by a search tool, to reconcile for staleness and supersession."
    )


class ProposeActionArgs(BaseModel):
    action_type: Literal["github_issue", "escalation_note", "status_update"] = Field(
        description="Which action to prepare."
    )
    payload: dict[str, str] = Field(
        description="Action fields. github_issue: title, body. escalation_note: subject, body, recipient_role. status_update: subject, body."
    )
    destination: str | None = Field(
        default=None, description="Optional explicit destination; the product default is used when omitted."
    )


def _serialize(result: BaseModel) -> str:
    """Tool output as JSON, so the model sees structure rather than prose.

    Keeps the tool's own assertions (`status`, `reason`) syntactically separate
    from untrusted company content (`excerpt`), which is what lets the system
    prompt label one and not the other.
    """
    return result.model_dump_json(indent=None, exclude_none=True)


@dataclass(frozen=True)
class Toolset:
    """The five tools bound to one identity, plus what the trace needs."""

    employee: EmployeeContext
    tools: tuple[BaseTool, ...]
    knowledge_retriever: Retriever
    board_retriever: Retriever

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(tool.name for tool in self.tools)


def build_toolset(
    employee: EmployeeContext,
    *,
    index: VectorIndex,
    database_path: Path = DATABASE_PATH,
    limit: int = DEFAULT_LIMIT,
    lexical_weight: float = DECIDED_LEXICAL_WEIGHT,
    retrieval_mode: RetrievalMode = "hybrid",
) -> Toolset:
    """Construct the five tools for exactly one employee.

    Two namespace-scoped retrievers share one loaded embedding model. The scoping
    is what makes F-13 structural: `search_company_knowledge` is wired to a
    retriever that cannot see the `project_board` collection, so live board
    issues cannot contaminate company-knowledge answers even if the ranker would
    have preferred them.
    """
    knowledge_retriever = HybridRetriever(
        index, namespace=COMPANY_KNOWLEDGE, lexical_weight=lexical_weight
    )
    board_retriever = HybridRetriever(
        index, namespace=PROJECT_BOARD, lexical_weight=lexical_weight
    )

    def resolve_permitted(context: EmployeeContext):
        """Every record this employee may see, across both namespaces.

        Read from the store through the same permission pre-filter the retriever
        uses, so the recheck in `compare_sources` cannot disagree with the filter
        that admitted the evidence in the first place.
        """
        return (
            *index.permitted_documents(COMPANY_KNOWLEDGE, context.role),
            *index.permitted_documents(PROJECT_BOARD, context.role),
        )

    def _search_company_knowledge(query: str) -> str:
        return _serialize(
            search_company_knowledge(query, employee, retriever=knowledge_retriever,
                                     limit=limit, retrieval_mode=retrieval_mode)
        )

    def _search_work_items(query: str) -> str:
        return _serialize(
            search_work_items(
                query,
                employee,
                board_retriever=board_retriever,
                export_retriever=knowledge_retriever,
                limit=limit,
                retrieval_mode=retrieval_mode,
            )
        )

    def _get_support_case(case_id: str) -> str:
        return _serialize(get_support_case(case_id, employee, database_path=database_path))

    def _compare_sources(source_ids: list[str]) -> str:
        return _serialize(compare_sources(source_ids, employee, resolver=resolve_permitted))

    def _propose_action(
        action_type: str, payload: dict[str, str], destination: str | None = None
    ) -> str:
        return _serialize(propose_action(action_type, payload, employee, destination=destination))

    tools: tuple[BaseTool, ...] = (
        StructuredTool.from_function(
            func=_search_company_knowledge,
            name="search_company_knowledge",
            description=(
                "Search the company's private Slack messages, emails, policy and release documents, "
                "and the committed GitHub export. Returns permitted evidence with source ids, "
                "lifecycle status and dates, the full set of records this employee may see, and a "
                "conflict flag when results disagree. Use this first for almost any question."
            ),
            args_schema=KnowledgeSearchArgs,
        ),
        StructuredTool.from_function(
            func=_search_work_items,
            name="search_work_items",
            description=(
                "Search GitHub work items across the live project board and the committed export. "
                "Reports which of the two id spaces each item came from and whether the data is "
                "live, a degraded fallback, or a local fixture. Use for questions about engineering "
                "work, blockers and issue state."
            ),
            args_schema=WorkItemSearchArgs,
        ),
        StructuredTool.from_function(
            func=_get_support_case,
            name="get_support_case",
            description=(
                "Look up exactly one customer support case by its id. Returns the case row, or an "
                "explicit 'no such case' when it does not exist, or a denial when this employee may "
                "not read business records. Accepts a case id only - it is not a query interface."
            ),
            args_schema=SupportCaseArgs,
        ),
        StructuredTool.from_function(
            func=_compare_sources,
            name="compare_sources",
            description=(
                "Reconcile two or more sources that may disagree. Reports which is authoritative "
                "when a lifecycle status settles it (for example an archived policy against the "
                "current one), or flags a date-only conflict without deciding it. Call this before "
                "quoting a figure whenever a search reported a conflict."
            ),
            args_schema=CompareSourcesArgs,
        ),
        StructuredTool.from_function(
            func=_propose_action,
            name="propose_action",
            description=(
                "Prepare an action for human approval: "
                f"{', '.join(sorted(REQUIRED_PAYLOAD))}. Returns a pending proposal showing the exact "
                "operation, destination, payload and expected effect. It does NOT perform the action; "
                "only a separate human approval can do that. Never claim an action was taken."
            ),
            args_schema=ProposeActionArgs,
        ),
    )

    return Toolset(
        employee=employee,
        tools=tools,
        knowledge_retriever=knowledge_retriever,
        board_retriever=board_retriever,
    )
