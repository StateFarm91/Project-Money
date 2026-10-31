# Independent security review OPUS2D: `opus2/p0-revenue-workforce` @ fb52cb9e (delta from 9c1a0037)

**STATUS: PARTIAL. Mutation results are pending.** This file will be replaced by the final report.

Scope: the opus2 commits 1cc31974 (OPUS2B2 fixes; its merge of Batch 4 base f4c3899b is excluded)
and fb52cb9e (OPUS2C fixes). 9b8f842 and 3232862 are opus2 commits after 9c1a0037, but they were
not named in scope and are not reviewed here.

Interim results:
- **F2-1 (HIGH):** fixed at the root. `release_gates.sample_photo_lead` calls
  `sample_photo.qualifying_photos` and matches on photo id and SHA-256 together. It copies none
  of the rule's logic.
- **F3.1 (MEDIUM):** fixed on the watchlist path. One LOW residual remains on the anchor path:
  a pending or running `mjs.scan` job masks a newer refusal.
- **New LOW:** the N1.1 size-claim patterns over-refuse. Examples are "4 mm / 4.5 mm hook" and
  "2 bags of yarn". This fails closed, so it is not a safety issue.
- **Suites:** every `test_opus2_*` suite passes so far.
