# A8 culture-to-ideation continuation

Source `opus2/a8-culture-ideation` at `4f99bd8ff867755a67c4bf0671c85e70cf0580c4`; continuation `codex/a8-culture-continuation`. The source branch includes A4a at `993cc0c` and therefore inherits the separate A4a Product Truth finding; this continuation is not an integration candidate by itself.

A culture signal key may be 80 characters, but `culture:` plus the key was truncated to an 80-character coverage arena. Distinct signals with the same first 72 characters could therefore share a research gap. Long keys now use a deterministic 128-bit digest suffix; existing truncated gaps are reused only if their stored full signal identity matches. The actual arena is passed into the research brief; no existing row is overwritten.

The previous bridge used momentum across all observation channels and dates. The bridge now requires two distinct dated, sourced readings from the same `reference` series, within the preceding 30 days and no later than the as-of date. Separate sources, duplicate same-day readings, future readings, stale series and marketplace/reference scale mixing cannot establish rising momentum. The 30-day operational cutoff is conservative and needs independent product review; rejected cases remain unknown, not negative demand. This does not change the shared radar or activate any provider.

Python 3.11: `test_w5_a8_culture_to_ideation.py` 7/7, `test_culture.py` and `test_culture_feed.py` both pass. The A8 suite uses persistent SQLite and actual registered workers; it covers colliding signal keys, legacy identity, restart, and incomparable/stale/future data.

Open for independent review: this branch inherits A4a's unaccepted safety finding, and the culture bridge does not consult `CultureSignal.protected_tokens` before recording a signal in a coverage arena and research brief. The resulting proposal path uses pod observations and house descriptors, but token propagation and title overlap require explicit review; do not certify protected-content isolation on these tests. No deployment or shared-branch change was made.
