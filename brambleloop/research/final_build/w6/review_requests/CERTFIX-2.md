# CERTFIX-2 — review request

- **Branch:** `certfix/2`, cut from `claude/w6-INTEG8-wip` (511a8c6). **Fix SHA:** `26317fb80907126a6377e966afddeac0514bb007`.
- **Status:** not deployed, and production is unchanged. No PR opened.
- **Interpreter:** Python 3.13 venv built from requirements.lock + requirements-test.lock.

## Cause 1: the research cadence could never reach an approved concept (r5_research_2/3/4, ws2_r5_proposal_writer, ws2_research_m2)
`radar/proposal_writer.POD_CONCEPTS` mapped `kitchen_bath` to a **coaster** (form `coaster`, flat rows).
Bisected to `2ed3294` (ENG-FAMILIES slice one; the parent a35ad30 passes). Since that commit, intake routes every
concept through `construction_families.route`. That route asks `fallback_constructions.plan`, which has always
refused a coaster on the flat path: a coaster "needs a disc worked in joined rounds". So every kitchen-arena
proposal was refused at intake with `construction_unsupported:flat_panel`. This was not caused by `intake_refused`,
benchbuy or demand-led supply.

**Fix (code):** `kitchen_bath` now maps to a **placemat** pair (`flat_panel`). That pair is admitted by the verified
flat_panel family, with its end-to-end proof in `PAIR_PROOFS`, and it has a POOL concept to take bands from. Its
form is still in `GENERIC_FORMS`, so #108 still judges it on its qualifiers. `test_research_flow`'s kitchen-arena
hold now takes its `gate_refused` branch, which the test already allows.

**Tests:**
- `test_ws2_r5_proposal_writer`: the slug and category assertion now names placemat; the reason is cited in the
  test.
- The mapping test is **strengthened**: every mapped pod's proposal must be admitted by `construction_families.route`.
- `test_r5_research_2` takes its fixture band from the mapped category rather than a hard-coded "coaster". This is
  not an assertion.

## Cause 2: the one-product chain fixtures ran the whole catalogue (cert_parity_copy, cert_rebuild_chain, w6_listing_chain_e2e)
Bisected to `2d5f2eb` (ENG-SUPPLY event-driven refill; the parent 0a2af3b passes). D-ENG-DEMAND-SUPPLY Rule 2
restates this design: "capacity refill: `after_chain_job`". When a chain ends, the worker enqueues `supply.admit`.
On a fresh database that pass admits the next Launch-0 product. A fixture that drains "everything" therefore ran up
to 8 products, which caused three failures:
- `other_listing_tags` came out at 40, not 3.
- Readiness read 8 releases' rehearsals, and the divergent-listing test picked another slug's `listing.seo`.
- `_stage` found 8 `cir.draft` jobs.

**Fix:**
- *Code:* `supply.after_chain_job` now records the ending job as the refill's parent in `job_links`
  (`lineage.record`). The refill is caused by that job; without the link it read as a manual enqueue.
- *Tests:* the three chain fixtures drain every registered handler except `supply.admit`, so the refill stays
  pending and the chain stays one product. The comment in each fixture cites ENG-SUPPLY and D-ENG-DEMAND-SUPPLY.
  No assertion was changed. `test_eng_supply` still proves the refill itself.

## Results at 26317fb8 (all rc=0)
| suite | passing | failing |
|---|---|---|
| test_r5_research_2 | 10 | 0 |
| test_r5_research_3 | 7 | 0 |
| test_r5_research_4 | 6 | 0 |
| test_ws2_r5_proposal_writer | 8 | 0 |
| test_ws2_research_m2 | 7 | 0 |
| test_cert_parity_copy | 20 | 0 |
| test_cert_rebuild_chain | 10 | 0 |
| test_w6_listing_chain_e2e | 6 | 0 |
| test_vacuity | 8 | 0 |
| test_w4_resume_runner | 40 | 0 |
| test_eng_supply (touched code) | 17 | 0 |
| test_eng_families (touched route) | 16 | 0 |

## Not fixed here (pre-existing)
`test_research_flow::test_a_never_succeeded_or_failing_source_never_reads_ok` also fails at the unmodified base
511a8c6. It is out of scope. Its kitchen-arena test passes with this change.
