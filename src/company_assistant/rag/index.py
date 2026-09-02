"""Chroma-backed vector index with permission filtering applied at query time.

Design constraints this module exists to satisfy
------------------------------------------------
* **D-002 — the permission filter must be a *pre*-filter on the vector query.**
  Post-filtering would let a restricted record reach the model before being
  removed, which hides the disclosure rather than preventing it. Chroma applies
  `where` during search, so a non-permitted record is never a candidate.
* **D-004 — two namespaces.** The live project board is indexed separately from
  company knowledge, because merging them was measured to contaminate retrieval
  (F-13). Namespaces are separate Chroma collections.
* **F-12 — a degraded batch may never authorise deletions.** Live and fallback
  GitHub records occupy disjoint id spaces, so a manifest diff over a fallback
  batch would delete every live chunk. `sync` refuses deletions unless the batch
  is live.
* **2.2 — two identifiers, two jobs.** The Chroma id is the `chunk_id`
  (`<source_id>::<fingerprint>::<nn>`) so a revision upserts cleanly; the
  `source_id` travels in metadata unchanged so citations keep resolving.

Chroma metadata may only hold scalars, so `allowed_roles` is stored as one
boolean flag per role (`role_engineering` and so on). That is what makes it
usable in a `where` clause at all - a list would not be filterable.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import chromadb
from chromadb.api.types import EmbeddingFunction
from chromadb.utils import embedding_functions

from company_assistant.models import CompanyDocument, EmployeeRole
from company_assistant.rag.contract import Freshness, IndexStatus, SourceFreshness

#: Small, fast, local. Chosen deliberately over a larger model: F-8 recorded that
#: this corpus is 15 short records, so recall is easy and a heavier model would
#: cost load time and memory for no measurable retrieval gain. Comparing model
#: sizes is a Phase 10 extension, not a core requirement.
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

DEFAULT_INDEX_DIR = Path("data/index")

#: Freshness state written beside the Chroma store so a last-indexed
#: disclosure survives a process restart rather than resetting to "never".
INDEX_MANIFEST = "freshness_manifest.json"

Namespace = Literal["company_knowledge", "project_board"]
COMPANY_KNOWLEDGE: Namespace = "company_knowledge"
PROJECT_BOARD: Namespace = "project_board"

ALL_ROLES: tuple[EmployeeRole, ...] = (
    "customer_success",
    "engineering",
    "people_operations",
    "finance",
)
GOVERNANCE_FIELDS = ("content", "title", "allowed_roles", "confidentiality", "status", "occurred_at")


def revision_fingerprint(document: CompanyDocument) -> str:
    """12 hex chars over content plus every field governing retrieval or access.

    Metadata is included on purpose (step 2.2): a content-only hash would miss a
    tightened `allowed_roles`, leaving an already-indexed chunk retrievable under
    its old policy - a stale authorization rather than a stale answer.
    """
    payload = {
        "content": " ".join(document.content.split()),
        "title": document.title,
        "allowed_roles": sorted(document.allowed_roles),
        "confidentiality": document.confidentiality,
        "status": str(document.metadata.get("status", "")),
        "occurred_at": document.occurred_at.isoformat() if document.occurred_at else None,
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def chunk_id(document: CompanyDocument, chunk_index: int = 0) -> str:
    return f"{document.source_id}::{revision_fingerprint(document)}::{chunk_index:02d}"


def namespace_for(document: CompanyDocument) -> Namespace:
    """Live board issues are a different corpus from company knowledge (D-004)."""
    return PROJECT_BOARD if document.source_id.startswith("GH-LIVE-") else COMPANY_KNOWLEDGE


def role_filter(role: EmployeeRole) -> dict[str, Any]:
    """The `where` clause that makes permission enforcement structural."""
    return {f"role_{role}": True}


def to_metadata(document: CompanyDocument, *, freshness: Freshness) -> dict[str, Any]:
    """Flatten a document into Chroma-safe scalars, preserving governance."""
    metadata: dict[str, Any] = {
        "source_id": document.source_id,
        "source_type": document.source_type,
        "title": document.title,
        "source_path": document.source_path,
        "author": document.author or "",
        "confidentiality": document.confidentiality,
        "status": str(document.metadata.get("status", document.metadata.get("state", ""))),
        "occurred_at": document.occurred_at.isoformat() if document.occurred_at else "",
        # epoch kept alongside the ISO string so freshness can be range-filtered
        # later without parsing, e.g. for the Phase 10 recency-aware extension
        "occurred_ts": document.occurred_at.timestamp() if document.occurred_at else 0.0,
        "fingerprint": revision_fingerprint(document),
        "source_freshness": freshness,
        "namespace": namespace_for(document),
    }
    # one boolean per role - a list is not filterable in a Chroma `where` clause
    for role in ALL_ROLES:
        metadata[f"role_{role}"] = role in document.allowed_roles
    return metadata


def from_metadata(metadata: dict[str, Any], content: str) -> CompanyDocument:
    """Rebuild a CompanyDocument from stored metadata.

    Permissions are reconstructed from the role flags rather than trusted from
    anywhere else, so a record recovered from the index carries exactly the
    access policy it was indexed with - which is what makes the citation-time
    recheck meaningful.
    """
    roles = frozenset(role for role in ALL_ROLES if metadata.get(f"role_{role}"))
    occurred = metadata.get("occurred_at") or ""
    return CompanyDocument(
        source_id=str(metadata["source_id"]),
        source_type=str(metadata["source_type"]),  # type: ignore[arg-type]
        title=str(metadata["title"]),
        content=content,
        source_path=str(metadata["source_path"]),
        allowed_roles=roles,
        confidentiality=str(metadata.get("confidentiality", "internal")),  # type: ignore[arg-type]
        author=str(metadata.get("author")) or None,
        occurred_at=datetime.fromisoformat(occurred) if occurred else None,
        metadata={
            "status": str(metadata.get("status", "")),
            "source_freshness": str(metadata.get("source_freshness", "local")),
            "namespace": str(metadata.get("namespace", COMPANY_KNOWLEDGE)),
            "fingerprint": str(metadata.get("fingerprint", "")),
        },
    )


@dataclass(frozen=True, slots=True)
class SyncReport:
    """What one namespace synchronization actually changed."""

    namespace: str
    upserted: int
    deleted: int
    unchanged: int
    freshness: Freshness
    deletions_skipped: bool = False
    detail: str = ""


class VectorIndex:
    """Persistent Chroma index, one collection per namespace."""

    def __init__(
        self,
        directory: Path = DEFAULT_INDEX_DIR,
        *,
        embedding_function: EmbeddingFunction | None = None,
    ) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(directory))
        # Loaded once per process. Uncached this is ~90 MB and the single largest
        # perceived-latency factor in the product (D-001), which is why Phase 7
        # wraps the whole retriever in @st.cache_resource rather than rebuilding it.
        self._embed = embedding_function or embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL
        )
        self._manifest_path = directory / INDEX_MANIFEST
        self._freshness: dict[str, SourceFreshness] = {}
        self._last_indexed: datetime | None = None
        self._load_manifest()

    # -- freshness manifest --------------------------------------------------
    # Phase 7 (step 7.3) must disclose a last-indexed status, and the agent must
    # never present fallback data as live (F-12, T-07). Both facts were held only
    # in instance attributes, so any freshly started process - Streamlit,
    # FastAPI, the agent - reported "indexed never" and defaulted every namespace
    # to `local`, silently asserting "committed fixture" over data that was
    # really live or a degraded substitute. That is a disclosure claim being
    # wrong by construction, so the state is now written beside the store.

    def _load_manifest(self) -> None:
        """Restore last-indexed time and per-namespace freshness from disk."""
        if not self._manifest_path.exists():
            return
        try:
            payload = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # A corrupt manifest must not claim freshness it cannot support, and
            # must not stop the index loading either: unknown is the safe state.
            return
        indexed_at = payload.get("last_indexed_at")
        self._last_indexed = datetime.fromisoformat(indexed_at) if indexed_at else None
        for namespace, entry in (payload.get("sources") or {}).items():
            self._freshness[namespace] = SourceFreshness(
                source=namespace,
                freshness=entry.get("freshness", "local"),
                detail=entry.get("detail", ""),
            )

    def _save_manifest(self) -> None:
        """Write the manifest next to the store. Never fatal: it is disclosure."""
        payload = {
            "last_indexed_at": self._last_indexed.isoformat() if self._last_indexed else None,
            "sources": {
                namespace: {"freshness": entry.freshness, "detail": entry.detail}
                for namespace, entry in self._freshness.items()
            },
        }
        try:
            self._manifest_path.write_text(
                json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            pass

    def _stamp_indexed(self) -> None:
        self._last_indexed = datetime.now(timezone.utc)
        self._save_manifest()

    @property
    def embedding_function(self) -> EmbeddingFunction:
        """Exposed so a second index can share the loaded model.

        Constructing a new VectorIndex otherwise reloads ~90 MB from disk, which
        makes an isolated lifecycle test needlessly slow.
        """
        return self._embed

    def collection(self, namespace: Namespace):
        return self._client.get_or_create_collection(
            name=namespace,
            embedding_function=self._embed,
            # cosine rather than the L2 default: similarity must be comparable
            # across records of different lengths, and 1 - distance then gives a
            # bounded score we can report next to the lexical one
            metadata={"hnsw:space": "cosine"},
        )

    def sync(
        self,
        documents: Iterable[CompanyDocument],
        *,
        namespace: Namespace,
        freshness: Freshness = "local",
        detail: str = "",
    ) -> SyncReport:
        """Upsert changed records and delete records absent from this batch.

        Deletions are **scoped to one namespace** and are **refused for a
        degraded batch** (F-12). A fallback batch carries a different id space
        than the live one, so allowing it to drive deletions would remove every
        live chunk on a transient API failure - amplifying an outage into an
        empty index rather than a stale one, and stale-but-disclosed is strictly
        better than absent.
        """
        collection = self.collection(namespace)
        incoming = list(documents)
        ids = [chunk_id(document) for document in incoming]

        existing = set(collection.get(include=[])["ids"])
        to_delete = sorted(existing - set(ids))
        unchanged = len(existing & set(ids))

        # A degraded batch whose id space is DISJOINT from what this namespace
        # already holds is not a stale version of this corpus - it is a different
        # corpus. Writing it here would duplicate records across namespaces (the
        # local GitHub export belongs to company_knowledge, not project_board) and
        # answer board questions with unrelated Atlas issues. The correct degraded
        # behaviour is to serve what is already indexed and disclose that it is
        # stale, because stale-but-disclosed beats both absent and wrong.
        foreign_fallback = (
            freshness == "fallback" and bool(existing) and not (set(ids) & existing)
        )
        if foreign_fallback:
            self._freshness[namespace] = SourceFreshness(
                namespace,
                freshness,
                f"{detail} - retained {len(existing)} previously indexed record(s); the fallback "
                f"batch shares no id with this namespace, so it is a different corpus rather than "
                f"a stale copy of this one",
            )
            self._stamp_indexed()
            return SyncReport(
                namespace=namespace,
                upserted=0,
                deleted=0,
                unchanged=len(existing),
                freshness=freshness,
                deletions_skipped=True,
                detail=(
                    f"refused the whole sync: a fallback batch with a disjoint id space "
                    f"({len(ids)} record(s)) cannot substitute for this namespace's "
                    f"{len(existing)} record(s) (F-12)"
                ),
            )

        if incoming:
            collection.upsert(
                ids=ids,
                documents=[document.content for document in incoming],
                metadatas=[to_metadata(document, freshness=freshness) for document in incoming],
            )

        deletions_skipped = freshness == "fallback" and bool(to_delete)
        if to_delete and not deletions_skipped:
            collection.delete(ids=to_delete)

        self._freshness[namespace] = SourceFreshness(namespace, freshness, detail)
        self._stamp_indexed()
        return SyncReport(
            namespace=namespace,
            upserted=len(ids),
            deleted=0 if deletions_skipped else len(to_delete),
            unchanged=unchanged,
            freshness=freshness,
            deletions_skipped=deletions_skipped,
            detail=(
                f"skipped {len(to_delete)} deletion(s): batch is a fallback, so its id space "
                "cannot authorise removals (F-12)"
                if deletions_skipped else detail
            ),
        )

    def rebuild(self, namespace: Namespace) -> None:
        """Drop a namespace entirely, for when incremental sync cannot be trusted."""
        try:
            self._client.delete_collection(namespace)
        except Exception:  # collection may not exist yet; a rebuild should be idempotent
            pass
        self.collection(namespace)

    def permitted_ids(self, namespace: Namespace, role: EmployeeRole) -> tuple[str, ...]:
        """Every source id this role may see in this namespace.

        Uses an exact metadata `get`, not a vector search, so the result is the
        pre-filter's admitted set independent of ranking. That is the evidence
        F-4 requires: a record missing from here was never visible at all, as
        opposed to merely having ranked low.
        """
        found = self.collection(namespace).get(where=role_filter(role), include=["metadatas"])
        return tuple(str(m["source_id"]) for m in (found.get("metadatas") or []))

    def permitted_documents(
        self, namespace: Namespace, role: EmployeeRole
    ) -> tuple[CompanyDocument, ...]:
        """Every record this role may see in this namespace, rebuilt in full.

        Used by the hybrid retriever so that BOTH signals are computed over the
        same permitted set read from the same store. Deriving the lexical
        candidate set from a separate in-memory list would introduce a confound
        into the Phase 8 comparison: a mode could then appear better simply
        because it saw a different corpus.
        """
        found = self.collection(namespace).get(
            where=role_filter(role), include=["documents", "metadatas"]
        )
        documents = found.get("documents") or []
        metadatas = found.get("metadatas") or []
        return tuple(
            from_metadata(dict(metadata), str(content))
            for content, metadata in zip(documents, metadatas, strict=True)
        )

    def query(
        self,
        text: str,
        *,
        namespace: Namespace,
        role: EmployeeRole,
        limit: int,
    ) -> list[tuple[CompanyDocument, float]]:
        """Vector search with the permission filter applied *during* the search."""
        collection = self.collection(namespace)
        total = collection.count()
        if total == 0 or not text.strip():
            return []
        found = collection.query(
            query_texts=[text],
            n_results=min(limit, total),
            where=role_filter(role),          # <- the structural pre-filter (D-002)
            include=["documents", "metadatas", "distances"],
        )
        results: list[tuple[CompanyDocument, float]] = []
        for content, metadata, distance in zip(
            found["documents"][0], found["metadatas"][0], found["distances"][0], strict=True
        ):
            similarity = max(0.0, min(1.0, 1.0 - float(distance)))
            results.append((from_metadata(dict(metadata), str(content)), similarity))
        return results

    def status(self, namespaces: Sequence[Namespace] = (COMPANY_KNOWLEDGE, PROJECT_BOARD)) -> IndexStatus:
        return IndexStatus(
            last_indexed_at=self._last_indexed,
            unit_count=sum(self.collection(namespace).count() for namespace in namespaces),
            sources=tuple(
                self._freshness.get(namespace, SourceFreshness(namespace, "local"))
                for namespace in namespaces
            ),
        )
