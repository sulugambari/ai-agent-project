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
from company_assistant.rag.lexical import LexicalRetriever

__all__ = [
    "DEFAULT_LIMIT",
    "Freshness",
    "IndexStatus",
    "LexicalRetriever",
    "RetrievalOutcome",
    "Retriever",
    "SourceFreshness",
    "UnsupportedRetrievalMode",
]
