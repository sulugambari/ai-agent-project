# Access Matrix

Declared access policy for the **Northstar Release Coordinator**. Completed in
Phase 2 before any semantic retrieval, per `AGENTS.md`.

- **Primary profile:** Leo Martins (`engineering`) · **Secondary:** Maya Chen (`customer_success`)
- **Figures:** `deliverables/figures/2_1_access_matrix.png` (declared policy),
  `deliverables/figures/2_1_policy_vs_fixture.png` (audit against enforced metadata)
- **Audit result:** 32 of 32 auditable cells match the `allowed_roles` metadata
  carried by the fixtures. 0 mismatches. 12 cells are not auditable and are
  labelled as such rather than assumed.

## Record Classes

The supplied template offered six rows. We use **eleven**, because six could not
express the boundary without misrepresenting it — the refund policies are neither
a handbook nor a financial record, and release documents are not customer
communications. Each of the 15 fixture records maps to **exactly one** class; this
is asserted in the notebook, so a new source cannot be silently unclassified.

### Three states, not two

| State | Meaning |
| --- | --- |
| `Allow` | Every record in the class is available to the role |
| `Conditional` | **No blanket class access.** Per-record `allowed_roles` governs |
| `Deny` | No record in the class is available to the role |

`Conditional` exists because two classes are genuinely non-uniform: `GH-142` is
visible to Finance but `GH-149` is not; the Acme emails are visible to Engineering
but the customer-operations thread is not. Recording those as `Allow` would
overstate access, and as `Deny` would understate it. Both would be wrong.

## Access Matrix

| Record class | Customer Success | Engineering | People Operations | Finance | Owner and reason |
| --- | --- | --- | --- | --- | --- |
| General handbook & announcements | Allow | Allow | Allow | Allow | Security Team / Leadership — company-wide operating guidance, no restriction justified |
| Release documents | Allow | Allow | **Deny** | Allow | Nora Kim — release brief drives delivery and customer commitments; People Ops has no release remit |
| Release decisions (Slack) | Allow | Allow | **Deny** | Allow | Nora Kim — decision records, same remit as the release documents they authorise |
| Engineering discussion (Slack) | **Deny** | Allow | **Deny** | Conditional | Engineering — implementation detail and imported third-party notes. Finance is conditional: billing-reconciliation threads only. Denied to Customer Success because unreviewed engineering chatter reaching a customer conversation is the failure mode this product exists to prevent |
| Customer communications | Allow | Conditional | **Deny** | Allow | Customer Success — Engineering is conditional: release-commitment threads only, not the customer-operations case thread, which carries account handling detail engineers do not need |
| Customer policy documents | Allow | **Deny** | **Deny** | Allow | Finance Operations — refund authority thresholds. Denied to Engineering: no engineering task requires a refund limit, and exposure invites out-of-remit advice |
| Local GitHub work items | Conditional | Allow | **Deny** | Conditional | Engineering — conditional for Customer Success (customer-visible support items) and Finance (billing items), per label |
| Live GitHub work items | **Deny** | Allow | **Deny** | **Deny** | Engineering — see *API reachability is not authorization* below |
| Business records (projects/cases) | Allow | Allow | **Deny** | Allow | Operations — project status, owner, target date, and support-case status are operational facts needed across the three delivery roles |
| Financial records (contract value) | **Deny** | **Deny** | **Deny** | Allow | Finance — `customers.annual_value_eur`. Denied to Customer Success by deliberate decision: no priority question needs contract value, and the narrower default is the correct one when need is not demonstrated |
| Restricted HR records | **Deny** | **Deny** | Allow | **Deny** | People Operations only — personal compensation data; disclosure is irreversible and a personal-data breach |

### API reachability is not authorization

The live GitHub source is `sulugambari/ai-agent-project`, a **public** repository:
anyone can read its issues without a token. We nonetheless scope live work items
to `engineering` only, matching the local class. The restriction is **not** claimed
to protect confidentiality of public data. It exists for three reasons:

1. **Policy stability under infrastructure change.** A policy derived from "it is
   public anyway" becomes silently wrong the moment the repository is made private
   — the realistic production case. A policy derived from the product's remit
   stays correct either way.
2. **Coherence across ingestion paths.** If local `GH-142` is denied to Customer
   Success while a live issue is allowed, the same class of information carries two
   policies depending on how it was ingested. That is an incoherent boundary and a
   defect source.
3. **`04-connected-rag-and-agent.md` requires it:** *"apply an intentional access
   policy instead of assuming that API access equals employee access."*

## Enforcement Notes

- **Identity source in the prototype:** a Streamlit profile selector and the
  `employee_id` field on the API request, resolved against the fixed `EMPLOYEES`
  map in `company_assistant/api.py`. This is **role simulation, not
  authentication** — there is no credential, session, or token behind it. An
  unrecognised profile is rejected with HTTP 403 rather than defaulted to a role
  (verified in step 0.3).
- **Where filtering happens:** `security.filter_permitted()` is applied to the
  document set **before** any retrieval scoring, and in Phase 5 becomes a metadata
  pre-filter on the vector query so unauthorized records are never candidates.
  Filtering is never delegated to the system prompt.
- **Default when metadata is missing:** **deny**, enforced at three layers.
  `connectors.common.parse_roles()` raises on empty or unknown roles at parse
  time; `CompanyDocument` requires `allowed_roles`; and the membership test in
  `filter_permitted()` excludes anything the role is not explicitly listed in.
  A malformed record therefore fails loudly at ingestion rather than becoming
  silently world-readable.
- **How citations are rechecked:** every cited `source_id` is re-validated against
  `filter_permitted()` for the current employee *at citation time*, not trusted
  from retrieval. An unresolvable or unpermitted citation counts as a fabricated
  citation, which is a release blocker.
- **How live API access differs from employee authorization:** see *API
  reachability is not authorization* above.
- **Where GitHub credentials are stored:** `.env` only, git-ignored. The chosen
  public repository requires **no token**, which removes the credential from the
  system entirely rather than managing it. If a private repository is ever
  substituted, a fine-grained token limited to one repository with read-only issue
  access goes in `.env` and nowhere else — never in prompts, traces, indexed
  content, screenshots, or deliverables.
- **How identity is rechecked before an approved action:** the proposal records
  `requested_by`. At approval, identity is re-resolved and permission re-evaluated
  immediately before execution; a mismatch between the approver context and the
  proposal cancels rather than executes. Text inside a retrieved document can
  never constitute approval.
- **What the prototype does not secure yet:** real authentication and identity
  propagation; source-level permissions read from the systems of record rather
  than fixture metadata; encryption at rest; access control on traces and audit
  records; retention and deletion guarantees; tenant isolation; rate limiting.
  Streamlit also binds all network interfaces by default and advertised a LAN URL
  during step 0.3 — an unauthenticated assistant should not be network-reachable,
  which is a Phase 9 packaging decision.
- **Evidence that unauthorized content is excluded before retrieval:** the
  candidate-set trace recorded per query, plus the mechanical audit in
  `2_1_policy_vs_fixture.png`. **A refusal is not evidence** — it is equally
  consistent with a model that was merely instructed to decline. Only the
  candidate set proves the record never reached the model.

## Source Governance

**Figure:** `deliverables/figures/2_2_change_detection.png`

### Two identifiers, two jobs

| Identifier | Purpose | Behaviour on change |
| --- | --- | --- |
| `source_id` | Resolving a **citation** | **Never changes.** A citation written today must still resolve after the record is revised |
| `chunk_id` = `<source_id>::<fingerprint>::<nn>` | Addressing a **chunk in the index** | **Changes on every revision**, so an upsert replaces the old chunk instead of appending beside it |

Conflating these is the EVAL-011 failure: a single ID cannot both stay constant for
citations and vary for upserts.

### Revision fingerprint

12 hex characters of `sha256` over content **plus every field that governs
retrieval or access**: normalized content, title, `allowed_roles`,
`confidentiality`, `status`, and `occurred_at`.

Metadata is included deliberately, and the reason is security rather than
correctness. `python-frontmatter` places YAML in `.metadata` and body text in
`.content`, so tightening `allowed_roles` or `confidentiality` leaves the content
**byte-identical**. A content-only hash would not fire an upsert, and the
already-indexed chunk would keep its **old permission metadata and remain
retrievable under the old policy** — a stale *authorization*, not a stale answer.
That would reintroduce, through an indexing shortcut, exactly the leak this access
matrix exists to prevent. Tested against five change types in the notebook; a
timestamp-based ID misses three of them and a content-only hash misses two.

### Per-source governance

| Source | Stable ID strategy | Citation target | Update or deletion policy | Fallback |
| --- | --- | --- | --- | --- |
| Slack export | `source_id` from the export (`SLACK-ATLAS-103`). Chunk ID adds the governance fingerprint | File path + channel + author + timestamp. **No permalink exists** in the fixture — the export carries no URL field, so the citation resolves to the record, not to Slack | Whole folder re-read each sync; manifest diff upserts changed records and deletes records absent from the export. An edited message keeps its timestamp, so detection relies on the fingerprint, not recency | None required — local file. A missing or malformed file raises at parse time and fails visibly |
| Email export | `X-Source-ID` header. `Message-ID` retained as a second, genuinely global identifier | File path + `Message-ID` + Subject + Date | Manifest diff as above | None required — local file |
| Documents | `source_id` from YAML front matter | File path + title + `effective_at` + **`status`**. Status is part of the citation, not just metadata: P2 and T4 both require the reader to see that a source is archived | Manifest diff. **Front-matter-only changes are the critical case** — `status: current → archived` leaves content identical, so the fingerprint must span metadata or the stale threshold keeps being served | None required — local file |
| Local GitHub export | `source_id` (`GH-142`). Deliberately independent of the issue title, per `04`: a retitled issue must keep its identity | File path + issue number + state. No URL in the fixture | Manifest diff. A retitled or reworded issue produces a new fingerprint (correct — content changed) while `source_id` holds, so existing citations still resolve | This source **is** the fallback for the live connector |
| Live GitHub repository | `GH-LIVE-<number>` derived from the immutable issue number, with GitHub's `node_id` retained in metadata. Never derived from the title | **`html_url`** — the only source in the product with a genuine clickable deep link | Fetched each sync; manifest diff removes issues no longer returned (deleted or transferred) and upserts state changes such as open → closed. Records `source_freshness` (`live` \| `fallback`) and `fetched_at` | Local export under `data/raw/github/`. On failure the degraded state is **disclosed** in the answer and `source_freshness` is set to `fallback`; fallback data is never presented as live freshness |
| SQLite records | `DB-<TABLE>-<primary key>` (`DB-CASE-481`), matching the convention already in `database.py` | Table + primary key, rendered as a record card. No URL | **Not indexed at all.** Queried live through narrow read-only tools at answer time, so there is no chunk to upsert or delete and no staleness window. This also keeps `annual_value_eur` out of the vector store entirely, shrinking the permission surface | None. If the database is unavailable the tool returns a controlled error and the agent must not invent a value (EVAL-008) |

### Consequences carried into Phase 5

1. **Two mechanisms are required, not one.** Fingerprints detect revision;
   only a **manifest diff** detects deletion. `2_2_change_detection.png` shows
   deletion is invisible to every ID scheme.
2. **A full local rebuild must be available** for when incremental
   synchronization fails, per `04`.
3. **A visible last-indexed status** is required in the interface, and must
   distinguish live from fallback for GitHub-sourced evidence.
4. **The database is queried, never embedded.** Structured facts stay
   authoritative and current by construction.
