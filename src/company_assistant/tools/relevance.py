"""Absolute relevance, because the retrieval score is only relative.

The problem
-----------
`HybridRetriever` min-max normalises both signals, so the best permitted record
always scores 1.0 no matter how badly it matches. Cosine similarity is never
exactly zero either, so `combined > 0.0` filters nothing in hybrid mode. Two
consequences, both measured on this corpus:

* `search_company_knowledge` can **never** return `status="empty"` while the
  employee can see anything at all.
* EVAL-007 ("What revenue will Atlas generate next quarter?") - the case that
  must abstain, and for which no forecast exists anywhere in the company -
  returns six sources with the top one scoring **1.0**. Maximum apparent
  confidence on an unanswerable question.

A model handed `score: 1.0` will read certainty. So the tool has to report an
*absolute* signal alongside the relative one. This is the same shape as the F-2
fix: retrieval cannot express the distinction, so the tool layer adds it.

Why term coverage, and why stopwords must go
--------------------------------------------
The baseline's own measure - the fraction of query tokens present in a record -
is absolute and interpretable. But its tokenizer only drops tokens of two
characters or fewer, so "what", "will" and "next" count as evidence of a match.
On EVAL-007 that inflates coverage to 0.25 purely from question grammar.
Removing a small stopword list makes the measure mean "how many of the terms the
employee actually asked about appear in this record".

The threshold, and how far to trust it
--------------------------------------
Measured over all 12 supplied cases plus a nonsense and an off-topic control:

* unanswerable: nonsense 0.00, EVAL-007 0.20, off-topic 0.25
* answerable:   0.33 (EVAL-005, EVAL-008, EVAL-011) up to 0.78

`0.30` separates them cleanly - but the margin is 0.25 against 0.33, which on
short records is a single token. So this is deliberately **not** used to
suppress evidence or force an abstention. It annotates the result as weak and
lets the agent decide, because a threshold this tight will misclassify
eventually and the cost of hiding real evidence is higher than the cost of
labelling it cautiously.
"""

from __future__ import annotations

from typing import Literal

from company_assistant.retrieval import _tokens

#: Interrogatives, auxiliaries and generic verbs that carry no subject matter.
#: Kept small and explicit rather than pulled from a library: this list changes
#: a measured threshold, so it belongs in the repository where a reviewer can
#: see exactly what was excluded.
STOPWORDS: frozenset[str] = frozenset(
    """
    what which who whom whose when where why how
    are was were will would can could should shall must may might does did done
    has have had the and for with from that this these those
    any all our their its his her they them you your about into over under per
    not but than then there here more most much many some such only just also
    very upon while both each other same now
    tell give show find need want know say get make use please
    """.split()
)

#: Below this, the retrieved evidence does not contain what was asked about.
#: See the module docstring for the measurement behind the number and for why it
#: annotates rather than filters.
WEAK_COVERAGE_THRESHOLD = 0.30

Relevance = Literal["strong", "weak", "none"]


def content_terms(query: str) -> set[str]:
    """Query tokens with grammar removed - what the employee actually asked about."""
    return {token for token in _tokens(query) if token not in STOPWORDS}


def term_coverage(query: str, text: str) -> float:
    """Fraction of the query's content terms that appear in `text`.

    Absolute: unlike the retrieval score, it does not depend on what else was in
    the corpus, so 0.2 means the same thing on every question.
    """
    terms = content_terms(query)
    if not terms:
        return 0.0
    return len(terms & _tokens(text)) / len(terms)


def classify(max_coverage: float) -> Relevance:
    if max_coverage <= 0.0:
        return "none"
    if max_coverage < WEAK_COVERAGE_THRESHOLD:
        return "weak"
    return "strong"


def relevance_note(relevance: Relevance, max_coverage: float) -> str:
    """The sentence the agent needs in order to read the scores correctly."""
    shared = (
        "Retrieval scores are RELATIVE ranks within this employee's permitted set, "
        "normalised so the best record always scores 1.0. A high score is not evidence "
        "of relevance. `term_coverage` is the absolute measure."
    )
    if relevance == "none":
        return (
            f"{shared} No query term appears in any retrieved record (coverage 0.00). "
            "This is almost certainly not evidence for the question asked - abstain "
            "rather than answering from it."
        )
    if relevance == "weak":
        return (
            f"{shared} Best coverage is only {max_coverage:.2f}, below the {WEAK_COVERAGE_THRESHOLD:.2f} "
            "level that every answerable evaluation case cleared. The company may hold no "
            "answer to this question; prefer saying so over assembling one from these records."
        )
    return shared
