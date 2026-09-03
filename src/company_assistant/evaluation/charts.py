"""Charts for the evaluation view and the notebook, defined once.

Both the Streamlit page and the notebook render these, so a figure in the deck
and the same figure in the app cannot drift apart.

Colour follows the job it does, not taste:

* **Verdicts and blockers are STATUS**, so they use the reserved status steps and
  always carry a text label in the mark. Meaning is never colour-alone.
* **Variants are CATEGORICAL**, in fixed slot order. They deliberately do NOT
  borrow the status palette: an earlier version painted the hybrid variant in the
  same hex as "allow", which reads as *good* rather than as *a series*. Those
  slots were also validated rather than eyeballed - the previous blue/purple pair
  measured a normal-vision separation of dE 10.0, below the readable floor, so the
  two variants were hard to tell apart for every reader.
"""

from __future__ import annotations

from typing import Any

import altair as alt
import pandas as pd

STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a",
          "critical": "#d03b3b", "neutral": "#52514e"}
CATEGORICAL = {"lexical_baseline": "#2a78d6", "semantic_agent": "#eb6834",
               "hybrid_agent": "#1baf7a", "hybrid_agent_pre_f26": "#eda100"}
VERDICT_COLOR = {"Pass": STATUS["good"], "Partial": STATUS["warning"],
                 "Fail": STATUS["critical"], "Not scored": STATUS["neutral"]}
VERDICT_ORDER = ["Pass", "Partial", "Fail", "Not scored"]

#: Short display names. The raw keys overflow an axis label, and one of them needs
#: to say what it *is*: `hybrid_agent_pre_f26` is the DEFECTIVE system, kept as
#: evidence that F-26 was real. Shown unlabelled it reads as a fourth variant
#: under comparison, which would be a misreading with real consequences.
VARIANT_LABEL = {
    "lexical_baseline": "lexical baseline",
    "semantic_agent": "semantic +agent",
    "hybrid_agent": "hybrid +agent",
    "hybrid_agent_pre_f26": "hybrid PRE-FIX",
}


def display_variant(name: str) -> str:
    return VARIANT_LABEL.get(name, name)


def verdict_matrix(verdict_rows: list[Any]) -> alt.Chart:
    """Case x variant, each cell labelled with its verdict."""
    frame = pd.DataFrame([{
        "case": v.case_id, "variant": display_variant(v.variant), "verdict": v.verdict,
        "tier": v.tier, "runs": f"{v.scored_runs}/{v.runs}", "note": v.note or "-",
    } for v in verdict_rows])
    if frame.empty:
        return alt.Chart(pd.DataFrame({"x": []})).mark_point()

    cases = sorted(frame.case.unique(), key=lambda c: (not c.startswith("EVAL"), c))
    base = alt.Chart(frame).encode(
        x=alt.X("variant:N", title=None, axis=alt.Axis(
            orient="top", labelAngle=0, labelFontSize=10,
            labelExpr="split(datum.label, ' ')", labelPadding=26, grid=False, ticks=False)),
        y=alt.Y("case:N", title=None, sort=cases,
                axis=alt.Axis(grid=False, ticks=False, labelFontSize=10)),
    )
    return (
        base.mark_rect(stroke="white", strokeWidth=2).encode(
            color=alt.Color("verdict:N",
                            scale=alt.Scale(domain=VERDICT_ORDER,
                                            range=[VERDICT_COLOR[v] for v in VERDICT_ORDER]),
                            legend=alt.Legend(title=None, orient="bottom")),
            tooltip=["case", "variant", "verdict", "tier", "runs", "note"])
        # the label is what makes this readable without colour, which the
        # accessibility pass requires and greyscale printing needs
        + base.mark_text(fontSize=8, fontWeight="bold", color="white").encode(
            text=alt.Text("verdict:N"))
    ).properties(width=300, height=alt.Step(26),
                 title=alt.TitleParams(
                     "Case verdicts by variant",
                     subtitle=("Tier A passes on >=2 of 3 runs, Tier B on its single run. "
                               "PRE-FIX is the defective system, kept as evidence - not a candidate.")))


def layer_rates(verdict_rows: list[Any]) -> alt.Chart:
    """Pass rate per evaluation layer, per variant. One axis, no dual scales."""
    LABEL = {"retrieval_pass": "retrieval", "permissions_pass": "permissions",
             "citations_pass": "citations", "status_acceptable": "behaviour"}
    frame = pd.DataFrame([
        {"variant": display_variant(v.variant), "layer": LABEL[layer], "rate": rate}
        for v in verdict_rows if v.scored_runs
        for layer, rate in v.layer_rates.items()
    ])
    if frame.empty:
        return alt.Chart(pd.DataFrame({"x": []})).mark_point()
    grouped = frame.groupby(["variant", "layer"], as_index=False)["rate"].mean()
    return (
        alt.Chart(grouped).mark_bar(cornerRadiusEnd=3).encode(
            y=alt.Y("variant:N", title=None, axis=alt.Axis(labelFontSize=9)),
            x=alt.X("rate:Q", title=None, scale=alt.Scale(domain=[0, 1]),
                    axis=alt.Axis(format=".0%", tickCount=3)),
            color=alt.Color("variant:N",
                            scale=alt.Scale(domain=[display_variant(k) for k in CATEGORICAL],
                                            range=list(CATEGORICAL.values())),
                            legend=None),
            row=alt.Row("layer:N", title=None, sort=list(LABEL.values()),
                        header=alt.Header(labelFontWeight="bold", labelAnchor="start",
                                          labelFontSize=10)),
            tooltip=["variant", "layer", alt.Tooltip("rate:Q", format=".0%")])
        .properties(width=250, height=34,
                    title=alt.TitleParams(
                        "Pass rate by evaluation layer",
                        subtitle="A fluent answer can pass one layer and fail another, so they are scored apart"))
    )


def latency_strip(rows: list[dict[str, Any]]) -> alt.Chart:
    """Per-turn latency, with the median marked. Rate-limit waits excluded."""
    scored = [r for r in rows if r.get("scored")]
    if not scored:
        return alt.Chart(pd.DataFrame({"x": []})).mark_point()
    frame = pd.DataFrame([{"variant": display_variant(r["variant"]), "seconds": r["product_s"],
                           "case": r["case_id"]} for r in scored])
    points = alt.Chart(frame).mark_circle(size=70, opacity=0.75).encode(
        x=alt.X("seconds:Q", title="seconds per turn, rate-limit waits excluded"),
        y=alt.Y("variant:N", title=None, axis=alt.Axis(labelFontSize=9)),
        color=alt.Color("variant:N",
                        scale=alt.Scale(domain=[display_variant(k) for k in CATEGORICAL],
                                        range=list(CATEGORICAL.values())), legend=None),
        tooltip=["case", "variant", alt.Tooltip("seconds:Q", format=".1f")])
    medians = alt.Chart(frame).mark_tick(thickness=3, size=26, color="#0b0b0b").encode(
        x=alt.X("median(seconds):Q"), y=alt.Y("variant:N"))
    return (points + medians).properties(
        width=420, height=alt.Step(46),
        title=alt.TitleParams("Latency per turn",
                              subtitle="Tick marks the median. Thresholds: p50 30s, p95 90s"))
