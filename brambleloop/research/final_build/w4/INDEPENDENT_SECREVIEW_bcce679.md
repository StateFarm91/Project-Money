# Independent security review: release candidate bcce679 (integration-specific risk)

**VERDICT for deploying bcce679 with every activation switch OFF: NO BLOCKER, no HIGH, no
MEDIUM.** The merge undid none of b997efd's fixes (B1, `/api/audit` digest truncation, L1-L4,
M1, I7, I8). The new routes are owner-only, and the unified routes are closed when the switch
is off. The harness fix only makes the tests stricter. The schema change is additive.

Read these two findings before deploying:

- **S-1 (LOW).** "All switches OFF" does not mean "no new model spend". Business Laura's
  model-written chat and the tick's priority ordering (LAURACEO) have no activation switch.
  They start spending on deploy, inside Laura's existing CA$0.50/day.
- **S-2 (LOW).** Rolling back from bcce679 is safe for the schema. It is not safe for privacy
  once the unified thread has been used.

Neither is a blocker. S-1 is owner-authorised behaviour (D-W4-LAURA-CEO) with ceilings
enforced in code. S-2 only matters after an activation that is itself gated.

| Item | |
|---|---|
| Reviewer | W-SECREVIEW-bcce679. I am independent and wrote none of the code reviewed. |
| Date | 2026-10-20 (UTC) |
| Mode | Read-only. No deploy, no production request, no paid call, no secret read. Every test and probe ran in a network namespace with no network (`unshare -rn`). |
| Candidate | `claude/final-candidate-bcce679` = `bcce679` |
| Base | `claude/final-candidate-b997efd` = `b997efda` |
| Merges | `79285c4` (b997efd + LAURAONE a112da1), `ffe88d9` (+ freeze c13e20d) |
| Harness fix | `e24f6f6` |
| Diff | `git diff b997efd..bcce679`: 52 files, +8361/−143. Under `src/`: 25 files, +3693/−95. |

**Out of scope, covered by other reviews:**
- Unified Laura's own code: `INDEPENDENT_SECREVIEW_LAURAONE.md`.
- The delta a4a6841..c13e20d: running separately.
- b997efd itself: `INDEPENDENT_SECREVIEW_b997efd.md`.

This review looks only at what the integration could break.

## Findings at a glance

| ID | Severity | Where | One line |
|---|---|---|---|
| S-1 | LOW | `app/command_center/static/js/views/laura.js:310`, `api.py:1093`, `laura/executive/loop.py:756` | LAURACEO's paid Anthropic calls are not behind any activation switch. They run on deploy if `laura` has CA$0.50/day and `ANTHROPIC_API_KEY` is set. |
| S-2 | LOW | `laura/private/store.py:248-262`, `private_context.py:302,464-480` (new); b997efd `store.py:219-228` | Rolling back to b997efd/b931d17 after the unified thread was used drops the H-1 and L-5 protections: excluded or business turns can reach the private model, and forgotten turns can survive in `xing` rows and `laura_boundary_crossings`. |
| S-3 | INFO | `api.py:1335-1340` | `/laura/unified/feed-preview` is owner-session only. It is not switch-gated and needs no private grant. Business data only. |
| S-4 | INFO | `credentials.py:456-471`, `:83` | The credentials page lists a Venice card (status UNKNOWN) even when Venice is not selected. Its PERMISSION text names `venice-uncensored-1-2`, while `BRAMBLELOOP_PRIVATE_MODEL` may choose another model. |
| S-5 | INFO | `tests/w4_pl_harness.py:93-97` | The new refusal raises AssertionError, which the reply path turns into `PROVIDER_ERROR`. It "fails the test" only where the test asserts the outcome. This is the same as the pre-freeze Anthropic refusal. |
| S-6 | INFO | `tests/test_cert_spend_hosts.py:36-49` | I16 (whole-file declaration) now also covers `api.venice.ai` in `credentials.py`. `test_w4_venice.py:679,683` pins both Venice URLs, which mitigates it. |

## (1) Merge resolutions

**Conflicts.** `79285c4` had one textual conflict, in `tests/test_cert_spend_hosts.py`
DECLARED. `ffe88d9` merged clean. I checked both with `git show --cc` against both parents.

### `gateway/credentials.py` (auto-merged): SAFE

- **b997efd's `model_for` is intact (`:103-112`).** `PROVIDERS["anthropic"]` still has
  `model_task: "asset_inspection"` and no `model` key (`:76-78`), so the count_tokens body
  still asks about the routed vision model (`:246`). LAURAONE added `PROVIDERS["venice"]` with
  a fixed `model` (`:83`), so `model_for("venice")` returns that string. Only
  `owner_action`'s message uses it (`:488`). No request uses it.
- **b997efd's I8 domain-separated fingerprint is unchanged (`:115-127`).**
- **`_http` (`:143-166`)** now opens through `venice.no_redirect_opener()` (`venice.py:115-129`).
  This applies to the BFL and Anthropic checks too.
  - It is stricter: a 3xx comes back as `HTTPError`, and no credential header is forwarded.
    Before, urllib's default handler followed redirects with the `x-key`/`x-api-key` headers.
  - `build_opener` still installs the default `ProxyHandler`, so proxy behaviour is the same
    as `urlopen`.
  - The success body is now read whole, up to 2 MiB. Larger is refused (status 0 → OUTAGE).
    Before, it was cut to 2,000 characters.
  - Every stored `why` is still redacted, then cut to 300 characters (`:218,255,322`), and
    the record is redacted again as a whole (`:438`). The longer body cannot put a key into a
    record.
- **The Venice check is skipped unless `BRAMBLELOOP_PRIVATE_PROVIDER=venice` (`:415-416`).**
  With the switch off, no request is made and no row is written, so no notification card is
  raised (`notification_candidates` needs a row, `:501-502`). `_venice_models` sends no
  Authorization header (`:361`).

### `tests/test_cert_spend_hosts.py` DECLARED: SAFE and accurate

- Both sides' entries are kept and none is removed. The merged description of
  `credentials.py` is true: BFL credits, count_tokens, and Venice's two no-inference GETs,
  owner-enabled only.
- The `gateway/venice.py` entry says "laura_register reserves via check_budget_cad first".
  That is correct: `VeniceProvider` is constructed only at `laura_register.py:525`, after
  `gw.check_budget_cad(..., agent=AGENT)` at `:531`. A grep of `src/` finds no other caller of
  `VeniceProvider`.
- Suite result: PASS, 0 failing.

### b997efd's security fixes: none undone or bypassed

- **Untouched files.** `git diff --quiet b997efd bcce679` holds for `app/main.py` (B1 byte
  route; `/api/audit` and `_shorten_digests`/I7 at `:4936-4964`), `gateway/images.py`,
  `experiments/` (M1 resume settle), `app/command_center/auth.py` (gate, `PUBLIC_ROUTES`,
  step-up) and `gateway/anthropic.py` (atomic reservation). They are byte-identical.
- **No new byte-serving or credential-bypass code.** The added lines under `src/` contain no
  `FileResponse`, `StreamingResponse`, `ArtifactStore`, `presents_operator_credential`,
  `PUBLIC_ROUTES` or `@app.` route.
- **New audit rows on the public `/api/audit`.** The merged code adds one audit writer,
  `venice_context.record_sent` (`laura/agency/venice_context.py:371-380`).
  - It writes the pack's sha256, field names, counts and bytes, never a value.
  - It runs only with `BRAMBLELOOP_LAURA_BUSINESS_TO_VENICE=1`.
  - Without the operator credential, b997efd's I7 regex cuts the digest to 12 hex characters
    in both `artifact` and `detail`.
  - `private_context.py` and `laura/private/store.py` state, and a grep confirms, that they
    write nothing private to `audit_log`.
- **Business timeline report** (`loop.py:677-722`). It contains counts and CA$ totals only,
  and the timeline is owner-only (Command Center).
- **Regression suites on bcce679:** see (6).

## (2) New routes in the merged app

There are eight new routes, all under `/api/cc/`. They are therefore inside `auth.gate`'s
default deny: owner session, same-origin, and `X-CSRF-Token` + single-use nonce + timestamp on
POST. `PUBLIC_ROUTES` is unchanged (only `auth/status` and `auth/login`).

I sent unauthenticated requests, then owner-session requests, to each route (in-process
`TestClient`, network namespace with no network).

| Route | Unauthenticated | Owner, switches OFF | Owner, unified ON, no private grant |
|---|---|---|---|
| `GET /laura/costs` | 401 | 200 no-store (costs summary) | — |
| `POST /laura/converse` | 401 | 200 no-store (unavailable: no key in test) | 409 `UNIFIED_THREAD` by code (`api.py:1104-1109`) |
| `GET /laura/unified/status` | 401 | 200, `unified=off`, non-content | — |
| `POST /laura/unified/view` | 401 | **404 `UNIFIED_OFF`** | 403 `PRIVATE_REFUSED` |
| `POST /laura/unified/turn` | 401 | **404 `UNIFIED_OFF`** | 403 `PRIVATE_REFUSED` |
| `POST /laura/unified/crossing` | 401 | **404 `UNIFIED_OFF`** | 403 `PRIVATE_REFUSED` |
| `POST /laura/unified/control` | 401 | **404 `UNIFIED_OFF`** | 403 `PRIVATE_REFUSED` |
| `POST /laura/unified/feed-preview` | 401 | 200 no-store (S-3) | 200 |

- **The step-up chain works as designed.**
  - Unified content routes need the private grant. `_principal` → grant, opened only through
    `/private/open` with `auth.require_stepup` (`api.py:1263-1265`).
  - Approving a crossing that needs step-up also needs a step-up performed after the offer,
    and not the login window (`private_context.py:669-686`).
- **The route sweep passes 7/7** (`test_route_auth_default_deny.py`). It enumerates
  `app.routes`, so it covers the new routes.
- **No public exposure.**
  - `main.py` is unchanged.
  - The service worker never intercepts `/api/` (`sw.js:63`). It adds only
    `laura_unified.js` to the shell.
  - `laura_unified.js` and `laura.js` contain no `innerHTML`/`eval`, and their links are
    restricted to `#/`.

## (3) Harness fix e24f6f6: SAFE, stricter only

- **The diff** is `tests/w4_pl_harness.py` +7/−2.
  - It captures the real `VeniceProvider._post` at import (`:33`).
  - Under `enabled(None)`, if `_post` is still the real one, it is replaced by `_refuse`
    (`:93-97`).
  - The `finally` block restores it (`:107`).
- **No assertion changes**, and no test file changes in the commit.
- **Callers that installed their own mock** keep it (the `is` identity check). If a caller had
  mocked before importing the harness, its mock would be captured as "real" and refused. That
  case makes a test fail; it never makes one pass.
- See S-5 for how the refusal surfaces.

## (4) Schema: additive, rollback-safe at the schema level

I read `evidence_INTEG5/pg_migration_output.txt` and INTEG5.md §4, and checked them against
the code.

- **Plain boot:** 136 → 136 tables, with `create_all` changes `[]`.
- **Full lazy surface:** 143 → 145. `+laura_cost_events`, `+laura_boundary_crossings`.
  - They are created lazily by `laura.agency.models.ensure_tables`.
  - No column on an existing table is added, removed or altered.
  - A second boot is a no-op.
  - Booting back to b997efd and to b931d17 changes nothing.
- **The `xing` row kind** goes into the existing `laura_private_entries`. I checked b997efd's
  `store.py`:
  - `facts` and `conversation` filter `kind == "fact"`/`"turn"`, so they ignore `xing`.
  - `sealed_export` and `restore_sealed` carry all rows.
  - `rekey` re-seals non-fact rows with the `"turn"` blind index. The index is part of the
    AAD and is recomputed, so they authenticate, as INTEG5 says.
  - New code finds crossings by `kind` (`store.py:254,438`).
- **Data-level rollback has a privacy gap.** See S-2.

## (5) Switches: every one defaults OFF in code

I read the code and probed it in-process with the variables unset.

| Switch | Code | Unset → | Values that turn it on |
|---|---|---|---|
| `BRAMBLELOOP_LAURA_UNIFIED` | `laura_unified.py:62-70` | `enabled()` False | exactly `venice` (case and space-insensitive) |
| `BRAMBLELOOP_LAURA_BUSINESS_TO_VENICE` | `laura_unified.py:73-78`, `venice_context.py:49-51` | False | exactly `1` after strip (`true`, `yes`, `01` → False) |
| `BRAMBLELOOP_PRIVATE_PROVIDER` | `venice.py:192-200` | `""` (no provider; no Venice credential check) | `venice` or `anthropic` |
| `BRAMBLELOOP_LAURA_PRIVATE_REGISTER` | `laura_register.py:323-337` | `register_switch` False, `enabled` False | `1`, which also needs daily CAD > 0, a provider key and the private memory key |
| `BRAMBLELOOP_LAURA_PRIVATE_DAILY_CAD` | `laura_register.py:302-312` | 0.0 | finite > 0, capped at the agent ceiling |

LAURACEO adds no switch. See S-1.

## (6) Tests run on bcce679

All tests ran offline (`unshare -rn`, `PYTHONPATH=src:tests`, `requirements.lock` + `httpx2`).

| Test file | What it covers | Result |
|---|---|---|
| `test_route_auth_default_deny.py` | route sweep over `app.routes` | 7/7 |
| `test_v11_cc_auth.py` | CC gate, CSRF, nonce, step-up | 16/16 |
| `test_customer_data_auth.py` | customer-data route enumeration | 9/9 |
| `test_w4_integ4_secfixes.py` | B1, L1-L4 | 12/12 |
| `test_w4_integ4_deliverable_routes.py` | B1 byte-route sweep | 4/4 |
| `test_w4_credhealth.py` | I8, leak scan, URL pins | 13 passed, 0 failed |
| `test_cert_spend_hosts.py` | paid-host declarations | PASS, 0 failing |
| `test_w4_venice.py` | Venice transport, credential URLs | 19/19 |
| `test_w4_laura_unified.py` | unified thread, review fixes | 40/40 (see note) |
| `test_w4_laura_ceo.py` | LAURACEO | 13/13 |
| `test_w4_pl_boundary.py`, `_budget.py`, `_continuity.py` | private register | all OK, exit 0 |
| `test_w4_pl_leak.py` | private-to-business leak | 2/2 |
| `test_w4_pl_reply.py` | private replies | 3/3 |
| `test_w4_plact.py` | activation status | 8/8 |
| `test_w4_ccfm1.py` | Command Center money view | all OK, exit 0 |
| `test_w3_laura_cc_providers.py` | Laura provider surface | 7/7 |

**Note on `test_w4_laura_unified.py`.** On the first run it reported 39/40:
`test_review_m2_the_bearer_key_is_never_forwarded_on_a_redirect` got status 0. That came from
my sandbox, not the code. The test starts two HTTP servers on 127.0.0.1, and a fresh network
namespace has its loopback interface down. I brought `lo` up inside the namespace (still no
external route) and reran it: **40/40**. The M-2 test passed, so the redirect refusal holds for
both `VeniceProvider._post` and `credentials._http`.

I also probed the eight new routes directly; the results are in (2).

## Findings

### S-1 (LOW): LAURACEO's paid calls start on deploy with every switch OFF

- **Where:**
  - `static/js/views/laura.js:310`: the Ask box now calls `api.lauraConverse`, where it
    called `lauraAsk` before.
  - `api.py:1093-1113` (`/laura/converse` → `ceo_chat.converse` → `laura_converse.call`).
  - `laura/executive/loop.py:611-674,756` (`_model_rank` on every executive tick).
- **What gates them.**
  - Gates: `laura_converse.available` (`laura_converse.py:120-133`), which needs Laura's
    registry ceiling > 0, room in the purpose allocation, and an Anthropic key.
  - Production values: `laura` has had CA$0.50/day since the owner's 2026-10-11 decision
    (`agents/registry.py:839`), and `ANTHROPIC_API_KEY` is required by the vision checks, so it is normally set. I did not read production; this is inferred.
  - None of the four switches in (5) gates these calls.
- **Scenario.** bcce679 is deployed with every switch unset. After that:
  1. Every question the owner types in the Command Center's Laura view becomes a cheap-tier
     Anthropic call (`laura.converse@1`).
  2. The heartbeat's executive tick makes up to two standard-tier calls per UTC day
     (`laura.exec_rank@1`) whenever there are two or more delegable priorities.
  3. Both draw on the same CA$0.50/day as `laura.business_phrase@1`.
- **What bounds it.**
  - The calls are owner-approved (D-W4-LAURA-CEO, D-W4-LAURACEO-ROUTE).
  - Code enforces the bounds: the CA$0.50/day agent ceiling, atomic reservation, the CA$100
    month, and allocation stops of converse CA$8, executive CA$5 and exec_rank CA$2.
- **Why it is still a finding.** The release brief describes a deploy "with all switches OFF"
  as inert. It is not inert for Business Laura. The tick call also runs with no owner action
  at all.
- **Fix.**
  - Option 1: add `BRAMBLELOOP_LAURA_CEO_MODEL` (default OFF), checked in
    `laura_converse.available`. Off means the Ask box stays on `/laura/ask` and the tick keeps
    the deterministic order.
  - Option 2: state in the deploy note that LAURACEO spend begins on deploy, at most
    CA$15/month inside the existing ceilings.

### S-2 (LOW): rolling back the code after unified use drops the H-1/L-5 protections

- **Where.**
  - New code: `private_context.py:302,464-480`, the shared context builder. It skips
    `excluded` turns and replaces business exchanges with `BUSINESS_PLACEHOLDER`.
  - New code: `store.py:248-262`. `forget` also deletes `xing` rows that quote the turn.
  - New code: `private_context.py:774-797`. Forget and mark-private also redact the
    business-side `laura_boundary_crossings` rows.
  - b997efd: `store.py:205-228`. `conversation` returns every `turn` row and ignores the
    sealed `label`/`excluded` flags. `forget` deletes only the record and its reply.
- **Scenario.**
  1. The owner turns on the unified thread.
  2. The owner marks some turns "exclude from model context" or "private", and holds some
     business exchanges in the thread.
  3. The release is then rolled back to b997efd or b931d17.
  4. If the old split private register is enabled (old provider: Anthropic), the next private
     reply sends the last turns to the model, excluded and business-labelled ones included.
  5. Also, a "forget" done under the old code leaves the sealed `xing` row with the quoted
     text, and the plaintext approved text in `laura_boundary_crossings`.
- **Impact.** This is the H-1 exposure brought back by a code rollback. INTEG5 §4 calls the
  rollback safe, which holds for the schema only. Nothing happens until the gated unified
  thread has actually been used.
- **Fix.** Add a rollback rule to the runbook and INTEG5 §4: "after the unified thread has
  been used, do not roll back below bcce679 with `BRAMBLELOOP_LAURA_PRIVATE_REGISTER=1`. Turn
  the register off first, and forget turns before rolling back." An alternative is to ship a
  tiny forward-compatible filter (skip `excluded`/`label=business` payloads) in any hotfix
  branch kept for rollback.

### S-3 (INFO): `feed-preview` is not switch-gated and needs no private grant

- **Where:** `api.py:1335-1340` → `venice_context.preview` (`venice_context.py:356-368`).
- **What it returns:** with a plain owner session (no step-up, no grant, either switch state),
  it returns the allowlisted business pack with values: phase, counts, spend, revenue total,
  priority and decision titles.
- **Why it is only INFO:**
  - Everything in it is business data the owner already sees elsewhere in the Command Center.
  - The pack's deny patterns exclude customer data, and it reads no private table.
  - The response is `no-store`.
- **The only inconsistency** is with the section comment ("Off by default").
- **Fix (optional):** return `{"enabled": false}` without values while
  `BRAMBLELOOP_LAURA_BUSINESS_TO_VENICE` is off.

### S-4 (INFO): the Venice card is shown before Venice is selected; the model name is fixed

- **Where:** `credentials.state` (`credentials.py:456-471`) and `PROVIDERS["venice"]["model"]`
  (`:83`).
- **The card.** `state` iterates every provider, so the owner page shows a Venice row,
  status UNKNOWN, with no check run. The module docstring says "no request, no record, no
  card". Requests and records are indeed absent. The page row is cosmetic. There is no
  notification.
- **The model name.** The PERMISSION advice names `venice-uncensored-1-2` even when
  `BRAMBLELOOP_PRIVATE_MODEL` selects another eligible model.
- **Fix:** skip the Venice row unless it is selected, and use `venice.model(env)` in
  `model_for("venice")`.

### S-5 (INFO): the harness refusal is reported as `PROVIDER_ERROR`

- **Where:** `tests/w4_pl_harness.py:93-97`.
- **What happens:** `_refuse` raises AssertionError inside the transport. The reply path's
  sanitising `except` turns it into `PROVIDER_ERROR` instead of letting it fail the test.
- **What it means:** a suite that does not assert the reply status would not notice an
  unexpected request. It still could not reach the network.
- **This is the pre-freeze behaviour of the Anthropic `_send` refusal. It is not a
  regression.**
- **Fix (optional):** record the refusal in a list and assert in `enabled()`'s `finally` that
  the list is empty unless the caller allowed it.

### S-6 (INFO): I16 now covers Venice too

- **Where:** `tests/test_cert_spend_hosts.py:36-49`.
- **What changed:** `credentials.py` now holds a third host, `api.venice.ai`, under the same
  whole-file declaration, so a future billable Venice call added there would pass the
  scanner.
- **Mitigation:** `test_w4_venice.py:679,683` pins both Venice credential URLs, and `:172`
  pins the chat URL in `venice.py`.
- **Fix:** carry I16's open fix, a per-URL allowlist, forward.

## Verdict

**bcce679 may be deployed with every activation switch OFF.**

- Nothing in the integration undoes or bypasses b997efd's B1, `/api/audit` truncation,
  L1-L4, M1, I7 or I8. The files that hold them are byte-identical.
- The `model_for`/Venice merge in `credentials.py` is correct and slightly stricter
  (no redirects).
- The unified routes are owner-only, behind the private grant and step-up, and return 404
  while the switch is off.
- The harness fix only tightens the tests.
- The schema change is additive and boots back cleanly.

**Two things the owner must know before deploying:**
- **S-1:** Business Laura's model chat and the tick's ordering begin spending on deploy,
  bounded by the CA$0.50/day ceiling.
- **S-2:** after the unified thread has been used, rolling the code back needs the private
  register off first.

The LAURAONE review's own activation blockers (B-1 etc.) are tracked there and are not
re-judged here.
