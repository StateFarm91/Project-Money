# INTEG5 (2026-10-20): Unified Laura on top of the first-sale candidate b997efd

Integrator: W-INTEG5. Worktree `.claude/worktrees/W4-INTEG5`, branch `claude/w4-INTEG5`, created from
`origin/claude/final-candidate-b997efd` (b997efda). Production: b931d17, SHADOW. No deploy, no
production write, no spend, no credential change, no Railway change, and no switch set. Production
contact: none (local PostgreSQL only).

Goal (owner): "a real working Laura to test, not another round of architecture planning". The release
is the smallest one that does that: b997efd plus Unified Laura (`claude/w4-LAURAONE`, which already
contains LAURACEO and VENICE-adult-wip). **Not included:** CLOSE6, VISNEXT2, FIRSTSALE2 or any other
branch.

Status: **PHASE B**. LAURAONE a112da1 was merged in Phase A. The freeze
`claude/w4-LAURAONE-freeze` @ c13e20d was merged in Phase B, as row 2 of the table in §1.

## 0. Environment note: the b997efd suite was lost

The container restarted at about 20:44Z, so at 20:46Z uptime was 1 minute. The b997efd full suite
(`W4-FCb997efd/brambleloop/artifacts/suite_runs/20261020T195156Z-15285.json`) is no longer running:
its record has `exit_code: null` and `finished_utc: null`, and no `run_tests.sh` process exists. That
record also names `python: /usr/bin/python3.11`, not venv-integ4. W-INTEG5 did not touch that
worktree or restart its suite; the coordinator was told at 20:47Z. The local PostgreSQL was also
gone, so a fresh cluster was created (§4).

## 1. Merges

| # | Branch @ head | Merge commit | Conflicts and resolution |
|---|---|---|---|
| 1 | w4-LAURAONE @ a112da1 (Unified Laura; contains LAURACEO a3eec7b and VENICE-adult-wip 3cf3c8b). Merge base with b997efd: 6531769 (the INTEG4 checkpoint). | 79285c4 | One conflict, in `tests/test_cert_spend_hosts.py` `DECLARED` (§2). `DECISION_LOG.md` and `BUILD_STATE.md` merged cleanly and append-only: 0 lines removed relative to either parent (+178 and +29 lines relative to b997efd). |

| 2 | w4-LAURAONE-freeze @ c13e20d: the security-review fixes (B-1, H-1, M-1, M-2, L-1..L-6, I-2, I-4) and the INTEG5 finding (@3 only on Venice, `REGISTER_NEEDS_VENICE`) | ffe88d9 | none. `credentials.py` auto-merged again; `model_for`/`model_task` are intact. No change to DECISION_LOG.md. The decision index is unaffected. |
| - | INTEG5 harness fix (§3a) | e24f6f6 | — |

`gateway/credentials.py` auto-merged both sides and was checked by hand:
- **b997efd (INTEG4):** Anthropic's check model comes from routing (`model_for`, `model_task`).
- **LAURAONE:** the `venice` provider entry, the Venice check and the Venice cost basis.

Both behaviours are present. `model_for("venice")` resolves through the entry's fixed `"model"`
key, so INTEG4's `owner_action(PERMISSION)` path works for Venice too. No `PROVIDERS[...]["model"]`
reference to Anthropic survives anywhere.

## 2. Conflict resolution (code)

`tests/test_cert_spend_hosts.py` `DECLARED`:

| Side | What it declared |
|---|---|
| b997efd (ef17a3d) | `gateway/credentials.py` with the CREDHEALTH review reference |
| LAURAONE (f535597) | the same file, re-described for the Venice checks, plus `gateway/venice.py` as a new declared caller |

**Resolution:** both were kept, and nothing was removed.
- `credentials.py` is declared once. The description covers the CREDHEALTH free checks and the
  Venice no-inference reads, which are owner-enabled only.
- The comment says the Venice check's billing basis is UNKNOWN (`credentials.VENICE_CHECK_COST_BASIS`),
  never free.
- `venice.py` is declared as the Private Laura transport.

**Claim verified:** the only place `VeniceProvider` is constructed is
`gateway/laura_register.py:515`, inside `_reply`. Other modules use only `venice.model`, `selected`,
`eligible`, `estimate_for` and `reply_code`, which make no request.

The scan regex gained `api\.venice\.ai`. That makes the test stricter.

## 3. Edits to existing tests (diff b997efd..INTEG5): none weakens a test

| File | Edit | Verdict |
|---|---|---|
| `test_cert_spend_hosts.py` | adds the `api.venice.ai` host to the scan; declares `venice.py`; widens the `credentials.py` description | stricter (one more paid host scanned) |
| `test_w4_pl_budget.py` | the enablement test passes `BRAMBLELOOP_PRIVATE_PROVIDER=anthropic`, and asserts the switches are OFF when no provider is selected | stricter: one more OFF-by-default assertion; every original assertion kept |
| `w4_pl_harness.py` | `ENABLE` selects the Anthropic transport explicitly | adaptation to the new default-OFF provider switch; the suites still drive the same path over a stub |
| `test_w4_plact.py` | purpose `@1` -> `@3`; asserts that `@1`/`@2` stay registered word for word; the prerequisite list gains `private_provider_venice` | stricter (one more prerequisite, never fewer); every truthful-AI clause is still asserted on the active prompt |
| `test_w4_pl_leak.py` | positive-control purpose string `@1` -> `@3` | equivalent (the same leak assertions) |
| `test_w4_pl_reply.py` | comment only | none |
| `test_w4_pl_boundary.py` | the active prompt is `@3`. The assertions that the **active** prompt says "nothing you write is sexually explicit", "erotic roleplay" and "usage policies" moved to `@1`, which is still registered. The active prompt is instead asserted to carry the explicit hard limits: no minor or age-play, no non-consensual content, no real person's likeness or voice, nothing unlawful, Venice's terms as the outer limit, never working around them | **a deliberate change of the asserted policy, not a stealth weakening.** It implements D-W4-PL-VENICE-ADULT (DECISION_LOG: owner ruling, attested; "IMPLEMENTED IN CODE; pending security review and production acceptance"). The identity, truthful-AI, no-tools and quoted-data assertions are all unchanged. The reviewer should confirm it against the decision (see the note below). |

**Note for the independent reviewer (observation, not changed by the integrator).**
`laura_register.PROMPT` is `@3` whatever the transport. If the owner set
`BRAMBLELOOP_PRIVATE_PROVIDER=anthropic`, the adult-register system prompt would be sent to
Anthropic. Two things bound this:
- the default is OFF, and the switch is an owner action;
- the unified intent router refuses any provider other than Venice (`UNIFIED_NEEDS_VENICE`), but the
  plain private reply does not.

It is the security-fix session's call whether `@3` should be Venice-only.

### 3a. The freeze's new test edits (a112da1..c13e20d) and one fix

The freeze moved the Private Laura suites from the stubbed Anthropic transport to a **stubbed Venice
transport**, because `@3` now runs only on Venice.

| File | Edit | Verdict |
|---|---|---|
| `test_w4_pl_budget.py` | the ceiling figures are derived from Venice's own estimate (`est/2`, `0.40 - est/2`, `0.50 - est/2`) instead of fixed Anthropic-sized ones; the model ref is `venice/<model>` | equivalent: the same three refusals (`SPEND_CEILING` on the owner figure, Laura's day and the agent day), now at the boundary of the real estimate |
| `test_w4_pl_continuity.py` | model names follow `PL.MODEL` | equivalent |
| `test_w4_pl_reply.py` | the model is `PL.MODEL`; `NO_PROVIDER` is now keyed on `VENICE_API_KEY`; a **new** case: provider=anthropic gives `REGISTER_NEEDS_VENICE` | stricter |
| `test_w4_plact.py` | `_estimate()` is Venice's estimate (the one `_reply` reserves); the race stub takes `*args` | equivalent |
| `w4_pl_harness.py` | the Stub stands in for `VeniceProvider._post` and records the same request shape; `AnthropicProvider._send` is **always** refused | stricter for Anthropic, but **weaker for no-stub tests**, fixed below |

**Weakening found and fixed (e24f6f6).**
- **Before the freeze:** `PL.enabled(None)` replaced the only transport the private suites used with a
  refusal. Several tests rely on that: `pl_auth`, `pl_continuity` ("any model request fails this
  test"), `pl_budget`, `pl_leak` and `plact`.
- **At the freeze:** with no stub, Venice's real `_post` was left live. The comment says "the harness
  refuses sockets", but `w4_pl_harness.py` installs no socket guard (`tests/network_guard.py` is not
  used by these suites). A regression that reached the model under `enabled(None)` would have made a
  real outbound request to api.venice.ai with the dummy key, instead of failing deterministically.
- **Fix:** with no stub, and when the caller has not installed its own Venice mock, Venice `_post` is
  refused just like Anthropic `_send`. The mocks that `test_w4_venice` and `test_w4_laura_unified`
  install are detected by identity against the transport captured at import, and are left in place.
- **Probe** (scratch): under `enabled(None)`, a reply that gets through the budget gates reaches the
  refusal, so the result is `PROVIDER_ERROR` with no socket opened, and `_post` is restored on exit.
  That is the same observable result the Anthropic refusal gave before the freeze.

The Phase-A observation about `@3` reaching Anthropic is closed by the freeze. `_reply` refuses
`REGISTER_NEEDS_VENICE`, and `test_w4_pl_reply` asserts it.

## 4. Migration proof (fresh local PostgreSQL 16.15, never production)

- **Cluster:** a fresh cluster `16/integ5` on port 5433. The container restart took the previous one.
- **Output:** `evidence_INTEG5/pg_migration_output.txt`.
- **Scripts:**
  - `pg_schema_boot.py` and `pg_schema_diff.py`, copied unchanged from INTEG4;
  - `pg_schema_boot_full.py` (new).
- **Code under test:** production b931d17 and base b997efd were `git archive`d into a scratch
  directory, so no other worktree was touched.

**Plain boot** (`Database.create_all`, as INTEG4 §7):

| Step | Code | Tables | Result |
|---|---|---|---|
| 1 | b931d17, reset | 131 | — |
| 2 | b997efd | 136 | +5 (INTEG4's) |
| 3 | candidate | 136 | +0 |
| 4 | candidate, second boot | 136 | no change |
| 5 | b997efd, rollback | 136 | no change |
| 6 | b931d17, rollback | 136 | no change |
| 7 | b931d17 -> candidate, directly | 131 -> 136 | — |

`create_all` changes `[]` throughout, and **no column was added, removed or altered on any existing
table**.

**Full lazy surface.** LAURACEO's tables are created lazily by `laura/agency/models.ensure_tables`,
and the private store keeps its own `PrivateBase` metadata. A plain boot therefore does not create
them, so this proof needs `pg_schema_boot_full.py`, which:
- imports every `brambleloop` module (0 import failures for every code version);
- then creates every `Base` and `PrivateBase` table.

That is a superset of any code path's lazy creation.

| Step | Code | Tables | Result |
|---|---|---|---|
| F1 | b931d17, reset | 138 | — |
| F2 | b997efd | 143 | +5 (INTEG4's) |
| F3 | candidate | **145** | **+2: `laura_boundary_crossings`, `laura_cost_events`**; no existing table changed |
| F4 | candidate, second boot | 145 | no change |
| F5 | b997efd, rollback | 145 | no change |
| F6 | b931d17, rollback | 145 | no change |

New tables and columns in this release:

| table | from | created | columns |
|---|---|---|---|
| `laura_cost_events` | LAURACEO (ADD-LCEO-06) | lazily, `laura.agency.models.ensure_tables` | id, at, kind, ref, cost_cad, measured, basis, model, purpose, outcome, detail (JSON) |
| `laura_boundary_crossings` | LAURAONE (ADD-LCONT-05) | lazily, same | id, at, session_public_id, approved_text, text_sha256, approval |

**Private store additions:** no new table and no new column. LAURAONE adds a new row kind `"xing"`
(sealed crossing requests, record id prefix `px_`) to the existing `laura_private_entries`.

**Rollback at the data level:**
- Older code reads only `kind = 'fact'` and `kind = 'turn'`, so it ignores `xing` rows.
- Its `forget` deletes by record id.
- Its `rekey` carries `xing` rows through `sealed_export` and re-seals them with a `"turn"` blind
  index. The index is inside the AAD, so they still authenticate.
- LAURAONE code finds crossings by `kind`, not by `key_index`, so it reads them again after a
  roll-forward.
- `laura_cost_events` and `laura_boundary_crossings` are invisible to older code.

**Rollback is safe to b997efd and to b931d17.**

## 5. Focused suites (venv-integ4, through testslot.sh; no full suite)

Tree: merge 79285c4 (identical code at 41d3951 and later Phase A commits, which add records only).
Run 20:51Z-21:20Z. From 20:47Z the coordinator's restarted b997efd full suite shared the machine, and
these runs used nice 19 through `testslot.sh`.

**Result: 39/39 suite files exit 0.** No `FAIL`, `SKIP` or traceback appears in any log.

- **Required set:**
  - vacuity 8 OK;
  - launch 28 OK;
  - cost_governance_wave2 39 OK;
  - search_hero_publish 4 OK;
  - cert_listing_frames PASS;
  - v11_autonomy_timeline PASS.
- **Laura:**
  - w4_laura_unified 26/26;
  - w4_venice 19/19;
  - w4_laura_ceo 13/13.
- **Private Laura:**
  - pl_auth 2/2, pl_boundary 4 OK, pl_budget 5 OK, pl_continuity 3 OK, pl_leak 2/2, pl_reply 3/3;
  - plact 8/8;
  - priv_access 7, priv_continuity 3, priv_firewall 7, priv_leak 7, priv_provenance 7, priv_store 8
    (all OK).
- **Laura CC** (laura_cc_*): access 5/5, delegation 5/5, followon 4/4, integration 5/5, private 7/7,
  providers 7/7, talk 9/9, wiring 5/5.
- **Release gates and security:**
  - voice_spec 7/7;
  - credhealth 13/13;
  - cert_spend_hosts PASS;
  - integ3_secfixes PASS;
  - integ4_secfixes 12/12;
  - integ4_deliverable_routes 4/4.
- **App and records:** pwa_static 82/82, cc_company 23/23, decision_index 3 OK.

**Rerun after the freeze merge and the harness fix (e24f6f6), 21:2xZ: 39/39 suite files exit 0.** No
FAIL, SKIP or traceback. Changed counts:
- `w4_laura_unified`: 40/40 (the freeze added 14 tests).
- Unchanged: venice 19/19, laura_ceo 13/13, plact 8/8, pl_reply 3/3, pl_leak 2/2, pl_auth 2/2,
  pl_budget 5 OK, pl_boundary 4 OK, pl_continuity 3 OK, vacuity 8 OK.

Logs: scratch only (`focusA/` and `focusB/` in the integrator's scratchpad). The full suite in Phase B is the
certifying run.

## 6. Phase B

(pending the `claude/w4-LAURAONE-freeze` SHA)
