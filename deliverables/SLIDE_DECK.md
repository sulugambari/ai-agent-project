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
| 5 | The information boundary | `ACCESS_MATRIX.md`, Step 2.1-2.2 | Pending |
| 6 | Architecture, and the alternative we rejected | Step 2.3, `D-001` | Pending |
| 7 | Baseline: what transparent lexical search cannot do | Step 3.3 figures | Pending |
| 8 | Connecting a live source safely | Step 4.3 figures | Pending |
| 9 | Retrieval: lexical vs semantic vs hybrid | Step 5.5 figures | Pending |
| 10 | Index lifecycle: change and deletion | Step 5.4, EVAL-011 | Pending |
| 11 | Five narrow tools, one bounded agent | Step 6.1-6.2 figures | Pending |
| 12 | Trust boundary: refusal, conflict, injection | Step 6.5, EVAL-005/006 | Pending |
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

## Presentation Notes

- Lead with the **problem**, not the architecture. The Acme Freight scenario lands
  in fifteen seconds and makes every later slide legible.
- Every claim on a slide must trace to a figure, a deliverable, or a live demo
  step. No unsupported assertions.
- The refusal, conflict, and injection slides matter more than the answer-quality
  slides. Those are the differentiators of a *trustworthy* internal assistant.
- Do not present the container as production readiness.
