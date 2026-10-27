# Branch and file ownership — read this before writing code

Maintained by the lead operator and release integrator. Last updated 2026-10-27T21:10Z.

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

Contact: hand off through your branch and a handoff document. The integrator reviews, tests and merges only accepted changes.
