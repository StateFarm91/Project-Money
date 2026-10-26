# Independent security and integrity review: INTEG7 / Batch 3 at 967502d

- **Reviewed:** `git diff 62770fbe..967502d -- brambleloop/src brambleloop/tests ops brambleloop/run_tests.sh`
  on `claude/w4-INTEG7` (98 commits; FMBATCH1, AGENTS, the integrator's fixes and the SECPATCH
  merge).
- **Read first:**
  - `INDEPENDENT_SECREVIEW_FMBATCH1_cbd4ff1.md` (from `claude/w4-SECREVIEW-FMBATCH1-cbd4ff1`);
  - `INDEPENDENT_SECREVIEW_AGENTS_b199cdb.md` (from `claude/w4-SECREVIEW-AGENTS-b199cdb`);
  - `research/final_build/w4/INTEG7.md`.

  `claude/w4-SECREVIEW-SECPATCH-4ff953d` does not exist on the remote yet, so SECPATCH was
  reviewed here from first principles.
- **Reviewer:** an independent Claude Code context that did not write this code. Review only:
  nothing was fixed. No production calls, no secrets, no deploys. The probes ran offline (socket
  connect patched to refuse) against throwaway SQLite databases.
- **Environment:** a venv built from `brambleloop/requirements.lock` plus
  `requirements-test.lock`. Every suite ran at `nice -n 19`, one at a time.
- **Date:** 2026-10-26 (UTC).

## Verdict

| Question | Answer |
|---|---|
| **Can 967502d ship as Batch 3 with SHADOW on and every switch OFF?** | **Not as it stands: one blocking item, R-1.** The tree is safe, but its own test suite is red. Once R-1 is fixed (test-only, in the stricter direction) and the full suite is green: **yes**. |
| Why R-1 blocks | The SECPATCH merge (967502d) made every non-allow-listed GET operator-only. FMBATCH1 suites still GET those routes anonymously and expect 200. **10 suites fail at 967502d** (list in §6): 9 have that cause, and 1 is an AGENTS × FMBATCH1 band-map gap. `run_tests.sh` globs `tests/test_*.py`, so the full suite is red. INTEG7.md §8 counted 122/122 *before* this merge, and §9 (full suite) is still "pending". A release whose suite is red is not certifiable. |
| Is anything exposed? | **No.** (Q1) |
| 1. Public exposure | **None found.** An enumerated sweep covered every route, every method (GET/HEAD/POST/PUT/PATCH/DELETE), three path fills, token set and unset, and projected-path variants, with finance, customer, support, tester, research, Learn-draft, owner-action, incident and unpublished-product sentinels seeded. It found **0 leaks** and 0 unexpected 2xx. All 17 sentinel kinds are visible to the operator, so the sweep is not vacuous. |
| 2. Defaults | **All OFF in code.** No new Etsy-write, publication or outward path is reachable by default. The one paid path new to Batch 3 (the VISNEXT2 Cloudline FLUX experiment, ≤ CA$5 shared cap and CA$1 vision) needs the owner session plus step-up, and it was reviewed in AGENTS a14c9ef. |
| 3. Storefront grants | **Nothing can mint outside the Command Center route.** One Low gap (R-2): FMBATCH1's new HQ worker does not mark itself as a job process. |
| 4. Retention | **Complete.** `unknown_read_actions()` is `[]`. Nothing is downgraded or unclassified relative to 62770fbe, and no protection is lost. |
| 5. Research Agent | **Bounded.** No loop, ≤ 25 investigations per daily sweep (idempotent per task per day), CA$0, no network unless `BRAMBLELOOP_RESEARCH_FETCH=1`. |
| 6. Tests weakened? | **No.** I read all 38 edited pre-existing test files, not only the 10 in INTEG7.md §6. One end-to-end scrub assertion became function-level (R-6). The real problem is the opposite: tests that were *not* edited now fail (R-1). |
| 7. Deploy path | **Safe.** `readback.py` gives the same verdict anonymously as with the operator credential, feature by feature. Every field the readback reads is in `PUBLIC_PROJECTIONS`. Auto-rollback stays OFF unless `AUTO_ROLLBACK=1` and `--auto-rollback-reason` are given on that invocation. |

| # | Severity | Area | Short title |
|---|---|---|---|
| R-1 | **Medium (release-blocking, not a vulnerability)** | merge FMBATCH1/AGENTS × SECPATCH | 10 of the 131 suites the range adds or edits fail at 967502d; the full suite is red |
| R-2 | Low | FMBATCH1 `app/hq_worker.py` × AGENTS M-2R | The HQ worker runs jobs without `mark_job_process()`; with the signing key in its env and `EMBEDDED_WORKER=0` it may sign |
| R-3 | Info | SECPATCH allow-list | `/api/learn/metrics` is allow-listed as "distinct from the operator token", but its `_editor` check *is* the operator token |
| R-4 | Info | SECPATCH projection | The projection is keyed on the raw path (fails open on a mismatch); there is no `Cache-Control`/`Vary` on bodies that vary with `Authorization` |
| R-5 | Info | SECPATCH owner-text scrub | Every unauthenticated request (401s and `/health` included) runs 2–3 table reads and a regex compile |
| R-6 | Info | test edits | INTEG7.md §6 under-reports the edited tests; the customer-scrub middleware lost its end-to-end assertion |
| R-7 | Info | VISNEXT2 controlled experiments | The shared-cap check-then-update is not atomic across the two definitions in one cap group |
| carried | Low | FMBATCH1 N-2 | With re-queue OFF, a drift incident still does not halt `store.publish` (unchanged; not reachable in SHADOW) |
| carried | Low | AGENTS L-1 | `store.update` compares against the stored reading; UNKNOWN equals UNKNOWN (unchanged; not reachable, since no grant can be minted) |

---

## 1. Public exposure after the merge

### Gate model at 967502d (SECPATCH)

- **`requires_operator("GET", p)`** is true unless `p` is in `PUBLIC_GET_ROUTES`. Reads are
  now default-deny, as writes already were.
- **`PublicProjectionMiddleware`** reduces the six readback JSON routes to allow-listed fields
  for any caller without a valid operator credential.
- **`OwnerTextScrubMiddleware`** redacts owner-inbox and open-incident texts from every
  unauthenticated response, except under `/api/cc/*` and `OWNER_SESSION_PAGES` (both behind
  the owner-session gate).
- **Ordering.** Outermost first: `SecurityHeaders` → `OwnerTextScrub` → `CustomerRefScrub` →
  `PublicProjection` → app. There is no GZip, so the projection always sees a parseable body.
  A body that is not JSON is replaced, not passed through.

### The routes reachable without a credential

These are enumerated with `security.iter_api_routes`, which includes routers. The `/cc` static
mount is covered by SECPATCH's own bundle sweep.

```
/  /health  /api/status  /api/build  /api/catalogue  /api/verify  /api/verify/smoke
/api/etsy/oauth/callback  /api/learn/metrics  /api/model-tournament/image/{sha256}
/brand/fonts/{name}  /learn/{slug}  /learn/{slug}/technique/{stitch}.svg
/ops/teardown  /ops/teardown.js  /ops/insights
POST: /api/learn/lessons/{slug}/review (own reviewer credential), /api/cc/auth/login, /api/etsy/webhook (HMAC)
```

Every entry in `PUBLIC_GET_ROUTES` is served (no stale entry). `/api/learn/metrics` refuses
without the operator token anyway (R-3).

### Routes named in the brief

| Route (all methods) | Gate at 967502d |
|---|---|
| `GET /m` | operator |
| `GET /api/finance`, `GET /api/finance/owner` | operator (N-1 closed twice over) |
| `GET /api/useful-work`, `/api/orchestrator`, `/api/opportunities`, `/api/etsy/scorecard`, `/api/evidence` | operator |
| `GET /api/product/{slug}/dossier` | operator |
| `POST /api/research/evidence` | operator (both the gate and its own `opsauth.check`) |
| `GET /api/company/departments`, `/api/company/departments/{key}` | operator |
| `POST /api/owner/storefront/{preview,proposals,{id}/revoke}` | operator, 403 contract (approve and rebase exist only on the CC route) |
| `GET /api/learn/{graph,curriculum,queue,lessons/{slug}}`, `PUT /api/learn/lessons/{slug}`, `POST /api/learn/graph/edges` | operator |
| `GET /api/learn/metrics` | allow-listed, but its handler requires the operator token (R-3) |
| `GET /learn/{slug}`, `/learn/{slug}/technique/{stitch}.svg` | public; APPROVED lessons only (a seeded DRAFT returns 404 by slug) |

### Proof (reviewer probe, not committed)

**Seeded sentinels:**
- a bank statement balance line (CA$98,765.43, with an external id and a payee description);
- a customer and an order (external ref, search term) and a support case (question, answer);
- a physical test (tester ref, private note);
- a research task (question, outcome);
- a DRAFT Learn lesson (slug, title);
- an owner action (title, reason, consequence);
- an open P1 incident;
- an unpublished product (slug, title).

**Sweep:**
- every `(path, method)` from `iter_api_routes`, plus HEAD for each GET;
- path parameters filled with `1`, the unpublished slug and the draft slug;
- token unset (503 regime) and token set (401/403 regime);
- for each projected route, the variants `/x/`, `//x`, `?x=1`, `%2F`, upper case, `/.` and `;a`,
  each compared with the projected body.

**Result:**
- `BAD: 0`: no sentinel in any response body, and no 2xx from a gated route or an unlisted
  mutating route.
- With the credential, all 17 sentinel kinds appear somewhere, so the sweep is not vacuous.
- `/api/etsy/oauth/callback` with a bogus state answers 403. The F-467 unblock fan-out enqueues
  `build.tick` only on 2xx, so an anonymous caller cannot drive it.

`test_w4_secpatch_public_surface` passed 10/10, `test_route_auth_default_deny` 8/8 and
`test_customer_data_auth` 9/9.

## 2. Safety defaults and new outward or paid paths

| Default | Code | Off unless |
|---|---|---|
| Auto-rollback | `ops/deploy.sh:147` | `AUTO_ROLLBACK=1` **and** `--auto-rollback-reason` on this invocation **and** a known predecessor. A standing `AUTO_ROLLBACK_REASON` is ignored, with a message. A rollback of a rollback is refused (exit 6). |
| Taxonomy requeue | `integrations/taxonomy_drift.py:57` | `BRAMBLELOOP_TAXONOMY_DRIFT_REQUEUE == "1"` |
| Research fetch | `intel/research_fetch.py:274` | `BRAMBLELOOP_RESEARCH_FETCH == "1"`. The agent's `official_docs` method follows the same switch. |
| Storefront writes | `ops/storefront_authority.py:179` | `BRAMBLELOOP_STOREFRONT_WRITES_AUTHORISED == "1"` **and** a sealed owner grant **and** a signing-capable process (none exists today; see §3) |
| Laura | `gateway/laura_unified.py`, `laura_converse.py`, `laura_register.py`, `laura/agency/venice_context.py` | `_UNIFIED == "venice"`; `_CEO_MODEL`, `_BUSINESS_TO_VENICE`, `_PRIVATE_REGISTER == "1"`. Private replies also need `BRAMBLELOOP_LAURA_PRIVATE_DAILY_CAD > 0`. Unchanged from Batch 2. |

**New outward or paid paths, from a grep of every added line for HTTP clients, transports,
Etsy write verbs and gateway calls:**
- **Etsy:** `update_shop`, `create_shop_section`, `update_shop_section` and
  `delete_shop_section` all go through `_authorise_storefront_write`. `test_w4_store_live_state`
  proves nothing is sent in shadow or production without a grant, nor for owner-configured or
  EU-only fields (12 passed).
- **Research fetch:** this is the only new HTTP client (stdlib urllib, allowlisted, https only,
  redirect-checked). It is switched OFF. The cbd4ff1 N-5 IDN redirect fix is present.
- **`gateway/compat_pack.run`:** reserves and bills through the ceilings (N-8 fixed with a
  `billed` flag). It has no live caller.
- **VISNEXT2 Cloudline acceptance** (`experiments/definitions/exp-2026-10-21-cloudline-acceptance`):
  - a paid FLUX image path that is new relative to Batch 2;
  - `owner_authorization.required`: `controlled.authorize` and `submit` refuse without
    `stepped_up`, and the route is under `/api/cc/*`;
  - the generation cap is CA$5.00 *shared* with `exp-2026-10-20-wrap-7ref` (`_group_spent`),
    and the vision cap is CA$1.00;
  - every render also reserves through `gateway.images` → `check_budget_cad`;
  - reviewed in AGENTS a14c9ef §8. See R-7 for a race.
- **No new publish or `store.publish` enqueue.** The FMBATCH1 review's enqueue audit still holds.
  New enqueues in AGENTS and integration (`research.investigate`, `build.tick` on a gate write)
  are CA$0 or internal.

## 3. Storefront grants (M-2R) after the merge

- **Minting.** `sfa.approve` and `sfa.rebase` call `_require_owner_request()`. The only setter of
  that context is `app/command_center/api.py:812`, after session, CSRF/nonce and `require_stepup`.
  `approvals.execute` has no caller other than that route (the Laura imports read
  `approvals.ACTIONS` only). The bearer storefront router has preview, proposals and revoke, and
  no approve.
- **Signing.** `_seal` refuses while `BRAMBLELOOP_EMBEDDED_WORKER` is unset or `"1"`. That is
  today's single container, so nothing can sign. `test_w4_agents_secfix` passed 11/11 at
  967502d.
- **What the merge added: R-2.** FMBATCH1's `app/hq_worker.py` is a third `Worker(...)` entry
  point. It does not call `mark_job_process()`. The AGENTS review's statement that "Worker( is
  constructed only in runner.py and worker_entry.py" no longer holds.

## 4. Retention

The probe imported `ops.retention` at 62770fbe and at 967502d and compared them:

```
base classified: 89   head classified: 206
removed from classification: []
downgraded base->head: []           (rank latest < windowed < lifetime_total)
lost protection: []
literal entry shadowing a resolved entry: image.benchmark_candidate, image.benchmark_trial
                                     (literal lifetime_total over resolved latest: stricter)
unknown_read_actions(head): []      (no unclassified exact read, prefix or unresolved site)
```

- **INTEG7 §4 fix holds.** `gate.certified`, `gate.halted` and `gate.version_conflict` are all
  `lifetime_total`, and `release_recovery.halted_releases` is a registered unresolved site.
- **Structural note.** `_RESOLVED_READ_ACTIONS` merges with `setdefault`, so a *weaker* literal
  silently wins. Today every collision is in the stricter direction. A guard asserting "literal
  rank ≥ resolved rank" would stop the `gate.certified` regression from recurring.
- **Suites:** `test_w4_fmbatch1_retention_guard` passed and `test_w4_firstsale_retention` passed
  6/6.

## 5. Research Agent after the integrator's breakpoint fixes

- **No loop.**
  - `research.sweep` is on a 24-hour cadence (`runtime/worker.py:929`). It enqueues at most 25
    `research.investigate` jobs, keyed `research.investigate:<task>:<day>`.
  - `investigate` enqueues nothing.
  - `request_research` and `request_architecture_review` are idempotency-keyed.
- **The INTEG7 STOPPED-episode fix is correct.**
  - A STOPPED task suppresses re-opening for the domain's freshness window. `R.stop` sets
    `answered_at`, so the window is real.
  - `days is None` (a never-dated domain) suppresses indefinitely. That errs toward *fewer*
    tasks, never a loop.
  - `open_question` dedupes only OPEN tasks, so without this fix the episode would indeed have
    re-opened daily.
- **No spend.** `research_agent` and `research` import no gateway or HTTP client. The agent is
  declared CA$0 (`test_w4_finhealth`). `R.stop` writes an escalation reading, not an
  `OwnerAction`, so the owner inbox cannot flood.
- **Suites:** `test_w4_research_agent` passed; `test_w4_fmbatch1_research` 13/13;
  `test_w4_fmbatch1_research_run` 11/11.

## 6. Tests

### Edits to existing tests (all 38 files, 62770fbe..967502d)

INTEG7.md §6 lists 10 files. The range edits 38 pre-existing test files plus the `cc_mock`
fixtures. I read every hunk that removes or changes an assertion.

- **SECPATCH `_opread` edits (about 25 files):** a read that used to be anonymous now presents
  the operator credential. Where it matters, a new assertion checks that the anonymous read
  refuses or is projected (`test_deploy`, `test_health`, `test_cert_dashboard`,
  `test_route_auth_default_deny`, `test_w4_integ4_secfixes`, `test_w3_laura_cc_providers`).
  **Stricter.**
- **`test_customer_data_auth`:**
  - `== 200` became `in (200, 401)`, because the owner views now refuse. Each body is still
    swept for buyer refs, and an operator assertion was added. **Equivalent.**
  - The end-to-end "public response is scrubbed" check became `security.scrub_body(...)` plus a
    check that the middleware is installed. **See R-6.**
- **The rest:** `test_w4_store_live_state`, `test_w4_research`, `test_w4_finhealth`,
  `test_roles`, `test_deploy`'s loop and `run_tests.sh` (the F-150 label) match the FMBATCH1 and
  AGENTS reviews: equivalent or stricter.
- **`ops/` and `run_tests.sh`:** `status` and `failed` still come from exit codes.

**No test was weakened.**

### Tests the merge broke (R-1)

These were run at 967502d. The reviewer's batches over every test file the range added or
edited are in "Tests run" below.

| Suite | Failure | Cause |
|---|---|---|
| `test_w4_fmbatch1_route_audit` | `AssertionError: /api/finance` | `PUBLIC = ("/api/finance", "/api/useful-work", "/api/company/departments", "/api/spend-report", "/api/owned", "/m")` asserts these are public. SECPATCH made them operator-only. The later `len(paths) > 20` and `"/m" in paths` would fail too. |
| `test_w4_fmbatch1_mobile` | `assert tables > 3` | anonymous `/` is now the static public page with no tables |
| `test_w4_fmbatch1_useful_work` | `set(c.get("/api/useful-work").json()) >= {...}` | anonymous GET → 401 |
| `test_w4_fmbatch1_learn_card` | `"Studio Learn"` not in `/` | anonymous `/` has no cards |
| `test_w4_fmbatch1_dashboard` | `'CA$5,000/month model' missing from the dashboard` | anonymous `/` |
| `test_w4_fmbatch1_seasonal_cohort` | `<th>Cohort</th>` not in `/` | anonymous `/` |
| `test_w4_fmbatch1_theme` | `<h2>Trends</h2>` not in `/` | anonymous `/` |
| `test_w4_fmbatch1_provider_health` | `KeyError: 'status'` on `/api/verify` | the anonymous body is projected to `{ok, checks[check, ok]}` |
| `test_cert_dashboard::test_a_satisfied_gate_and_its_open_shop_action_never_both_render` | `KeyError: 'actions'` on `/api/owner-actions` | SECPATCH's own edit: `seeded()` sends the bearer header, but the preceding test pops `BRAMBLELOOP_OPS_TOKEN`, so the call gets 503. Order-dependent; the suite passes only on a clean process with the token still set. |
| `test_swarm_runtime::test_every_runnable_job_type_has_a_band_decided_rather_than_defaulted` | 11 job types unmapped: `creative.capability_scorecard`, `creative.family_engine`, `creative.photo_principles`, `creative.salvage_review`, `intel.children_portfolio`, `listing.cross_sell_graph`, `research.flag_architecture`, `research.investigate`, `research.sweep`, `storefront.review`, `visual.model_ledger` | not SECPATCH: AGENTS job types missing from the orchestrator's band map. They fall to band 95 (housekeeping, lowest), which is the safe direction, but the test is red. INTEG7 §5 classified these for FMBATCH1's WORK_CLASS and missed this map. |

## Findings

### R-1 (Medium; blocks the Batch 3 certification, not a vulnerability): the SECPATCH merge left FMBATCH1 suites red

**Where**
- `tests/test_w4_fmbatch1_route_audit.py:51-70, 100-111`;
- `tests/test_w4_fmbatch1_mobile.py:35`;
- `tests/test_w4_fmbatch1_useful_work.py:105`;
- `tests/test_w4_fmbatch1_learn_card.py:31`;
- `test_w4_fmbatch1_dashboard`, `_seasonal_cohort`, `_theme` and `_provider_health`;
- `tests/test_cert_dashboard.py` (token lifetime across tests);
- `swarm/orchestrate` band map, for `test_swarm_runtime`.

**Scenario**
1. INTEG7.md §8 recorded 122/122 focused suites passing on the FMBATCH1+AGENTS tree.
2. 641dfc1/967502d then merged SECPATCH, which flipped GETs to default-deny and made `/` a page
   with no data.
3. The FMBATCH1 suites that SECPATCH never saw were not re-run. §9 (full suite) is still
   "pending".
4. `run_tests.sh` runs `ls tests/test_*.py`, so Batch 3 at 967502d does not pass its own gate.

**Why it matters for safety.** The tree is in the *safe* state: the routes really are gated.
The risk is the fix. The quickest way to turn these suites green is to add
`/api/finance`, `/api/useful-work`, `/m`, `/api/company/departments` and the rest back to
`PUBLIC_GET_ROUTES`, or to restore the old `/`. Either would re-open what SECPATCH closed
(`/api/finance` carries P&L and close state; `/m` carries the inbox count, worker state and
spend today).

**Fix (test-only, stricter direction)**
- **`test_w4_fmbatch1_route_audit`:**
  - Turn `PUBLIC` into an "operator now" list asserting 401 anonymously and 200 with the token,
    keeping the `FORBIDDEN` check on the operator body where it is still meant to hold.
  - Drive `_public_get_paths()` from `security.iter_api_routes` (not `app.routes`).
  - Replace `len(paths) > 20` and `"/m" in paths` with `set(paths) <= security.PUBLIC_GET_ROUTES`
    and `"/" in paths`.
- **`_mobile`, `_useful_work`, `_learn_card`, `_dashboard`, `_seasonal_cohort`, `_theme`,
  `_provider_health`:** read through `_opread.get(...)` for the operator view, and add one
  anonymous assertion that refuses or shows nothing (or, for `/api/verify`, only the projected
  keys).
- **`test_cert_dashboard`:** keep the operator token set for the whole `seeded()` client
  lifetime (restore it, rather than pop it, in the test at line 476).
- **`test_swarm_runtime`:** add the 11 AGENTS job types to the orchestrator's band map with a
  deliberate band each.
- **Then:** run the **full** suite (`run_tests.sh`) and record it in INTEG7.md §9 before
  certifying.
- **Do not** widen `PUBLIC_GET_ROUTES` or `PUBLIC_PROJECTIONS` to make a test pass.

### R-2 (Low): the HQ worker runs jobs without declaring itself a job process

**Where:** `app/hq_worker.py:75-86` (FMBATCH1 F-496), against AGENTS M-2R
(`ops/storefront_authority.py:84-100`).

**Proof (reviewer probe):** set `BRAMBLELOOP_EMBEDDED_WORKER=0` and
`BRAMBLELOOP_STOREFRONT_SIGNING_KEY`, stub `Worker.run`, then call `hq_worker.main()`:

```
hq types: ['assets.build']  main() -> 0
after hq_worker.main: _JOB_PROCESS = {'is': False} | key still in env: True | signing_refusal(): None
```

**Scenario**
1. After the service split, the operator starts an HQ worker on a machine whose environment was
   copied from the web service: the database URL, `EMBEDDED_WORKER=0` and the signing key.
2. That process runs job handlers, and `signing_refusal()` is `None` in it.
3. Today only the `owner_request` ContextVar (I-2 in the AGENTS review: a public function,
   regex/AST-guarded) still stands between a handler and `_seal`.
4. This is exactly the barrier M-2R was meant not to rely on.

**Why it is Low:** HQ is optional and runs only GREEN-only job types. No storefront job is
GREEN-only. The single-container deployment has no HQ. The ContextVar still holds.

**Fix**
- Call `storefront_authority.mark_job_process()` first in `hq_worker.main()`, as
  `worker_entry.main` does.
- Generalise the AGENTS AST test: every module that constructs `Worker(` must call
  `mark_job_process()` before it.

### R-3 (Info): `/api/learn/metrics` is allow-listed for a reason that is not true

- **Where:** `app/security.py` (`PUBLIC_GET_NOTES["/api/learn/metrics"]`) and
  `learn/api.py:29-35`.
- **What:**
  - The note says the route is "guarded by its own Learn editor credential, which is
    deliberately distinct from the operator token".
  - But `_editor` is `opsauth.check`, so it *is* the operator token. Probe: with the token set,
    the operator bearer gets 200. (The distinct credential is the *reviewer*'s,
    `BRAMBLELOOP_LEARN_REVIEW_TOKEN`, on the POST review route.)
  - The sibling editor reads (`/api/learn/graph`, `/curriculum`, `/queue`) are *not* on the
    allow-list. So this one route relies on its handler alone, and the projection and owner-scrub
    defences do not know it is sensitive.
- **Fix:** remove it from `PUBLIC_GET_ROUTES`. The gate then gives the same 401 and 503, and the
  handler check stays as defence in depth.

### R-4 (Info): projection robustness

- **Keyed on the raw path.** `PublicProjectionMiddleware` uses `scope["path"]`, while the gate
  uses the route template.
  - Today they coincide: no `--root-path` in `railway.json`, and every variant probed
    (`/x/`, `//x`, `%2F`, case, `;a`, `?q`) either redirects to the projected route or does not
    route.
  - But a mismatch (a root path, a mount, a route alias) fails **open**: the full body goes out
    on an allow-listed route.
  - Fix: resolve the spec from the matched route template, or refuse any allow-listed route whose
    path does not match a projection key exactly.
- **No cache headers.** The same URL returns different bodies by `Authorization`, with no
  `Cache-Control` or `Vary`.
  - RFC 9111 keeps a compliant shared cache from storing the authorised response, so this is not
    exploitable through a compliant cache.
  - Fix: set `Cache-Control: no-store` and `Vary: Authorization` on these six routes, so the
    property does not depend on whatever proxy is in front.

### R-5 (Info): the owner-text scrub costs a database read per anonymous request

- **Where:** `app/main.py::_owner_only_texts`, `security.OwnerTextScrubMiddleware._scrubber`.
- **What:** every request without the operator credential, including every 401 and every
  platform `/health` probe, does the following:
  - selects all `OwnerAction` rows and all open incidents;
  - builds the access-request texts;
  - compiles one alternation regex over all their variants;
  - runs alongside the existing customer-ref scrub (customers and orders).
- **Effect:** this is unauthenticated work amplification, and it grows with the owner inbox.
  It is not a leak.
- **Fix:** cache the compiled scrubber for a few seconds, keyed on `max(id)` and a count.

### R-6 (Info): test-edit record and one coverage shift

- **The record.** INTEG7.md §6 omits 28 of the 38 edited existing test files (the SECPATCH
  `_opread` edits). I reviewed them all, and none is weakened. Still, the integration record
  should list them, or point at SECPATCH's own record.
- **The coverage shift.**
  - `test_customer_data_auth::test_a_card_that_does_quote_a_buyer_is_redacted_on_render` no
    longer proves that `CustomerRefScrubMiddleware` scrubs a live public response. It now checks
    `scrub_body` as a function and that the middleware is listed.
  - No public route carries such a card any more, so the test had nothing left to drive.
  - Fix: add an end-to-end test with a throwaway public route (or the ASGI-level fake app used
    by `test_the_owner_text_scrub_leaves_the_command_center_alone`) that emits a buyer ref.

### R-7 (Info): the controlled-experiment shared cap is check-then-update

- **Where:** `experiments/controlled.py` (`guard_generation` lines 840-860, and the run loop
  around lines 605-617).
- **What:**
  - `_group_spent` is read and the run's `generation_spent_cad` is then updated, in separate
    sessions with no lock.
  - Two runs in the same cap group, executing at once on two worker threads, can both pass
    with one image price of headroom.
- **Bound:** the overshoot is at most one render per concurrent run. The global ceiling still
  applies through `gateway.images.reserve_render`. Every run needs owner step-up.
- **Fix:** take the budget lock (as LISTREADY's launch-review grant does) around check and
  update.

### Carried, unchanged and still not reachable in SHADOW

- **FMBATCH1 N-2:** `taxonomy_drift` with re-queue OFF still opens the incident with
  `halts_publication=False`.
- **AGENTS L-1:** the `live_replaced` execution check still reads the stored snapshot.
- **AGENTS I-2:** the ContextVar is the in-process barrier after the split. R-2 adds a process
  where it is the *only* barrier.

Verified fixed in this range: cbd4ff1 N-1, N-3, N-4, N-5 and N-8, and b199cdb L-2 (creative
part) and L-3.

## 7. Deploy path

- **The readback still reads with the projection.**
  - The probe ran `ops/readback.py::run` against TestClient twice, anonymously and with the
    operator credential.
  - **All 11 features gave the same verdict.** The twelfth, "launch packet route deployed and
    operator-gated", is PASS anonymously and FAIL with the credential, which is correct, because
    it expects 401.
  - Some FAILs are the sandbox's own state: no boot guard record, no worker, no publication
    attempt, smoke matrix. They are FAIL in both modes, so the projection removes nothing the
    verdict needs.
  - `rollback_decision.decide` gives the same decision for both.
  - `test_w4_secpatch_public_surface::test_deploy_readback_still_reads_every_field` passes: no
    UNKNOWN, and `deployed_sha` and `verify_deploy` read the commit.
- **`deploy.sh`:** the readback writes `--json`. A P0 decision triggers one re-read after
  `READBACK_RETRY_S`, then exits 6 with the exact manual command. It pushes only under the
  three-way condition in §2. `test_w4_fmbatch1_rollback` passed.
- **Production-side caution.** Production (Batch 2 / 051dbee2) does **not** yet have the
  projection, so its readback is unaffected until Batch 3 deploys. The first Batch 3 readback
  will read projected bodies. Verified above.

## Tests run (at 967502d, `nice -n 19`, one suite at a time)

**131 suites** were run. They are the reviewer's focused set plus **every** test file the range adds (79 more) and every pre-existing test file it edits (26 more), each with `PYTHONPATH=../src:.` in `brambleloop/tests`.

- **Failed (10):** `test_w4_fmbatch1_route_audit`, `test_w4_fmbatch1_mobile`,
  `test_w4_fmbatch1_useful_work`, `test_w4_fmbatch1_learn_card`, `test_w4_fmbatch1_dashboard`,
  `test_w4_fmbatch1_provider_health`, `test_w4_fmbatch1_seasonal_cohort`,
  `test_w4_fmbatch1_theme`, `test_cert_dashboard` and `test_swarm_runtime`. All are R-1.
- **Passed (121):** `test_cert_culture_teardown`, `test_cert_growth_ops`, `test_cert_growth_seasonal`, `test_cert_spend_hosts`, `test_cert_wiring`, `test_closure`, `test_customer_data_auth`, `test_dashboard_spend`, `test_deploy`, `test_health`, `test_incident_lifecycle`, `test_model_spend_paths`, `test_policy_intake`, `test_provenance_backfill`, `test_ranking_readiness`, `test_roles`, `test_route_auth_default_deny`, `test_search_visibility`, `test_w3_laura_cc_providers`, `test_w4_agents`, `test_w4_agents_secfix`, `test_w4_board_close`, `test_w4_c2_visual`, `test_w4_c3`, `test_w4_capability_scorecard`, `test_w4_cc_company`, `test_w4_children`, `test_w4_close5_r1`, `test_w4_close5_rows`, `test_w4_close5_rows4`, `test_w4_contracts`, `test_w4_departments`, `test_w4_finhealth`, `test_w4_firstsale_retention`, `test_w4_fmbatch1_adoptions`, `test_w4_fmbatch1_audit`, `test_w4_fmbatch1_awaiting`, `test_w4_fmbatch1_backpressure`, `test_w4_fmbatch1_capability_audit`, `test_w4_fmbatch1_cc`, `test_w4_fmbatch1_childrens_demand`, `test_w4_fmbatch1_compat`, `test_w4_fmbatch1_constellation`, `test_w4_fmbatch1_context_pack`, `test_w4_fmbatch1_contracts`, `test_w4_fmbatch1_cost_learning`, `test_w4_fmbatch1_creator_outcomes`, `test_w4_fmbatch1_critical_path`, `test_w4_fmbatch1_cross_team`, `test_w4_fmbatch1_curriculum`, `test_w4_fmbatch1_deadlock`, `test_w4_fmbatch1_departments`, `test_w4_fmbatch1_dept_workspace`, `test_w4_fmbatch1_dispatch`, `test_w4_fmbatch1_dossier`, `test_w4_fmbatch1_drift`, `test_w4_fmbatch1_dupwork`, `test_w4_fmbatch1_etsy_ops`, `test_w4_fmbatch1_etsy_scorecard`, `test_w4_fmbatch1_evidence`, `test_w4_fmbatch1_evidence_index`, `test_w4_fmbatch1_executive_plan`, `test_w4_fmbatch1_failclass`, `test_w4_fmbatch1_finance_owner`, `test_w4_fmbatch1_fm_graph`, `test_w4_fmbatch1_hq_worker`, `test_w4_fmbatch1_hygiene`, `test_w4_fmbatch1_integrate`, `test_w4_fmbatch1_kill_learn`, `test_w4_fmbatch1_lane_stop`, `test_w4_fmbatch1_launch_scope`, `test_w4_fmbatch1_learn_a11y`, `test_w4_fmbatch1_learn_graph`, `test_w4_fmbatch1_learning_value`, `test_w4_fmbatch1_lease_scope`, `test_w4_fmbatch1_licenses`, `test_w4_fmbatch1_lifecycle`, `test_w4_fmbatch1_master_view`, `test_w4_fmbatch1_metrics`, `test_w4_fmbatch1_opportunity_cards`, `test_w4_fmbatch1_owned_assisted`, `test_w4_fmbatch1_owned_surfaces`, `test_w4_fmbatch1_owner_evidence`, `test_w4_fmbatch1_physical_truth`, `test_w4_fmbatch1_pricing_trial`, `test_w4_fmbatch1_progress`, `test_w4_fmbatch1_proof_customer`, `test_w4_fmbatch1_provider_boundary`, `test_w4_fmbatch1_providers`, `test_w4_fmbatch1_pwa`, `test_w4_fmbatch1_readings_bus`, `test_w4_fmbatch1_refill`, `test_w4_fmbatch1_remerch`, `test_w4_fmbatch1_research`, `test_w4_fmbatch1_research_run`, `test_w4_fmbatch1_retention_guard`, `test_w4_fmbatch1_rollback`, `test_w4_fmbatch1_runtests_trap`, `test_w4_fmbatch1_search_strategy`, `test_w4_fmbatch1_session_log`, `test_w4_fmbatch1_signing`, `test_w4_fmbatch1_swarm`, `test_w4_fmbatch1_task_contract`, `test_w4_fmbatch1_tool_spend`, `test_w4_fmbatch1_unblock`, `test_w4_fmbatch1_value_units`, `test_w4_fmclose_etsy`, `test_w4_fmgate_catalogue_filters`, `test_w4_integ4_secfixes`, `test_w4_listing_memory`, `test_w4_listready`, `test_w4_mobile_live_text`, `test_w4_photo_principles`, `test_w4_rel2`, `test_w4_research`, `test_w4_research_agent`, `test_w4_secfix_insights_private`, `test_w4_secpatch_public_surface`, `test_w4_store_live_state`, `test_w4_visnext2`, `test_web_security`.

**Reviewer probes (scratch, not committed):**
- the public-surface sweep: §1, 0 findings;
- `hq_worker` signing: R-2;
- the retention base/head diff: §4;
- the readback anonymous vs operator comparison: §7.


**Not run here:** the full `run_tests.sh`; the roughly 200 untouched suites were not run individually, and R-1 blocks it in any case, the `cc_mock` browser
checks, and anything in production.

---
_Generated by [Claude Code](https://claude.ai/code)_
