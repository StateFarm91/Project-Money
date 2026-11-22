# MC-PERF — Mission Control latency (eng/mc-perf, from claude/w6-release-19i7)

Owner report: "Mission control is so slow. Takes minutes and minutes to load when I click stuff."

## How measured
`brambleloop/tests/mc_perf_harness.py` seeds a production-shaped SQLite DB (`tests/_mc_perf_seed.py`:
`_evidence_seed` + 20k jobs, 30k audit rows, 5k paid_call_records, 8k cost entries, 24 × 1 MB
durable blobs, 3 × 8 MB continuity archives), logs in with a real owner session (passphrase + TOTP)
and GETs all 68 `/api/cc/*` GET routes twice through the test client, counting SQL statements and
outbound network attempts (all refused). `--profile <route>` samples every thread's stack.
Local SQLite, so production (Postgres, per-statement round trip) is slower for high-query routes.

## Root causes found
| Route(s) | Cause |
|---|---|
| `/autonomy`, `/learn` | `rule1.summary` → `generators.provider_candidates` runs every department's `next_work` planner per click (accounting ledger scans, ads readiness, storefront gate, PIL resize): ~16.9k statements. |
| `/company` | Did not finish in >10 min. Aggregates autonomy + approvals inbox + finance summary + storefront gate per click, **and** a background thread in the same process (build2 reachability AST walk, pure CPU) holds the GIL alongside it (F-11). |
| `/money`, `/home`, `/operations`, `/truth` | The finance summary (`accounting.dashboard.summary(refresh=True)`) runs `posting_rules.post_all` — **ledger writes inside a GET**, one flush per row — plus ledger reads: 56k–113k statements per click. |
| `/store`, `/store/catalogue` | storefront gate re-hashes brand image files from disk per click (`visual/canonical.py:_sha`). |
| approvals, approve-all, approve-everything | 589–1122 statements (gate checks across GATES); not cached on purpose (see below). |
| network | No route made an outbound call (net=0 on every route). |

## Fixes in this branch
1. **Page snapshots with visible age** (`app/command_center/page_cache.py`): autonomy, learn,
   company, home, money, operations, truth and store bodies are computed once and served for up to
   60 s. Every such body carries `snapshot: {computed_at, age_s, ttl_s, served_from_snapshot}` —
   never presented as fresh. Single-flight (concurrent cold clicks run one computation). A failure
   is never cached. **Explicit invalidation:** any successful non-GET `/api/cc/` request drops all
   snapshots (ASGI wrapper `RequestsInFlight`); a refused write does not. `BRAMBLELOOP_CC_SNAPSHOT_TTL_S`
   can shorten (or 0 = disable), never lengthen.
2. **Approvals untouched for correctness:** `/approvals`, `/approve-all`, `/approve-everything`
   previews and every POST stay live; each press still re-checks every item at press time; step-up
   auth is unchanged (tested: `test_approvals_and_previews_are_always_live`, `test_eng_approvals` 34/34).
3. **F-11 in-process mitigation:** `RequestsInFlight.count` + `yield_to_requests()`; the build2
   reachability walk (`_visit`, `_rescan_methods`) calls it, sleeping 2 ms every 200 steps while a
   request is in flight (`BRAMBLELOOP_BG_YIELD_S`). Timing only, never results.
   **Measured** (`test_f11_...`): `/api/cc/demand` median idle 26 ms; with 4 CPU-bound background
   threads 2049 ms; with the same threads yielding 572 ms.

## Before / after per route (ms; before = cold/warm on base 19i7; after = repeat click)
Routes under 500 ms before are unchanged and guarded at 500 ms by `tests/test_mc_perf.py`.
"After (repeat)" for snapshotted routes is asserted < 500 ms by the test; the **first** click after
expiry or after an owner action still costs the cold time below (not yet fixed — see Remaining).

| Route | Before cold | Before warm | Statements | After (repeat click) | Change |
|---|---:|---:|---:|---|---|
| `/api/cc/account` | 28 | 12 | 24 | unchanged (< 500) | — |
| `/api/cc/account/sessions` | 7 | 7 | 7 | unchanged (< 500) | — |
| `/api/cc/approvals` | 642 | 418 | 589 | unchanged | — |
| `/api/cc/approvals/x` | 421 | 427 | 589 | unchanged (< 500) | — |
| `/api/cc/approve-all` | 440 | 437 | 590 | unchanged (< 500) | — |
| `/api/cc/approve-everything` | 937 | 782 | 1122 | unchanged | — |
| `/api/cc/autocoder` | 22 | 10 | 9 | unchanged (< 500) | — |
| `/api/cc/autonomy` | 5808 | 4398 | 16915 | < 500 (snapshot, age shown) | snapshot |
| `/api/cc/brief/morning` | 764 | 611 | 679 | unchanged | — |
| `/api/cc/catalogue` | 646 | 11 | 382 | unchanged | — |
| `/api/cc/checks` | 25 | 20 | 23 | unchanged (< 500) | — |
| `/api/cc/completion` | 27 | 25 | 12 | unchanged (< 500) | — |
| `/api/cc/credentials` | 12 | 11 | 8 | unchanged (< 500) | — |
| `/api/cc/customers` | 20 | 16 | 18 | unchanged (< 500) | — |
| `/api/cc/daily` | 187 | 176 | 42 | unchanged (< 500) | — |
| `/api/cc/demand` | 371 | 28 | 11 | unchanged (< 500) | — |
| `/api/cc/drill` | 9 | 8 | 6 | unchanged (< 500) | — |
| `/api/cc/emergency` | 11 | 10 | 12 | unchanged (< 500) | — |
| `/api/cc/etsy` | 20 | 10 | 8 | unchanged (< 500) | — |
| `/api/cc/etsy/registers` | 29 | 11 | 9 | unchanged (< 500) | — |
| `/api/cc/etsy/search-visibility` | 11 | 11 | 17 | unchanged (< 500) | — |
| `/api/cc/experiments` | 30 | 23 | 13 | unchanged (< 500) | — |
| `/api/cc/experiments/runs/1/card` | 14 | 8 | 7 | unchanged (< 500) | — |
| `/api/cc/experiments/runs/1/image` | 8 | 7 | 7 | unchanged (< 500) | — |
| `/api/cc/first-sale` | 491 | 8 | 316 | unchanged (< 500) | — |
| `/api/cc/home` | 28742 | 28765 | 113030 | < 500 (snapshot, age shown) | snapshot |
| `/api/cc/images` | 30 | 16 | 16 | unchanged (< 500) | — |
| `/api/cc/images/candidates/1/image` | 9 | 8 | 8 | unchanged (< 500) | — |
| `/api/cc/images/plans` | 14 | 11 | 6 | unchanged (< 500) | — |
| `/api/cc/images/runs/card` | 8 | 6 | 7 | unchanged (< 500) | — |
| `/api/cc/images/seed-product-00` | 6 | 6 | 6 | unchanged (< 500) | — |
| `/api/cc/insights` | 1788 | 1812 | 512 | unchanged | — |
| `/api/cc/launch-review` | 20 | 13 | 19 | unchanged (< 500) | — |
| `/api/cc/launch/packet` | 2140 | 2221 | 314 | unchanged | — |
| `/api/cc/laura` | 610 | 828 | 688 | unchanged | — |
| `/api/cc/laura-gallery/card` | 14 | 13 | 7 | unchanged (< 500) | — |
| `/api/cc/laura/conversation` | 13 | 12 | 7 | unchanged (< 500) | — |
| `/api/cc/laura/costs` | 20 | 13 | 8 | unchanged (< 500) | — |
| `/api/cc/laura/portrait` | 11 | 10 | 3 | unchanged (< 500) | — |
| `/api/cc/laura/presence` | 43 | 34 | 7 | unchanged (< 500) | — |
| `/api/cc/laura/unified/status` | 55 | 16 | 10 | unchanged (< 500) | — |
| `/api/cc/laura/voice-spec` | 13 | 12 | 6 | unchanged (< 500) | — |
| `/api/cc/learn` | 5895 | 6347 | 16898 | < 500 (snapshot, age shown) | snapshot |
| `/api/cc/mission` | 1329 | 964 | 804 | unchanged | — |
| `/api/cc/money` | 28164 | 21126 | 56075 | < 500 (snapshot, age shown) | snapshot |
| `/api/cc/money/drill` | 14 | 6 | 6 | unchanged (< 500) | — |
| `/api/cc/notifications` | 492 | 545 | 974 | unchanged | — |
| `/api/cc/operating-evidence` | 168 | 151 | 55 | unchanged (< 500) | — |
| `/api/cc/operations` | 24151 | 18363 | 57052 | < 500 (snapshot, age shown) | snapshot |
| `/api/cc/operations/drill` | 15 | 8 | 6 | unchanged (< 500) | — |
| `/api/cc/operations/recovery` | 15 | 12 | 7 | unchanged (< 500) | — |
| `/api/cc/operations/soak` | 8 | 7 | 6 | unchanged (< 500) | — |
| `/api/cc/p0-board` | 228 | 196 | 360 | unchanged (< 500) | — |
| `/api/cc/paid-providers` | 24 | 20 | 56 | unchanged (< 500) | — |
| `/api/cc/policy/readings` | 17 | 8 | 9 | unchanged (< 500) | — |
| `/api/cc/private/status` | 9 | 8 | 10 | unchanged (< 500) | — |
| `/api/cc/production` | 849 | 7 | 386 | unchanged | — |
| `/api/cc/store` | 12972 | 13400 | 2155 | < 500 (snapshot, age shown) | snapshot |
| `/api/cc/store/catalogue` | 4043 | 4024 | 12 | unchanged | — |
| `/api/cc/store/image/1` | 24 | 25 | 6 | unchanged (< 500) | — |
| `/api/cc/store/pdf/seed-product-00` | 30 | 34 | 6 | unchanged (< 500) | — |
| `/api/cc/store/settings` | 29 | 28 | 20 | unchanged (< 500) | — |
| `/api/cc/timeline` | 122 | 74 | 20 | unchanged (< 500) | — |
| `/api/cc/truth` | 21758 | 16368 | 56652 | < 500 (snapshot, age shown) | snapshot |
| `/api/cc/visual/evidence/seed-product-00` | 24 | 10 | 10 | unchanged (< 500) | — |
| `/api/cc/visual/studio` | 75 | 69 | 17 | unchanged (< 500) | — |
| `/api/cc/wardrobe` | 9 | 8 | 7 | unchanged (< 500) | — |
| `/api/cc/company` | > 600000 (did not finish) | — | — | < 500 (snapshot, age shown) | snapshot + F-11 yield |

## Remaining (not fixed here, honest)
- **First click is still slow** on autonomy/learn (~6 s), money/home/operations/truth (20–29 s) and
  store (13 s) on this seed. The proper fix is to stop the finance summary posting ledger rows inside
  a GET (call it with `refresh=False` and show the unposted count; the autonomy loop already queues
  `finance:post_rows`), batch `post_all`, and precompute the rule1 candidate list in a worker job.
  Those change finance semantics and need their own tests; not attempted in this 75-minute lane.
- A background pre-warmer that refreshes snapshots before they expire (so no owner click ever pays
  the cold cost) is the next step; the snapshot layer is built for it.
- The real F-11 remedy (separate worker service) remains an OWNER ACTION per AUDIT-REPORT F-11.
- After-fix cold timings were not re-measured with the full harness for every route (time box);
  the after column is what `tests/test_mc_perf.py` asserts.

## Tests
`JOBS=4 SUITE_REGISTRY=0 SUITES="tests/test_mc_perf.py tests/test_vacuity.py tests/test_eng_approvals.py
tests/test_mission.py tests/test_mission_control2.py tests/test_cert_dashboard.py tests/test_dashboard_spend.py
tests/test_rc1_own_dashboard.py tests/test_w4_c12_dashboard_registers.py tests/test_w4_fmbatch1_dashboard.py"
bash run_tests.sh` → TOTAL PASSING: 118; suites failing: 0 (run record 20261122T063115Z-2072).
