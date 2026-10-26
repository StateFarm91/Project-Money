# Independent security & integrity review — W4-PRODFIX

- Reviewer: independent (did not write the code). Review only: nothing fixed, no PR opened.
- Scope: `git diff 051dbee2..origin/claude/w4-PRODFIX -- brambleloop/src brambleloop/tests`
  (two commits). Base `051dbee2` is current production.
  - `7967711`: the deadlock and repeat-paid-request fix (claims 1–4).
  - `cbb0177`: the owner Command Center action that records a platform-policy change review.
    It landed while this review was in progress and is included (findings F8–F9).
- Rules followed: no production calls, no secrets, no deploys. venv built from
  `brambleloop/requirements.lock`. **`requirements-test.lock` does not exist in the repo**, and
  `pytest` is not in `requirements.lock`. Suites were run as scripts (`python tests/<suite>.py`,
  the repo's own convention) under `nice -n 19`.

## Verdict

| Question | Answer |
|---|---|
| **Ship with SHADOW on?** | **Yes, it is safe to ship.** No path lets anything publish, certify or skip a gate, and no paid path loses its budget ceiling. **It does not do what claim 2 says** (F1): on the production estate the daily retry is a no-op, so the deadlock stays unbroken until F1 is fixed. |
| Can the waiver let anything publish, certify or skip a gate? | **No.** It changes only `outstanding_only_marketing`, which only `marketing.schedule` reads, and only when it is a `rebuild` run. That handler drafts `ContentPiece` rows and records marketing lineage. It publishes nothing and enqueues nothing. `halted`, `blocks` and `reasons` (what publication reads) are unchanged. |
| Can a real integrity problem be masked as "stale-artefact only"? | **Not through this diff's logic.** Any open `authority_chain_tamper:*` row (store activation, publication authority, the Etsy ledger mapping), or any second widespread family, turns the waiver off. Caveats: the integrity family list has one entry (F4), there is a small read-time race (F5), and the prefix match is wider than the one signature it means (F3). |
| Rebuild storm / unbounded jobs / extra paid calls from the retry? | **No storm.** At most one retry per product per UTC day, and none while any `chain.rebuild` for the product is pending, running or failed-retrying. Each retry is 1 `chain.rebuild` plus ≤3 verify jobs, all unpaid. Because the stage key is deduplicated (F1), a retry currently buys no paid stage work at all. There is a full-table scan per product per run (F6). |
| Budget ceilings on every paid path? | **Yes.** No paid path was added. Vision still goes through `gw.check_budget` (per-agent daily and monthly ceilings) on every call. Probe reuse only removes calls. Any stage a retry did enqueue would go through that stage's existing gates. |
| Gallery give-up loses data / suppresses a legitimate retry? | **Not after a transient provider error.** `PermanentError` and `TransientError` still take the counted path (3 tries). The immediate give-up fires only on `AnalysisRefused` *after a paid answer*. Two edge cases now cost the image on the first attempt (F2). |
| Owner policy-review action: owner session + step-up only, audited, no replay? | **Yes.** The action is reachable only at `POST /api/cc/actions/policy.review`. That path goes through `auth.gate`, which requires an owner session, same-origin, the CSRF token and a nonce/timestamp. `policy.review` is marked `requires_step_up=True`, so the route calls `auth.require_stepup`. Nothing grants it to the operator bearer: `/api/cc/*` takes the owner-session branch of `operator_gate`. No public route, worker handler or CLI calls `approvals.execute` or `review_change`. Each success writes two audit rows, `policy.change_reviewed` (with the full `shown` content, its digest, the session and the tested text) and `cc.owner_action.policy.review`; refusals are audited through `auth.refuse`. Replay is refused with `ActionNotFound` (404), because the change is no longer unreviewed, and `review_change` also refuses a row that is already reviewed. A stale preview (wrong `expected_digest`) is refused. Two low and info-level points: F8, F9. |
| Was any test weakened? | **No.** The diff only adds `tests/test_w4_prodfix.py` and `tests/test_w4_prodfix_policy_review.py`. No existing test line was removed or changed. The new tests are too narrow to catch F1 (F7). |

## Findings (most severe first)

### F1 — HIGH (functional; not a safety risk) — the daily retry cannot rebuild anything for an unchanged stale set

- **Location:** `src/brambleloop/ops/rebuild_graph.py:enqueue` (the `DuplicateJob` retry
  branch), interacting with `src/brambleloop/runtime/release.py:_targeted_rebuild` (the stage
  `token` and the `chain_key(..., token)` idempotency keys, about lines 4697-4743).
- **Scenario:** the retry job carries the same `artefacts` and `fingerprints` as the attempt it
  retries (`{**payload, "retry_of_key": key}`). `_targeted_rebuild` derives
  `token = sha256({artefacts, fingerprints})[:12]`, so the token is identical. The stage enqueue
  (`chain_key("price", slug, version, release, token)`, or `assets`/`rebuild-cert`) hits the
  first attempt's key and `ctx.enqueue` swallows the `DuplicateJob`, which leaves
  `stage_job=None`. The verify pass binds completion to `requested_by` (the retry job), and no
  job after it writes the rows. After three verifies the product's `rebuild-incomplete` incident
  gets `report_count += 1`. This repeats daily and nothing is rebuilt. That is exactly
  production's case: the same 299 stale artefacts, and `marketing.schedule` previously refused
  under the same token.
- **Reproduced locally** on the real chain, reusing the `tests/test_cert_rebuild_chain.py`
  harness (`chain()`, `_run`). The script is below.

  ```python
  import test_cert_rebuild_chain as t   # run with tests/ on sys.path
  st = t.chain(); db, slug = st["db"], st["slug"]
  # make one marketing_asset row stale (cir:<slug> -> "0"*16), keep its current fp as `new`
  payload = {"product_slug": slug, "artefacts": [node], "reason": "sentinel",
             "fingerprints": {f"cir:{slug}": {"old": "0"*16, "new": new}}}
  first = t._run(db, "listing", "chain.rebuild", payload, "rebuild:product:orig")
  # deadlock: downstream refused, row still stale (re-staled, pending jobs cancelled)
  retry = t._run(db, "listing", "chain.rebuild",
                 {**payload, "retry_of_key": "rebuild:product:orig"},
                 "rebuild:product:orig:retry:2026-10-27")
  ```

  Output: `first attempt stage_job: 15 pricing.position` and then
  `retry attempt stage_job: None pricing.position requested: ['marketing_asset:cloudline-baby-blanket:article:…']`.
  The retry enqueues no stage, and the artefact is still requested.
- **Consequence:** claim 2 holds only in form (a job is enqueued once a day). Claim 1's waiver
  never runs, because nothing new reaches `marketing.schedule`. The deadlock persists after
  deploy. Rebuild-incomplete noise grows by one report per product per day.
- **Fix:** make the stage token attempt-specific for retries. For example, include
  `retry_of_key` plus the retry key (or the retrying job id) in the `token` hash in
  `_targeted_rebuild`. Every downstream `chain_key` then moves once per retry, and the
  one-per-day bound still caps it. Add an end-to-end test on the real chain: the attempt is
  refused, then the retry produces a new `pricing.position` job id and a bound
  `chain.rebuild_completed`.

### F2 — LOW — the immediate give-up also fires on refusals that are not "the model's answer was unusable"

- **Location:** `src/brambleloop/intel/vision.py:analyse` (`except AnalysisRefused` → `_mark_failed(..., give_up=True)`), `record()`.
- **Scenario:**
  - (a) `record()` raises `AnalysisRefused` when `access.available("model_provider", env)` is
    false. That is a configuration or env-visibility condition, not a property of the answer. If
    it happens after a paid call, every image in the batch is now given up permanently on its
    first attempt. Before this change each image had 3 tries.
  - (b) A response truncated at `ANALYSIS_MAX_TOKENS`, or malformed once (the model is not
    deterministic), is given up at once, although a retry might have succeeded.
  - There is no reset path for `gallery_ranks_failed` anywhere outside `vision.py`, so a
    give-up is permanent even across a `method_version()` change.
- **Data loss:** the paid response text is discarded except `str(exc)[:200]` in `failures`.
  That was also true before. The new part is that the image is not re-asked.
- **Not affected:** transient and permanent provider errors keep their 3 counted attempts. The
  breaker in `finance.systematic` still stops paying for a method that never parses.
- **Fix:** give up immediately only for parse and vocabulary refusals (`parse_observation`,
  `check_observation`). Check `access.available` *before* the paid call and stop the run, not
  the image. Optionally key `gallery_ranks_failed` by `method_version()` so a parser fix
  re-opens the images.

### F3 — LOW — the waiver matches the `systemic-halt:` prefix, not the one signature its evidence describes

- **Location:** `src/brambleloop/publish/release_gates.py:staleness`
  (`str(i.signature).startswith("systemic-halt:")`).
- **Scenario:** today only `SYSTEMIC_SIGNATURE = "systemic-halt:publication"` exists. The
  evidence check (`systemic_evidence`) describes that row only. If a future
  `systemic-halt:<other>` row is added with different evidence, a staleness-only reading of the
  publication evidence would waive it too.
- **Fix:** compare `i.signature == incident_lifecycle.SYSTEMIC_SIGNATURE`.

### F4 — LOW — "integrity failure" means one family; other corruption families are only caught if they are widespread

- **Location:** `src/brambleloop/ops/incident_lifecycle.py:INTEGRITY_FAMILIES = ("authority_chain_tamper",)`,
  used by `_systemic_halt_is_staleness_only`.
- **Scenario:** suppose a non-stale, non-tamper halting family is open on 1–2 products (below
  `SYSTEMIC_MIN_SLUGS`). The waiver still applies for *other* products' marketing rebuilds.
  The affected product's own incident still blocks that product, because `halting_other`
  includes it. So nothing is masked for the product that is actually affected. A data change
  made outside the authority chain (for example a direct DB edit of a CIR) shows up as
  `stale-artefact`, not as tamper. A marketing rebuild would then re-derive drafts from that
  release and record "passed" lineage. Only drafts are affected (nothing publishes), and this
  is the same as R4's pre-existing per-product behaviour.
- **Fix:** none required for SHADOW. Before LIMITED PRODUCTION, review whether any
  checksum/ledger/manifest mismatch family should join `INTEGRITY_FAMILIES`.

### F5 — INFO — the evidence and the incident list are read in different sessions

- **Location:** `release_gates.staleness`. `_systemic_halt_is_staleness_only` opens its own
  session, then `tracker.open_incidents` is read again.
- **Scenario:** a tamper incident on another product is opened between the two reads, so the
  waiver applies to a marketing *draft* rebuild once. On the next read the evidence includes
  the tamper and the waiver turns off. Only drafts are affected, so the impact is negligible.
  The evidence is computed live, not from the halt row's stored detail. That is the safer
  choice: a halt opened for tamper never inherits a stale "staleness only" label.
- **Fix:** optional. Compute both from one session.

### F6 — INFO — `_retry_key` loads every `chain.rebuild` job, once per duplicate product per sentinel run

- **Location:** `src/brambleloop/ops/rebuild_graph.py:_retry_key`.
- **Scenario:** no SQL filter on product. Every row's `inputs` is deserialised in Python. With
  verify jobs (×4 per attempt) this grows without bound. The hourly sentinel does
  O(products × all chain.rebuild jobs) work. No money is spent, but it costs lock-holding time
  on SQLite and Postgres.
- **Fix:** filter on `status` / a JSON path, or keep the newest end time per product.

### F7 — INFO — test coverage gaps (no weakening)

- `test_a_rebuild_that_ended_without_delivering_is_asked_for_again_once_a_day` stubs
  `rebuild_set` and stops at "a job was enqueued". It never runs the retry through
  `_targeted_rebuild`, which is why F1 passes CI.
- `test_a_paid_unusable_observation_gives_the_image_up_at_once` calls `_mark_failed` directly.
  It does not drive `analyse()`, so it does not test the classification that decides between
  paid-unusable (give up) and provider error (retry).
- Probe reuse: `images.usable()` still reads only the newest row and never its age (this is
  pre-existing). With reuse, a revoked image credential keeps the `image_generation` condition
  open for up to about 24 h + 6 h (the sweep period), where before it was up to about 6 h.
  Every render path still fails closed at the provider and is budget-gated. The
  `ops.capability_probes` audit does not record `reused`, so the audit can't tell a reused
  result from a fresh probe.

### F8 — LOW — the policy review checks the digest against one snapshot but marks whichever snapshot is newest when it writes

- **Location:** `src/brambleloop/app/command_center/approvals.py:_review_policy_change` →
  `gates/platform_policy.py:review_change`.
- **Scenario:** `_review_policy_change` computes `shown` (and checks `expected_digest`) for
  `unreviewed_changes()[source]["snapshot_id"]`. It then calls
  `review_change(db, source, ...)`, which reviews *the newest material change of `source`*,
  looked up again in a separate session. `ops.policy_watch` or `record_page_reading` could
  insert a newer material snapshot between the digest check and the write. The owner's review
  would then be recorded against text they were never shown. The audit row would also name the
  old `snapshot_id`, which does not match the row actually marked. The window is milliseconds,
  and the next owner preview would show the discrepancy, but this is exactly the binding the
  digest exists to guarantee.
- **Fix:** pass `snapshot_id=shown["snapshot_id"]` to `review_change`. Refuse there unless that
  row is still the newest unreviewed material change, and do the check and the write in one
  session.

### F9 — INFO — the confirmation phrase is case-insensitive although the code calls it "verbatim"

- **Location:** `approvals.py`. `POLICY_REVIEW_CONFIRMATION` is documented as "The words the
  owner confirms, verbatim", but the check is `confirmed.lower() != ...`.
- **Reproduced:** `confirm: "REVIEWED AND TESTED"` was accepted. There is no security impact,
  because step-up and the digest are the real controls. Either drop `.lower()` or fix the
  comment.
- `reviewed_by` is hard-coded to `"owner:command-center"`. The session id is recorded only in
  the audit row, not on the snapshot. That is acceptable, since the audit row is the record.

## Claims checked

| Claim | Verdict |
|---|---|
| 1. Staleness-only systemic halt waived only for the marketing rebuild; publication still sees it; tamper still refuses | **Holds** (F3–F5 are hardening) |
| 2. Sentinel re-requests `chain.rebuild` once per UTC day when the last attempt is terminal and ≥ 12 h old | **Enqueue holds; the rebuild does not happen** (F1) |
| 3. Paid unusable gallery answer gives the image up at once | **Holds; too broad** (F2) |
| 4. `probe_if_due` reuses a successful probe < 24 h old | **Holds.** A failed probe, a missing `at` or a malformed `at` re-probes. |
| 5. (`cbb0177`) The owner can record a policy review from the Command Center, step-up only | **Holds** (F8, F9) |

## Test runs (this review, `nice -n 19`, scripts, venv from `requirements.lock`)

Code under test is `7967711`. The `cbb0177` change touches only `app/command_center/approvals.py`
plus its new test, and `test_w4_prodfix.py` was re-run on `cbb0177`.

| Suite | Result |
|---|---|
| `test_w4_prodfix` (on `7967711` and on `cbb0177`) | PASS, 5/5 |
| `test_cert_rebuild_chain` | PASS |
| `test_cert_thrash` | PASS |
| `test_executor` | PASS |
| `test_intel` | PASS |
| `test_rc1_spend` | PASS |
| `test_w3_k7_ops_truth` | PASS |
| `test_w4_close5_vision_timeout` | PASS |
| `test_w4_fmgate_rebuild_key` | PASS |
| `test_w4_gatesi` | PASS |
| `test_w4_listready` | PASS |
| `test_compiler` | PASS |
| `test_reverse` | PASS |
| `test_twin` | PASS |
| `test_w4_b2gates` | 11 passed, 1 failed (`test_tester_agreement_route_opens_the_gate_only_with_consent`): *environment* |
| `test_w4_laurafix_truncation` | aborted at import: *environment*, **did not run** |
| `test_w4_ondemand` | aborted at import: *environment*, **did not run** |
| `test_w4_prodfix_policy_review` (new in `cbb0177`) | aborted at import: *environment*, **did not run** |

**Environment cause:** `starlette==1.6.0` (from `requirements.lock`) needs the `httpx2` package
for `TestClient`, and nothing in the repo pins it, because `requirements-test.lock` is absent. The
three earlier failures reproduce **identically on base `051dbee2`**, so they are not caused by
PRODFIX. No package outside the lock was installed.

**Policy review not covered by the HTTP tests:** since `test_w4_prodfix_policy_review` could not
run, the route-level claims (no session refused, bearer only refused, no step-up refused) were
verified by reading `security.operator_gate`, `auth.gate` and `auth.require_stepup`. The
approvals layer was exercised directly with an in-memory DB:

- wrong `expected_digest` → `ActionRefused`
- empty `tested` → `ActionRefused`
- uppercase confirm → accepted (F9)
- replay of the same body → `ActionNotFound`
- audit rows written: `policy.change_reviewed` and `cc.owner_action.policy.review`

**Before merging:** add `httpx2` to a committed test lock and run
`test_w4_prodfix_policy_review`, `test_w4_ondemand` and `test_w4_laurafix_truncation` for real.
