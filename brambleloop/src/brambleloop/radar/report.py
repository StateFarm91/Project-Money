"""Render the scored opportunity pool as a document a human can argue with.

The portfolio decision is the most consequential one the system makes without asking: it
commits engineering effort to eight-to-twelve products and, by omission, declines the other
twenty-odd. A number in a database is not accountable. This writes the whole ranking, the
component breakdown, the constraints, and every swap the selector made, so the owner can
disagree with a specific line rather than with "the algorithm".

    python -m brambleloop.radar.report [YYYY-MM-DD] > reports/opportunity_pool.md
"""
from __future__ import annotations

import sys
from datetime import date

from .market import COMPETITORS, OBSERVATIONS, OBSERVED_ON, SEASONAL_EVENTS, shopping_window
from .opportunity import (
    CATEGORY_COMPETITION, CATEGORY_DEMAND, WEIGHTS, score_pool, select_portfolio,
)

_ORDER = ["demand", "competition_headroom", "verifiability", "seasonal_fit", "margin",
          "whitespace"]


def render(today: date | None = None, target: int = 10) -> str:
    today = today or date.today()
    scored = score_pool(today=today)
    portfolio = select_portfolio(scored, target=target, today=today)
    chosen = {c.slug for c in portfolio.selected}
    out: list[str] = []
    w = out.append

    w("# Opportunity pool and release portfolio")
    w("")
    w(f"_Generated {today.isoformat()} (UTC) from `brambleloop.radar`. "
      f"Competitor observations dated {OBSERVED_ON}. Regenerate with "
      f"`python -m brambleloop.radar.report`._")
    w("")
    w("Master Plan section 33: do not commit the first SKUs before Market Radar runs; start "
      "from at least 30 concepts across several categories, score them, then choose roughly "
      "8-12 release candidates. This document is that step, in full.")
    w("")

    w("## Portfolio decision")
    w("")
    w(f"{len(portfolio.selected)} selected from a pool of "
      f"{len(portfolio.selected) + len(portfolio.rejected)}.")
    w("")
    w("| Constraint (section 33) | Met |")
    w("|---|---|")
    for k, v in portfolio.constraints_met.items():
        w(f"| {k.replace('_', ' ')} | {'yes' if v else '**NO**'} |")
    w("")
    if portfolio.reasons:
        w("Ranking alone would not have satisfied those constraints. The selector made these "
          "swaps, each one deliberately choosing a lower score to avoid concentrating the "
          "portfolio in a single demand pattern:")
        w("")
        for r in portfolio.reasons:
            w(f"- {r}")
        w("")

    w("## Selected release candidates")
    w("")
    w("| # | Concept | Category | Class | CA$ | Score | Window / status |")
    w("|---|---|---|---|---|---|---|")
    for i, c in enumerate(portfolio.selected, 1):
        w(f"| {i} | **{c.seed.title}** | {c.seed.category} | {c.seed.risk_class} | "
          f"{c.seed.price_cad:.2f} | {c.score:.4f} | {c.notes[0]} |")
    w("")
    for c in portfolio.selected:
        w(f"### {c.seed.title}")
        w("")
        w(f"`{c.slug}` · {c.seed.category} · Class {c.seed.risk_class} · "
          f"CA${c.seed.price_cad:.2f} · maker {c.seed.maker_hours[0]:g}-"
          f"{c.seed.maker_hours[1]:g}h · our build lead {c.seed.build_lead_days}d"
          + (f" · family `{c.seed.family}`" if c.seed.family else ""))
        w("")
        w(c.seed.rationale)
        w("")
        w("| " + " | ".join(k.replace("_", " ") for k in _ORDER) + " | **score** |")
        w("|" + "---|" * (len(_ORDER) + 1))
        w("| " + " | ".join(f"{c.components[k]:.2f}" for k in _ORDER)
          + f" | **{c.score:.4f}** |")
        w("")

    w("## Full ranking")
    w("")
    w("| Rank | Concept | Cat | Cls | Score | " +
      " | ".join(k.replace("_", " ") for k in _ORDER) + " | In |")
    w("|---|---|---|---|---|" + "---|" * (len(_ORDER) + 1))
    for i, c in enumerate(scored, 1):
        marks = " | ".join(f"{c.components[k]:.2f}" for k in _ORDER)
        w(f"| {i} | {c.seed.title} | {c.seed.category} | {c.seed.risk_class} | "
          f"{c.score:.4f} | {marks} | {'yes' if c.slug in chosen else ''} |")
    w("")

    w("## How the score is computed")
    w("")
    w("Weighted sum of six components, each 0-1. Weights:")
    w("")
    for k in _ORDER:
        w(f"- **{k.replace('_', ' ')}** — {WEIGHTS[k]:.2f}")
    w("")
    w("No model is asked to rank concepts. A model is good at proposing concepts and bad at "
      "being consistent about why one beats another, and \"the model preferred it\" is not a "
      "reason anyone can audit six weeks later when a SKU underperforms.")
    w("")

    w("## Category evidence")
    w("")
    w("| Category | Demand | Competition | Headroom |")
    w("|---|---|---|---|")
    for cat in sorted(CATEGORY_DEMAND):
        d, comp = CATEGORY_DEMAND[cat], CATEGORY_COMPETITION[cat]
        w(f"| {cat} | {d:.2f} | {comp:.2f} | {d - comp:+.2f} |")
    w("")

    w("## Competitor profiles")
    w("")
    for c in COMPETITORS:
        w(f"### {c.shop}")
        w("")
        w(f"{c.positioning}. Observed {c.observed_on} at CA${c.observed_price_band_cad[0]:.2f}"
          f"-{c.observed_price_band_cad[1]:.2f}."
          + (f" Discounting: {c.discount_pattern}." if c.discount_pattern else ""))
        w("")
        w(f"- **Strength.** {c.strength}")
        w(f"- **Gap we can attack.** {c.gap}")
        if c.format_signals:
            w(f"- **Formats.** {', '.join(c.format_signals)}")
        w("")
    w("Competitor research is demand and merchandising intelligence only. No competitor "
      "instructions, charts, photography or protected designs are copied, referenced as "
      "source material, or used to derive a pattern.")
    w("")

    w("## Category-level observations")
    w("")
    for k, v in OBSERVATIONS.items():
        w(f"- **{k.replace('_', ' ')}** — {v}")
    w("")

    w("## Buying windows")
    w("")
    w("Shopping date is modelled separately from making date (section 5). A 60-hour throw "
      "bought in December cannot be finished for Christmas, so the demand peak for a "
      "Christmas blanket pattern is autumn, and a radar sorted by \"days until the holiday\" "
      "would be wrong by three months.")
    w("")
    w("| Event | Date | Typical make | Buy window | Status today |")
    w("|---|---|---|---|---|")
    for e in SEASONAL_EVENTS:
        opens, closes = shopping_window(e)
        status = ("open" if opens <= today <= closes else
                  "not yet" if today < opens else "closed")
        w(f"| {e.name} | {e.event_date.isoformat()} | "
          f"{e.typical_make_hours[0]:g}-{e.typical_make_hours[1]:g}h | "
          f"{opens.isoformat()} → {closes.isoformat()} | {status} |")
    w("")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    when = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    sys.stdout.write(render(when))
