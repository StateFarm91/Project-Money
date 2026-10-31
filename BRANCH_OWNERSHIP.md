# Branch and file ownership — read this before writing code

Maintained by the lead operator and release integrator. Last updated 2026-10-31T01:10Z.

All other contributors work on their own isolated branches. **Any contributor not listed below, including Fable, must:**
- take only UNOWNED work;
- never edit an owned branch;
- never merge into `claude/w4-INTEG8-next` or `claude/repository-setup-nc9x6o`;
- never touch Railway or Etsy;
- leave Laura's identity (`laura-r2-a42aeac7`, `visual/canonical.py`) unchanged.

If your work overlaps an owned area, stop. Record the overlap in your handoff and pick an unowned cluster.

## Release sequence

| Release | Branch | State |
|---|---|---|
| Production | `claude/repository-setup-nc9x6o` | ee35a493, deployed 2026-10-27T16:06Z |
| Batch 4 integration | `claude/w4-INTEG8-next` | d11d494c; integrator only |
| Batch 5 | product factory | branches below |

## Owned work: do not duplicate

| Area / files | Branch | Owner |
|---|---|---|
| Launch gates: `gates/first_customer.py`, `launch/readiness.py`, `ops/launch_decisions.py`, `publish/sample_photo.py`, policy baseline in `gates/platform_policy.py`, CC `#/policy` form | `claude/w4-LAUNCHFIX` | W-LAUNCHFIX (fixing review findings) |
| Brand knock-out screening, `brand/clearance.py` evidence | `claude/w4-BRANDSCREEN` | W-LAUNCHFIX |
| Production evidence: `ops/production_evidence.py`, `core/readbackauth.py`, `/api/readback/evidence`, `/api/verify` `evidence_checks`, `ops/readback.py` | `claude/w4-READBACK` | W-READBACK (in review) |
| Physical sample intake, `physical_upgrade`, tester kits, photo-first gallery ordering | `claude/w4-PHYSFIX` | W-PHYSFIX |
| Manual listing adoption: `publish/manual_adoption.py`, census/orders adoption, `published_manually` readers | `claude/w4-ADOPT` | W-ADOPT |
| Restartable test runner: `run_tests.sh`, `scripts/suite_checkpoint.py`, deploy-guard resume refusal | `claude/w4-RESUMEFIX` | W-RESUMEFIX |
| Premium customer PDFs: `publish/pdf.py`, customer editions | `claude/w4-PDF1` | W-PDF |
| Manual listing packages; basket identity source fix (launch0 product data, SEO inputs) | `claude/w4-LISTING1` | W-LISTING |
| Research-to-concept intake (`radar/`, `intel/`, `creative/` concept path); seed-shop watchlist | `claude/w5-CONCEPT` | W-CONCEPT |
| 15-state product inventory, flow health (stall/loop), CC Production dashboard | `claude/w5-INVENTORY` | W-INVENTORY |
| Ledger six-state evidence (`ledger9_states.py`) | `claude/w4-LEDGER9` | W-LEDGER (done) |

## Planned, owned by the integrator (do not start)

- Automatic premium-PDF production inside the chain (`assets.build` → premium PDF), after W-PDF passes review.
- An automatic listing-package assembly job, after W-PDF and W-LISTING.

## Candidate UNOWNED P0 clusters

Verify each against the code first.
- Visual Production: wire the listing-gallery assembly (hero, detail, measurement, contents and disclosure frames) to the certified release, with Laura identity checks where she appears. No paid generation without approval.
- Growth and performance learning: ingest live-listing performance into Winner Amplification and the next product priorities, without fabricating data while nothing is published.
- Market intelligence: production evidence that the competitor scans ran, with source timestamps and downstream research activity; honest "not accessible" records.
- Executive orchestration (deterministic): idle-capacity detection and automatic selection of the next eligible product.

## Update 2026-10-31: second Opus operator (formerly Fable)

- `fable/p0-revenue-workforce` (f4f3f7bf) built `products/stage_register.py`, a fifteen-stage register. **This DUPLICATES the owned W-INVENTORY work** (`claude/w5-INVENTORY`: `products/production_inventory.py`, `ops/flow_health.py`, CC Production view). It will NOT be merged as a parallel implementation.
  - Do not continue the stage register.
  - If you believe part of it is better (for example the daily orchestrator reading job), say exactly which part in your handoff. The integrator will port it into W-INVENTORY.
- Reviews done: READBACK = SHIP (Low L1–L4 to fix during integration). RESUMEFIX e634e6fc is awaiting re-review.
- The UNOWNED P0 clusters listed above are still open for the second operator:
  - visual listing-gallery assembly with Laura identity checks;
  - deterministic idle-capacity detection and automatic next-product selection;
  - growth and performance-learning ingestion into future product decisions;
  - production evidence of competitor scans.

  Claim one by committing a line to your branch's handoff before starting.

Contact: hand off through your branch and a handoff document. The integrator reviews, tests and merges only accepted changes.

## Owner decisions, 2026-10-31 (verbatim intent; to be recorded in DECISION_LOG at integration)

- **D-W4-OWNER-LAURA-HOME:** `laura-home-v1` is APPROVED with all six rooms.
  - Keep a believable, modest Canadian family home, with consistent architecture, furniture, finishes and layouts across galleries.
  - Allow realistic variation: natural clutter, ordinary belongings, different camera angles, lighting and activity.
  - No sterile showroom, and not every image identical.
  - Preserve Laura's canonical identity, listing-specific outfit consistency, Product Truth and generated-image disclosures.
  - Integration note: the current `laura_home.py` varies only one lived-in detail per listing. Variation of angle, light and activity is to be added within the fixed architecture.
- **D-W4-OWNER-NESTING-OUTFIT:** sage blouse, cream trousers and gold jewellery, approved for the Nesting Baskets listing ONLY, subject to identity and gallery consistency checks.
- **D-W4-OWNER-VISION-SUBLIMIT:** CA$15/month vision-review sublimit, approved in principle, inside the CA$100 company ceiling. NOT active until the Command Center owner grant is completed and headroom is verified.
- **D-W4-OWNER-FLUX3-SUBLIMIT:** CA$15/month FLUX 3 sublimit at 1K, approved in principle, inside the CA$100 ceiling. Keep identity checks, image-to-pattern verification, retries within budget and truthful disclosures. NOT active until the owner grant is completed and headroom is verified.
- **Financial control:** the combined sublimits are CA$30/month, inside CA$100, not on top of it. Verified 2026-10-31: `gateway/anthropic.spent_this_month_cad` counts model, vision AND image-render cost rows against the monthly ceiling (`routing.counts_against_monthly_ceiling`). No automatic top-ups.

## Coordination with the second Opus operator (opus2/p0-revenue-workforce)

- The integrator accepts: the size-claim gate 0343b6b0 (after the LAUNCHFIX delta review and the LISTING1 basket fix), the rim negative, `laura_home` (now owner-approved), and `scripts/p0_acceptance.py` (as instrumentation). Each goes through a focused independent review before merge.
- **Please split f3b763fb** into three commits on your branch: (a) `laura_home` plus the flux3 wiring, (b) the rim negative, (c) acceptance instrumentation. Add the owner's variation requirement above to `laura_home`, with tests.
- **Next unowned work for the second operator, after the split:**
  - deterministic idle-capacity detection and automatic next-product selection;
  - production evidence of competitor scans.

  Claim it in your handoff.

## Update 2026-10-31T02:45Z: channel isolation (owner directive D-W5-OWNER-CHANNEL-ISOLATION)

- Etsy's AI-generated-craft-pattern rule is a **channel-specific publication gate only**, never a company-wide engineering blocker. Research, design, validation, PDFs, imagery, gallery assembly, listing preparation and learning all continue for every product.
- **SUPERSEDED the same day by D-W5-OWNER-RETURN-TO-PLAN:** W-CHANNELGATE and W-CHANNELRESEARCH were stopped before producing anything, and nothing was merged. Existing safeguards are unchanged. A publication-eligibility requirement is handled only when a specific publication action needs it. Do not start policy research or compliance engineering on this topic.
- **Second operator:** your size-claims gate will sit beside this in `for_publish`. Keep your lines clearly separated; the integrator reconciles them.
- Batch 4 merged so far: READBACK (with L1–L4 fixed), LAUNCHFIX, RESUMEFIX. PHYSFIX, ADOPT and INVENTORY are fixing their review findings.

## Update 2026-10-31T02:35Z: back to the original plan (D-W5-OWNER-RETURN-TO-PLAN, permanent)

- Roadmap: Master Plan, Build 2, Final Master and the P0 workforce, with 24/7 Railway operation that does not depend on Claude sessions.
- The second operator's claims, now in review: P0-CHAIN-DEADENDS, P0-COMPETITOR-EVIDENCE and P0-PERF-LEARNING (54766c9e).
- Still unowned: P0-GALLERY-ASSEMBLY (including a disclosed certificate for photo-led or mixed galleries) and deterministic idle-capacity detection with automatic next-product selection.
