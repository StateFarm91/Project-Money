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


## 2026-11-02T14:00Z: wiring verification at claude/w5-INTEG1 50937469 (authoritative acceptance matrix)

Full evidence (file:line) and the 16-department × 12-criterion matrix are in `P0_WIRING_50937469.md` (this folder). Production evidence is UNKNOWN for every row until Batch 5 is deployed and read back. Code that exists is not counted as operational.

**Handoffs:** 25 checked. 14 are CONNECTED (automatic, durable, idempotent, no Claude), 9 PARTIAL and 2 MISSING.

**CONNECTED**
- POOL concept → `cir.draft` → `cir.compile` (one revision) → `gate.certify` → `listing.draft` → `assets.build` (US/UK PDFs, charts, disclosed renders) → pricing → `listing.seo` → `launch.plan` → `store.publish`. Publication is refused in SHADOW.
- Withholding, and dead-end successors re-driven once per commit.
- Halted certifications retried.
- Imagery started automatically but spend-gated: FLUX 3 is refused while the `image_generation` gate is closed.
- Listing-package sweep plus the owner review request.
- Lease reclaim with fencing, and dead letters.
- A blocked product does not stop others.

**Gaps and their assignments (opus2; see PR #3 and `COORDINATION.json` `assignments`)**

| # | Gap | Status | Assignment |
|---|---|---|---|
| 1 | Research brief / coverage gap → new concept outside the 34 (`attach_proposal` has test callers only) | MISSING in practice | A4 |
| 2 | Refused or held draft → enrichment → re-draft (no consumer; the `draft:<slug>` key is permanent) | MISSING | A4 |
| 3 | Bounded correction loop after certify, quality and assets failures; named hold when exhausted | PARTIAL | A5 |
| 4 | Learning knowledge into later designs (lessons only nudge scores; knowledge gaps are read by nobody) | PARTIAL | A6 (consumer side; Codex owns the knowledge store) |
| 5 | POOL exhaustion: no supply-stall reading or alert | PARTIAL | A7 |
| 6 | Culture signals → ideation (learning notes only) | PARTIAL | A8 |
| 7 | Listing package polled every 6 h instead of event-driven | PARTIAL | A9 |
| 8 | Family amplification has no input until orders exist | UNMEASURED | none |

Not assigned now:
- Marketing channel adapters (Instagram, Pinterest): this needs channel authorisation.
- Private Etsy drafts are refused in SHADOW; that is correct.
- The two MJ basket benchmarks exist only in a research document. This is folded into A4's intelligence inputs.
