# HANDOVER — Northstar Release Coordinator

**For Karthik.** Everything needed to continue from Phase 4 without reverse-engineering
decisions already taken. Read sections 1–3 (about 10 minutes), then jump to §8.

- **Written:** 1 September 2026, end of Tuesday, after Phase 3 closed
- **State:** Phases 0–3 complete · Phases 4–10 open · 10 commits on `main`
- **Board:** <https://github.com/users/sulugambari/projects/12>
- **Full session transcript:** `docs/CHAT_HISTORY.md` (readable, 21 turns) and
  `docs/chat-history-raw.jsonl` (verbatim, 8.4 MB)

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

Then open `notebooks/northstar_build.ipynb`, select the `.venv` kernel, and run all
cells. It executes clean end to end (27 code cells, 0 errors) and is the fastest way to
see every finding below with its evidence.

**You will need `.env` for Phase 4:**
```bash
cp .env.example .env
# GITHUB_REPOSITORY=sulugambari/ai-agent-project
# GITHUB_TOKEN=            <- leave EMPTY. The repo needs no token (see §5, D-003)
# GROQ_API_KEY=            <- needed from Phase 6, not Phase 4
```

## 3 · Where we are

| Phase | Owner | Status |
| --- | --- | --- |
| 0 · Project setup | Together | ✅ Done |
| 1 · Frame the product | Together | ✅ Done — cleared the `AGENTS.md` implementation gate |
| 2 · Information boundary | Together | ✅ Done — cleared the semantic-retrieval gate |
| 3 · Deterministic baseline | Sulu | ✅ Done |
| **4 · Live GitHub source** | **Karthik** | **← you start here** |
| 5 · Managed RAG pipeline | Sulu | Todo (Wed) |
| 6 · Tools and one agent | **Karthik** | Todo (Wed) |
| 7 · Product experience | Together | Todo (Wed eve) |
| 8 · Comparative evaluation | Sulu | Todo (Thu) |
| 9 · Package the product | **Karthik** | Todo (Thu) |
| 10 · Decide and demonstrate | Together | Todo (Thu) |

**Phase 3 and Phase 4 were parallel, not sequential** — neither blocks the other, and
both feed Phase 5. Same for 5 ‖ 6 and 8 ‖ 9.

## 4 · The findings that constrain your work

These are the reason to read this document rather than just the course files. Each was
measured, not assumed, and each changes what Phases 4–6 must do.

### F-1 · The lexical baseline is not a strawman
It retrieved **all three** EVAL-002 expected sources (`GH-142`, `GH-149`,
`DOC-ATLAS-403`) for the Atlas blocker question. Phase 5 must beat something real, and
the evaluation must be framed honestly.

### F-2 · The archived refund policy OUTRANKS the current one — 0.571 vs 0.429
For *"What is the current approval threshold for a refund?"*, `DOC-POLICY-OLD-402`
(archived, EUR 2,500) beats `DOC-POLICY-401` (current, EUR 1,000).

**Why:** the archived document's own warning — *"Do not use this archived **threshold**
for **current** decisions"* — supplies the two query terms the current policy never
uses. **The disclaimer written to prevent misuse is what makes the stale document win.**

**Consequence for you:** semantic retrieval will *not* fix this — the two documents are
semantically near-identical and the archived one is *more* on-topic for "current". The
fix has to be **status-aware reasoning in the agent** over `status` and `effective_at`.
Your Phase 6 agent, not Sulu's Phase 5 retriever, is where this gets solved. Figure:
`3_3_conflict_baseline.png`.

### F-3 · The permission filter is load-bearing, and proven by counterfactual
`DOC-HR-001` ranks **#1 at score 0.86** in an unfiltered copy of the same scoring
function, and is **absent** from Leo's filtered candidate set. Priya correctly retrieves
it. 4 roles × 9 adversarial queries → **0 violations**, asserted in executable code.

**Consequence:** that assertion is a regression guard. If your tools ever retrieve
without passing `EmployeeContext`, it fails. Figure: `3_2_filter_is_loadbearing.png`.

### F-4 · A refusal is NOT evidence of pre-retrieval filtering
A refusal is equally consistent with a model that was merely instructed to decline. Only
the **candidate set** proves the record never reached the model.

**Consequence:** the Phase 7 trace panel is the evidence for our most important access
claim, not a UI nicety. Your agent must expose the candidate set per turn.

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

## 5 · Decisions already taken

Full entries in `deliverables/DECISIONS.md`. Do not relitigate without new evidence.

| ID | Decision | One-line reason |
| --- | --- | --- |
| **D-001** | Keep Groq + Streamlit as the core path | `AGENTS.md` requires it; alternatives are Phase 10 extensions only |
| **D-002** | One agent, five narrow typed tools, permission **pre**-filter, database queried not embedded | The pre-filter is the only arrangement where a leak is structurally impossible |
| — | **Leo primary, Maya secondary** | Leo owns 7 of 12 cases incl. the engineering-only injection fixture; Maya is *required* because both refund policies are scoped to `customer_success, finance` and a Leo-only product cannot demonstrate the conflicting-policy behaviour |
| — | **Live source = `sulugambari/ai-agent-project`** | Guaranteed access for both of us, **no token needed**, and our own phase issues are the live data |
| — | **Live work items scoped to `engineering`** despite the repo being readable | Policy stability if the repo goes private, and coherence with the local class. *Not* a claim to protect public data |
| — | **Contract value denied to Customer Success** | No priority question needs it; narrower default when need is not demonstrated |
| — | **Notebook = narrative/evidence layer; `src/` = graded production code** | `AGENTS.md` grades module architecture and requires agent logic independent of the interfaces |
| — | Rejected: post-retrieval filtering | Retrieve-then-redact still puts restricted content in the model, trace and logs |
| — | Rejected: injection pattern-matching as a primary control | Regex-detectable *here*, does not generalise. Data-not-instructions is the control that does |

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

## 7 · Handover points

| # | When | Direction | Artifact |
| --- | --- | --- | --- |
| **H1** | End of Tue | **Karthik → Sulu** | Live connector emitting `CompanyDocument` on the same contract, with fallback and `source_freshness` |
| **H2** | Wed 09:00 | **Sulu → Karthik** | The retriever **signature** (not the implementation) — 20 minutes, together |
| **H3** | Wed midday | **Sulu → Karthik** | Working hybrid retriever swapped in behind that signature |
| **H4** | Thu PM | **Karthik → Sulu** | Container startup evidence for `EVALUATION_REPORT.md` |

### The one real blocking dependency

**Phase 6's `search_company_knowledge` tool wraps Phase 5's retriever.** Do not wait for
it. At H2 we freeze the signature:

```python
def search(query: str, employee: EmployeeContext, *,
           mode: RetrievalMode = "hybrid", limit: int = 6) -> list[SearchResult]: ...
```

Code all five tools against that, using the existing `lexical_search` as a stand-in, and
swap in the hybrid retriever at H3 with no tool changes. **Your other four tools have
zero dependency on Phase 5** — build and test them first.

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

## 8 · Your Phase 4 brief

Board issue: [#5](https://github.com/sulugambari/ai-agent-project/issues/5).
Course text: `04-connected-rag-and-agent.md` Phase 4.

### Steps
- **4.1** Configure `.env` / `GITHUB_REPOSITORY`; confirm the token boundary
- **4.2** Build the live connector: pagination, explicit API error handling, stable IDs,
  intentional access policy
- **4.3** Fallback and controlled-failure test; prove no fabricated freshness

### What the connector must do
1. Accept the repository through configuration, never hardcoded.
2. Handle **pagination** and API errors **explicitly** — no bare `except`.
3. Normalize into the same `CompanyDocument` contract. A malformed response must
   **raise** (F-6), not produce a record with empty `allowed_roles`.
4. Stable ID **independent of the issue title** — use the issue number, keep `node_id`
   in metadata. `04` requires this explicitly.
5. Preserve `html_url`, number, labels, state, author, assignees, update time.
   **`html_url` is the only genuine deep link in the entire product** — every other
   source's citation resolves to the record, not the origin system.
6. Set `allowed_roles = {"engineering"}` — an **intentional** policy, not "whatever the
   API allowed" (§5).
7. Record `source_freshness` = `live` | `fallback` and `fetched_at` on every record.
8. Fall back to `data/raw/github/` on failure, **disclose** the degraded state, and never
   present fallback data as live freshness.

### Dependency
`httpx` is already installed (0.28.1) as a transitive dependency. **`04` requires you to
add it as a direct project dependency** if the connector imports it:
`uv add httpx`. Do not add a GitHub SDK — a few REST calls do not justify it.

### A consequence you should know about before you start
Our live repo's issues are the **project-management issues** (Phases 0–10), not Atlas
issues. EVAL-012 expects `GH-142`/`GH-149`, which exist only in the local export. So:

- Treat the live repo as an **additional** work-item source merged with the local export,
  both on the same contract.
- EVAL-012 is satisfied by **disclosure of fallback state**, verified in both
  configurations (live available / live deliberately unavailable).
- Do not fabricate Atlas-shaped issues in the repo to make the case pass. If we decide we
  want live Atlas issues, that is a joint decision to record in `DECISIONS.md`.

### Completion evidence required
The interface cites one live issue; the same connector works against the local fallback;
a failed API call produces a controlled state rather than fabricated evidence.

## 9 · Working conventions

We have been running the project as **permission-gated steps**. Each step:

1. State what is done, what is next, and why.
2. Get human approval before executing.
3. Execute, then record evidence in the notebook.
4. Tick the step checkbox on the board issue and comment the findings.
5. Append presentable findings to `deliverables/SLIDE_DECK.md` (39 entries so far).
6. Commit with a message that explains *why*, not just *what*.

**Every chart** goes through `save_chart(chart, name, caption=...)`, which writes a
tracked 2× PNG to `deliverables/figures/`, a git-ignored Vega-Lite spec to
`data/generated/charts/`, and a `.txt` holding the one-line message the figure proves.
10 figures so far. A final slide deck is required (step 10.4) and is assembled from that
ledger.

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

## 11 · Open questions

| Question | Owner | Needed by |
| --- | --- | --- |
| Which Groq model — `llama-3.3-70b-versatile` vs `openai/gpt-oss-20b`? Bake off before fixing a default | Karthik | Step 6.3 |
| Do we want live Atlas-shaped issues in the repo so the live path can serve EVAL-012 directly? | Joint | Phase 4 / 8 |
| Default retrieval mode — must follow measured results, not preference | Sulu | Step 5.5 |
| P2 as a **Leo** question needs a custom eval case; supplied EVAL-003 covers the same conflict as **Maya** | Sulu | Step 8.2 |
| Which Phase 10 extension, if time allows? Current recommendation: freshness-aware ranking (attacks F-2 directly) | Joint | Phase 10 |

## 12 · File map

| Path | What |
| --- | --- |
| `PROJECT_PLAN.md` | 11 phases / 37 steps, plain-language product explanation, ground rules |
| `HANDOVER.md` | This file |
| `deliverables/PRODUCT_BRIEF.md` | Product direction, priority questions, trust demonstrations, thresholds |
| `deliverables/ACCESS_MATRIX.md` | 11 record classes × 4 roles, audited 32/32; source governance |
| `deliverables/THREAT_MODEL.md` | 8 threats, 26 controls classified structural / behavioural / detective |
| `deliverables/DECISIONS.md` | D-001, D-002 |
| `deliverables/EVALUATION_REPORT.md` | Thresholds and the Phase 3 baseline, fixed before any variant existed |
| `deliverables/SLIDE_DECK.md` | 17-slide structure + 39-entry step ledger |
| `deliverables/figures/` | 10 tracked 2× PNGs with captions |
| `notebooks/northstar_build.ipynb` | Sulu's spine — 56 cells, executes clean |
| `notebooks/phase_04_live_github.ipynb` | **Yours** |
| `docs/CHAT_HISTORY.md` | Readable session transcript, 21 turns |
| `docs/chat-history-raw.jsonl` | Verbatim transcript, 8.4 MB |
| `src/company_assistant/` | Starter connectors, permissions, lexical baseline, API, service |

## 13 · The single most important thing

We have a **correct permission boundary and a measurably weak reasoning layer.**
0 release blockers, 5 product failures in the baseline.

Phases 5 and 6 must fix abstention and authority **without regressing the boundary**.
The executable assertions in the notebook — 36 adversarial retrievals with 0 violations,
and every threat retaining a structural control — exist so that a regression fails loudly
instead of quietly. Please keep them passing.
