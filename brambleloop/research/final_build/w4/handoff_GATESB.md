# W4-GATESB handoff (business gates)

Branch `claude/w4-GATESB` (worktree .claude/worktrees/W4-GATESB). Latest pushed SHA: `git log -1 origin/claude/w4-GATESB`.
Report: `research/final_build/w4/GATE_CLEARANCE_BUSINESS.{md,json}` (regenerate:
`PYTHONPATH=src python research/final_build/w4/gate_clearance_business.py`).

## Gates -> status -> evidence
| gate | status | evidence |
|---|---|---|
| benchmark_purchases (#163 #165 #168 #315 #317) | OWNER-ACTION: buy 13 listed (CA$280.50 observed, ceiling 300), upload at /ops/teardown | gate_clearance.benchmark_purchase_list; evidence_GATESB/prod_benchmark_selection_13_300_fcb982d.json |
| physical_proof (#64) | NOT-YET-ASKABLE until a tester agrees; kit ready (market-basket-small@1.2.0, ceiling CA$59.65) | quality/tester_kit.py; tester_kit/ PDFs + KIT_MANIFEST.json |
| tester_roster (#9 #43 #250) | OWNER-ACTION: confirm prepared public Ravelry call (not sent) | quality/tester_programme.py; tester_kit/OUTREACH.md |
| second_market_benchmark (#268) | COMPANY-SELECTED (D-W4-GATESB-1): LakesideLoops (CA), HanJanCrochet (UK), verified by getShop inside intel.panel_discovery | intel/second_market.py |
| owned_surfaces (#4 #10 #246 #247 #248 #251 #255) | Etsy shop recognised (paid destination); missing site/pinterest/email/video, CA$25, 65 min | gate_clearance.owned_surfaces_inventory |
| customers | DATA-GATED (buyers), never an owner card | test_w4_gatesb::test_customers_is_data_gated_and_never_an_owner_card |
| ad_authority (#294 #295) | NOT-YET-ASKABLE; ready definition + CONSERVATIVE_CAPS recommendation in code | gate_clearance.ad_readiness |
| live_listings | NOT-YET-ASKABLE: company work (PIPE) first | gate_clearance.live_listing_readiness |

Integrator extras: #242-245 re-parked ad_authority -> customers (DATA); #10/#54/#165 split recorded in
notes (company part named/proven, owner part kept); tests mapped for #254 #263 #37 #14 #16 #9 #51
(+#64 #250 #268); store OA items -> OwnerAction rows (`store_readiness.sync_owner_actions`, called by
the `store.live_drift` handler; batched etsy_account / paid_media).

## Tests run
tests/test_w4_gatesb.py 10/10; regression batch: see final report.

## Wiring requests
- AUTO: `autonomy/status.py` labels every closed gate `kind: owner_gate`; use `closure.kind_of(g)` so
  `customers` reads as a data wait.
- CC: render `approval_inbox()["not_yet_askable"]` (precondition text) beside the owner cards.
- Deploy: production fcb982d still shows customers / second_market as owner cards; fixed on deploy.

## Next
Nothing in progress. After deploy: watch `intel.panel_discovered` audit for `second_market` joins.
