# Independent security and integrity review: W4-FMBATCH1

- **Reviewed:** `origin/claude/w4-FMBATCH1` at `871b84a`, diffed against
  `origin/claude/final-candidate-b997efd` (three-dot).
- **Paths:** `brambleloop/src`, `brambleloop/tests`, `brambleloop/ops`, `brambleloop/run_tests.sh`.
  I also read `brambleloop/scripts/classify_failure.py` and the root `ops/` changes
  (`deploy_guard.py`, `signing_audit.py`, `deploy.sh`, `rollback_decision.py`), because the
  batches under review call them.
- **Batch map:** `brambleloop/research/final_build/w4/FMBATCH1.md`.
- **Reviewer:** an independent Claude Code context that did not write this code. Review only:
  nothing was fixed. There were no production writes, no paid calls and no deploys.
- **Date:** 2026-10-26 (UTC).

## How the review was done

- I read every new module and the hooks that call it.
- I traced the paid and outward paths to their gates.
- I ran these small suites at `nice -n 19`:
  - `test_w4_fmbatch1_failclass`: 2/2 OK;
  - `test_w4_fmbatch1_signing`: OK.
- The suites that need SQLAlchemy could not run: this machine has no `.venv`, and I did not
  install one on a shared machine. They are **not verified here**.
- I wrote pure-Python probes, with no database and no network, to confirm F-2 and F-6.
  Their output is quoted below.

## Verdict

**Not ready to ship independently on top of the listings release as it stands.**

- **On a SHADOW deployment it is safe to ship.** Every new paid path reserves before it
  calls. The new route that carries personal data is operator-only. No change sets a live
  price. `store.publish` still refuses in SHADOW.
- **Two new behaviours are on by default and act outward with no switch.** That breaks the
  "every new behaviour defaults OFF or read-only" condition:
  - **F-1.** Taxonomy drift re-drives the release chain through to `store.publish`.
  - **F-3.** `deploy.sh` automatically rolls production back.
- **Ship it on the listings release once:**
  - F-1 is gated or stops before `store.publish`;
  - F-3 defaults off, or the owner explicitly accepts it as containment;
  - F-2 (redirects) is fixed before anyone sets `BRAMBLELOOP_RESEARCH_FETCH=1`.
- **The other findings are Low or Info.** They can ship and be fixed forward.

| # | Severity | Area | Short title |
|---|---|---|---|
| F-1 | **High** (on a past-SHADOW release) / Low (in SHADOW) | F-010 taxonomy drift | Etsy schema change re-runs `listing.seo → launch.plan → store.publish`, default ON |
| F-2 | **Medium** (latent: fetch is OFF by default) | F-431 research fetch | Redirects followed to any host and scheme; allowlist checked only on the first URL |
| F-3 | **Medium** | F-381 deploy.sh | Automatic production rollback (a push) defaults ON, with a machine-written "owner reason" |
| F-4 | **Medium** (latent: no live caller) | F-096 compat pack | Billed calls never reach `spend_report`, so a released reservation hides spend from the ceiling |
| F-5 | Low | F-096 compat pack | Vision task under-reserves (no image tokens) and leaks the reservation on the `continue` path |
| F-6 | Low | F-150 `run_tests.sh` | Assertion failures whose text contains an OS/network phrase are labelled "ENVIRONMENT FAILURE … do not revert" |
| F-7 | Low | F-153/F-157 signing | `empty_range` (git unreadable) is never refused, even with `BRAMBLELOOP_SIGNING_REQUIRED=1` |
| F-8 | Low | F-431 research fetch | Network errors are uncaught, so one bad host aborts promotion and erases the `learn.scan` research counts |
| F-9 | Low | F-089 physical truth | A demand with no `risk_class` and no test, or a bad `needed_by`, gives the whole operator route a 500 |
| F-10 | Info | F-095 failover | A contract-evaluation exception still routes the same-provider fallback (UNKNOWN routed) |
| F-11 | Info | F-656 orchestrator | Pull order changed (RUN > GROW > IMPROVE) and WATCHING memory is written every tick, default ON |

### Focus items with no finding

- **Spend (F-091 provider boundary).** The paid calls in `culture/classify`, `intel/serp` and
  `intel/vision` still reserve before they call.
  - `providers.check_budget` forwards to `anthropic.check_budget` with `purpose` required, and
    every caller passes it.
  - `BudgetExceeded` and `AgentCeilingExceeded` still resolve through `providers.__getattr__`.
  - An unregistered `BRAMBLELOOP_MODEL_VENDOR` raises; it never falls back.
- **Spend attribution (F-107).** `value_units.buckets` keeps every dollar; anything it cannot
  attribute goes to `unattributed`. `stamp` only adds keys and never changes `amount_cad`.
- **Cost learning (F-389).** It writes proposals only. `routing.override_route` still refuses
  without recorded equivalence.
- **Pricing shadow trial (F-374).** There is no executor, monitor, rollback or verifier for
  `pricing_shadow`, and nothing produces a `price_point` proposal. It reads `listing_outcomes`
  and enforces the regulatory and net-contribution floors. **No live price can change.**
- **Routes and auth.**
  - `/api/physical-truth` is in `OPERATOR_GET_ROUTES`.
  - `/api/departments` is public but returns static charter metadata only: no PII, spend or
    job rows.
  - `/api/swarm/runtime` adds `parallel_window`: aggregate counts only.
- **HTML injection.**
  - `company.js` `kpiTrend` builds through `h()` and `barChart`. `components.js:291` says the
    chart is inline SVG with no `innerHTML`.
  - The server-rendered `_fold` summary goes through `esc()`.
- **Release gating (`run_tests.sh`).**
  - The F-150 change only prints a label and an `ENVIRONMENT FAILURES:` line.
  - `status`, `failed` and `failing_list` are still computed from exit codes.
  - `deploy_guard._record_problems` still refuses on `suites failing: N`.
  - **An "ENVIRONMENT FAILURE" label cannot make a failing run release-eligible.**
- **`deploy_guard` signing section.** It only adds refusals (`claimed_but_unsigned`, or
  required and unsigned). Records without a `signing` key pass exactly as before. **Gating is
  not weakened** (but see F-7).
- **Existing tests.**
  - `tests/test_w4_research.py` now passes more required fields (stop condition, evidence,
    effect, conclusion), so it is tighter, not looser. It also points `DOCUMENTS` and
    `TESTS_DIR` at an empty fixture, so counts are isolated from the repository.
  - `tests/fixtures/cc_mock/check.mjs` separates KPI bars from the existing bar count and adds
    `vis.kpiBars === 0`.
  - **No assertion was removed or relaxed.**
- **UNKNOWN values.** These all keep UNKNOWN or None and never turn it into 0 or a pass:
  - `swarm.metrics.parallel_window`, `scale.confidence.progress` (`share=None`) and
    `signal_hygiene.disk_trend` (UNKNOWN below `MIN_SAMPLES`);
  - `rollback_decision.decide` (UNKNOWN or unreadable is a P0) and the `executive` blocks;
  - `funding_packet._trigger` (`triggered: None`).
  - The only zero-fill is in `company.departments` `kpi_trend_7d`. It is inside a window the
    whole company measured, so zero is real data there.

---

## Findings

### F-1 (High on a past-SHADOW release; Low in SHADOW): F-010 drives the release chain to `store.publish` on an Etsy-side change, default ON

**Where**
- `brambleloop/src/brambleloop/integrations/taxonomy_drift.py:241`:
  `ctx.enqueue("listing", "listing.seo", {**inputs, "rebuild": token}, ...)`.
- `brambleloop/src/brambleloop/runtime/release.py:1351`: `listing.seo` enqueues `launch.plan`
  with `i.get("rebuild", "")` in its idempotency key.
- `runtime/release.py:75-78` says the rebuild token rides the whole chain, so every stage
  re-runs once per rebuild.
- `autonomy_map.json` edges: `listing.seo → launch.plan → {marketing.schedule, store.publish}`.
- `runtime/pipeline.py:1555`: `store.publish` refuses only in SHADOW. Past SHADOW it builds
  the `EtsyClient` and publishes.

**Scenario**
1. The daily `listing.taxonomy_refresh` stores a new snapshot: Etsy renamed a node, or added a
   property schema. FMBATCH1.md §2 says this will happen on the first refresh after release.
2. For each affected or UNKNOWN profile, `listing.seo` is re-queued with a new `tx<id>` token.
3. A new `launch.plan` key is minted, then `store.publish` for that rebuild.
4. For CHOSEN profiles the drift incident halts publication only until `listing.seo` rebuilds
   the profile: `_persist_search_profile → resolve_if_current`. The halt is lifted before
   `store.publish` runs.
5. For UNKNOWN or refused profiles there is no incident at all.

**Result:** on a deployment past SHADOW, an upstream Etsy taxonomy change autonomously
triggers `store.publish` (an **Etsy write**), with no owner action and no switch. This branch
was described as making no Etsy write. In SHADOW the chain ends in `store.publish_refused`
(a deliberate refusal), so it is safe today.

**Fix (one of):**
- Run the drift rebuild as a re-certification only: re-run `listing.seo` with a flag that
  stops the chain before `launch.plan`, or use a separate key namespace that `launch.plan`
  does not inherit.
- Gate the re-queue behind a default-OFF switch (`BRAMBLELOOP_TAXONOMY_DRIFT_REQUEUE=1`) while
  the drift incidents and the report stay on.

**Test to add:** a drift re-queue never yields a `store.publish` job with a `tx*` rebuild key.

### F-2 (Medium, latent): research fetch follows redirects to hosts and schemes off the allowlist

**Where**
- `brambleloop/src/brambleloop/intel/research_fetch.py:92`:
  `urllib.request.urlopen(req, timeout=TIMEOUT_S)`.
- `check_url` (`:68-80`) runs once, on the requested URL only (`:124`).
- `robots_allows` (`:98`) fetches through the same `_default_get`.

**Scenario**
1. With `BRAMBLELOOP_RESEARCH_FETCH=1`, the default opener's `HTTPRedirectHandler` follows up
   to 10 redirects to **any** host and to `http://`.
2. An allowlisted host that redirects can land the fetch on a host nobody reviewed: canada.ca
   moving a page to another domain, an `en.wikipedia.org` redirect, or an Etsy help article
   bouncing to a login or CDN host.
3. In a container, a redirect to `http://169.254.169.254/` or an internal Railway hostname is
   the textbook SSRF pivot.
4. The response body is then stored with `source=host` of the *original* allowlisted URL and
   `basis=ALLOWED_HOSTS[host]`. The provenance is false, and a later `fact` rests on it.
5. robots.txt is also read through redirects, so a robots answer from another host is obeyed
   as if it were the original's.

**Mitigating factors**
- Off by default; `run()` only fetches when the variable is `1`.
- The planned URLs are constants from `childrens.SOURCES`, not attacker input.
- The fetch sends no credentials.

**Fix**
- Install an opener whose `HTTPRedirectHandler.redirect_request` re-runs `check_url` on
  `newurl` and refuses (raises) otherwise. Or disable redirects and record a 3xx as "not
  fetched: redirected to X".
- Record `r.geturl()` and refuse when it differs from the checked URL.
- Smaller hardening:
  - refuse a non-default port in `check_url` (today `https://en.wikipedia.org:8443/` passes);
  - treat a robots.txt over `MAX_BYTES` as unreadable rather than parsing it truncated.

**Test to add:** a stub redirect to a host off the allowlist, and to `http://`, is refused and
audited.

### F-3 (Medium): `deploy.sh` automatically rolls production back by default

**Where**
- `ops/deploy.sh:118`: `"${AUTO_ROLLBACK:-1}"`.
- `ops/deploy.sh:123`: `exec deploy.sh --rollback-to "$deployed" --reason "automatic containment: …"`.
- `ops/rollback_decision.py:71`: unreachable after deploy is a P0.

**Scenario**
1. Any P0 readback FAIL or UNKNOWN pushes the predecessor to the production branch with no
   human in the loop. P0 includes production being briefly unreachable after `verify_deploy`
   passed.
2. The `--reason` the guard was built to receive from the owner is filled in by the script.
3. This is a new outward action (a git push to `claude/repository-setup-nc9x6o`) that
   defaults ON.

**Mitigating factors**
- The rollback re-enters the guarded path: `rollback-commit`, then `check`.
- It refuses to roll back a rollback (`--rollback-to` set means exit 6).
- It only targets the recorded predecessor.

**Fix**
- Default `AUTO_ROLLBACK` to `0` (report exit 6 with the exact command) until the owner
  accepts automatic containment in `DECISION_LOG.md`.
- Re-read once after a short delay before treating "unreachable" as a P0, so a cold start does
  not cause a rollback.

### F-4 (Medium, latent): compat-pack calls leave no `spend_report` row, so the ceiling stops seeing them

**Where:** `brambleloop/src/brambleloop/gateway/compat_pack.py:148-163`.

**Scenario**
1. With `db`, each task reserves (`gw.check_budget`, `:148`), calls the model, then
   `release_reservation(db, reservation, actual_cad=cost)` (`:163`).
2. Unlike every other paid caller, it never calls `spend_report.record`. Compare
   `culture/classify.py`, which does both.
3. `reservations.release` only stamps `actual_cad` on the reservation row, and released rows
   are not counted (`reservations.outstanding`). The month's billed total that
   `check_budget_cad` reads comes from the spend ledger.
4. **Result:** a live compatibility drill would spend money the ceilings, `what_it_bought`
   and the F-107 value units never see. That is hidden spend.
5. If cost computation raises after the provider answered (for example a response without
   `input_tokens`), the `except` branch releases with **no** `actual_cad` at all.

**Mitigating factor:** there is no production caller today. `provider_watch` only reads
`compat_pack.latest`.

**Fix**
- After every billed response, call `spend_report.record(...)` with `purpose="compat_pack"`,
  provider, model and tokens, as `classify` does.
- In the `except` path, when a response was received, release with the computed or estimated
  cost rather than `None`.
- Add `compat_pack` to the spend-path pin in `tests/test_model_spend_paths.py`.

### F-5 (Low): compat-pack vision under-reserves and leaks its reservation

**Where:** `compat_pack.py:149` (`input_tokens=len(t.prompt) // 4`) and `:151-156`.

**Scenario**
- The vision task's reservation omits `IMAGE_TOKENS_ESTIMATE`, which the vision callers add,
  so the pre-call check under-states the call.
- When the provider has no `see`, the loop `continue`s with the reservation still held. It
  expires after its TTL and shows up as an abandonment in `reservations.sweep`.

**Fix**
- Add `IMAGE_TOKENS_ESTIMATE * len(t.image_urls)` for vision tasks.
- Check `see` before reserving, or release before `continue`.

### F-6 (Low): F-150 labels code failures as environment failures

**Where:** `brambleloop/scripts/classify_failure.py:33` (any line, any substring) and
`brambleloop/run_tests.sh:470-475`.

**Probe**

```
$ printf 'FAIL test_owner_route_refuses\nAssertionError: expected 401, body={"error": "Permission denied"}\n' > o.txt
$ python3 -I scripts/classify_failure.py o.txt
PERMISSION	AssertionError: expected 401, body={"error": "Permission denied"}
$ printf 'AssertionError: retry loop logged "Connection refused" 0 times, expected 3\n' > o2.txt
$ python3 -I scripts/classify_failure.py o2.txt
NETWORK	AssertionError: retry loop logged "Connection refused" 0 times, expected 3
```

**Impact**
- The run still reports `status=failed`, and the release record still refuses. **Gating is
  intact.**
- But the log tells the operator "not a code regression; do not revert for it" about a
  genuine assertion failure. This repository's tests routinely assert on refusal bodies and
  network-error handling, so it will happen.

**Fix**
- Skip lines that start with `AssertionError`, `assert` or `FAIL`.
- Prefer exception-type matches: `OSError: [Errno 28]`, `PermissionError:`, `ConnectionRefusedError:`, `socket.gaierror`.
- Do not classify a suite whose output contains an `AssertionError` traceback.
- Soften the printed advice to "check the environment before reverting".

### F-7 (Low): signing evidence passes an empty or unreadable range even when signing is required

**Where:** `ops/signing_audit.py:71` (`if not commits: status = "empty_range"`) and
`ops/deploy_guard.py:540` (`elif req and a["unsigned"]`).

**Probe:** `BRAMBLELOOP_SIGNING_REQUIRED=1` with an unreadable repo gives
`{'status': 'empty_range', 'unsigned': [], 'required': True, …}` with no `refused`.

**Impact**
- `_git` turns every git error into `""`: dubious ownership, a missing `gpg`, or a shallow
  clone without the commit.
- With signing required, "could not read" is treated as "nothing unsigned". That is UNKNOWN
  turned into a pass.
- In `record_release` the SHA was already resolved, so this is narrow.

**Fix:** with `required`, refuse any status other than `verified`, including `empty_range`
and `partial`.

### F-8 (Low): research-fetch network errors abort promotion

**Where**
- `research_fetch._default_get` (`:92-96`) catches only `HTTPError`.
- `fetch_for_task` (`:135`) does not catch `URLError`, `TimeoutError` or `ssl` errors.
- `learn/runtime.py:42-43`: the outer `except` replaces the whole `result["research"]`.

**Scenario**
1. With fetch on, one DNS failure or timeout raises out of `run()` before `promote(db)`.
2. Answered tasks are not promoted on that run.
3. The `opened`, `expired_reopened` and `overdue_stopped` counts already computed are
   overwritten by `{"error": …}` in the `learn.scanned` audit.

**Fix**
- Catch `OSError` and `urllib.error.URLError` in `_default_get`, returning `(0, b"")` with the
  reason, so the fetch is recorded as not fetched.
- Wrap each fetch so `promote` always runs.

### F-9 (Low): `/api/physical-truth` can 500 on one malformed plan row

**Where:** `brambleloop/src/brambleloop/quality/physical_truth.py:76` and `:97`.

**Scenario**
- A tester-plan demand with no `risk_class` and no `physical_tests` row raises
  `KeyError` (`by_slug[slug]`).
- A `needed_by` that is not ISO raises `ValueError`.
- Either takes down the whole dashboard. It is operator-only, so there is no exposure, but the
  failure is total rather than UNKNOWN.

**Fix**
- Use `by_slug.get(slug)`.
- Parse `due` defensively; an unparseable date is `overdue: None` with a reason.

### F-10 (Info): an exception in the fallback contract still routes a same-provider fallback

**Where:** `brambleloop/src/brambleloop/gateway/failover.py:289`.

When `fallback_contract.may_route` raises, the row records `contract: "UNKNOWN: …"` and the
model is still appended to `order`. This only affects reviewed same-provider fallbacks
(`APPROVED_FALLBACKS`). The behaviour is documented, and before this branch there was no check
at all. But it is the one place in the batch where UNKNOWN is routed. Consider `continue` for
cross-provider rows, if one is ever added.

### F-11 (Info): orchestrator behaviour change, default ON

**Where:** `brambleloop/src/brambleloop/autonomy/orchestrator.py`, in `tick()`.

- Runnable candidates are now ordered RUN, then GROW, then IMPROVE, ahead of value.
- A SATURATED department writes a `department.watching:*` company-memory row on **every** tick.
- This is not a safety issue: it does not publish, spend or set a price. But it changes
  production scheduling without a switch, and the memory writes amplify each tick.
- **Fix:** write the WATCHING row only on a state change, or when `last_seen` is older than N
  minutes.

---

## What ships under which condition

| Behaviour | Default | Outward effect | Ship on the listings release? |
|---|---|---|---|
| F-431 research fetch | OFF (`BRAMBLELOOP_RESEARCH_FETCH`) | outbound GETs | Yes; fix F-2 before switching it on |
| F-431 promotion into lessons | ON | writes improvement-bus lessons | Yes |
| F-010 drift incidents and requeue | ON | halts publication; **re-drives `store.publish`** | **No, until F-1 is fixed** |
| F-381 automatic rollback | ON | **git push to production** | **Only if AUTO_ROLLBACK defaults to 0, or the owner accepts it** |
| Signal hygiene (F-139/140/149) | ON | P1/P2 incidents, none halting | Yes |
| Provider boundary and compat pack | ON / no caller | none today | Yes; fix F-4 before any live drill |
| Signing section of the release record | ON | can only refuse | Yes (F-7 is a hardening item) |
| F-150 label | ON | log text only | Yes (F-6 is advisory text) |
| CC/dashboard views, physical truth, departments | ON | read-only | Yes |
| Pricing shadow trial, cost learning, value units | ON | read-only or proposals | Yes |
| Orchestrator pull order and WATCHING | ON | scheduling | Yes (F-11 is Info) |

**Not verified here:** the SQLAlchemy-backed FMBATCH1 suites, the full suite and the
browser (`cc_mock`) checks. None of them ran on this machine.
