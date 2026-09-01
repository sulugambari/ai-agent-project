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
