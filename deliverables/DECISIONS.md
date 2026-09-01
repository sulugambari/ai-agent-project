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
