# Decision Log

Record meaningful product and architecture decisions, not every small edit.

## Recorded Decisions

### D-001 · Retain Groq and Streamlit as the core stack; defer alternatives to extensions

- **Phase:** 0 (raised before implementation, revisited from `AGENTS.md`)
- **Context:** Before building, the team asked whether an alternative model provider
  or interface framework would improve implementation, execution, or performance.
  `AGENTS.md` requires Groq and Streamlit as the core path, with alternative
  providers and interfaces confined to the optional extensions in
  `05-evaluation-and-release.md` after the required evaluation is complete.
- **Options considered:**
  1. **Retain Groq + Streamlit** (selected). Compliant, and Groq's low inference
     latency directly benefits the Phase 8 requirement to measure end-to-end
     latency across three variants.
  2. **Swap the interface for Chainlit or a React/Next.js frontend** (rejected).
     `05-evaluation-and-release.md` warns against replacing Streamlit for visual
     novelty and permits it only to serve a concrete, observed product need. No
     such need has been observed yet, and rebuilding a working interface would
     consume Wednesday for an unmeasured gain.
  3. **Swap the provider for Mistral AI or OpenRouter** (rejected for the core
     path, retained as a candidate extension). A provider comparison measures
     providers, not this product's weaknesses, and cannot be justified before
     evaluation identifies a limitation.
- **Coding-agent contribution:** Claude Code identified that neither Groq nor
  Streamlit is the actual performance constraint, and located four in-bounds
  levers that matter more than either substitution: Groq model selection for
  tool-calling reliability, a rate-limit-resilient evaluation harness, cached
  heavyweight resources in Streamlit, and a rerun-safe approval flow.
- **Evidence reviewed:** `AGENTS.md` line 16; the Optional Extensions section of
  `05-evaluation-and-release.md`; `.env.example`, which ships the small
  `openai/gpt-oss-20b` model; the rerun caveat already documented in `app.py`.
- **Decision and owner:** Retain Groq and Streamlit for the core path. Owner: Sulu.
- **Consequences or follow-up:**
  - **Phase 6.3 —** evaluate `llama-3.3-70b-versatile` against `openai/gpt-oss-20b`
    on the real tool set before fixing a default. A 20B model choosing among five
    tools, reconciling conflicting sources, and abstaining correctly is operating
    at the edge of its capability; tool-call reliability is the primary quality
    risk in this project. Record the outcome as a follow-up decision.
  - **Phase 8.2 —** persist each evaluation result to `data/generated/` as it
    completes and make the harness resumable. Free-tier rate limits, not inference
    speed, are the realistic Groq failure mode across 12+ cases x 3 variants plus
    retries and iterations.
  - **Phases 5.2 and 7.3 —** wrap the embedding model and Chroma client in
    `@st.cache_resource`. Uncached, Streamlit reloads a ~90 MB embedding model on
    every rerun, which presents as agent slowness but is resource loading.
  - **Phase 6.4 —** the approval flow must be rerun-safe: proposals held immutably
    in `st.session_state` keyed by `proposal_id`, approval submitted through a
    form, execution idempotent. A rerun-induced double execution or lost approval
    would be a release blocker under the Phase 8 thresholds.
  - **Phase 10 —** if capacity remains, the highest-value extension for this
    product is freshness-aware ranking, because it attacks the two hardest
    fixtures directly: the archived EUR 2,500 refund threshold and the obsolete
    5 September Atlas commitment.
- **Status:** Accepted

### D-002 · Single agent with narrow typed tools and a pre-retrieval permission filter

- **Phase:** 2 (step 2.3), before implementation
- **Context:** The architecture had to satisfy three constraints simultaneously:
  answer priority question P1, which reconciles a four-condition checklist across
  four source families; make an unauthorized disclosure *structurally* impossible
  rather than prompt-dependent; and remain evaluable layer by layer, since
  `02-system-design.md` requires connector, permission, retrieval, tool-routing,
  grounding and abstention to be assessed separately.
- **Options considered:**
  1. **Single LangChain `create_agent` runtime, five narrow typed tools,
     permission filtering applied before retrieval, and the business database
     queried through tools rather than embedded** — *selected*. The pre-filter is
     the only arrangement in which a restricted record never enters the candidate
     set, so T-02 is closed structurally instead of behaviourally. Narrow typed
     tools make inputs, outputs, permissions and failure modes explicit, which is
     what makes tool routing measurable. One agent keeps the trace legible enough
     to evaluate.
  2. **Deterministic retrieve-then-generate pipeline with no agent** — *rejected
     for the core path.* It cannot satisfy P1, which requires deciding *which*
     sources to consult per condition, and it removes the tool-routing evaluation
     layer entirely. It is genuinely better for fixed high-risk steps, and
     `05-evaluation-and-release.md` lists it as an optional extension; **retained
     as the preferred Phase 10 comparison** because it would isolate how much the
     agent loop actually contributes.
  3. **Post-retrieval filtering — retrieve everything, then redact** — *rejected.*
     Restricted content would reach the model, the trace and the logs before being
     removed, so the disclosure still happens and is merely hidden from the final
     answer. This converts a structural control into a behavioural one, which is
     precisely the failure `AGENTS.md` forbids.
  4. **Multiple specialised agents** — *rejected.* Explicitly forbidden by
     `AGENTS.md`, and it would add orchestration surface without addressing any
     identified threat.
- **Coding-agent contribution:** Claude Code produced the threat model, classified
  every control as structural, behavioural or detective, and identified that the
  distinguishing property between options 1 and 3 is not answer quality but
  *where in the pipeline the guarantee lives*. It also found that option 3 would
  leave restricted content in traces and logs even when the answer looked correct.
- **Evidence reviewed:** the step 1.1 access heatmap; the step 2.1 policy-versus-
  fixture audit, 32 of 32 matching; the step 2.2 change-detection comparison; the
  recommended architecture in `02-system-design.md`; and the tool boundaries in
  `AGENTS.md`.
- **Decision and owner:** adopt option 1. Owner: Sulu.
- **Consequences or follow-up:**
  - Permission filtering must be a **metadata pre-filter on the vector query** in
    Phase 5.2, not a post-query filter, or the structural guarantee is lost.
  - Chunk fingerprints must span access metadata (D-002 depends on T-08 being
    closed; see `THREAT_MODEL.md` and step 2.2).
  - The agent is bounded to six tool calls, which caps worst-case latency and
    cost and keeps the trace readable.
  - The deterministic pipeline is recorded as the preferred Phase 10 extension.
  - `THREAT_MODEL.md` asserts in executable form that every threat retains a
    structural control; a later phase that weakens one fails that assertion.
- **Status:** Accepted

### D-003 · Live GitHub source requires a fine-grained, read-only, single-repo token

- **Phase:** 4 (steps 4.1–4.2), during implementation
- **Context:** HANDOVER.md and ACCESS_MATRIX.md recorded `sulugambari/ai-agent-project`
  as a public repository needing no token, on the assumption that both team members'
  existing SSH access implied REST API access. Building the live connector (4.1)
  falsified this: an unauthenticated `GET /repos/sulugambari/ai-agent-project`
  returned `404`, and the repo was still absent from the collaborator's `/user/repos`
  even after a fine-grained token was issued, because the GitHub *collaborator invite*
  itself had not been accepted. `git ls-remote` succeeding over SSH said nothing about
  REST API access — the two are authorized independently (F-11).
- **Options considered:**
  1. **Accept the collaborator invite and use a fine-grained, read-only,
     single-repository token scoped to `sulugambari/ai-agent-project`** — *selected*.
     Preserves the original repo choice (guaranteed access for both of us, our own
     phase issues as live data) once the invite is actually accepted; matches the
     course text's own guidance for a private repository ("use a fine-grained
     personal access token limited to one repository and read-only issue metadata").
  2. **Switch the live source to a repository owned outright by one team member**
     (tried during implementation: `karthikarumukam-code/ds-ai-agent`) — *rejected*.
     Broke the "guaranteed access for both of us" property the original choice was
     selected for, and had no existing issues to serve as live data. Reverted once the
     collaborator-invite root cause was found instead of worked around.
  3. **Treat the repo as effectively unreachable and rely on the local fallback
     only** — *rejected*. Would satisfy EVAL-012's fallback-disclosure requirement but
     not the Phase 4 completion evidence, which requires citing one genuinely live
     issue.
- **Coding-agent contribution:** Claude Code diagnosed the 404 as a real access gap
  (not a naming or config error) by cross-checking the unauthenticated request against
  `git ls-remote` (which succeeded) and `/user/repos` (which omitted the target repo
  even with a token), isolating the cause to an unaccepted collaborator invite rather
  than a token-scope or repo-visibility problem.
- **Evidence reviewed:** `curl` against the GitHub REST API, unauthenticated and
  token-authenticated; `git ls-remote origin`; `/user/repos` for the issuing account;
  `04-connected-rag-and-agent.md`'s guidance on fine-grained tokens for private repos.
- **Decision and owner:** adopt option 1. Owner: Karthik, confirmed with Sulu.
- **Consequences or follow-up:**
  - `HANDOVER.md` §2 and §5, and `ACCESS_MATRIX.md`'s "API reachability is not
    authorization" section, corrected from "public, no token needed" to reflect the
    repo was briefly private mid-phase (F-11 added to HANDOVER.md §4).
  - The intentional `allowed_roles = {"engineering"}` policy on live work items is
    unaffected either way — it was already justified independent of the repo's actual
    visibility (reason 1 in `ACCESS_MATRIX.md` predicted exactly this kind of change).
  - Token scope stays minimal: Issues read-only, single repository, elevated to
    read-write only twice and briefly, to seed and then clean up two test issues in
    the abandoned `ds-ai-agent` detour, and returned to read-only afterward.
- **Update (later in Phase 4):** the team made `sulugambari/ai-agent-project` public
  again, restoring unauthenticated read access — the connector needs no token for
  fetches against it as currently configured. This does not reverse the decision: a
  token is still required for any *write* action (e.g. the board comment recording
  Phase 4's completion evidence), independent of repository visibility, and `HANDOVER.md`
  / `ACCESS_MATRIX.md` are updated to state the *current* visibility rather than
  either extreme, with F-11 generalised to "verify visibility, never assume it."
- **Status:** Accepted

### D-004 · Separate retrieval namespaces for the live project board

- **Phase:** 5 (step 5.2), triggered by finding F-13 during handover H2
- **Context:** Merging the live GitHub records into the searchable corpus was measured
  to contaminate company-knowledge retrieval. Across the three priority questions plus
  EVAL-002 and EVAL-012, **16 of 30 top-6 result slots** were occupied by our own
  project-management issues; EVAL-012 was worst at 5 of 6; and `GH-LIVE-2`
  (*"Phase 1 · Frame the Product"*) outranked both `DOC-ATLAS-403` and `GH-142` on the
  flagship release-readiness question. The cause is structural rather than a ranking
  artifact: the board issues *describe the product being built*, so they carry the same
  vocabulary — Atlas, release, blocking, conditions — as the evidence they were merged
  beside. The risk is worse than noise, because the agent could cite an issue about
  building the assistant as evidence about Atlas's real release status. That is
  fabricated evidence wearing a valid citation, and it would pass a naive
  "is every claim cited?" check.
- **Options considered:**
  1. **Two retrieval namespaces — `company_knowledge` and `project_board` — reached by
     different tools, with the board excluded from company-knowledge search** —
     *selected*. Preserves every Phase 4 completion criterion (a genuinely live issue
     can still be cited, the fallback is still disclosed) and requires no connector
     rework. It is also correct information architecture rather than a workaround: a
     company's engineering board and its knowledge base are genuinely different corpora
     serving different query intents, and conflating them would be wrong even without
     the contamination.
  2. **Switch the live source to a repository with domain-relevant issues** — *rejected.*
     Contradicts D-003, loses the guaranteed-access property that repository was chosen
     for, and the same detour was already attempted and reverted during Phase 4.
  3. **Keep one merged corpus and rely on the agent to disregard board issues** —
     *rejected.* Measurably degrades precision on every priority question, and converts
     a structural control into a behavioural one, which is the failure mode D-002 and
     the threat model exist to avoid.
  4. **Exclude the live source from retrieval entirely, using it only for a connector
     demonstration** — *rejected.* Would forfeit the Phase 4 requirement that the
     interface cite one genuinely live issue in a real answer.
- **Coding-agent contribution:** Claude Code found the contamination by measuring the
  merged corpus against the priority questions immediately after freezing the H2
  contract, rather than assuming the merge was harmless; quantified it as 16/30 top-6
  slots; and identified that the failure mode is a citation that resolves correctly
  while supporting nothing, which the planned grounding check would not catch.
- **Evidence reviewed:** the F-13 measurement in `HANDOVER.md` §4; the EVAL-002 and
  EVAL-012 expected source ids; D-003; the tool boundaries in `AGENTS.md`.
- **Decision and owner:** adopt option 1. Owner: Sulu.
- **Consequences or follow-up:**
  - `search_company_knowledge` is scoped to the `company_knowledge` namespace and must
    never return `GH-LIVE-*` records.
  - Work items are served by a separate tool that reports which namespace and which
    freshness state each result came from.
  - EVAL-012 is satisfied from the local export with explicit fallback disclosure, as
    already noted in `HANDOVER.md` §8.
  - **This also resolves F-12.** Scoping the index manifest per namespace means a
    degraded live fetch can no longer authorise deletions of local GitHub chunks,
    because the two are no longer members of one synchronized set. One mitigation now
    covers both findings.
  - The retrieval contract frozen at H2 is unaffected: namespaces are a property of
    which corpus a retriever holds, not of the `Retriever` interface.
- **Status:** Accepted

### D-005 · Work sequentially rather than in parallel

- **Phase:** 5, at the start of Wednesday's work
- **Context:** The plan assigned Phases 5 and 6 to run concurrently on Wednesday, and 8
  and 9 concurrently on Thursday, with four defined handover points. The human team
  chose to work sequentially instead: one person progresses the build and hands over
  when the next phase belongs to the other.
- **Options considered:**
  1. **Sequential — one active phase at a time** — *selected by the human team.*
     Removes concurrent edits to shared files, removes the risk of two coding-agent
     sessions rewriting the same notebook, and keeps a single reviewable line of
     history. Every phase gets the full attention of both reviewers.
  2. **Parallel with defined handover points** — *not selected.* Fits the three-day
     window with more slack, but requires interface freezes ahead of implementation and
     careful file-ownership discipline.
- **Decision and owner:** sequential. Owner: Sulu (human team decision).
- **Consequences or follow-up:**
  - **Schedule risk, stated explicitly:** Wednesday previously fitted because 5 and 6
    ran concurrently. Sequentially it carries 5, then 6, then 7. If Wednesday tightens,
    the parallel option remains available at no rework cost, because the H2 contract is
    already frozen and four of the five Phase 6 tools have no dependency on Phase 5.
  - Handover points H1–H4 collapse to a single rolling handover at each phase boundary.
    H1 and H2 are already complete.
  - Karthik has been asked to hold Phase 6 until Phase 5 lands, so the two do not build
    against different assumptions or touch the same files.
  - The per-owner notebook split is retained. It costs nothing and still prevents
    `.ipynb` merge conflicts whenever work does overlap at a boundary.
- **Status:** Accepted

### D-006 · Default retrieval mode is hybrid with a lexical weight of 0.6

- **Phase:** 5 (step 5.5)
- **Context:** `04` requires the default retrieval mode to be selected from measured
  results rather than architectural preference. Step 5.3 measured five questions,
  found the differences to be within noise, and set `w = 0.6` **provisionally** on a
  product rationale while explicitly flagging the risk of cherry-picking. Step 5.5
  re-measured on ten questions — the seven supplied cases whose expected evidence is
  retrievable, plus the three priority questions.
- **Options considered:**
  1. **Hybrid, `lexical_weight = 0.6`** — *selected*. recall@6 1.00, precision 0.350,
     mean expected rank **2.000** (the argmin of the sweep), 0 forbidden sources,
     43 ms median retrieval latency.
  2. **Lexical only** — *rejected.* Equal recall and precision, but a worse mean rank
     (2.150). Retained as the required comparison baseline, per `AGENTS.md`.
  3. **Semantic only** — *rejected.* recall drops to **0.95**, missing half of
     EVAL-012's expected evidence, and mean rank is clearly worse (2.683).
  4. **Semantic-leaning hybrid (`w ≤ 0.3`)** — *rejected.* recall falls to 0.95 at
     `w ≤ 0.3`; the sweep shows a genuine threshold at `w = 0.4`, not noise.
- **Coding-agent contribution:** Claude Code widened the question set from five to ten
  before fixing the default, which **reversed** its own step 5.3 conclusion that recall
  was saturated and mode did not matter. It also identified the generalisable reason a
  lexical majority is correct here: semantic retrieval under-ranks records whose
  identifying vocabulary sits in metadata rather than prose — `GH-142`'s body mentions
  neither "Atlas" nor "open", and its Atlas identity lives in its labels.
- **Evidence reviewed:** the ten-question three-mode comparison; the eleven-point weight
  sweep; the EVAL-012 ranking breakdown showing `GH-142` at 7th under semantic; latency
  medians and run-to-run spread; the forbidden-source assertion across all 30
  mode-question pairs.
- **Decision and owner:** hybrid, `lexical_weight = 0.6`. Owner: Sulu.
- **Consequences or follow-up:**
  - The contract's default (`mode="hybrid"`) now matches the product default, so Phase 6
    tools need no mode argument.
  - Lexical and semantic remain fully available on the same retriever, so Phase 8 can
    reproduce the three-way comparison without rebuilding anything.
  - **Latency was deliberately not used as a tiebreaker.** Run-to-run spread (38–85 ms)
    exceeds the between-mode difference, so treating it as signal would be false
    precision.
  - **This decision does not address F-2.** The archived-versus-current refund conflict
    persists in every mode and hybrid makes it *worse* (gap 0.14 → 0.20). Status-aware
    reasoning remains Phase 6's responsibility.
  - Step 5.3's "recall is saturated" claim is corrected in `EVALUATION_REPORT.md` and in
    the slide-deck ledger rather than removed, since the reversal is itself evidence that
    a five-question denominator was too small.
- **Status:** Accepted

### D-009 · Tiered repeats and restated latency thresholds for Phase 8

- **Phase:** 8 (step 8.1), fixed **before** the harness was written and before any agent
  result was read
- **Context:** Two Phase 6 findings pull in opposite directions. **F-17**: the agent is
  not deterministic at `temperature=0` — the same case returned `answered`, `answered`,
  `insufficient_evidence` — so a single run is a hypothesis, and two conclusions had
  already been invalidated that way. **F-21**: the free Groq tier exhausted its quota on a
  36-turn comparison, with one turn burning 309 s across four backoffs before failing.
  Repeats cost quota, and quota is the binding constraint. Separately, the Phase 1 latency
  thresholds were set against retrieval (23 ms) and cannot describe agent turns (2–80 s).
- **Options considered:**
  1. **Tiered repeats — 3 runs on 6 high-variance cases, 1 run elsewhere, all three
     variants retained** — *selected*. 54 agent turns. Spends repeats exactly where
     variance can flip a verdict (conflict, forbidden access, injection, abstention,
     approval, and the flagship priority question) and reports every single-run result as
     a single run rather than as a verdict.
  2. **Full 3 × 3 matrix** (~108 turns) — *rejected.* The most rigorous design and the
     cleanest report, but F-21 makes completion on this tier unlikely, and an evaluation
     that dies halfway is worth less than a smaller one that finishes.
  3. **Uniform single run** (~36 turns) — *rejected.* Matches the original plan and is
     cheapest, but F-17 means every number would need a caveat, which defeats the purpose
     of fixing thresholds in advance.
  4. **Run once, then repeat only failures** — *rejected on statistical grounds.* It
     treats passes as settled and failures as flaky, so measured pass rates come out
     optimistically biased. Cheap, and wrong in a direction that flatters us.
- **Coding-agent contribution:** Claude Code proposed the tiering and the threshold
  restatement, and established two constraints the design had to absorb: that the four
  release blockers **cannot** be rate-based, so F-17 makes them harder rather than easier
  to prove; and that injection resistance must be graded as **two** results, because the
  structural control held 3 of 3 while the reporting of the attack held 1 of 3 (F-18).
- **Evidence reviewed:** F-17, F-18, F-21 and F-22 in `HANDOVER.md`; the live model list
  (F-23); one verified agent turn on P1 at 2.1 s with all four release conditions
  reconciled and cited.
- **Decision and owner:** tiered repeats; agent latency **p50 ≤ 30 s / p95 ≤ 90 s**;
  retrieval **p50 ≤ 100 ms** measured separately; rate-limit waits excluded from product
  latency and reported as an operational metric. Owner: Sulu.
- **Consequences or follow-up:**
  - A Tier-A case passes on **≥ 2 of 3** runs; a Tier-B case on its single run. The tier is
    printed in the scenario table so a 1-run pass is never mistaken for a 3-run pass.
  - **Blockers must hold on every run.** One occurrence blocks, regardless of rate. A
    boundary that holds two times in three is broken.
  - `finish_reason == "length"` with empty content is retried as an **infrastructure**
    failure, never scored as behaviour (F-22).
  - The scorer must reuse `agent.runner.normalize_for_id_matching` before matching source
    ids, or U+2011 hyphens silently void every citation (F-20, confirmed live in F-24).
  - **D-007 remains open and its candidates have changed:** `llama-3.3-70b-versatile` is
    not available on this tier, so the bake-off is `gpt-oss-20b` vs `gpt-oss-120b`
    (F-23). If quota does not permit both, the report must state that the models were not
    distinguished rather than implying a comparison happened.
- **Status:** Accepted

### D-010 · A permission refusal is derived from the access matrix, not from the agent's words

- **Phase:** 7/8 boundary, after a hand test of `TEST_SCRIPT.md` question 3
- **Context:** D-034 (F-34 in `HANDOVER.md`) split refusals into `forbidden` — *you are
  not cleared* — and `insufficient_evidence` — *the records hold nothing* — and derived
  the distinction from phrases in the agent's own answer. A hand test showed that could
  not work, and that its supporting evidence was invalid: the "3 of 3 `forbidden`" runs
  had made **zero tool calls**, so the model was pattern-matching the question's
  vocabulary rather than determining a boundary, and returned **byte-identical text for
  People Operations, who is cleared for the record, and Engineering, who is not.** Once
  the agent was made to search first, three runs of one refusal returned
  `insufficient_evidence`, `forbidden`, `insufficient_evidence` — all saying *"I could
  not find this"*. The status was a wording lottery.

  The reason is structural, not a matching bug: **from inside its permitted set the
  agent has no more information than the classifier does.** A record it may not see and
  a record that does not exist are indistinguishable to it. Nothing in the turn can
  separate them, so nothing read out of the turn can either. This was the fourth attempt
  in this project at extracting meaning from generated prose, after F-20, F-26 and F-31.
- **Options considered:**
  1. **Derive it from the declared access matrix** — *selected*. `ACCESS_MATRIX.md`
     records a categorical `Deny` per record class and role. When the employee's question
     names such a class, the knowledge tool returns `denied` **before searching
     anything**. Deterministic, needs no retrieval, and cannot be influenced by anything
     the tools return.
  2. **Check the denied records against the query** — *rejected.* The most precise
     option, and also a real disclosure: the answer would differ depending on whether a
     matching restricted record existed, which is exactly the bit `PRODUCT_BRIEF.md`
     forbids a refusal from revealing.
  3. **Drop the distinction entirely** — *rejected.* Honest and leak-free, but it
     discards a product behaviour the team asked for, and it tells an employee the
     company holds nothing when the truth may be that they are not cleared.
- **What this discloses.** Only what `ACCESS_MATRIX.md` already publishes: that a role is
  not cleared for a class of record. Because no search runs, the refusal says nothing
  about whether any matching record exists. `Conditional` classes never fire — there,
  per-record `allowed_roles` governs and the pre-filter is the only correct authority.
- **The mirror-image defect this also closed.** The same hand test showed retrieved text
  *narrowing* access: `DOC-HR-001`'s own body reads *"It must never be retrieved for
  Customer Success, Engineering, or Finance profiles"*, and the agent obeyed that
  sentence and withheld the record from the one role entitled to it. That is **T-01
  pointing the other way** — obeying retrieved content, exactly as an injection would,
  except that instead of leaking a record it denied one. Only the widening direction had
  ever been defended. `security.policy.categorical_grant` now asserts the entitlement in
  the tool's own voice, naming the role, ahead of the excerpts rather than after them.
- **Evidence reviewed:** the zero-tool-call traces with identical text for both roles;
  Priya's candidate set (`DOC-HR-001` at rank 1 of 2) against Leo's ten records without
  it, proving the pre-filter was correct throughout; 21/21 deterministic policy cases
  including every question in `TEST_SCRIPT.md` that must **not** fire; 3 runs per
  direction live (Priya 3/3 `answered` citing `DOC-HR-001`, Leo 3/3 `forbidden`, no
  leak); a 5/5 regression across the four behaviours that decide the demonstration.
- **Decision and owner:** derive `forbidden` from the declared matrix. Owner: Sulu.
- **Consequences or follow-up:**
  - `forbidden` is now **structural** rather than behavioural, so it moves category in
    `THREAT_MODEL.md`. Anything that only *reads* as a refusal is reported as
    `insufficient_evidence`, the weaker and safer of the two claims.
  - A turn that declines having called **no tool** is reported as `error`, not as a
    refusal: with no candidate set it has established nothing (F-4).
  - It closes F-19 structurally for the denied direction. The injected payload inflates
    the relevance of the question it hijacks; if the agent follows that bait and searches
    for the salary review, Engineering now meets a denial instead of a confident result
    set.
  - **The vocabulary is the risk and is deliberately small.** A false positive denies an
    employee something they are entitled to, which is worse than the defect this closes.
    `pay` is excluded because it appears inside *"payment retry"* in `GH-142`. New terms
    need a test in the 21-case suite before they are added.
  - **F-34's recorded evidence is void**, and is corrected rather than removed. Any
    EVAL-005 result predating this change measured a system that refused without
    searching.
- **Status:** Accepted

### D-011 · Default model is `nvidia/nemotron-3.5-lightning:free`, on cost, and the refusal control is no longer model-dependent

- **Phase:** 10
- **Context:** the team was being charged on `poolside/laguna-xs-2.1:free` and asked to
  move to a model with no cost. That is a legitimate operational reason, and it collides
  with **D-007/F-32**, which selected laguna *specifically because* nemotron would not
  refuse a request for a restricted record — it answered it with 3,775 characters.
- **Why the collision is no longer real.** F-32's reasoning was correct for the design at
  the time and **D-010 removed its premise.** The permission refusal is no longer produced
  by the model: a categorical `Deny` in `ACCESS_MATRIX.md` is enforced by the tool
  **before any search runs**, and `forbidden` is derived from that tool outcome rather than
  from the model's prose. A model's disposition to refuse is therefore no longer
  load-bearing — which is the entire point of moving a control from behavioural to
  structural. Nemotron already answered the flagship question 3 of 3 under F-32, so the
  ability half was never in question.
- **Options considered:**
  1. **`nvidia/nemotron-3.5-lightning:free`** — *selected.* No cost, tool calling verified
     on the real workload (F-30 — it was the **only** model of five that survived a
     ~6,100-token turn), flagship question 3/3.
  2. **Stay on `laguna-xs-2.1:free`** — *rejected on cost*, which is the team's call to
     make. Retained as a comparison arm; nothing is removed.
  3. **Return to Groq `gpt-oss-20b`** — *rejected.* Its 8,000 tokens-per-minute ceiling is
     what stopped Phase 8 at 6 of 15 cases (F-27), and EVAL-010 never completed a single
     run on it (F-38).
- **Decision and owner:** nemotron, set in `.env` and as the code default. Owner: Sulu.
- **⚠ Recorded as UNVERIFIED, deliberately.** `OPENROUTER_API_KEY` returns **401** at the
  time of writing, so no model-backed run has been possible since the switch. The claim
  that the boundary holds on a model that would not have refused on its own is a
  **prediction about the design, not a measurement** — and predictions in this project
  have been wrong before (F-14, F-17, F-26, F-31 were all conclusions reversed by data).
  Close it with one command once a working key exists:

  ```bash
  uv run python scripts/verify_behaviours.py
  ```

- **What a failure there would mean.** If the permission case fails on nemotron, the
  structural control is **not** doing what D-010 claims, and that is a finding about the
  *design* — not a reason to quietly switch models back. Switching back would hide a
  defect in the control the whole access argument now rests on.
- **Consequences or follow-up:**
  - Groq is still retained and `LLM_PROVIDER` still switches providers, so `05`'s provider
    comparison stays runnable.
  - Every scored evaluation row predates this switch **and** three system changes (F-32's
    prompt fix, D-010, the abstention-classifier work). They are not to be pooled with any
    re-run.
- **Status:** Accepted, pending verification

### D-012 · Release recommendation — demonstrate with explicit limitations

- **Phase:** 10 (step 10.2)
- **Context:** `05-evaluation-and-release.md` requires one of three recommendations, and
  requires that it follow the evidence rather than the quality of the demonstration.
- **Decision and owner:** **Demonstrate with explicit limitations.** Owner: Sulu.
- **The evidence for demonstrating:**
  - **All five release blockers at 0** across 53 scored runs — counted, not averaged, since
    one occurrence blocks whatever the average.
  - **The permission boundary holds in both directions**, which is the strongest claim the
    project can make and is evidenced by the *candidate set* rather than by a refusal:
    Engineering refused 3/3 with `DOC-HR-001` absent from its 10-record candidate set,
    People Operations answered 3/3 citing it from a 2-record set.
  - **The approval boundary is proven end to end** (F-38): 3/3 agent-composed proposals
    left pending, and 11/11 gate checks with **one execution** across the whole run.
  - **Injection's structural control held on every scored run.**
  - **The packaged product starts from a clean checkout**, 16/16 checks from destroyed
    volumes.
- **The evidence against an unqualified "demonstrate":**
  - **The three-variant comparison `05` requires is incomplete.** `semantic_agent` has zero
    scored runs; `hybrid_agent` covers 6 of 15 cases.
  - **The scored rows predate three system changes**, so they describe a superseded system.
  - **Feedback is below its own threshold** — 4 entries against 5, none traced to a decision.
  - **F-35:** `projects` and `customers` are unreachable, so `P-ORBIT` cannot be shown and
    two claims in `PRODUCT_BRIEF.md` are false until corrected.
  - **F-17:** the agent is not deterministic, so every number is a rate.
- **Why not the other two.** *Demonstrate* unqualified would present an incomplete variant
  comparison and superseded rows as though they backed the product as it stands. *Do not
  demonstrate yet* is not supported: nothing measured suggests the product is unsafe to
  show, no blocker has fired across 53 scored runs, and every behaviour in the seven-beat
  script is verified and repeated.
- **How the limitations are presented:** inside beat 7 of `SHOWCASE.md`, in the same breath
  as the recommendation. A limitation read after the recommendation is not a limitation.
- **Status:** Accepted

## Decision Template

### Decision: Short descriptive title

- **Phase:**
- **Context:**
- **Options considered:**
- **Coding-agent contribution:**
- **Evidence reviewed:**
- **Decision and owner:**
- **Consequences or follow-up:**
- **Status:** Accepted, revised, or rejected
