"""Build both retrieval namespaces from source. The documented index bootstrap.

Why this script exists
----------------------
`data/index/` is git-ignored, so **a clean checkout has no index and nothing
retrieves until one is built**. Until now the only way to build it was to execute
`notebooks/northstar_build.ipynb` step 5.2 - which is fine for the person who
wrote the notebook and useless as a documented command, and impossible inside a
container that ships no notebook. Phase 9's completion evidence is that a
teammate starts the packaged product *from the repository instructions* and
reaches both interfaces, so the index build has to be one command.

It is the same call sequence as the notebook, deliberately: two namespaces
(D-004), company knowledge stamped `local` because it is a committed fixture, and
the project board stamped with whatever freshness the live fetch actually
achieved.

Three properties this has to keep
---------------------------------
* **A failed GitHub fetch must not fail the build.** `load_github_live_issues`
  degrades to the committed export and reports `fallback`; the index records that
  freshness, and the interface discloses it. An outage should leave the product
  serving stale-but-disclosed data, never no data (T-07, F-12).
* **The freshness manifest must be written.** It lives beside the store and is
  what stops a freshly started process claiming `local` over data that was really
  live or a degraded fallback - a disclosure wrong by construction (F-15.2). A
  sync is what writes it, which is why an index built before that fix still
  reports `indexed never` until something re-syncs.
* **Re-running must be cheap and idempotent.** The governance fingerprint means an
  unchanged corpus upserts the same chunk ids and deletes nothing, so this is safe
  to run on every container start.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from company_assistant.connectors import load_all_documents
from company_assistant.connectors.github_live import load_github_live_issues
from company_assistant.rag import (COMPANY_KNOWLEDGE, DEFAULT_INDEX_DIR, PROJECT_BOARD,
                                   VectorIndex, namespace_for)

#: The live repository. Read from the environment so a container can point
#: elsewhere without a code change; the fallback is the committed export either way.
DEFAULT_REPOSITORY = "sulugambari/ai-agent-project"


def main() -> int:
    load_dotenv()
    import os

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--index-dir", type=Path, default=DEFAULT_INDEX_DIR)
    parser.add_argument("--data-root", type=Path, default=Path("data/raw"))
    parser.add_argument(
        "--rebuild", action="store_true",
        help="Drop both namespaces before syncing. The full-rebuild path 04 requires, "
             "for when an incremental sync cannot be trusted.",
    )
    args = parser.parse_args()

    repository = os.getenv("GITHUB_REPOSITORY") or DEFAULT_REPOSITORY
    token = (os.getenv("GITHUB_TOKEN") or "").strip() or None

    documents = load_all_documents(args.data_root)
    knowledge = [d for d in documents if namespace_for(d) == COMPANY_KNOWLEDGE]

    # Attempted before the index is opened so a network stall does not sit behind
    # a ~90 MB model load, and so the degraded path is visible in the log first.
    live = load_github_live_issues(repository, token)
    if live.source_freshness != "live":
        print(f"  live fetch degraded: {live.detail}", file=sys.stderr)

    index = VectorIndex(args.index_dir)
    if args.rebuild:
        for namespace in (COMPANY_KNOWLEDGE, PROJECT_BOARD):
            index.rebuild(namespace)
        print("  rebuilt: both namespaces dropped before syncing")

    reports = [
        index.sync(knowledge, namespace=COMPANY_KNOWLEDGE, freshness="local",
                   detail="committed teaching fixtures"),
        index.sync(live.documents, namespace=PROJECT_BOARD,
                   freshness=live.source_freshness, detail=live.detail),
    ]

    for report in reports:
        print(f"  {report.namespace:<18} upserted={report.upserted:<3} "
              f"deleted={report.deleted:<3} unchanged={report.unchanged:<3} "
              f"freshness={report.freshness}"
              + (f"  [{report.detail}]" if report.deletions_skipped else ""))

    status = index.status()
    print(f"  status: {status.describe()}")
    for source in status.sources:
        print(f"    {source.source:<18} {source.freshness:<9} {source.detail[:70]}")

    # An empty index is a silent failure that only shows up as "the assistant
    # cannot find anything", so it fails here instead.
    if status.unit_count == 0:
        print("index is empty after sync - refusing to report success", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
