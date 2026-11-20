# P0 gap register: product-to-listing factory

Owner: integrator. Updated: 2026-11-02T03:45Z. This register is honest about what does not
exist. "Merged" means merged into `claude/w5-INTEG1`, which is **not deployed**. Production is
Batch 4, 0967c3ee, in SHADOW.

**Completion rule (owner directive 2026-11-02, item 8):** neither Batch 5 nor the autonomous
workforce is complete until one product goes from a radar or culture signal to a CIR, then a
certified release, then assets, then an owner-review listing package, end to end, unattended,
in production SHADOW, with every gate's verdict read back.

**Current state of that chain:** not demonstrated. The listing package is still blocked in
SHADOW for real reasons (see row 5).

| # | Area | State | Gap | Owner | Next action |
|---|---|---|---|---|---|
| 1 | Construction breadth | **Merged:** baskets in the round and shaped forms refused by name (PR #3 c8); per-stitch colour in the CIR (PR #9, J-7 satisfied). **In fix:** pet bed (PR #10, OPUS2K-7 HIGH) and stocking (PR #11, OPUS2L-1 HIGH). | Hats stay refused: no sourced sizing standard. Mosaic and tapestry drafting do not exist yet. | opus2 | Fix the pet bed and stocking HIGHs; then mosaic vessel drafting (approved 2026-11-02). |
| 2 | Catalogue expansion and families | **Merged:** culture-family membership (PR #8). Launch-0 catalogue: 40 CIRs. | Culture families have no production evidence yet: the new code is not deployed. | integrator | Certify Batch 5. |
| 3 | Autonomous Learning | **Merged:** knowledge gaps become capped owner-approval reference recommendations (PR #3 c9); commercial lessons (PR #3 c3). | Reference-pattern intake does not exist yet. | Codex (`codex/p0-learning-reference`, claim only, not started) | Owner starts Codex. No one else builds it. Tranche 1 purchase (about CA$54) awaits the owner. |
| 4 | Image production | **Merged:** laura_home and FLUX 3 wiring (PR #3 c2a); photo-led listing-set certificate (PR #3 c6). | **P0-PHOTO-ASSET-REVIEW:** nothing re-approves an attested physical photo frame, so a photo-led set never certifies (fails closed). No physical sample photo exists yet. | opus2 (assigned 2026-11-02) | A deterministic asset-truth review job. |
| 5 | Listing assembly | **Merged:** the automatic `listing.package` job (PR #5). | In SHADOW every package is blocked: Etsy taxonomy not chosen ("Crochet" in the schema is UNKNOWN), no search profile, no bound physical sample, unverified Etsy claims, no sample photo. | integrator / owner | Read the taxonomy after Batch 5 deploys. Physical-sample actions belong to the owner. |
| 6 | Next-product selection | **Production:** `chain.rebuild` seeds the next uncertified Launch-0 release hourly. **Merged:** chain successors (PR #3 c4). | Whether that seeding is progressing is UNKNOWN. `stale_artefacts_rebuilding` and `publishing_halt_clear` read false in production (2026-11-02 03:31Z), and their detail needs the readback token. | integrator | Owner sets `BRAMBLELOOP_READBACK_TOKEN`; then diagnose. |
| 7 | Production runtime health | 0967c3ee deployed; `/api/verify` 13/13. | 3 of 4 evidence checks are false (row 6, plus `no_repeated_paid_call_in_24h`). The culture.sweep dead-letter fix is in W5-INTEG1, not production. | integrator | 24-hour acceptance runs until 2026-11-03T03:31Z. Diagnosis needs the readback token. |
| 8 | Execution capacity | Secondary is dispatched by its own 2-hourly trigger and by integrator fires on new findings or idle over 2 h. Reviews are tracked by send_later check-ins. | None blocking. | integrator | Keep running. |
