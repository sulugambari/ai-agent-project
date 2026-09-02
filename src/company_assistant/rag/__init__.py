"""Retrieval-augmented generation: the H2 contract and its implementations."""

from company_assistant.rag.contract import (
    DEFAULT_LIMIT,
    Freshness,
    IndexStatus,
    RetrievalOutcome,
    Retriever,
    SourceFreshness,
    UnsupportedRetrievalMode,
)
from company_assistant.rag.index import (
    ALL_ROLES,
    COMPANY_KNOWLEDGE,
    EMBEDDING_MODEL,
    PROJECT_BOARD,
    Namespace,
    SyncReport,
    VectorIndex,
    chunk_id,
    namespace_for,
    revision_fingerprint,
    role_filter,
)
from company_assistant.rag.lexical import LexicalRetriever
from company_assistant.rag.semantic import SemanticRetriever

__all__ = [
    "ALL_ROLES",
    "COMPANY_KNOWLEDGE",
    "DEFAULT_LIMIT",
    "EMBEDDING_MODEL",
    "Freshness",
    "IndexStatus",
    "LexicalRetriever",
    "Namespace",
    "PROJECT_BOARD",
    "RetrievalOutcome",
    "Retriever",
    "SemanticRetriever",
    "SourceFreshness",
    "SyncReport",
    "UnsupportedRetrievalMode",
    "VectorIndex",
    "chunk_id",
    "namespace_for",
    "revision_fingerprint",
    "role_filter",
]
