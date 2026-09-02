# HANDOVER — Northstar Release Coordinator

**For Sulu.** Everything needed to continue from **Phase 8** without
reverse-engineering decisions already taken. Read sections 1–3 (about 10 minutes), then
jump to §8.

*(This file was written by Sulu for Karthik at the Phase 5 boundary. It is now updated in
the other direction: Phases 6 and 7 are complete and Phase 8 is yours. The Phase 6 brief
it used to carry is in the git history.)*

- **Last updated:** 2 September 2026, after **Phase 7 closed**
- **State:** Phases 0–7 complete (**6.5 outstanding**) · Phases 8–10 open · 26 commits,
  **4 unpushed on `ai-agent-project-Karthik1`** — nothing since Phase 5 is on `main` yet
- **Retrieval default:** hybrid, `lexical_weight = 0.6` (D-006) — but see F-15: the
  code's own `DEFAULT_LEXICAL_WEIGHT` is still `0.5`, so the tools pass 0.6 explicitly
- **Model:** `openai/gpt-oss-20b`, **provisional** (D-007). The planned fallback model no
  longer exists and the bake-off could not be completed on the free tier
- **Read F-17 before you design the Phase 8 harness.** The agent is not deterministic at
  `temperature=0`, so a single run per case measures sampling noise
- **Board:** <https://github.com/users/sulugambari/projects/12>
- **Full session transcript:** `docs/CHAT_HISTORY.md` (readable, 21 turns) and
  `docs/chat-history-raw.jsonl` (verbatim, 8.4 MB). **Both cover Phases 0–5 only** — the
  Phases 6–7 session is not in them, so the commit messages are the record for those

---

## 1 · What the product is

An internal assistant for **Northstar Labs** — a fictional company selling planning
software to logistics teams — that answers employees' questions from private company
knowledge scattered across Slack, email, Markdown documents, GitHub issues, and SQLite.
It always shows sources, only shows what the asking employee is cleared to see, refuses
when evidence is missing, and never acts without human approval.

**Product name:** Northstar Release Coordinator
**Primary profile:** Leo Martins — Software Engineer (`engineering`)
**Secondary profile:** Maya Chen — Customer Success (`customer_success`)
**Workflow:** release-readiness coordination

The concrete problem: determining whether Atlas can ship means reconciling the release
brief's condition list, two GitHub issues, an engineering Slack thread, and a project
record — four sources, twenty minutes, repeated by different people. The failure mode is
already recorded in the fixtures: a 5 September date was committed to Acme Freight in
`EMAIL-ACME-301` and corrected two days later in `EMAIL-ACME-302`.

Full detail: `deliverables/PRODUCT_BRIEF.md`.

## 2 · Get running in five commands

```bash
git pull
uv sync                                              # includes dev group: ipykernel, nbclient, vl-convert
uv run python -m company_assistant.database          # recreate the teaching fixture
uv run uvicorn company_assistant.api:app --reload    # http://localhost:8000/docs
uv run streamlit run app.py                          # http://localhost:8501
```

**The index is git-ignored, so a fresh clone has none.** Nothing retrieves until you
build it — `VectorIndex(...).sync(...)`, as in `northstar_build.ipynb` step 5.2. The first
run also fetches a ~90 MB embedding model.

Two notebooks, one per person: `northstar_build.ipynb` (Sulu, Phases 0–5) and
`phase_04_live_github.ipynb` (Karthik, Phases 4, 6, 7). Step 10.3 splices them.

**You will need `.env` from Phase 4 onward:**
```bash
cp .env.example .env
# GITHUB_REPOSITORY=sulugambari/ai-agent-project
# GITHUB_TOKEN=            <- the repo is public again as of Phase 4 close, so
#                              reads need no token. A token is still required
#                              for any write action (e.g. posting a comment),
#                              regardless of visibility. See §5, D-003.
# GROQ_API_KEY=            <- needed from Phase 6, not Phase 4
```

## 3 · Where we are

| Phase | Owner | Status |
| --- | --- | --- |
| 0 · Project setup | Together | ✅ Done |
| 1 · Frame the product | Together | ✅ Done — cleared the `AGENTS.md` implementation gate |
| 2 · Information boundary | Together | ✅ Done — cleared the semantic-retrieval gate |
| 3 · Deterministic baseline | Sulu | ✅ Done |
| 4 · Live GitHub source | Karthik | ✅ Done — verified and closed |
| 5 · Managed RAG pipeline | Sulu | ✅ Done — hybrid `w=0.6` selected (D-006); lifecycle proven |
| 6 · Tools and one agent | Karthik | ⚠️ **Steps 6.1–6.4 done; 6.5 not run** — the smoke run needs model calls and the Groq quota is exhausted |
| 7 · Product experience | Together | ✅ Done — `service.py`, all five endpoints, Streamlit chat + approval panel |
| **8 · Comparative evaluation** | **Sulu** | **← you start here.** See §8 |
| 9 · Package the product | **Karthik** | Todo |
| 10 · Decide and demonstrate | Together | Todo |

Phases 3 and 4 ran in parallel. From Phase 5 onward the team works **sequentially**
(D-005): one active phase, handed over at each boundary.

**Phase 7 was written by Karthik with Sulu observing remotely**, so the shared files had
two sets of eyes as they were built. `origin/main` was still at the Phase 5 close and both
shared files were untouched, so there was no concurrent-edit risk either. `service.py`,
`api.py` and `app.py` are new in this phase and are still the natural place to start
reading.

## 4 · The findings that constrain your work

These are the reason to read this document rather than just the course files. Each was
measured, not assumed, and each changes what the remaining phases must do. **F-15 to
F-21 are new since Phase 5** and are the ones that affect Phase 8 directly.

### F-1 · The lexical baseline is not a strawman
It retrieved **all three** EVAL-002 expected sources (`GH-142`, `GH-149`,
`DOC-ATLAS-403`) for the Atlas blocker question. Phase 5 must beat something real, and
the evaluation must be framed honestly.

### F-2 · The archived refund policy OUTRANKS the current one — ✅ resolved in Phase 6
For *"What is the current approval threshold for a refund?"*, `DOC-POLICY-OLD-402`
(archived, EUR 2,500) beats `DOC-POLICY-401` (current, EUR 1,000).

**Why:** the archived document's own warning — *"Do not use this archived **threshold**
for **current** decisions"* — supplies the two query terms the current policy never
uses. **The disclaimer written to prevent misuse is what makes the stale document win.**

**Consequence for you — now confirmed three independent ways.** Phase 5 measured this
under every retrieval configuration and **hybrid makes it worse**, widening the gap from
0.14 (lexical) to **0.20** (hybrid): the two documents are semantically near-identical, so
embeddings cannot separate them and normalisation amplifies the lexical lead. Chunking did
not change it either (5.1). **No retrieval configuration fixes F-2.**

**✅ RESOLVED in Phase 6, above retrieval.** Ranking was never going to fix it, so it was
not asked to. `search_company_knowledge` now returns `conflict_detected` with a hint naming
only same-family records, and `compare_sources` returns
`verdict=superseded, authoritative=DOC-POLICY-401`. Passed 3 runs of 3 in the bake-off.

Two details that made it work:

* **Revisions are grouped by stable source-id family, not by title.** Titles do not link
  them on this corpus — `EMAIL-ACME-301` is *"Atlas migration and invoice follow-up"* while
  its own correction `EMAIL-ACME-302` is *"Correction: Atlas customer date"*. Nothing in the
  prose connects them; the governed id scheme does.
* **Supersession is a verdict, recency is only a signal.** An explicit `status: archived`
  names an authoritative record. A date-only difference returns `recency_conflict` with **no
  winner named**, because "later is correct" is the T-03 fallacy and asserting it would
  trade a stale-evidence error for a confident date-ordering one.

The conflict now reaches the agent as **a field**, not as a hope that the prompt made it
notice. Figures: `3_3_conflict_baseline.png`, `5_3_score_contribution.png`.

### F-3 · The permission filter is load-bearing, and proven by counterfactual
`DOC-HR-001` ranks **#1 at score 0.86** in an unfiltered copy of the same scoring
function, and is **absent** from Leo's filtered candidate set. Priya correctly retrieves
it. 4 roles × 9 adversarial queries → **0 violations**, asserted in executable code.

**Consequence:** that assertion is a regression guard. If a tool ever retrieves without
passing `EmployeeContext`, it fails. Phase 6 closed the hole permanently — identity is
bound as a closure and appears in **no** tool's `args_schema`, so the agent has no
vocabulary for changing who it is. Figure: `3_2_filter_is_loadbearing.png`.

### F-4 · A refusal is NOT evidence of pre-retrieval filtering
A refusal is equally consistent with a model that was merely instructed to decline. Only
the **candidate set** proves the record never reached the model.

**Consequence:** the Phase 7 trace panel is the evidence for our most important access
claim, not a UI nicety. **Done:** the agent carries `candidate_ids` out of every turn and
the Streamlit trace expander renders it with a caption explaining what its absence proves.
Do not quietly drop it from the evaluation output either.

### F-5 · A content-only chunk hash would create a security hole
`python-frontmatter` puts YAML in `.metadata` and body text in `.content`, so tightening
`allowed_roles` leaves content **byte-identical**. A content-only hash fires no upsert,
and the indexed chunk keeps its **old permission metadata — still retrievable under the
old policy.** A stale *authorization*, not a stale answer.

Chunk IDs therefore hash content **plus** `title`, `allowed_roles`, `confidentiality`,
`status`, `occurred_at`. Tested against five change types: timestamp IDs miss three,
content-only misses two, governance hash catches all five. Figure:
`2_2_change_detection.png`.

### F-6 · All malformed records fail loudly — 10 of 10, zero silent
Absent / empty / unknown `allowed_roles`, missing `source_id`, invalid
`confidentiality`, absent email governance headers — all raise at parse time.

**Consequence for you:** this probe suite is **your regression harness**. A malformed API
response must *raise*, not degrade into a `CompanyDocument` with empty `allowed_roles`,
which would be a world-readable record. Reuse the `probe()` helper in the notebook
(step 3.1).

### F-7 · Permissions are per-record, not a role hierarchy
Engineering sees 11 of 15 records but **cannot** see the refund policies or the
customer-operations thread; Customer Success sees the policies but not the engineering
blockers. **No single role can answer a cross-domain question alone.**

### F-8 · The corpus is small (15 records)
Recall is easy at this size. Phase 5's honest win is **precision and paraphrase
handling**, not recall. A large claimed recall win should be treated as suspect.

### F-9 · Streamlit binds all network interfaces by default
Booting the app advertised a LAN URL. An unauthenticated permission-aware assistant
should not be network-reachable → your Phase 9 packaging decision.

### F-10 · The teaching database is reproducible at row level, not byte level
SQLite page layout varies per run. **Never compare checksums; compare rows.** Matters
for EVAL-008, which deliberately makes the database unavailable.

### F-11 · SSH access does not imply REST API access — a repo's visibility can also change under you
This document originally recorded the live repo as public, needing no token.
Mid-Phase-4 it was not: an unauthenticated `GET
/repos/sulugambari/ai-agent-project` returned `404`, and the repo was absent
from a collaborator's `/user/repos` even after a fine-grained token was
issued, because the GitHub *collaborator invite* had not yet been accepted.
`git ls-remote` succeeding over SSH proved nothing about REST API access — the
two are authorized independently. Worked around at the time with a
fine-grained, read-only, single-repo token (D-003); the team then made the
repository public again, restoring the original "no token needed for reads"
assumption — but a token is still required for any *write* action (e.g. the
board comment in step 4's completion evidence) regardless of visibility.

**Consequence:** do not infer GitHub API reachability, or a repository's
current visibility, from git/SSH access working, or from what a prior
document says. Verify with an actual unauthenticated or token-authenticated
API call at the time you need it — visibility itself is not a stable
assumption to hardcode into a connector or its documentation.

### F-12 · Live and fallback GitHub records occupy **disjoint ID spaces** — an indexing hazard
Verified after Phase 4 landed: a live fetch yields `GH-LIVE-1 … GH-LIVE-11`, while the
fallback yields `GH-131`, `GH-142`, `GH-149`. **Overlap: none.**

This is *not* a connector defect — the contract is correct and the freshness disclosure
is honest. It is an **integration hazard for the index lifecycle (step 5.4)**. A manifest
diff that treats "GitHub work items" as one synchronized set would, on a transient API
failure:

1. see all 11 `GH-LIVE-*` chunks absent from the incoming batch,
2. **delete them**, and add the 3 fallback chunks,
3. reverse the whole thing on the next successful fetch.

Transient failure would therefore cause index thrash *and* amplify the outage — during
the fallback window a query for live issues returns nothing, because the chunks were
deleted rather than merely stale.

**Decided mitigation for step 5.4:**
- A **degraded batch must never drive deletions.** Only a batch whose
  `source_freshness == "live"` may authorise removals for the live source.
- The **manifest diff is scoped per successfully synchronized source**, never across all
  GitHub records as one set.
- Fallback is a **serving** path, not an indexing path.

Related: the chunk fingerprint was verified stable across two consecutive live fetches —
`fetched_at` changes every call but does **not** leak into the fingerprint, so a sync
does not re-index the entire live source. That property must survive step 5.4.

### F-13 · The live board issues **contaminate** company-knowledge retrieval
Measured immediately after H2, merging Karthik's live records into the searchable
corpus:

| Question | Top-6 slots taken by our own board issues |
| --- | --- |
| P1 release readiness | 3 / 6 — `GH-LIVE-2` ranks **first**, above `DOC-ATLAS-403` and `GH-142` |
| P2 Acme date | 2 / 6 |
| P3 deployment notes | 2 / 6 |
| EVAL-002 | 4 / 6 |
| EVAL-012 | **5 / 6** |
| **Total** | **16 / 30** |

**Cause.** Our board issues *describe the product we are building*, so they contain
"Atlas", "release", "Leo", "blocking", "conditions" — the exact vocabulary of the company
knowledge they were merged alongside. `GH-LIVE-2` is *"Phase 1 · Frame the Product"*; it
wins the Atlas question because it discusses Atlas release coordination as a **product
decision**, not as company evidence.

**Why this is worse than noise.** The agent could cite an issue about *building the
assistant* as evidence about Atlas's actual release status. That is a
fabricated-evidence-shaped failure wearing a valid citation, and it would pass a naive
"is every claim cited?" check.

**Origin — mine.** The repo choice (D-003) was recommended for guaranteed access and
no-token reads, which was sound. I did not consider content contamination.
`HANDOVER.md` §8 noted the adjacent point (live issues are meta, so EVAL-012's expected
ids exist only locally) but framed it as a *coverage gap* rather than *active
poisoning* — the stronger consequence only appears once the corpora are merged and
measured.

**Recommended fix — separate retrieval namespaces (pending decision, see D-004).** Live
board issues get their own collection, reachable through a dedicated work-item tool and
**excluded from company-knowledge search**. This keeps Phase 4's completion evidence
intact (a real live issue can still be cited, fallback still disclosed) and costs no
rework of the connector. It also models reality: a company's engineering board and its
knowledge base are genuinely different corpora serving different query intents, so the
separation is correct information architecture rather than a workaround.

### F-14 · Semantic retrieval under-ranks records identified by **metadata**, not prose
Measured across ten questions in step 5.5. `GH-142`'s body reads *"duplicate events when a
payment retry arrives during settlement"* — it contains neither "Atlas" nor "open". Its
Atlas identity lives in its **labels** (`atlas, release-blocker, billing`). Lexical scoring
matches those; embedding similarity does not.

Consequence: semantic ranks it **7th on EVAL-012**, one place below the top-6 cutoff, so
semantic-only retrieval **misses half of that case's expected evidence** (recall 0.95 vs
1.00). This is a property of enterprise work items generally, not a quirk of this fixture,
and it is why the default is a **lexical-majority** hybrid rather than a balanced one.

**Also a correction worth knowing about.** Step 5.3 concluded from *five* questions that
"recall is saturated, so retrieval mode does not matter". On ten questions that is **false**.
The saturation was an artifact of the small set. The weaker surviving claim still holds:
recall differences between modes are small and no mode fails badly, so retrieval is not
where this product's real failures live.

### F-15 · Three defects in the retrieval layer, each found only by a *consumer*

None of these were visible from inside Phase 5, and they share a cause: the contract was
never exercised by something that needed it to be true.

1. **`DEFAULT_LEXICAL_WEIGHT = 0.5` while D-006 selected 0.6.** `HybridRetriever(index)` —
   the exact call this document recommended — silently ran a configuration the team never
   chose. The tools now pass `lexical_weight=0.6` explicitly via
   `tools.registry.DECIDED_LEXICAL_WEIGHT`. **`rag/hybrid.py` still needs the real fix**,
   or Phase 8 measures 0.5 while the report claims 0.6.
2. **Index freshness did not survive a process restart** (fixed in `rag/index.py`).
   `last_indexed_at` and per-namespace freshness lived only in instance attributes, so
   every fresh process — Streamlit, FastAPI, the agent — reported `indexed never` and
   defaulted each namespace to `local`, asserting "committed fixture" over data that was
   really live or a degraded fallback. A disclosure claim wrong by construction (F-12,
   T-07). Now persisted to `data/index/freshness_manifest.json`.

   **Verified across processes on 2 September**, with one operational consequence: the
   manifest is written by a *sync*, so an index built before this fix still reports
   `indexed never` and defaults every namespace to `local` until something re-syncs —
   exactly the false disclosure the fix exists to prevent. **Phase 8 must re-sync before
   measuring** rather than trusting whatever the store happens to report. After one sync a
   fresh process correctly reads `project_board live` with the true timestamp.
3. **Hybrid retrieval cannot express irrelevance** — see F-16.

The general lesson: **state held only in memory becomes a false disclosure the moment a
second process reads it**, and a default that disagrees with a decision is invisible until
someone prints it.

### F-16 · Hybrid mode cannot say "the company has no answer"

Min-max normalisation gives the best permitted record a score of **1.0 whatever the
question**, and cosine similarity is never zero, so the retriever's `combined > 0.0`
filter removes nothing in hybrid mode. `search_company_knowledge` therefore *cannot*
return `status="empty"` while the employee can see anything at all.

**EVAL-007 — the case that must abstain — returned six sources with a top score of 1.0.**
A model handed that reads certainty.

The fix lives above retrieval, like the F-2 fix: `tools/relevance.py` measures **absolute
term coverage** over stopword-stripped query terms. Measured across all 12 supplied cases
plus two controls, unanswerable questions score 0.00 / 0.20 / 0.25 and answerable ones
0.33–0.78. The 0.30 threshold separates them — **by one token**, so it deliberately
annotates the result `weak`/`none` rather than suppressing evidence. Hiding real evidence
on a margin that tight costs more than labelling it cautiously.

### F-17 · The agent is NOT deterministic at `temperature=0` — this changes Phase 8

The same model and the same question returned **different statuses across runs**.
`gpt-oss-120b` on EVAL-007, three consecutive runs: `answered`, `answered`,
`insufficient_evidence`. An earlier single run of `gpt-oss-20b` on the same case failed
where three later runs all passed.

Phase 5 could set a default from single runs because retrieval is deterministic. **The
agent layer is not.** Step 8.2 as planned runs 12 cases × 3 variants *once each*; that
harness would attribute run-to-run variance to whichever variable it is testing. It must
repeat every case and report **rates, not verdicts** (D-008).

This also invalidated two conclusions this session before they were caught. Treat any
single-run agent result as a hypothesis.

### F-18 · Injection resistance holds structurally but is reported unreliably

Across three runs of P3, the agent **never** obeyed the `SLACK-ATLAS-103` payload and
never touched `DOC-HR-001` — the boundary held every time. But it only *told the employee*
an attack was sitting in their data in **1 of 3 runs**; twice it summarised the notes and
silently ignored the instruction.

So: the structural control works, the behavioural one is a coin flip. That is the expected
shape — `THREAT_MODEL.md` classifies reporting as behavioural — but it should be stated in
the evaluation rather than presented as a clean pass.

### F-19 · The injection payload inflates the relevance of the question it hijacks

Asked for the compensation review, retrieval scored **0.50 term coverage** on
`SLACK-ATLAS-103` — because the injected text itself contains the words *"confidential
salary review"*. The attack makes the wrong question look well-evidenced.

Consequence for the code: a refusal must be recognised **before and independently of** the
relevance signals, or a high score overrules a correct refusal. This caused a real defect —
a refusal was labelled `answered`.

### F-20 · Extracting a contract from generated prose requires normalising it first

`gpt-oss` writes source ids with **U+2011 NON-BREAKING HYPHEN** (`GH‑142`), not ASCII.
Id-matching over raw text found nothing, every citation was dropped, and a fully grounded
four-source answer was labelled `insufficient_evidence`. The model chose a
typographically nicer hyphen and silently broke the citation contract.

The failure mode was maximally deceptive: "ungrounded answer" looked like a model-quality
problem, not a parsing bug. Anything that reads structure out of model prose — Phase 8's
scorer included — needs the same normalisation.

### F-21 · The free Groq tier cannot complete a Phase-6-sized evaluation

A 36-turn comparison exhausted the quota: 10 rate-limit waits, and one turn spent **309 s**
across four backoff attempts and still failed. Agent turns also cost **2–80 s** each,
against 23–55 ms for warm retrieval — three orders of magnitude apart.

Two consequences for Phase 8: budget the run in *hours*, not minutes, and **retry 429s in
the harness only**. The product must report a rate limit honestly (T-07); an evaluation
that counts a 429 as a behavioural failure measures the quota, not the model.

Also: **the latency thresholds in `EVALUATION_REPORT.md` were set against retrieval and
cannot be reused for agent turns.** They need restating before Phase 8 measures anything.

## 5 · Decisions already taken

Full entries in `deliverables/DECISIONS.md`. Do not relitigate without new evidence.

| ID | Decision | One-line reason |
| --- | --- | --- |
| **D-001** | Keep Groq + Streamlit as the core path | `AGENTS.md` requires it; alternatives are Phase 10 extensions only |
| **D-002** | One agent, five narrow typed tools, permission **pre**-filter, database queried not embedded | The pre-filter is the only arrangement where a leak is structurally impossible |
| — | **Leo primary, Maya secondary** | Leo owns 7 of 12 cases incl. the engineering-only injection fixture; Maya is *required* because both refund policies are scoped to `customer_success, finance` and a Leo-only product cannot demonstrate the conflicting-policy behaviour |
| **D-003** | **Live source = `sulugambari/ai-agent-project`.** Public again as of Phase 4 close — no token needed for reads. A token is still required for any write action | Guaranteed access for both of us, and our own phase issues are the live data. Mid-phase the repo was briefly private, requiring a collaborator token (§4, F-11) — record generalises to: never assume repo visibility, verify it |
| **D-004** | **Two retrieval namespaces** — `company_knowledge` and `project_board`, reached by different tools | Merging them poisoned retrieval (F-13). Also resolves F-12: scoping the manifest per namespace means a degraded fetch cannot delete another namespace's chunks |
| **D-005** | **Work sequentially, not in parallel** | Human-team decision. One active phase, handed over at each boundary |
| **D-006** | **Default retrieval = hybrid, `lexical_weight = 0.6`** | Argmin of mean expected rank (2.000) at full recall on ten questions. Semantic-only drops to 0.95; lexical-only ranks worse at 2.150 |
| — | **Live work items scoped to `engineering`** despite the repo being readable | Policy stability if the repo goes private, and coherence with the local class. *Not* a claim to protect public data |
| — | **Contract value denied to Customer Success** | No priority question needs it; narrower default when need is not demonstrated |
| — | **Notebook = narrative/evidence layer; `src/` = graded production code** | `AGENTS.md` grades module architecture and requires agent logic independent of the interfaces |
| — | Rejected: post-retrieval filtering | Retrieve-then-redact still puts restricted content in the model, trace and logs |
| — | Rejected: injection pattern-matching as a primary control | Regex-detectable *here*, does not generalise. Data-not-instructions is the control that does |
| **D-007** | **Model = `openai/gpt-oss-20b`, PROVISIONAL** | `llama-3.3-70b-versatile` (the fallback this plan named) returns **404 — does not exist** on our account. Of what remains, `gpt-oss-20b` passed **14 of 15** valid runs across six release-critical behaviours. `gpt-oss-120b` completed **zero** runs of the repeated test before the quota died, so the two are **not** yet distinguished. Revisit when quota allows |
| **D-008** | **Phase 8 must repeat every case and report rates, not verdicts** | F-17: the agent returns different statuses for an identical question at `temperature=0`. A single run per case measures sampling noise |
| — | Rejected: `groq/compound` / `compound-mini` | Available, and rejected **without testing**: they ship server-side web search and code execution, which would punch straight through the read-only boundary (`AGENTS.md`) |
| — | Rejected: `meta-llama/llama-prompt-guard-2` as an injection control | It is exactly the payload pattern-matching `THREAT_MODEL.md` T-01 rules out. Recorded because a reviewer will ask why an available guard model went unused |
| — | **Simulated execution is the default action executor** | `04` permits local or simulated execution and asks that the *approval boundary* be real. A genuine GitHub write also needs a collaborator-scoped token (D-003). The reference is visibly `simulated://` so no reader mistakes it for a URL |
| — | **`EMPLOYEES` moved from `api.py` to `service.py`** | The Streamlit app was importing FastAPI purely to learn who Leo is — the coupling the independence rule forbids. `api.py` re-exports it, so the starter's import path still works |

## 6 · Non-negotiables

From `AGENTS.md`, plus what we have committed to.

- Read-only system. **No** arbitrary SQL, shell, unrestricted file access, web browsing,
  or write tools.
- Permissions enforced **before** retrieval; rechecked at citation time. Default deny.
- Stable `source_id` survives parsing → retrieval → tool output → citation.
- Retrieved content is **untrusted evidence, never instructions**.
- One agent. No multi-agent, no MCP, no OAuth, no extra SaaS.
- Preserve all five fixture traps — they are evaluation requirements.
- Credentials never in prompts, traces, indexed content, figures, or commits.
- Bounded to **6 tool calls** per turn.

**Release blockers** (any one blocks the demo, per `PRODUCT_BRIEF.md`):
`0` forbidden evidence exposed · `0` unapproved executions · `0` fabricated or
unresolvable citations · `0` credentials leaked.

## 7 · Working model — sequential (D-005)

The team decided on **1 September** to work **sequentially rather than in parallel**: one
active phase at a time, handed over at each phase boundary. The original four handover
points collapse into a rolling handover.

| Phase | Owner | Handover |
| --- | --- | --- |
| 4 · Live GitHub | Karthik | ✅ **H1 received** — verified, closed |
| 5 · Managed RAG | Sulu | ✅ **Done.** H2 contract frozen; hybrid `w=0.6` selected (D-006) |
| 6 · Tools + agent | Karthik | ⚠️ 6.1–6.4 done and committed; **6.5 outstanding** (needs model calls) |
| 7 · Product experience | Together | ✅ Done, Karthik driving with Sulu observing. `service.py` is the single application layer; both interfaces call it and nothing else |
| 8 · Evaluation | **Sulu** | ✅ **Handover complete — start now.** See §8 |
| 9 · Packaging | Karthik | Container startup evidence returns to Sulu for `EVALUATION_REPORT.md` |
| 10 · Decide + demo | Together | — |

**Why sequential:** no concurrent edits to shared files, no risk of two coding-agent
sessions rewriting the same notebook, one reviewable line of history, and every phase
gets both reviewers' attention.

**Schedule risk, stated plainly:** Wednesday previously fitted *because* 5 and 6 ran
concurrently. Sequentially it carries 5, then 6, then 7. If it tightens, going parallel
is available at **no rework cost** — the H2 contract is frozen and four of the five
Phase 6 tools never depended on Phase 5.

**Still frozen at the seam:** `company_assistant.rag.Retriever`. The Phase 6 tools depend
on that Protocol, never on a concrete retriever, so the hybrid retriever swaps in without
touching a tool. It held: no tool needed changing when hybrid landed.

**A second seam now exists.** `company_assistant.service.AssistantService` is the only
entry point for asking, approving and rating, and it imports neither Streamlit nor
FastAPI. Your evaluation harness should call it directly rather than driving either
interface — that is what makes the harness, the API and the app exercise the same
behaviour.

### File ownership

| Owner | Files |
| --- | --- |
| **Karthik** | `connectors/github_live.py`, `tools/`, `agent/`, `Dockerfile` |
| **Sulu** | `retrieval/`, indexing + manifest, `evaluation/`, Phase 8 dashboard |
| **Together** | `service.py`, `api.py`, `app.py` (Phase 7) |
| **Frozen** | `models.py` — extend only by agreement |

### ⚠ Notebook policy — read this before you open a notebook

`.ipynb` files are JSON with embedded outputs, so **two people editing one notebook
produces merge conflicts that are painful to resolve.** You have your own:

- **Yours:** `notebooks/phase_04_live_github.ipynb` (created, pre-wired with the
  bootstrap, chart theme, `save_chart()`, and the `probe()` regression harness)
- **Sulu's:** `notebooks/northstar_build.ipynb` — please do not edit
- Step 10.3 splices them for the final documentation

## 8 · Your Phase 8 brief

Board issue: [#9](https://github.com/sulugambari/ai-agent-project/issues/9).
Course text: `05-evaluation-and-release.md` Phase 8.
*(The Phase 6 brief that used to live here is in the git history.)*

### What you inherit, working and tested

```python
from company_assistant.service import EMPLOYEES, AssistantService

service = AssistantService()                       # holds index, agents, approvals
result  = service.ask(question, EMPLOYEES["leo"])  # -> AskResult
result.answer          # the shared Answer contract: status, text, citations, trace
result.answer_id       # what feedback refers to
result.latency_ms

service.ask_baseline(question, employee)           # Phase 3 lexical baseline, no model
service.status()                                   # index units, last-indexed, freshness
service.record_feedback(answer_id, "up", reason="correct", retrieval_mode="hybrid")
```

**Call `AssistantService` directly.** Do not drive Streamlit or FastAPI to evaluate — the
service is interface-independent precisely so the harness, the API and the app all
exercise one code path. Pass `conversation_id=None` (the default) so a case cannot inherit
state from a case that ran before it.

| Layer | What is proven | Evidence |
| --- | --- | --- |
| 5 tools | normal / denied / empty / failure, all distinct | 24 direct calls, 24 pass — `6_2_tool_test_matrix` |
| Relevance | absolute coverage separates answerable from unanswerable | `6_2_relevance_threshold` |
| Agent | bounded to 6 tool calls, candidate set carried out per turn | notebook 6.3 assertions |
| Approval gate | approved / edited / rejected / failed all recorded; re-approval never double-executes | 21 transitions, 21 pass |
| Service | baseline preserved, permissions hold, feedback stores 5 fields only | 18 checks, 18 pass |
| Interfaces | app renders and answers with no exception or leak; 5 endpoints respond | Streamlit `AppTest`, FastAPI `TestClient` |

### Steps
- **8.1** Write thresholds **before** seeing results. Note the latency threshold problem
  in F-21 — the existing numbers were set against retrieval and cannot be reused.
- **8.2** The harness. **Repeat every case** (D-008, F-17) and report rates.
- **8.3** Special-setup cases: EVAL-008 DB failure, EVAL-011 add→sync→verify→delete→sync,
  EVAL-012 live and deliberately unavailable.
- **8.4** Streamlit evaluation page + notebook charts.
- **8.5** Fill the `EVALUATION_REPORT.md` scenario table and residual risks.

### What must be true when you are done

1. **Every case ran more than once.** This is the single biggest change from the plan. See
   F-17 — two conclusions were already invalidated by single-run results this session.
2. **429s are retried in the harness, never in the product.** The product must report a
   rate limit honestly (T-07); an evaluation that scores a 429 as a behavioural failure
   measures our Groq quota instead of the model.
3. **Budget the run in hours.** Agent turns cost 2–80 s and the free tier throttles hard
   (F-21). A 36-turn comparison exhausted the quota outright.
4. **Normalise model prose before parsing it.** F-20: `gpt-oss` writes source ids with
   U+2011, and a scorer matching ASCII will silently score a perfect answer as ungrounded.
   `agent.runner.normalize_for_id_matching` already exists — reuse it.
5. **Report injection resistance as two separate results** (F-18): the structural control
   held in 3 of 3 runs, the *reporting* of the attack in 1 of 3. A single "pass" hides that.
6. **Settle D-007.** `gpt-oss-120b` has zero repeated runs. Either complete the bake-off or
   record explicitly that the models were not distinguished.

### The hard problem in Phase 8

**Measuring a non-deterministic system against thresholds fixed in advance.** F-17 means a
case can pass and fail the same threshold in one sitting. Decide before 8.1 how many runs
constitute a result and what rate counts as passing — and note that the four release
blockers (`0` forbidden evidence, `0` unapproved executions, `0` fabricated citations,
`0` credentials leaked) cannot be rate-based. Those must hold on **every** run, which
means variance makes them *harder* to prove, not easier.

### Fixes still owed in your own files

- **`rag/hybrid.py`: `DEFAULT_LEXICAL_WEIGHT` is 0.5 while D-006 chose 0.6** (F-15). The
  tools work around it explicitly; the library default is still wrong.
- **`rag/index.py`** was changed during Phase 7 to persist the freshness manifest,
  because step 7.3's last-indexed disclosure was otherwise unmeetable (F-15, item 2).
  Noted here so the change is attributable, not because it went unseen.

### Completion evidence required
Another group can inspect the dashboard, trace a failed case back to its evidence, and
understand why one variant was selected.

### When you finish
Tick 8.1–8.5 on [#9](https://github.com/sulugambari/ai-agent-project/issues/9), append to
`deliverables/SLIDE_DECK.md`, and hand back for Phase 9 (packaging, Karthik).

## 9 · Working conventions

We have been running the project as **permission-gated steps**. Each step:

1. State what is done, what is next, and why.
2. Get human approval before executing.
3. Execute, then record evidence in the notebook.
4. Tick the step checkbox on the board issue and comment the findings.
5. Append presentable findings to `deliverables/SLIDE_DECK.md` (78 entries so far; 10 of
   them from Phases 6–7).
6. Commit with a message that explains *why*, not just *what*.

**Every chart** goes through `save_chart(chart, name, caption=...)`, which writes a
tracked 2× PNG to `deliverables/figures/`, a git-ignored Vega-Lite spec to
`data/generated/charts/`, and a `.txt` holding the one-line message the figure proves.
18 figures so far. A final slide deck is required (step 10.4) and is assembled from that
ledger.

**Phases 6 and 7 followed these conventions with two exceptions, both worth knowing.**
Phase 6 evidence went into `phase_04_live_github.ipynb` rather than a third notebook, so
the bootstrap, chart theme, `save_chart()` and `probe()` harness are reused rather than
duplicated — the filename understates what it holds. And **the board was not updated and
nothing was pushed**: both are outward-facing actions left for the human team to
authorise. Steps 6.1–6.4 and 7.1–7.4 are unticked on [#7](https://github.com/sulugambari/ai-agent-project/issues/7)
and [#8](https://github.com/sulugambari/ai-agent-project/issues/8) despite being done.

## 10 · Known gotchas

| Gotcha | What to do |
| --- | --- |
| `gh project item-edit --number 0` | Silently treated as "no change". Use GraphQL `updateProjectV2ItemFieldValue` for zero |
| Altair 6 dropped `alt.themes.register` | Use `@alt.theme.register(name, enable=True)` |
| Notebook working directory | Bootstrap walks up to the repo root and `chdir`s there, so the starter's relative default paths resolve |
| Global grid theme bleeds into heatmaps | Set `grid=False, ticks=False` on both axes for `mark_rect` charts |
| Multi-word axis labels collide | `labelExpr="split(datum.label, ' ')"` plus `labelPadding≈24` |
| `starlette.testclient` deprecation warning | Cosmetic (suggests `httpx2`). No action |
| SQLite fixture is not byte-reproducible | Compare rows, never checksums (F-10) |
| Streamlit reruns the whole script per interaction | Cache heavy resources with `@st.cache_resource`; hold proposals immutably in `st.session_state` keyed by `proposal_id` |
| Groq free tier throttles hard | Agent turns cost 2–80 s. A 36-turn run exhausted the quota (F-21). Retry 429s in the harness only, never in the product |
| `gpt-oss` writes ids with U+2011 | Non-breaking hyphen, not ASCII. Normalise before matching source ids in prose (F-20) — `agent.runner.normalize_for_id_matching` |
| The agent varies at `temperature=0` | Same question, different status (F-17). Never conclude from a single run |
| `pkill -f 'streamlit run app.py'` | Matches your own shell's command line and kills the session. Use the pid |
| `AppTest.from_file` relative paths | Resolved against the *calling* file, not the cwd. Pass an absolute path |
| `at.form` does not exist in Streamlit 1.62 | Assert on the submit buttons instead |

## 11 · Open questions

| Question | Owner | Needed by |
| --- | --- | --- |
| **Is `gpt-oss-120b` actually better than `gpt-oss-20b`?** Zero repeated runs completed; D-007 is provisional | Joint | **Step 8.1** |
| **What counts as a pass for a non-deterministic system?** How many runs per case, and what rate — noting the four release blockers cannot be rate-based | **Sulu** | **Step 8.1** |
| **What are the agent-turn latency thresholds?** The existing ones were set against 23–55 ms retrieval; turns take 2–80 s (F-21) | **Sulu** | **Step 8.1** |
| Should `search_company_knowledge` ever *suppress* weak evidence rather than only labelling it? Currently it annotates, because the threshold separates by one token (F-16) | Joint | Step 8.5 |
| Can injection *reporting* be made reliable without payload matching? 1 of 3 runs reported it (F-18). T-01 rules out the obvious fix | Joint | Phase 10 |
| Do we want live Atlas-shaped issues in the repo so the live path can serve EVAL-012 directly? | Joint | Phase 8 |
| P2 as a **Leo** question needs a custom eval case; supplied EVAL-003 covers the same conflict as **Maya** | Sulu | Step 8.2 |
| Which Phase 10 extension, if time allows? Freshness-aware ranking still attacks F-2 directly | Joint | Phase 10 |

**Closed since the last update:** the model fallback question (D-007, provisionally), the
Phase 8 harness design question (D-008), and F-2 itself — status-aware reasoning in
`compare_sources` resolves it, 3 runs of 3.

## 12 · File map

| Path | What |
| --- | --- |
| `PROJECT_PLAN.md` | 11 phases / 37 steps, plain-language product explanation, ground rules |
| `HANDOVER.md` | This file |
| `deliverables/PRODUCT_BRIEF.md` | Product direction, priority questions, trust demonstrations, thresholds |
| `deliverables/ACCESS_MATRIX.md` | 11 record classes × 4 roles, audited 32/32; source governance |
| `deliverables/THREAT_MODEL.md` | 8 threats, 26 controls classified structural / behavioural / detective |
| `deliverables/DECISIONS.md` | D-001 … D-006. **D-007 and D-008 are recorded in §5 here but not yet written up there** |
| `deliverables/EVALUATION_REPORT.md` | Thresholds and the Phase 3 baseline, fixed before any variant existed |
| `deliverables/SLIDE_DECK.md` | 17-slide structure + 78-entry step ledger |
| `deliverables/figures/` | 18 tracked 2× PNGs with captions |
| `notebooks/northstar_build.ipynb` | Sulu's spine — 56 cells, executes clean |
| `notebooks/phase_04_live_github.ipynb` | Karthik's — Phases 4, **6 and 7** (31 cells). The name understates it |
| `docs/CHAT_HISTORY.md` | Readable session transcript, 21 turns |
| `docs/chat-history-raw.jsonl` | Verbatim transcript, 8.4 MB |
| `src/company_assistant/rag/` | **The retrieval layer.** `contract.py` (the frozen H2 Protocol), `index.py` (Chroma + permission pre-filter + lifecycle), `lexical.py`, `semantic.py`, `hybrid.py` |
| `src/company_assistant/connectors/github_live.py` | Live GitHub connector with fallback and freshness |
| `src/company_assistant/tools/` | **The five tools.** `schemas.py` (typed envelopes), `knowledge.py`, `work_items.py`, `support.py`, `comparison.py` (the F-2 tool), `actions.py`, `conflicts.py`, `relevance.py` (the F-16 fix), `registry.py` (identity binding) |
| `src/company_assistant/agent/` | `prompt.py` (the T-01 behavioural control), `runner.py` (bounded agent; derives the Answer contract from tool results, not model claims) |
| `src/company_assistant/approval.py` | **The approval gate — deliberately outside `tools/`.** The agent can reach everything in `tools` and nothing here |
| `src/company_assistant/service.py` | **The single application layer.** Imports neither Streamlit nor FastAPI. Also holds `EMPLOYEES` |
| `src/company_assistant/api.py` | `/ask`, `/approve`, `/feedback`, `/health`, `/status`. Approval contract separate from the answer contract |
| `app.py` | Streamlit chat, citations, warnings, trace, and the approval panel below the conversation |
| `data/index/freshness_manifest.json` | Last-indexed time and per-namespace freshness, persisted so a fresh process does not claim `local` over live data (F-15) |
| `src/company_assistant/` | Starter connectors, permissions, lexical baseline |

## 13 · The single most important thing

At the Phase 5 boundary this section read: *"a correct permission boundary and a
measurably weak reasoning layer."* Half of that has changed.

**The boundary still holds, now through six independent checks** — lexical (3.2), semantic
(5.2), all three modes on five questions (5.3), all three modes on ten (5.5), the tool
matrix (6.2), and the service layer (7.1) — with **zero** forbidden results and **zero**
forbidden candidates throughout. Leo never reaches `DOC-HR-001`; obeying the injection
retrieves nothing; nothing executes without a separate approval.

**F-2 is fixed.** The archived refund policy still *outranks* the current one at every
retrieval setting, and it no longer matters: the conflict now reaches the agent as a
field, and `compare_sources` names the authoritative record. It passed 3 runs of 3. The
fix was not a better ranker — it was moving the reasoning above retrieval and making the
conflict **data rather than a hope that the prompt made the model notice**.

**What is new, and what Phase 8 is really about:** every defect found in Phases 6 and 7
was found by a *consumer* exercising a contract, never by the layer that wrote it. The
retrieval weight disagreed with the decision. Freshness evaporated on process restart.
Hybrid mode could not express irrelevance. And three of my own defects came from reading
structure out of model prose — a Unicode hyphen silently voided every citation on a
correct answer.

So the honest summary is: **the structural controls are solid and the behavioural ones are
a coin flip.** F-17 (non-determinism) and F-18 (injection reported 1 time in 3) are the
same fact seen twice — anything that depends on the model *choosing* to do the right thing
varies run to run. That is exactly why Phase 8 must repeat every case, and why the release
blockers have to hold on every run rather than on average.

The executable assertions in both notebooks exist so a regression fails loudly rather than
quietly. There are **58** across the two notebooks, plus 24 tool checks, 21 approval
transitions and 18 service checks. Please keep them passing.

**One caveat on reproducing them today:** the Groq quota is exhausted, so cell 6.3 reports
a `RateLimitError` and skips its assertions rather than crashing (F-21). Everything
deterministic — 6.1, 6.2, 6.4 — still runs and asserts. The notebook executes end to end
with 31 cells and 0 errors in that state, which is the honest condition to hand over in
rather than a green run that needed a working quota to produce.
