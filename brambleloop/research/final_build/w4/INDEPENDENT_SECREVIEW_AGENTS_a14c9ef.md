# Independent security review: W4-AGENTS at a14c9ef

- **Reviewer:** an independent Claude Code context. It did not write this code. It reviewed and reported only; nothing was fixed.
- **Date:** 2026-10-26 (UTC).
- **Scope:** `git diff b5226f77..a14c9ef8 -- brambleloop/src brambleloop/tests` on `origin/claude/w4-AGENTS` (83 files, +8235/−416, including the merges of `w4-LISTREADY` (bd9c6cd) and `w4-VISNEXT2` (13bd73e)). Read alongside it: `research/final_build/w4/AGENTS.md`, `DEPARTMENTS.md`, and the prior review `INDEPENDENT_SECREVIEW_AGENTS_b5226f7.md`.
- **Method:**
  - I read the M-1/M-2 fix commit (a14c9ef) in full, with `core/sealed_chain.GrantLedger`, the Command Center action route (`app/command_center/api.py:798-817`) and `approvals.execute`.
  - I traced the deployment topology (`railway.json`, `Dockerfile`, `app/runner.py`, `research/final_build/v1_1/CLOUD_HOSTING_PLAN.md`).
  - Two sub-reviews ran in parallel, one on the department capabilities and one on merge correctness. I spot-checked their load-bearing claims against the code. The sub-reviews used `git show --remerge-diff` and diffs against each merge parent.
- **Rules followed:** no network, no Etsy calls, no paid calls, no secrets, no deploys. Every test ran at `nice -n 19` in a scratch venv built from `requirements.txt`.

## Verdict

**PASS for shipping this branch with every write flag OFF and SHADOW on. No Critical or High findings.**

| # | Question | Result |
|---|---|---|
| 1 | M-1 and M-2 closed, with tests | **M-1 closed.** **M-2 closed in code but not in the deployed topology** (M-2R below). Both have real tests. |
| 2 | No grant minted by the worker or without the signing key; no key in the repository | Holds when the worker is a separate process. **In today's single-container deployment the embedded worker shares the web process's environment, which holds the signing key** (M-2R). No key material is in the repository. |
| 3 | Quality sweep never certifies, revokes or blocks | Holds. It writes only P2 `halts_publication=False` incidents, audit rows and non-protected check jobs. One indirect effect is noted in L-2. |
| 4 | `cir.revise` cannot yield an uncertified publishable pattern | Holds. It enqueues `cir.compile` only, which goes back through `gate.certify` and PT-03 immutability. |
| 5 | Competitor snapshot stores no competitor text, URLs or images | Holds for text, URLs and images. The group key embeds a competitor shop name (L-3). |
| 6 | No new paid, Etsy-write or publication path | Holds. |
| 7 | No test weakened | Holds. Every edit to a pre-existing test is justified, and several are stricter. |
| 8 | Merge correctness against LISTREADY, incl. E3 `policy_additional` | Holds. E3 is enforced in more places on HEAD than on LISTREADY's tip. |

M-2R has to be resolved before `BRAMBLELOOP_STOREFRONT_WRITES_AUTHORISED=1` and the storefront key pair are set in any publishing phase. Nothing in it is reachable in SHADOW: no key pair is configured, the kill switch is off, and `store.update` holds in SHADOW before any client or credential is built (`runtime/storefront_ops.py`, unchanged since the prior review).

## 1. M-1: owner-session approval (closed)

**Verified:**
- `app/storefront_authority_api.py` no longer has bearer `/approve` or `/rebase`. The bearer may list, preview and revoke, and revoke is deny-only.
- `approvals.ACTIONS` has four storefront actions (`approvals.py:42-47`). `storefront.approve` and `storefront.rebase` are flagged `True`, so `run_action` calls `auth.require_stepup` before executing (`api.py:804-805`). The `/api/cc/` router supplies the session, CSRF and nonce gate.
- `storefront_authority.approve` and `rebase` no longer take an `authorization` argument. Both refuse unless `stepped_up is True`. The grant records principal `owner:command-center`, the actor, `stepped_up: True` and a reason tagged "owner via command center".
- `_check_one` refuses a grant row that lacks `stepped_up`.
- The `storefront:write_authority` owner card now points at the Command Center action (`storefront_ops.py:101-103`).

**Tests:** `test_w4_agents_secfix.py` exercises the real HTTP route through `TestClient`:
- a request with no CSRF header is refused;
- a stale step-up gets 403 `STEP_UP_REQUIRED`;
- a fresh step-up records the grant;
- the bearer `/approve` and `/rebase` return 404 or 405, and the bearer revoke still answers.

Result: **6/6 passed.**

## 2. M-2: Ed25519 signing (closed in code; residual M-2R in deployment)

**Verified in code:**
- `_seal` signs with `BRAMBLELOOP_STOREFRONT_SIGNING_KEY`, an Ed25519 private key. `_verify` uses `BRAMBLELOOP_STOREFRONT_VERIFY_KEY`, the public key (`ops/storefront_authority.py:64-115`).
- `GrantLedger.verify_row` uses `verify` when one is supplied (`core/sealed_chain.py:184-196`), so verifying a row never needs the signing key. The HMAC families are unchanged.
- Fail-closed paths all hold:
  - missing or invalid key → `ValueError` → the row is refused;
  - foreign key pair → `append` refuses with "does not verify", and `validate` refuses;
  - a holder of the ops token without the signing key cannot mint.
- The keys are base64 environment variables. `generate_keypair()` runs at runtime in the tests. No private key and no `BEGIN … PRIVATE KEY` block exists in any tracked file. `cryptography>=42` is already a dependency (`requirements.txt:16`, locked at 50.0.1).

### M-2R (Medium, deployment): the worker *is* the web process today, so it holds the signing key

- **Where:**
  - `app/runner.py:16` and `:373`: `BRAMBLELOOP_EMBEDDED_WORKER` defaults to `"1"`, and the worker and scheduler then run as threads inside the uvicorn process.
  - `railway.json`: one service, uvicorn only.
  - `CLOUD_HOSTING_PLAN.md:305`: production config is `BRAMBLELOOP_EMBEDDED_WORKER=1`. The split is "documented, not recommended now" (`:123`), for cost.
  - `AGENTS.md` §6 tells the operator to set the signing key "on the web service only".
- **What:** in the deployed topology the web service runs the job handlers in its own process. Setting the signing key "on the web service" therefore puts it in `os.environ` for every job handler and every dependency the worker imports. That is exactly the M-2 scenario: a future handler, or a compromised dependency, calls `storefront_authority.approve(..., stepped_up=True)` or `LEDGER.append`. `stepped_up` is a caller-asserted boolean, not a proof, so the grant would be genuine and every downstream gate would pass.
- **Why the tests do not catch it:** `test_m2_the_worker_verifies_with_the_public_key_and_cannot_sign` simulates the worker by popping the signing key from the environment, which assumes a split that does not exist in production.
- **Partial mitigation:** `test_m2_no_worker_side_module_calls_approve_rebase_or_reads_the_signing_key` statically scans six packages. It does not scan `intel/`, `visual/`, `creative/`, `ops/` or `gates/`, which also register worker handlers. It does not catch `getattr` or `importlib` access, `sfa._seal` used as an attribute, or `sfa.LEDGER.append`.
- **Scenario:** the operator follows AGENTS.md §6 on the current single Railway service. A storefront handler (or an imported library) mints a 24 h grant for a recorded proposal. With the kill switch on and a publishing phase, the next `store.update` sends it. The blast radius is still bounded: announcement, buyer messages and new section titles only, using repo-drafted text that passes the truth lint.
- **Fix:** any one of the following.
  1. Make signing refuse in a process that runs jobs, and pin it with a test. In `_seal`, raise unless `BRAMBLELOOP_EMBEDDED_WORKER == "0"`. Also have `worker_entry` refuse to start when `SIGNING_KEY_VAR` is set. Storefront approval then becomes possible only after the services are split. That split is an owner spend decision; record it as a precondition in BUILD_STATE.
  2. Move signing out of the server: the owner's device signs the previewed digest (WebAuthn or a passphrase-derived key in the browser), and the server stores only the public key. This is the stronger form and needs no extra service.
  3. At minimum, correct AGENTS.md §6: "web only" gives no separation while `BRAMBLELOOP_EMBEDDED_WORKER=1`. Widen the AST scan to all of `src/brambleloop` except `app/command_center/approvals.py` and `ops/storefront_authority.py`, and include `LEDGER` and `_seal` attribute access.

### Info items on M-1/M-2

- **I-1:** `revoke(db, approval_id, actor=...)` skips `opsauth.check` whenever `actor` is passed (`storefront_authority.py:174-179`). It is in-process only and deny-only, so this is acceptable. Revoking appends a signed row, so revoke also needs the signing key. A process without it cannot revoke, but such a process cannot hold a grant either.
- **I-2:** any storefront grant row sealed with the old HMAC (before a14c9ef) no longer verifies. The whole family then fails closed and opens a P1 tamper incident until the owner rebases. This is safe. If production has such rows, expect that incident on first verification after deploy.

## 3. Quality & Compliance re-verification sweep (`runtime/quality_ops.py`)

**PASS: it never certifies, revokes or blocks.**
- **Writes:** the sweep writes only these:
  - `Incident(severity="P2", halts_publication=False)` (`quality_ops.py:142-149`; the detail says "the certificate is unchanged and nothing was blocked");
  - audit rows;
  - enqueues of `cir.twin`, `cir.reverse`, `gate.asset_truth` and `gate.policy`, none of them protected.
- There are no writes to PatternVersion, certificates, `release_gates` or Listing.
- **No automatic consumer** blocks on a non-halting P2:
  - `publication_halted` needs `halts_publication`;
  - `escalate_systemic` counts only halting rows;
  - Laura's priorities read only P0 and P1.
- **Tests:** the sweep's clean path asserts that the certificate is unchanged. `test_w4_departments` 12 OK.

**L-2 (Low): a `gate.policy` re-verification incident flips a scale condition.**
- **Where:** `scale/evidence.py:143-144,204`.
- **What:** the signature is `quality.reverify:gate.policy:<slug>@<v>`. It matches `Incident.signature LIKE '%policy%'`, so while one is open, `no_open_policy_risk` reads false.
- **Severity:** conservative (it can only withhold scale readiness), but it is an automatic effect of a "detection-only" incident.
- **Fix:** match the policy incidents by prefix, or choose a signature without the substring.

**L-4 (Low): re-verification incidents never auto-resolve, and freshness is optimistic.**
- **Where:** `quality_ops.py:130-151` and `:215-218`.
- **What:**
  - A later passing check does not close the open incident, so stale P2s accumulate.
  - A release counts as freshly re-verified if any one of the four checks wrote an audit row.
  - `reverify` at `:159` has no `try`, so a check that keeps raising goes unseen.
- **Fix:** resolve on `ok=True` with the same signature. Count a release fresh only when all four checks have a reading. Record a handler exception as a finding.

## 4. `cir.revise` (`runtime/engineering_ops.py`)

**PASS.**
- **Writes:** it writes audit rows and one `cir.compile` enqueue (`engineering_ops.py:120-131`). It writes no CIR, PatternVersion or certified flag.
- **Certification:** the compiled result still goes through `gate.certify` (`pipeline.py:833`) with:
  - the incident halt (`:911`);
  - the older-version refusal (`:926`);
  - PT-03 certified-version immutability (`:976`, `:1336`).
- **Properties:** it is deterministic, with no model call. It is bounded by `MAX_REVISIONS=1`, and fingerprint keys make it idempotent.
- **I-3:** a negative `revision` input passes the bound (`engineering_ops.py:104`, `pipeline.py:821`). In practice this is unreachable, because the job is enqueued only by our own failed-compile path. Clamp with `max(0, …)`.
- **Test gap:** the tests cover the bound and the re-compile, but no test covers certify-after-revision or the PT-03 overwrite refusal.

## 5. `radar.competitor_snapshot` (`runtime/intel_ops.py`)

**PASS for text, URLs and images.**
- The query selects only `benchmark_key`, `pod`, `price_cad`, `on_sale`, `media_count`, `seasonal`, `product_type` and `first_seen` (`intel_ops.py:43-47`). It never selects title, URL, `listing_ref` or tags.
- The audit records counts only.
- `children.py:94-101` reads competitor titles but outputs only counts and a fixed list of our own style words.

**L-3 (Low): the snapshot group key names a competitor shop.**
- **Where:** `intel_ops.py:61`, `"benchmark": bk`.
- **What:**
  - `benchmark_key` is our own key, but it embeds the shop name (e.g. `mjs_off_the_hook_designs`, `intel/benchmarks.py:33`).
  - `_assert_no_content` (`:76-80`) checks only top-level keys. It does not check the values under `seasonal` or `product_types`. Today those values are Etsy `taxonomy_id`s and our own labels, so nothing leaks, but nothing pins that.
- **Fix:** alias or hash the benchmark key in the snapshot, and allowlist the inner values (digits or our own label set).

## 6. Paid, Etsy-write and publication paths

**PASS.** None of the department commits adds a gateway, Anthropic, FLUX/BFL, HTTP, `store.*` or publish call.
- `etsy_ops.store_reading` writes a local `OperatingReading` only.
- `image_bench` (F-126) returns early as superseded (`runtime/release.py:7802-7807`), before any budget logic. That is less spend, not more.
- The F-218 sentinel (`visual/drift_series.py:157`) opens a `halts_publication=True` incident with no `product_slug`. Per `gates/incidents.py:96-109`, that halts no product. The behaviour matches the existing drift incidents.
- The F-365 Baby & Kids row in the Director is advisory and drafts no `createShopSection`.
- **Authority classes:**
  - `radar.competitor_snapshot`, `creative.family_engine` and `intel.children_portfolio` are read-only;
  - `cir.revise` is build;
  - `gate.quality` and its checks are test;
  - none is protected.
- `gate.quality` and `creative.family_engine` are in `SAFE_GENERATED` and `generatable`. `charters.validate()` still refuses protected or unlisted generatable types.
- The VISNEXT2 merge leaves `visual/image_production.py` and `creative/flux3_generator.py` identical to VISNEXT2's tip. The other differences only add guards:
  - resume re-sends nothing unless every earlier paid call was DECLINED;
  - LISTREADY's batch-scoped launch-review grant is checked under the budget lock, after the monthly cap.

## 7. Edits to existing tests: none weakened

| Test | Change | Assessment |
|---|---|---|
| `test_w4_agents.py:223-228, 335-345` | Now expects that `policy_additional` is *not* an owner step, and that OA-E is created | Matches E3 and LISTREADY's evidence-close rule. Justified. |
| `test_etsy_surfaces.py`, `test_w4_etsysurf.py` | LISTREADY E3 and FIRSTSALE2 rewrites | Byte-identical to LISTREADY's tip. Each loosened assertion is replaced by a check on the gate's own answer. Justified. |
| `test_roles.py:358-366` | `DECLARED_BUT_UNBUILT` is shorter | Stricter. |
| `test_w4_listready.py` | The merge adds F8 assertions: `_authorise_storefront_write` is required, and the shadow write lane is forbidden for storefront writes | Stricter. No lines were removed against LISTREADY's tip. |
| `test_w4_close5_rows.py`, `test_w4_shopsync.py` | No change since b5226f77 except additions | Additive. |

**Gap (Low):** no test shows that a *valid* storefront grant still refuses `policy_additional`. The code is correct: `live_state.write_refusal` checks `EU_ONLY` before the grant is considered (`live_state.py:171-174`). The prior review's probe confirmed this, but nothing pins it.

## 8. Merge correctness against LISTREADY (bd9c6cd) and VISNEXT2 (13bd73e)

**PASS. No LISTREADY rule was lost.** Only `store_readiness.py` and `autonomy_map.json` (a generated file) had real conflicts.

**E3 on HEAD:**
- `director.py:266-270` always records `policy_additional` as PROTECTED / `NOT_A_CHECK`. `owner_gaps` counts only `MISSING`.
- AGENTS' earlier `SET_ON_NON_EU_SHOP` "clear the additional-terms field" step was removed. The Director can no longer emit any ask or card for `policy_additional`.
- `live_state.write_refusal` refuses `EU_ONLY` unconditionally, before any grant. LISTREADY's own tip did not have this check, so HEAD is stricter.
- The only updateShop sender, `integrations/etsy.py`, runs every field through `write_refusal(grant=…)`.

**Other LISTREADY rules on HEAD:**
- **OA-E** again closes only on getShop evidence.
- **R1:** `delivery_policy` is attested by the owner session with step-up (`shop_observations.py:31-33`).
- **R2:** store-setting confirmations require step-up (`api.py:854-856`).
- **R3:** OA-F merges only into an open policy card (`store_readiness.py:441, 494-497`).
- **R4:** the Etsy listing census (`release_recovery.py:310`).
- **R11:** `identity_verified` (`launch/readiness.py:239-253`).
- `shop_observations.py`, `shop_sync.py`, `launch/readiness.py`, `release_recovery.py` and `command_center/readers.py` have no diff against LISTREADY's tip.

**L-5 (Low, design, not a LISTREADY loss): the OA-D1 card is superseded with nothing replacing it.**
- **Where:** `store_readiness.py:406-411, 505-514`.
- **What:** OA-D1 (create shop sections) is marked SUPERSEDED as agent work. While `store.update` holds in SHADOW, the owner sees neither a sections card nor a grant ask, unless a `store.update` actually raises `storefront:write_authority`.
- **Fix:** close OA-D1 on evidence (the shop_sync sections reading), or keep it until the grant card is open.

**I-4:** `director.validate_change` (`director.py:118-119`) detects owner-field and EU-only refusals by matching words in the refusal message. That match would break silently if the message were reworded. The Etsy client still blocks the write, so this is defence in depth only. Compare against `live_state.EU_ONLY` and `OWNER_CONFIGURED` directly.

**I-5:** LISTREADY's tip has two later commits (58b2e98, 82a3b7a), with owner approval, that raise the `test_cert_wiring` drain limit to 1525 s. HEAD keeps 1200 s, which is stricter. Expect that test to need the same change when LISTREADY is next merged.

## Tests run by the reviewer

All runs used `nice -n 19` and `PYTHONPATH=src:tests` in a scratch venv. Every one exited 0.

| Suite | Result |
|---|---|
| `test_w4_agents_secfix` | 6 OK, 0 failed |
| `test_w4_agents` | 0 failed |
| `test_w4_store_live_state` | 12 passed |
| `test_w4_storefront_checks` | 15 OK |
| `test_w4_listready` | 31 OK |
| `test_w4_departments` | 12 OK |
| `test_w4_children` | 5 OK |
| `test_roles` | 35 OK |
| `test_route_auth_default_deny` | 7/7 |
| `test_w4_visnext2` | 11 passed |

## Required and recommended actions

1. **Before any storefront key pair or kill switch is set in a publishing phase:** fix M-2R. Refuse signing in any process that runs jobs, and split the worker out (an owner spend decision). Better still, have the owner's device sign. At least correct the AGENTS.md §6 operator instructions and widen the AST scan.
2. L-2: remove the `%policy%` collision between quality incidents and scale readiness.
3. L-3: alias the competitor benchmark key in the snapshot and allowlist the inner values.
4. L-4: auto-resolve re-verification incidents, and require all four checks before a release counts as fresh.
5. L-5: close OA-D1 on evidence, or keep it until the storefront grant card is open.
6. Add tests: a valid grant still refuses `policy_additional`; certify-after-`cir.revise` and the PT-03 refusal; the snapshot's inner values.
7. Carried from b5226f7, still open: L-1 (Laura's delegation ordering) and L-2 of that review (the DIFFERS overwrite preview).

---
_Generated by [Claude Code](https://claude.ai/code)_
