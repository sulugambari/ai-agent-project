# Final Presentation — Slide Deck Ledger

Running capture of everything that must appear in the final deck. **Appended to as
each step completes**, so the deck is assembled from evidence rather than
reconstructed from memory on the last day.

- **Figures:** `deliverables/figures/*.png` (2x PNG, tracked in git). Each figure
  has a sibling `.txt` holding the one-line message it proves.
- **Chart specs:** `data/generated/charts/*.json` (git-ignored, regenerable) —
  used by the Phase 8 Streamlit dashboard.
- **Companion:** `SHOWCASE.md` holds the *live demonstration* script; this file
  holds the *slides*. They overlap deliberately at the demo section.

## Deck Structure

| # | Slide | Content source | Status |
| --- | --- | --- | --- |
| 1 | Title — product name, team, date | — | Pending |
| 2 | The problem: one question, four sources | Acme Freight scenario, `PROJECT_PLAN.md` | Pending |
| 3 | Northstar Labs and its data landscape | Step 1.1 corpus + access figures | Figures ready |
| 4 | Who we built for, and what we refuse | `PRODUCT_BRIEF.md`, Step 1.2-1.3 | Figure ready |
| 5 | The information boundary | `ACCESS_MATRIX.md`, Steps 2.1-2.2, **3.2 counterfactual** | **Ready** |
| 6 | Architecture, and the alternatives we rejected | Step 2.3, `D-001`, **`D-002` + threat-model figure** | Figure ready |
| 7 | Baseline: what transparent lexical search cannot do | Step 3.3 figures | **Ready** |
| 8 | Connecting a live source safely | Step 4.3 figures | Pending |
| 9 | Retrieval: lexical vs semantic vs hybrid | Step 5.5 figures | Pending |
| 10 | Index lifecycle: change and deletion | Step 5.4, EVAL-011 · **design + figure ready from 2.2** | Figure ready |
| 11 | Five narrow tools, one bounded agent | Step 6.1-6.2 figures | Pending |
| 12 | Trust boundary: refusal, conflict, injection | Step 6.5, EVAL-005/006 · **threat model 2.3** | Partly sourced |
| 13 | Human approval before any action | Step 6.4 state diagram | Pending |
| 14 | Evaluation results by layer | Step 8.4 figures | Pending |
| 15 | What failed, and what we learned | Step 8.5 failure analysis | Pending |
| 16 | Release recommendation | Step 10.2, `DECISIONS.md` | Pending |
| 17 | What real deployment would still require | `SHOWCASE.md` launch boundary | Pending |

## Step Ledger

Appended as each step completes. `Figure` names map to
`deliverables/figures/<name>.png`.

| Step | Key finding worth presenting | Figure(s) | Slide |
| --- | --- | --- | --- |
| 0.3 | The lexical baseline is not a strawman — it already retrieves all three EVAL-002 expected sources. Phase 5 must beat something real. | *(none — table evidence)* | 7 |
| 0.3 | The teaching database is reproducible at row level but not byte level; SQLite page layout varies per run. | *(none)* | — *(technical note only)* |
| 0.3 | Streamlit binds all network interfaces by default and advertised a LAN URL — an unauthenticated assistant should not be LAN-reachable. | *(none)* | 17 |
| 1.1 | Permissions are **per-record metadata, not a role hierarchy**. Engineering sees the most records yet cannot see the refund policies or the customer-operations thread; Customer Success sees the policies but not the engineering blockers. No single role can answer a cross-domain question alone. | `1_1_access_heatmap` | 3, 5 |
| 1.1 | **People Operations sees only 3 of 15 records** — the role holding the restricted HR document has the *narrowest* reach. Access breadth and seniority are unrelated. | `1_1_access_heatmap`, `1_1_profile_choice` | 5 |
| 1.1 | The corpus is **15 records across 4 families** — small enough that retrieval *recall* is easy. Phase 5's honest win is **precision and paraphrase handling**, not recall. A large claimed recall win would be suspect. | `1_1_corpus_composition` | 3, 9 |
| 1.1 | **Primary-profile choice is evidence-backed:** Engineering has the widest reach (11 records) and Leo owns **7 of 12** supplied cases, including the injection fixture no other role can retrieve. Priya owns **0** cases despite holding the restricted document. | `1_1_profile_choice` | 4 |
| 1.1 | **All five embedded traps verified programmatically**, not taken on trust: 1 restricted record, 1 archived policy, 1 injection payload authored by an "External integration bot", and the 5 vs 18 September conflict spanning email, Slack, and the release brief. | *(audit output)* | 3, 12 |
| 1.1 | The injection **is** regex-detectable — which is a trap. Pattern matching invites a shortcut we must refuse: the defence that generalises is treating retrieved content as data, never instructions. Regex is defence-in-depth at best. | *(audit output)* | 12 |
| 1.2 | **Priority questions are workflow decisions, not test cases.** P1 reconciles the release brief's four named conditions against GitHub, Slack and the database — four source families in one question. | *(transcript)* | 4, 11 |
| 1.2 | **A Leo-only product cannot demonstrate the refund-policy conflict** — both policies are scoped to `customer_success, finance`. Maya is therefore a required secondary profile, which also gives the strongest permission demo: same question, two profiles, different permitted evidence. | `1_1_access_heatmap` | 4, 5, 12 |
| 1.2 | **Injection resistance belongs in the priority set, not the test set.** Indirect injection is triggered by innocent work — P3 is a mundane "summarize the deployment notes" request that happens to retrieve the poisoned message. | *(transcript)* | 12 |
| 1.3 | **A refusal does not prove pre-retrieval filtering.** It is equally consistent with a politely-instructed model. The claim is only provable by exposing the candidate set — so the trace panel is the evidence for our most important access guarantee, not a convenience. | *(trace panel)* | 5, 12 |
| 1.3 | **"80% of 3 questions" is arithmetically misleading** — 2 of 3 is 67%. Priority-question target stated as **3 of 3**; the 80% moved to the 12-case scenario set where the denominator is real. | *(thresholds table)* | 14 |
| 1.3 | **Fabricated citations added as a third release blocker**, alongside permission leaks and unapproved actions. A citation that does not resolve destroys the product's premise as completely as a leak. | *(thresholds table)* | 14, 16 |
| 2.1 | **The access matrix needed 11 record classes, not 6.** The template's six could not express the boundary — refund policies are neither handbook nor financial record. Each of the 15 fixtures maps to exactly one class, asserted in code so a new source cannot be silently unclassified. | `2_1_access_matrix` | 5 |
| 2.1 | **Two states were not enough: `Conditional` was required.** `GH-142` is visible to Finance, `GH-149` is not; the Acme emails are visible to Engineering, the customer-operations thread is not. Calling those `Allow` overstates access and `Deny` understates it — both are wrong. | `2_1_access_matrix` | 5 |
| 2.1 | **The policy was audited against enforced metadata, not just written down: 32 of 32 auditable cells match, 0 mismatches.** A policy document that disagrees with the metadata actually enforced is worse than none, because it manufactures false confidence. Re-runnable after Phase 5. | `2_1_policy_vs_fixture` | 5, 14 |
| 2.1 | **API reachability is not authorization.** The live repo is public, so anyone can read its issues — yet live work items are scoped to engineering, matching the local class. Not to protect public data, but for policy stability if the repo goes private, and coherence across ingestion paths. | `2_1_access_matrix` | 5, 8 |
| 2.1 | **Default-deny is enforced at three layers**, not one: `parse_roles()` raises at ingestion, `CompanyDocument` requires the field, and the membership test excludes anything not explicitly listed. A malformed record fails loudly instead of becoming world-readable. | *(enforcement notes)* | 5 |
| 2.2 | **HIGHLIGHT — a content-only hash creates a security hole, not just a stale answer.** `python-frontmatter` puts YAML in `.metadata` and body text in `.content`, so tightening `allowed_roles` leaves content byte-identical. A content-only hash fires no upsert, and the indexed chunk keeps its **old permission metadata — still retrievable under the old policy**. An indexing shortcut would reintroduce the exact leak the access matrix exists to prevent. Chunk IDs therefore hash content **plus** every field governing retrieval or access. Tested against five change types: timestamp IDs miss three, content-only misses two, governance hash catches all five. | `2_2_change_detection` | **10**, 5, 6 |
| 2.2 | **Two identifiers, two jobs.** `source_id` never changes so citations keep resolving; `chunk_id` changes every revision so upserts replace rather than append. Conflating them *is* the EVAL-011 failure — one ID cannot be both constant and varying. | *(governance table)* | 10 |
| 2.2 | **Deletion is invisible to every ID scheme** — fingerprints detect revision, only a manifest diff detects removal. Phase 5.4 needs both mechanisms, not either. | `2_2_change_detection` | 10 |
| 2.2 | **The database is queried, never embedded.** Structured facts stay current by construction, with no staleness window — and `annual_value_eur` never enters the vector store, shrinking the permission surface. | *(governance table)* | 6, 10 |
| 2.2 | **Only one source has a real clickable citation:** the live GitHub `html_url`. Slack, email, and document fixtures carry no URL, so their citations resolve to the record, not to the origin system. Worth stating plainly rather than implying every citation deep-links. | *(governance table)* | 8 |
| 2.3 | **Every control is classified by what it depends on: structural (impossible by construction), behavioural (needs model compliance), detective (visible afterwards).** Tally: **14 structural, 4 behavioural, 8 detective**. Every one of 8 threats carries at least one structural control — asserted in executable code, so a later phase that weakens one fails loudly. | `2_3_threat_model` | 6, 12 |
| 2.3 | **Direct answer to "the system prompt will prevent leaks":** in this design the prompt is never the primary control for anything. It is defence in depth on 4 of 26 controls, and every threat it touches also has a structural control behind it. | `2_3_threat_model` | 6, 12 |
| 2.3 | **"The latest document is always correct" is empirically false in our own data** — `DOC-POLICY-OLD-402` is archived and `EMAIL-ACME-301` is a genuine but superseded commitment. Recency is a signal, never authority. | *(threat model T-03)* | 12 |
| 2.3 | **Post-retrieval filtering was rejected as an architecture.** Retrieve-then-redact still puts restricted content in the model, the trace and the logs — the disclosure happens and is merely hidden from the answer. It converts a structural control into a behavioural one. | *(D-002)* | 6 |
| 2.3 | **Injection pattern-matching explicitly rejected as a primary control.** It is trivially regex-detectable *in this fixture* and does not generalise to rephrasing. Data-not-instructions is the control that does. | *(threat model T-01)* | 12 |
| 3.1 | **Every malformed record fails loudly — 10 of 10 deliberate corruptions raise at parse time, 0 silent.** Missing / empty / unknown `allowed_roles`, missing `source_id`, invalid `confidentiality`, absent email governance headers. The default-deny claim is now tested, not asserted. | *(probe table)* | 7, 5 |
| 3.1 | **Why a silent drop would be undetectable.** Retrieval recall, grounding and citation checks all operate on what the connector emitted — so a swallowed record is indistinguishable from a record that never existed. No amount of Phase 8 evaluation would catch it. | *(probe table)* | 7 |
| 3.1 | **All 15 records populate every permission- and citation-critical field.** What varies by family is what a citation can *promise*: only email carries a globally unique locator, and **no local source offers a deep link** — the live GitHub connector will be the only one that can. | `3_1_citation_affordances` | 7, 8 |
| 3.1 | This probe suite is the **regression harness for Phase 4** — a malformed API response must raise, not degrade quietly into a document with no `allowed_roles`. | *(probe table)* | 8 |
| 3.2 | **HIGHLIGHT — the permission filter is proven load-bearing by counterfactual.** Given a query engineered to attract it, `DOC-HR-001` ranks **#1 at score 0.86** in the unfiltered corpus and is **absent** from Leo's filtered set, while Priya correctly retrieves it. A refusal could not prove this; only the candidate set can. | `3_2_filter_is_loadbearing` | **5**, 12 |
| 3.2 | **Asserted, not observed:** 4 roles × 9 adversarial queries — including the injection payload used *as* the query — gave **0 violations**. Executable, so it is the regression guard when Phase 5 swaps the retriever. | *(assertion)* | 5, 14 |
| 3.3 | **HIGHLIGHT — the archived refund policy OUTRANKS the current one, 0.571 vs 0.429.** Its own warning, *"Do not use this archived **threshold** for **current** decisions"*, supplies the two query terms the current policy never uses. **The disclaimer written to prevent misuse is what makes the stale document win.** Shipped as-is the baseline answers EUR 2,500 — an approval beyond Maya's authority. | `3_3_conflict_baseline` | **7**, 12 |
| 3.3 | **Semantic retrieval will not fix that.** The two policies are semantically near-identical and the archived one is *more* on-topic for "current". The fix must be status-aware reasoning over metadata — which is why step 2.2 carries governance fields on every chunk. | `3_3_conflict_baseline` | 7, 9 |
| 3.3 | **Baseline scorecard: 0 release blockers, 5 product failures.** The deterministic permission filter is already correct; what is missing is abstention and authority. Phase 5–6 must fix the second class without regressing the first. | *(probe table)* | 7, 14 |

## Presentation Notes

- Lead with the **problem**, not the architecture. The Acme Freight scenario lands
  in fifteen seconds and makes every later slide legible.
- Every claim on a slide must trace to a figure, a deliverable, or a live demo
  step. No unsupported assertions.
- The refusal, conflict, and injection slides matter more than the answer-quality
  slides. Those are the differentiators of a *trustworthy* internal assistant.
- Do not present the container as production readiness.
