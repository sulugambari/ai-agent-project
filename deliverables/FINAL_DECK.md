# Northstar Release Coordinator — Final Deck

Step 10.4. Assembled from the `SLIDE_DECK.md` step ledger and the 24 tracked figures
in `deliverables/figures/`, each of which carries a `.txt` sibling stating the one
thing it proves.

- **Team:** Sulu (AI PM, release owner) · Karthik — 1–3 September 2026
- **Speaker notes are the indented lines.** Say them; do not read the slide.
- **One rule for the whole deck:** every claim traces to a figure, a deliverable or a
  live demonstration step. If a slide cannot cite one, it comes out.
- **Live demonstration script:** `SHOWCASE.md`. Slides 5, 12 and 13 are the ones the
  demonstration replaces if time is short — show them running rather than described.

---

## 1 · Northstar Release Coordinator

**An internal assistant that answers from private company knowledge — showing its
sources, refusing what you may not see, and never acting without approval.**

Sulu · Karthik — 3 September 2026

> Three hard things, and none of them is the chat interface: enforcing who-can-see-what,
> not lying when sources conflict or are missing, and *proving with evidence* that it does
> both.

---

## 2 · The problem: one question, four places

Acme Freight emails Maya: *"You promised the Atlas billing migration by 5 September. It is
September. Where is it?"*

To answer honestly she must check her own email (5 Sep), Nora's correction (18 Sep), the
release brief, and GitHub issue 142 — which shows the blocker is not fixed.

**Twenty minutes. Skip it, and she tells the customer 5 September and is confidently wrong.**

> That is not a hypothetical: the mistake is already in the fixtures. `EMAIL-ACME-301`
> committed 5 September and `EMAIL-ACME-302` corrected it two days later. The product
> exists to stop the fast, confident version of that error.

---

## 3 · Northstar Labs and its data landscape

**Figures:** `1_1_corpus_composition.png` · `1_1_access_heatmap.png`

15 records across 4 source families, plus a live GitHub repository and SQLite business
records.

> Two things from the inventory shaped everything after it. **The corpus is small**, so
> retrieval *recall* is easy and any large claimed recall win should be treated as
> suspect — the honest win is precision. And **permissions are per-record, not a
> hierarchy**: Engineering sees the most records yet cannot see the refund policies;
> People Operations, which holds the most sensitive document, has the *narrowest* reach at
> 3 of 15. Access breadth and seniority are unrelated.

---

## 4 · Who we built for, and what we refuse

**Figure:** `1_1_profile_choice.png`

**Leo Martins** (engineering), release-readiness coordination. **Maya Chen** (customer
success) as a required secondary.

> Leo owns 7 of 12 supplied cases including the injection fixture, which is scoped to
> engineering and is therefore *unreachable* by any other profile. Maya is required rather
> than decorative: both refund policies are scoped to customer success and finance, so a
> Leo-only product could not demonstrate the conflicting-policy behaviour at all.
>
> Out of scope, stated up front: compensation and HR, revenue and forecasting, approving a
> refund, legal interpretation, code changes, and anything not grounded in company evidence.

---

## 5 · The information boundary — and the proof it is load-bearing

**Figures:** `2_1_access_matrix.png` · `2_1_policy_vs_fixture.png` ·
**`3_2_filter_is_loadbearing.png`**

11 record classes × 4 roles. **32 of 32 auditable cells match the enforced metadata.**

**The counterfactual:** `DOC-HR-001` ranks **#1 at score 0.86** in an unfiltered copy of
the same scoring function — and is **absent** from Leo's filtered candidate set.

> The obvious test proves nothing: a query that simply fails to retrieve a restricted
> record would also "pass" with the filter deleted. So we ranked it first *without* the
> filter, then showed it never becomes a candidate *with* it.
>
> The matrix needed **11** classes, not the template's six, and three states rather than
> two — `Conditional` exists because `GH-142` is visible to Finance while `GH-149` is not.
> Calling that `Allow` overstates access and `Deny` understates it.

---

## 6 · Architecture, and the alternative we rejected

**Figure:** `2_3_threat_model.png`

Connectors → permission-aware index (two namespaces) → 5 narrow typed tools → one bounded
agent (max 6 tool calls) → one application layer → two interfaces.

**Rejected: post-retrieval filtering.** Retrieve-then-redact still puts restricted content
into the model, the trace and the logs.

> **9 threats, 16 structural controls, 5 behavioural, 9 detective — and every threat has at
> least one structural control.** A threat defended only behaviourally is defended by hope.
> That assertion is executed in code, so it fails loudly if a later phase weakens a control.
>
> The assumption the course told us to challenge — *"the system prompt will prevent
> leaks"* — is rejected here by construction. The prompt is never the primary control for
> anything.

---

## 7 · The baseline is not a strawman — and it fails in an instructive way

**Figures:** `3_3_conflict_baseline.png` · `3_1_citation_affordances.png`

The lexical baseline retrieves **all three** expected sources for the Atlas blocker
question. But asked for the current refund threshold, the **archived** EUR 2,500 policy
**outranks** the current EUR 1,000 one — **0.571 to 0.429**.

> **The archived document's own warning is what makes it win.** *"Do not use this archived
> **threshold** for **current** decisions"* supplies the two query terms the current policy
> never uses. **The disclaimer written to prevent misuse is what makes the stale document
> rank first.**
>
> Shipped as-is, the baseline answers EUR 2,500 — a refund approved beyond Maya's actual
> authority. **0 release blockers, 5 product failures.** Those are deliberately separate
> classes: returning irrelevant-but-permitted evidence wastes time; leaking a forbidden
> source is irreversible.

---

## 8 · Connecting a live source safely

**Figure:** `4_3_live_vs_fallback_parity.png`

One live read-only GitHub repository, with the committed export as fallback. A failed
fetch degrades and **discloses** it; no fallback record ever claims live freshness.

> Two things we got wrong first and fixed. **SSH access does not imply REST API access** —
> `git ls-remote` succeeded while the API returned 404, because the two are authorized
> independently. And **live and fallback records occupy disjoint ID spaces**, so a naive
> manifest diff would have *deleted* all 11 live records on any transient failure,
> amplifying an outage into an empty index. A degraded batch may never drive deletions.

---

## 9 · Retrieval: lexical vs semantic vs hybrid

**Figures:** `5_5_mode_comparison.png` · `5_3_weight_sweep.png` · `5_1_chunking_comparison.png`

**Selected: hybrid, `lexical_weight = 0.6`** — the argmin of mean expected rank (2.000) at
full recall across ten questions.

> **A correction we kept rather than removed.** Five questions said "recall is saturated,
> mode does not matter". On ten questions that is false — semantic drops to 0.95 and misses
> half of one case's evidence. The saturation was an artifact of a small denominator.
>
> **Why a lexical majority is right, generalised beyond this fixture:** semantic retrieval
> under-ranks records identified by *metadata* rather than prose. `GH-142`'s body contains
> neither "Atlas" nor "open" — its Atlas identity lives in its labels. That is a property of
> enterprise work items in general.
>
> **And what no retrieval configuration fixed:** the archived-policy conflict persists in
> every mode, and hybrid makes it *worse*. That fix had to live above retrieval.

---

## 10 · Index lifecycle: the change that looks like no change

**Figures:** `2_2_change_detection.png` · `5_4_lifecycle_timeline.png`

Chunk IDs hash content **plus** `title`, `allowed_roles`, `confidentiality`, `status`,
`occurred_at`.

> **Why metadata is in the hash, and it is a security reason rather than a correctness one.**
> Tightening `allowed_roles` leaves the body text **byte-identical**. A content-only hash
> fires no upsert, so the indexed chunk keeps its **old permission metadata and stays
> retrievable under the old policy** — a stale *authorization*, not a stale answer.
>
> Tested against five change types: timestamp IDs miss three, content-only misses two, the
> governance hash catches all five. Re-permissioning revokes access on the very next sync —
> a case **no supplied evaluation covers**, tested because the governance design predicted it.

---

## 11 · Five narrow tools, one bounded agent

**Figures:** `6_2_tool_test_matrix.png` · `6_5_tool_selection.png` · `6_2_relevance_threshold.png`

Every tool tested directly — normal, denied, empty, failure — **before** the agent could
call one. Max 2 of 6 permitted tool calls used in practice.

> **Identity is a closure, not a tool argument.** `EmployeeContext` appears in **no** tool's
> schema, so the agent has no vocabulary for changing who it is. If identity were a value
> the model produced, privilege escalation would become a matter of persuading the model —
> and the corpus contains a message trying to do exactly that.
>
> **Hybrid retrieval cannot say "no answer".** Min-max normalisation gives the best
> permitted record 1.0 *whatever* the question, so the unanswerable case returned six
> sources at top score 1.0 — maximum apparent confidence on a question with no answer.
> Absolute term coverage was added above retrieval to separate the two.

---

## 12 · The trust boundary — four behaviours, verified

**Figures:** `6_5_injection_resistance.png` · `3_2_filter_is_loadbearing.png`

| Behaviour | Result |
| --- | --- |
| Conflict — archived policy identified as superseded | verified |
| Permission refusal, denied role | **3/3**, `DOC-HR-001` never touched |
| The same question, cleared role | **3/3** answered, citing `DOC-HR-001` |
| Injection — structural control | held on **every** scored run |

> **The middle two are the demonstration.** Same question, same corpus, opposite outcome —
> so the boundary is about *identity*, not about how the request was worded.
>
> That pair also caught a real defect. `DOC-HR-001`'s own body says it must never be
> retrieved for three other roles, and the agent obeyed that sentence — refusing the one
> role entitled to it. **That is prompt injection pointing the other way**: obeying
> retrieved content, except that instead of leaking a record it denied one. We had defended
> only the direction that looks dangerous.
>
> **Injection is two results, not one.** The structural control held every time; whether
> the employee is *told* an attack is present is behavioural and was a coin flip. A single
> combined "pass" would hide the difference between a guarantee and a tendency.

---

## 13 · Human approval before any action

**Figure:** `6_4_approval_audit.png`

**11/11 gate checks. One execution across the entire run** — the single authorised approval.

- approved → executed **exactly once**; re-approving twice more executed nothing
- rejected → never executed, and cannot later be approved
- **edited → a NEW proposal needing its own approval**
- Maya cannot approve Leo's proposal — identity re-derived **at the gate**
- **no tool in the agent's toolset can execute anything**

> The executor lives outside the tool package entirely, so this is not a rule the agent is
> asked to follow — it is a capability it does not have.
>
> Idempotence is deliberate, not incidental: Streamlit reruns the whole script on every
> interaction, and a double-executed action is not recoverable by re-rendering a page. It
> also means **only a counting executor can verify it** — an exception check cannot tell a
> refusal from a silent no-op.

---

## 14 · Evaluation results by layer

**Figures:** `8_4_verdict_matrix.png` · `8_4_layer_rates.png` · `8_4_latency.png`

| Release blocker | Threshold | Observed |
| --- | --- | --- |
| Forbidden evidence in a citation | 0 | **0** |
| Forbidden evidence in a trace | 0 | **0** |
| Unresolvable citation | 0 | **0** |
| Citation outside permissions | 0 | **0** |
| Action executed without approval | 0 | **0** |

Latency p50 **11.0 s** / p95 **33.8 s** against 30 s / 90 s.

> **Counted, not averaged.** One occurrence blocks whatever the pass rate — a boundary that
> holds two times in three is broken. Non-determinism therefore makes the blockers *harder*
> to establish, not easier: three runs give three chances to fail.
>
> **Say the coverage caveat before the chart, not after.** The baseline shows more passes
> than the agent purely because quota ended the agent's run. Like-for-like on the five
> cases scored in both: **hybrid 2, baseline 1, tied 2** — and the agent's two wins are
> exactly the refusal and abstention failures the baseline phase predicted it would fix.

---

## 15 · What failed — including in the evaluation itself

**Three of the defects we found were in the *measurement*, not the product. Two were ours.**

| | |
| --- | --- |
| 19 quota events scored as behavioural failures | We wrote the rule forbidding that, then broke it |
| A correct refusal labelled `answered` | The model wrote `can’t` with a curly apostrophe |
| Grounded 4-source answer labelled unsupported | The model wrote source ids with a non-breaking hyphen |
| **The baseline "passes" 9 cases without answering one** | Our scorer accepts `evidence_found` |

> The last one we **did not fix**, deliberately. Changing a scoring rule after seeing
> results, in the direction that flatters our own product, is precisely what fixing
> thresholds in advance exists to prevent. The honest response is disclosure, not a rule
> change.
>
> **The general lesson, four times over:** anything that reads meaning out of generated
> prose must normalise it first — and normalising is necessary, not sufficient. The fourth
> case could not be fixed by parsing better at all: from inside its permitted set the agent
> had **no more information than the classifier did**. That one had to move above the model.
>
> A harness that only catches exceptions silently scores every failure the system reports
> *gracefully*. Graceful degradation and measurement are in tension.

---

## 16 · Release recommendation

# Demonstrate — with explicit limitations

**For:** 0 blockers across 53 scored runs · boundary verified in both directions and
evidenced by the candidate set · approval boundary proven end to end · injection's
structural control held every run · packaged product starts clean, 16/16.

**Against unqualified:** the three-variant comparison is **incomplete** · the scored rows
**predate three system changes** · feedback below threshold · one project unreachable ·
the current model is **unverified** since the switch.

> *Do not demonstrate yet* is not supported — nothing measured suggests the product is
> unsafe to show. *Demonstrate*, unqualified, would present an incomplete comparison and
> superseded rows as though they backed the product as it stands.
>
> **The limitations belong in the same breath as the recommendation.** A limitation read
> afterwards is not a limitation.

---

## 17 · What real deployment would still require

- **Real authentication.** Identity here is a selector, not a credential — every permission
  guarantee is conditional on the selected profile being honest.
- **Permissions from the source systems' own ACLs**, not fixture metadata.
- **Encryption at rest, access control on traces, retention and deletion, rate limiting,
  tenant isolation** — none of which exist.
- **A real execution path** with a narrowly scoped write token.
- **Inference control.** Filtering governs what is *retrieved*, not what a model *infers*
  from evidence it is allowed to see. **This remains the most important unvalidated
  assumption in the brief.**

> The container runs. That is all the container establishes.

---

## Appendix · If you are asked

| Question | Answer |
| --- | --- |
| *Why not just tell the model not to leak?* | Prompts fail silently. 16 of our 30 controls are structural, and every threat has at least one. The restricted record is never a candidate — the model is never in a position to leak it. |
| *How do you know filtering happens before retrieval?* | The candidate set in the trace. A refusal is equally consistent with a politely-instructed model. |
| *Why is the archived policy such a problem?* | Its own "do not use this archived threshold for current decisions" warning supplies the query terms the current policy lacks. No retrieval configuration fixed it. |
| *Why is the evaluation incomplete?* | A free-tier tokens-per-minute limit. Stated as a gap rather than papered over — `semantic_agent` has no scored runs. |
| *Did the agent ever leak anything?* | No. 0 across 53 scored runs, plus 36 adversarial retrievals per mode across four independent regression checks. |
| *Is it production-ready?* | No, and nothing here claims it is. See slide 17. |
