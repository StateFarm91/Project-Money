# Independent security and integrity review: INTEG7 combined candidate at 24ada53

- **Reviewed:** `git diff 967502d..24ada53 -- brambleloop/src brambleloop/tests ops brambleloop/requirements*.lock`
  on `claude/w4-INTEG7`. That is 14 commits: the R-1/R-6 test fixes (661957a), PRODFIX through
  86fe2b5, SECPATCH2 1c94f7c, the FMBATCH2 cherry-picks (c26439f, c1cd0bf), the test-lock note
  (8dc0b78), the SECPATCH deploy-record merge and 24ada53. `ops/` is unchanged in the range.
- **Read first:**
  - `INDEPENDENT_SECREVIEW_INTEG7_967502d.md` (R-1..R-7), from `claude/w4-SECREVIEW-INTEG7-967502d`;
  - `INDEPENDENT_SECREVIEW_PRODFIX.md` (F1..F9), from `claude/w4-SECREVIEW-PRODFIX`;
  - `INDEPENDENT_SECREVIEW_SECPATCH_4ff953d.md` (F1..F9), from `claude/w4-SECREVIEW-SECPATCH-4ff953d`;
  - `INTEG7.md` §6 addendum and §9, and `PRODFIX.md`.
- **Reviewer:** an independent Claude Code context that did not write this code. Review only:
  nothing was fixed. No production calls, no secrets, no deploys. The probes ran offline (socket
  connect patched to refuse) against throwaway SQLite databases.
- **Environment:** a venv built from `brambleloop/requirements.lock` plus
  `requirements-test.lock` (it installed cleanly, and the HTTP suites run on it). Every suite ran
  at `nice -n 19`, one at a time.
- **Date:** 2026-10-26 (UTC).

## Verdict

| Question | Answer |
|---|---|
| **Can 24ada53 ship as Batch 2+3 with SHADOW on and every switch OFF?** | **Yes, from a security and integrity standpoint.** No blocking finding. One Low (S-1, a repeat paid vision call that F1's fix makes reachable) should be fixed before the `image_vision` gate is relied on in production, and it does not stop a SHADOW ship. **Certification still needs the full `run_tests.sh`** (INTEG7.md §10 is "pending"). This review ran the focused set (see "Tests run"), not the full suite. |
| 1. R-1 and R-6 closed, nothing weakened? 503 sound? | **Closed, and stricter.** `PUBLIC_GET_ROUTES` and `PUBLIC_PROJECTIONS` are byte-identical to 967502d. Each of the 9 FMBATCH1 suites now asserts the anonymous refusal (or the projected key set) and reads the operator view with the credential. `test_cert_dashboard` restores the token, `test_swarm_runtime`'s band map is filled, and R-6 has a real ASGI-level end-to-end scrub test. **Accepting 503 is sound for these routes:** the gate answers 503 only when no operator token is configured, which fails closed. None of `/m`, `/api/useful-work` or `/api/company/departments` can return 503 from its handler, so a 503 there can only be the gate. If one of them were made public, the anonymous call would return 200 and the test would fail. `test_w4_fmbatch1_route_audit` also pins **401**, `requires_operator` and "not in `PUBLIC_GET_ROUTES`" for all six formerly public routes. Residual: see S-4. |
| 2. PRODFIX F1 really fixed? Storm or new paid calls? | **Fixed:** the retry rebuilds end to end. On the real chain, a refused attempt followed by a retry produces a new `pricing.position` job, then `listing.seo`, `launch.plan` and `marketing.schedule`, with bound `chain.rebuild_completed`. A re-run of the same retry is idempotent. **No storm:** at most one retry per product per UTC day, and none while any `chain.rebuild` for that product is in flight or ended in the last 12 h. One retry is about 9 jobs. **One new paid path does exist (S-1):** every retry re-drives `listing.seo`, which re-buys the exported-frame vision review with no reuse check while `image_vision` is open. It is budget-ceilinged, but it is the repeat-paid-request class that PRODFIX set out to stop. |
| 3. Can policy review be reached other than by owner session plus step-up? | **No.** `approvals.execute` has exactly one caller, `POST /api/cc/actions/{action}` (api.py:798-816). `/api/cc/*` is behind the owner-session gate (session, same-origin, CSRF, nonce). `ACTIONS["policy.review"][0] is True`, so `require_stepup` runs before `execute`. `review_change` has no other caller. Nothing else writes `reviewed_at` on a `PolicySnapshot`. Probe: anonymous, operator bearer and forged cookie+CSRF all got **401** on `policy.review` and `policy.review_preview`, and the seeded change stayed unreviewed. F8 (snapshot binding in one session) and F9 (exact phrase) are fixed. |
| 4. SECPATCH2 correct? Readback or CC broken? | **Correct.** The projection and the owner-scrub exemption key on `starlette.routing.get_route_path`, which is the path the router matches. Probe: with `root_path` set to `/x`, `/api` or `/x/y`, every projected route returned only its projected keys. A path that does not start with `root_path` is projected too. Duplicate `Authorization` headers get **400** before any layer runs, in either order and on every probed route, `/health` and `/api/cc/auth/status` included. **Nothing breaks:** `ops/readback.py`, `deployed_sha.py` and `verify_deploy.py` send no `Authorization` header, and the CC authenticates by cookie. There are no websocket routes, so the http-only check misses nothing. Minor points: S-5. |
| 5. `executive_plan` `now` change correct and bounded? | **Correct and bounded.** The only production caller (`swarm.allocate` → `allocate(ctx.db)`) passes `now=None`, so the behaviour is the wall clock, as before. A naive `now` raises `TypeError`, which is caught: no boost, the safe direction. The boost is `granted + 1` and is then clamped by `min(granted, affordable)` and the #31 unproductive cap, so it can never exceed the lane's budget. It confers no authority. |
| 6. Public exposure (anonymous sweep re-run)? | **None.** The sweep sent 6,034 requests: every route (API, routers and Starlette routes), each of GET/HEAD/POST/PUT/PATCH/DELETE/OPTIONS, with three path fills, token unset and token set. Seeded sentinels covered owner-action title, reason and consequence; incident text and signature; job type and error; unpublished slug and title; **an unreviewed policy change's summary and URL** (new in this range); a customer ref; and a support question and answer. Result: **BAD 0**, meaning no sentinel in any body and no unexpected 2xx. **Non-vacuous:** with the credential, all 14 seeded kinds were found on some GET route. |
| 7. Safety defaults OFF? New outward or paid path? | **All OFF** (runtime check, empty env): taxonomy requeue False, research fetch False, storefront kill switch refusing, signing refusing. Auto-rollback is unchanged (`ops/` is not in the diff), and so is Laura. **No new outward path.** The retry re-enqueues `store.publish` daily for a product that stays stale, but SHADOW refuses it ("capability not enabled", a deliberate refusal that does not turn `/api/verify` red). **One new recurring paid call:** S-1. Probe reuse and the gallery give-up both remove paid calls. |

### Findings

| # | Severity | Area | Short title |
|---|---|---|---|
| S-1 | **Low** | PRODFIX F1 fix × DISCLOSEDQA | Every daily retry re-runs `listing.seo`, which re-buys the exported-frame vision review with no reuse check |
| S-2 | Info | PRODFIX F1 fix | A product whose marketing stays refused (for example, an unreviewed policy change) retries forever, once a day, about 9 jobs plus one dead-lettered `store.publish` each time; all products retry in the same sentinel run |
| S-3 | Info | R-2 follow-up | R-2 is fixed at every entry point, but the generalised "every `Worker(` constructor marks the job process" guard was not added |
| S-4 | Info | R-1 test edits | Three anonymous assertions accept 503 without checking that the refusal came from the gate; this is sound today and fragile only against a future handler 503 |
| S-5 | Info | SECPATCH2 | The 400 for duplicate `Authorization` is sent outside `SecurityHeadersMiddleware` and carries no security headers |
| S-6 | Info | PRODFIX policy review | The inbox card pre-fills the exact confirmation phrase, so "verbatim" confirms nothing on its own (step-up and the digest are the real controls) |
| carried | Info | R-3, R-4 (cache headers), R-5, R-7 | Recorded in INTEG7.md §9 and unchanged. R-4's raw-path half is **closed** by SECPATCH2 |
| carried | Low | FMBATCH1 N-2, AGENTS L-1 | Unchanged; not reachable in SHADOW |
| carried | Low | PRODFIX F4 | One integrity family (`authority_chain_tamper`); accepted for SHADOW; review before LIMITED PRODUCTION |

---

## 1. R-1 and R-6

**What changed (661957a, plus 24ada53's follow-ups):**

- **`test_w4_fmbatch1_route_audit`:** `PUBLIC` became `NOW_OPERATOR`. Each of the six routes
  (`/api/finance`, `/api/useful-work`, `/api/company/departments`, `/api/spend-report`,
  `/api/owned`, `/m`) is checked four ways:
  - `requires_operator` is true;
  - it is not in `PUBLIC_GET_ROUTES`;
  - an anonymous request gets **401**, with `FORBIDDEN` absent from the body;
  - the operator gets 200.

  `_public_get_paths()` now walks `iter_api_routes` (routers included). The vacuous
  `len(paths) > 20` became `set(paths) <= PUBLIC_GET_ROUTES`. This is exactly the fix R-1
  recommended.
- **`_mobile`, `_useful_work`, `_learn_card`, `_dashboard`, `_seasonal_cohort`, `_theme`:** each
  adds an anonymous assertion (no `<table>`, no card text, or refused) before reading through
  `_opread`. **Stricter.**
- **`_provider_health`:** the anonymous `/api/verify` is asserted to be `⊆ {ok, checks}` and to
  carry no secret. `/api/verify/smoke` is read as operator. **Stricter.**
- **`test_cert_dashboard`:** the token is restored rather than popped. The suite passes 19/19 in
  one process.
- **`test_swarm_runtime`:** 11 AGENTS job types were given deliberate bands, all non-paid. That is
  a production change to `swarm/orchestrate.JOB_BANDS`, and it is priority only.
- **`test_customer_data_auth`:** new
  `test_the_customer_scrub_redacts_a_live_public_response_end_to_end` drives
  `CustomerRefScrubMiddleware` over a raw ASGI app. It asserts both that the anonymous body is
  redacted and still valid JSON, and that the operator sees the row. **R-6 closed.**
- **`test_w3_hq_independence`:** three allowances (`research_agent`'s `research/`,
  `research.py`'s `BUILD_STATE.md` and `DECISION_LOG.md`). Each one names a test proving the
  file is optional at runtime. This is not a security property.
- **`git diff 967502d..24ada53 -- app/security.py`** touches only SECPATCH2 helpers.
  `PUBLIC_GET_ROUTES`, `PUBLIC_GET_NOTES` and `PUBLIC_PROJECTIONS` are unchanged.

**The 503 question.** `security.operator_gate` returns 503 only when the operator token is not
configured (`OpsAuthUnavailable`) or the CC auth module is missing. Both fail closed. The suites
that accept `(401, 503)` (`_mobile` for `/m`, `_useful_work` for `/api/useful-work` and
`/api/company/departments`) run without the token in the environment, so the gate answers 503.

None of those three handlers returns 503: they return only 200 or 404, and an unhandled error is
500. So:

- the only source of a 503 on them is the gate;
- if a route were added to `PUBLIC_GET_ROUTES`, the anonymous call would reach the handler and
  return 200, and the assertion would fail.

A 503 cannot hide an open route here. In addition, `route_audit` pins 401 with the token set.
See S-4 for the residual brittleness.

## 2. PRODFIX F1 and the retry

**The fix.** `rebuild_graph.enqueue` adds `retry` (its own daily key,
`<key>:retry:<YYYY-MM-DD>`) to the retry payload. `_targeted_rebuild` folds `retry` into the
stage token, so every downstream `chain_key` moves for that retry: `price`, `seo`, `launch`,
`content`, `publish`.

**Reproduced on the real chain** (reviewer probe on the `test_cert_rebuild_chain` harness, with
the marketing row re-staled before each retry to simulate a product that stays refused):

```
2026-10-27 stage_job 18  jobs: chain.rebuild, pricing.position, chain.rebuild(verify), listing.seo,
                               launch.plan, marketing.schedule, store.publish(dead)
2026-10-28 stage_job 25  (same nine)
2026-10-29 stage_job 32  (same nine)
store.publish …dead "capability not enabled: … SHADOW mode … Draft retained for review."
```

When the retry cures the row, the next day's retry finds nothing stale and enqueues no stage, so
the loop stops itself. `test_w4_prodfix_review` passes.

**Bounds:**

- `_retry_key` returns a key only when no `chain.rebuild` for the product is PENDING, RUNNING or
  FAILED-retrying, and none finished (or, unfinished, was created) in the last 12 h. Verify jobs
  are `chain.rebuild` jobs too, so a running verify cycle holds the retry off.
- The date in the key caps it at one per UTC day.
- `_recent_rebuild_slugs` is one bounded query per sentinel run (F6 fixed).

**Paid calls:**

- pricing, launch and the marketing content are deterministic.
- `assets.build` runs only when no build exists. Its hero review is reused while the CIR
  fingerprint is unchanged.
- **`listing.seo` is not free** (S-1).

**The waiver** (`_halting_other_than_staleness`):

- It now compares `== SYSTEMIC_SIGNATURE` (F3), and it reads the evidence and the rows in one
  session (F5).
- Its row selection is the same as `IncidentTracker.open_incidents(slug)`: the product's own rows
  plus halting `systemic-halt:%` rows. So no company-wide halting row that the old path saw is
  dropped.
- `halted`, `reasons` and `blocks` are unchanged, so publication still sees the halt.
- Unreadable evidence never waives.

**Gallery and probes:**

- **Gallery (F2):** only a `parse_observation` refusal gives up at once. A `record()` refusal
  keeps its counted retries.
- **Probe reuse:** this only removes calls. A failed, missing or unparseable `at` re-probes. The
  audit now records `reused` and `probe_at` (F7).

## 3. Policy review

- **Single route:** `POST /api/cc/actions/{action}`. It refuses unknown actions with 404, runs
  `require_stepup` when `ACTIONS[action][0]` is set (it is for `policy.review`), then calls
  `execute`.
- **No other way in:** no worker handler, Laura path, CLI or public route imports `execute` or
  `review_change`. The Laura modules read `ACTIONS` only.
- **Preview:** `policy.review_preview` (no step-up) is a read of the change for the owner session.
  It returns policy text and nothing owner-private beyond it.
- **Binding:**
  - `expected_digest` must equal the digest of exactly what the preview showed.
  - `review_change(snapshot_id=…)` refuses inside its own session if a newer material change has
    arrived. That is mapped to "approval preview changed".
  - Replay gives `ActionNotFound`, because nothing is left unreviewed.
- **Audit:** `policy.change_reviewed` (with the full `shown`, the digest, the session and the
  tested text), plus `cc.owner_action.policy.review`.
- **Probe:** see the verdict table. `test_w4_prodfix_policy_review` covers the session, bearer and
  step-up refusals over HTTP and passes on this venv. The PRODFIX review could not run it.

## 4. SECPATCH2

- **`route_path(scope)`:** `get_route_path` falls back to the raw path only on a malformed scope.
  A malformed scope does not route, either.
- **Owner-scrub exemption:** this is now keyed on the routed path too. Under a root path,
  `/x/api/cc/...` is exempt from the scrub, as `/api/cc/...` already was. Both sit behind the
  owner-session gate, so nothing new is exposed.
- **`SingleAuthorizationMiddleware`:** this is the outermost layer. It counts header names case-
  insensitively, refuses with 400, and runs before the gate and every scrub. `scope_authorization`
  also returns `None` on more than one header, as defence in depth.
- **Readback and CC:** both unaffected (verdict row 4). `test_w4_secpatch2` and
  `test_w4_secpatch_public_surface` (including `test_deploy_readback_still_reads_every_field`)
  pass.

## 5. Other production changes

- **`hq_worker._mark_job_process()`:** this runs first in `main()`. Only `ImportError` is
  swallowed; any other error aborts `main`, which fails closed. Together with
  `runner.start:380` and `worker_entry`, all three `Worker(` entry points now mark themselves.
  **R-2 closed** (S-3).
- **`executive_plan.priority_agents(now=)`:** see verdict row 5.
- **`requirements-test.lock`:** comments only. The pins and hashes are unchanged.

## Findings

### S-1 (Low): a daily retry re-buys the exported-frame vision review

**Where:**
- `runtime/release.py:1320-1330` (`listing.seo` → `exported_review.review`);
- `visual/exported_review.py:52` (`review`);
- made reachable by `runtime/release.py:4731-4738` (the retry token) and
  `ops/rebuild_graph.py` (the daily retry).

**Scenario:**
1. A Launch-0 product exports a disclosed set.
2. Its marketing rebuild stays refused, for example because an unreviewed policy change is never
   waived (review F4 of the earlier PRODFIX round), or another halting incident is open.
3. Every UTC day the sentinel's retry re-drives pricing → `listing.seo`.
4. With `image_vision` open, `exported_review.review` describes every certified frame again, with
   one budgeted `describe_image` per frame plus one grid call. There is no check for a filed review
   that already covers exactly these frame sha256s. `review_state` already computes that, and
   `review` does not consult it.
5. The probe counted one `exported_review.review` per retry, on each of three days.

Before 86fe2b5 a retry rebuilt nothing, so this was not reachable. It is the same class as
production's `spend-repeat-paid-request` incidents, which PRODFIX's probe reuse and gallery
give-up were written to stop.

**Bound:**
- one review per such product per day;
- every call goes through `gw.check_budget` (the `quality_director` daily and monthly ceilings);
- nothing is published;
- only while `image_vision` is open.

**Fix:**
- In `exported_review.review`, return the filed reading unchanged when `review_state` shows a
  review that covers exactly the frames the certificate exports now (same shas). Re-describe only
  when the frame set changed.
- Add a test: two retries over unchanged frames produce one paid review.

### S-2 (Info): retries for a product that stays refused never stop

**Scenario:** while the cause persists, a product whose staleness the rebuild cannot cure gets
about 9 jobs a day. Those are `chain.rebuild`, 3 verifies, pricing, seo, launch, marketing and
one SHADOW-refused `store.publish`. The product's `rebuild-incomplete` report count also grows by
one a day.

Every eligible product retries in the first sentinel run of the UTC day, so the work arrives as
one burst. With production's estate (299 stale artefacts) that is a few hundred CA$0 jobs a day.
This is not a storm, and it is not paid apart from S-1.

**Fix (optional):**
- Back off exponentially after N consecutive retries that end in the same refusal reason.
- Spread the retries across the day, for example by jittering on a slug hash.

### S-3 (Info): the R-2 generalisation was not added

All three entry points that construct `Worker(` (`runner.start`, `worker_entry.main`,
`hq_worker.main`) now call `mark_job_process()`. `test_w4_fmbatch2_hq_job_process` covers only
HQ, though. A fourth entry point would again rely on the ContextVar alone.

**Fix:** an AST test asserting that every module which constructs `Worker(` calls
`mark_job_process` first.

### S-4 (Info): the 503 acceptance does not name the gate

**Where:**
- `test_w4_fmbatch1_mobile.py:43`;
- `test_w4_fmbatch1_useful_work.py:106-107`.

**What:** these assertions are sound today (§1). If one of these handlers ever learns to return
503 and the route is also allow-listed, the assertion would pass on an open route.

**Fix:** assert `security.requires_operator("GET", url)` beside the status, or check the gate's
refusal body.

### S-5 (Info): the 400 response has no security headers

`SingleAuthorizationMiddleware` is outside `SecurityHeadersMiddleware`, so its 400 has no
`X-Content-Type-Options` or CSP. The body is a fixed JSON string, so there is no impact.

**Fix:** optional. Add the headers, or move the guard one layer in, which would still keep it
ahead of the gate and the scrubs.

### S-6 (Info): the confirmation phrase is pre-filled

`approvals.inbox` puts `"confirm": POLICY_REVIEW_CONFIRMATION` into the card's `params`. The exact-
phrase check (F9) therefore adds no friction for a CC client that submits the card as given. The
real controls are step-up, the digest of the shown text, and the free-text `tested` field.

**Fix:** optional. Leave `confirm` empty in the card, so the owner types it.

## Tests run (at 24ada53, `nice -n 19`, one suite at a time, `PYTHONPATH=../src:.` in `brambleloop/tests`)

**51 suites, 51 passed, 0 failed.** Every log was checked for a non-vacuous ending (`N/N passed` or
`ok test_…`). `test_web_security`'s "failed" and "SUPERSECRETPW" lines are that suite's own
hostile-input fixtures, and it reports 11/11.

- **Every test file the range adds or edits (17):** `test_cert_dashboard` (19/19, one
  process), `test_customer_data_auth` (10/10), `test_w3_hq_independence`,
  `test_w4_fmbatch1_dashboard`, `_learn_card`, `_mobile`, `_provider_health`, `_route_audit`,
  `_seasonal_cohort`, `_theme`, `_useful_work`, `test_w4_fmbatch2_hq_job_process`,
  `test_w4_fmbatch2_research_docs_absent`, `test_w4_prodfix`, `test_w4_prodfix_policy_review`,
  `test_w4_prodfix_review` and `test_w4_secpatch2`.
- **The prior failures and neighbours (34):** `test_w4_secpatch_public_surface`,
  `test_route_auth_default_deny`, `test_swarm_runtime`, `test_cert_rebuild_chain`,
  `test_w4_fmbatch1_hq_worker`, `test_w4_agents_secfix`, `test_deploy`, `test_health`,
  `test_w4_fmbatch1_executive_plan`, `test_intel`, `test_w4_close5_vision_timeout`,
  `test_rc1_spend`, `test_w4_ondemand`, `test_w4_laurafix_truncation`, `test_w4_b2gates`,
  `test_w4_gatesi`, `test_policy_intake`, `test_w4_fmgate_rebuild_key`, `test_cert_thrash`,
  `test_executor`, `test_w3_k7_ops_truth`, `test_web_security`, `test_w4_fmbatch1_rollback`,
  `test_w4_listready`, `test_w4_store_live_state`, `test_w4_research_agent`,
  `test_w4_fmbatch1_retention_guard`, `test_w4_integ4_secfixes`, `test_w3_laura_cc_providers`,
  `test_roles`, `test_w4_disclosedqa`, `test_compiler`, `test_reverse` and `test_twin`.
- **On the PRODFIX review's environment note:** the three suites that review could not run
  (`test_w4_prodfix_policy_review`, `test_w4_ondemand`, `test_w4_laurafix_truncation`) and
  `test_w4_b2gates` (12/12) all pass on a venv built from the committed
  `requirements-test.lock`.

**Reviewer probes (scratch, not committed):**
- **Anonymous sweep:** 6,034 requests, BAD 0. Also covered `root_path` and path variants,
  duplicate `Authorization` (400) and the CC action refusals.
- **Operator non-vacuity:** 14/14 seeded kinds visible.
- **Retry chain:** three daily retries; S-1 counted.
- **Defaults:** checked with an empty env.

**Not run here:** the full `run_tests.sh` (INTEG7.md §10 is pending; it is required before
certifying), the `cc_mock` browser checks, and anything in production.

---
_Generated by [Claude Code](https://claude.ai/code)_
