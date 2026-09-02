"""Phase 6 tool set: five narrow, typed, permission-aware read-only tools.

No tool in this package writes anything. `propose_action` prepares an operation
and returns it as `pending_approval`; the approval gate that can advance it lives
outside the tool set, behind a separate user interaction (step 6.4).
"""

from company_assistant.tools.actions import (ALLOWED_DESTINATIONS, EXPECTED_EFFECT,
                                             REQUIRED_PAYLOAD, propose_action,
                                             proposal_id_for, render_preview)
from company_assistant.tools.comparison import compare_sources
from company_assistant.tools.conflicts import (CURRENT_STATUSES, SUPERSEDED_STATUSES,
                                               detect_conflicts, id_family, is_current,
                                               is_superseded)
from company_assistant.tools.knowledge import search_company_knowledge, to_evidence
from company_assistant.tools.relevance import (STOPWORDS, WEAK_COVERAGE_THRESHOLD,
                                                classify, content_terms, term_coverage)
from company_assistant.tools.registry import (DECIDED_LEXICAL_WEIGHT, Toolset,
                                              build_toolset)
from company_assistant.tools.schemas import (ComparisonVerdict, ConflictHint, EvidenceItem,
                                             KnowledgeSearchResult, ProposalResult,
                                             SourceComparison, SupportCase,
                                             SupportCaseResult, ToolStatus,
                                             WorkItemSearchResult)
from company_assistant.tools.support import CASE_READER_ROLES, get_support_case
from company_assistant.tools.work_items import search_work_items

__all__ = [
    "ALLOWED_DESTINATIONS",
    "CASE_READER_ROLES",
    "CURRENT_STATUSES",
    "ComparisonVerdict",
    "ConflictHint",
    "DECIDED_LEXICAL_WEIGHT",
    "EXPECTED_EFFECT",
    "EvidenceItem",
    "KnowledgeSearchResult",
    "ProposalResult",
    "REQUIRED_PAYLOAD",
    "STOPWORDS",
    "SUPERSEDED_STATUSES",
    "WEAK_COVERAGE_THRESHOLD",
    "SourceComparison",
    "SupportCase",
    "SupportCaseResult",
    "ToolStatus",
    "Toolset",
    "WorkItemSearchResult",
    "build_toolset",
    "classify",
    "compare_sources",
    "content_terms",
    "detect_conflicts",
    "get_support_case",
    "id_family",
    "is_current",
    "is_superseded",
    "proposal_id_for",
    "propose_action",
    "render_preview",
    "search_company_knowledge",
    "search_work_items",
    "term_coverage",
    "to_evidence",
]
