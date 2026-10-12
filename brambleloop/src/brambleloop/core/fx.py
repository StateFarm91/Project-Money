"""The one assumed USD/CAD exchange rate (v1.1 integrator wiring).

Two assumptions had drifted apart: `gateway.routing` / `finance.currency` / `scale.target`
used 0.715 USD per CAD, while `gateway.anthropic`, `gateway.images`, `gateway.image_bench`
and `visual.d_judge` used 1.37 CAD per USD. They are not reciprocals (1 / 0.715 = 1.3986),
so the same USD bill was 2.1% cheaper in the ledger than in the router's ceiling check.

One number now, stated once. 0.715 USD/CAD was kept because it is the rate the books,
fee schedule and ceiling conversions already report at (and that tests pin); the CAD-per-USD
figure is derived from it rather than restated. Relative to the old 1.37 this records model
and image spend about 2.1% *higher* -- the conservative direction for every spend ceiling,
none of which changed. It is an assumption, not a measurement, and is labelled so wherever
it is used; a settlement statement replaces it.
"""
from __future__ import annotations

ASSUMED_USD_PER_CAD = 0.715
ASSUMED_CAD_PER_USD = 1.0 / ASSUMED_USD_PER_CAD
