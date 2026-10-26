# Independent security re-review: W4-LAURAONE at 2c29b42 (delta from f87e430)

- **Reviewer.** An independent Claude Code session. I did not write this code, and I fixed nothing. This file is the only change.
- **Date.** 2026-10-26 (UTC).
- **Scope.**
  - `origin/claude/w4-LAURAONE-freeze` @ `2c29b42`.
  - Reviewed diff: `git diff f87e4303..2c29b425 -- brambleloop/src brambleloop/tests`. That is 10 files, +108/−30, in one commit (`2c29b42`).
  - `research/final_build/w4/LAURAONE.md` §10c, the new response table.
- **Documents read.** `INDEPENDENT_SECREVIEW_LAURAONE_f87e430.md` (R-1…R-10).
- **Rules kept.**
  - No production writes, no paid calls, no secrets, no deploys.
  - Every suite and PoC ran offline under `nice -n 19`, using the repository's harness, which refuses sockets.
  - In the PoCs, `AnthropicProvider._send` and `VeniceProvider._send` were replaced by recorders that raise before any network access.
  - The venv was built from `requirements.lock` plus `requirements-test.lock`.
  - Source mutations for the discrimination checks were made in a scratch copy and reverted. The working tree is clean.
  - PoC scripts are not committed.

## Verdict

| Decision | Verdict |
|---|---|
| (a) Ship with every switch OFF | **NO BLOCKER.** R-2 is closed. With every Laura switch unset and dummy Anthropic and Venice keys present, a sweep of every entry point made **0** Anthropic and **0** Venice `_send` calls (§4). Those entry points are `talk.converse` and `ceo_chat.converse` for 8 intents, `/laura/ask`, `/laura/converse`, `/laura/unified/turn`, `laura_register.reply` and `executive.tick`. `laura` still held its CA$0.50/day authorisation during the sweep. Note Q-5: OFF now also turns the CEO briefing deterministic. |
| (b) Activation (OA-LCONT-1/2/3, OA-LCEO-1) | **NO BLOCKER.** R-3 is closed, so runbook step U8's audit row now exists for post-send failures. It can over-report (Q-4), so U8 should read `outcome`. R-1 is narrowed but still **open (Q-1, LOW)**: a one-tap path for personal text remains with em-dash, hyphen, ellipsis, slash or "so" joins. Fix Q-1 before OA-LCONT-1 if practical, as with R-1. The same mitigation applies: nothing crosses automatically, and the owner sees the exact text. |

**Summary.**
- **Closed.** R-2 and R-3 are closed, each with a regression test that fails on f87e430 and passes on 2c29b42.
- **Partially closed.** R-1 is partially closed: the review's own PoC sentences are fixed, but the clause and first-person rule changes are not pinned by any test (Q-2). R-10 is closed in code, but its mixed relabel is untested (Q-3).
- **Earlier fixes.** All earlier fixes are intact: B-1, H-1, M-1, M-2, L-1…L-6, N-1…N-11 and @3 Venice-only.
- **Still open.** R-4…R-9 were not assigned in this round (LAURAONE §10c says so). Their code is untouched by this diff.
- **New findings.** One LOW (Q-1) and five INFO (Q-2…Q-6).
- **Test assertions.** One assertion was dropped, and that loses coverage: `screen == []` in the N-1 test (Q-2). Nothing else was weakened. The three briefing suites now set the switch ON at module level, before any test runs, and the switch is load-bearing (§3).

---

## 1. Closure table

"Fails on f87e430" means this: I copied 2c29b42's `tests/*.py` over a checkout of f87e430, so the new tests ran against the old source, and ran the named test there.

| Finding | Claimed fix | Verified at 2c29b42 | Named test fails on f87e430? | Closed? |
|---|---|---|---|---|
| **R-1** (LOW) one tap for personal text with no first-person word or no clause break | `_CLAUSE` also splits on `,` / and / but / then. `_FIRST_PERSON` adds me/we/us/our and subject-dropped openers. The health and relationship screens get new terms | `laura_unified.py:446`, `:461`, `:474-486`. All 7 R-1 PoC phrasings now get step-up. The clause split does real work: a personal clause that carries no business word now fails `one_tap_business` by itself (my rule-level probe: 16/17 personal probes refused). **But** `—`, `-`, `…`, `/` and "so" are not separators, so a one-clause personal + business sentence still gets one tap (Q-1, verified end to end). The regression samples pass only because of the new screen words (Q-2) | Yes (`requires_stepup: False` for the comma sample) | **PARTIAL** → Q-1, Q-2 |
| **R-2** (LOW) briefing synthesis calls Anthropic with the CEO switch OFF, labelled `not_called` | `laura_briefing.synthesize` returns `unavailable` when `ceo_model_enabled()` is false, before any permission, provider or gateway step | `laura_briefing.py:179-186`. This is the only `synthesize` caller (`briefing.py:937`), so `/laura/ask`, `/laura/converse` and `talk.converse` are all covered. `not_called` is now true. The sweep (§4) shows 0 sends with `laura` at CA$0.50/day and a key present | Yes (`test_ceo_model_switch_off_makes_no_model_call`: 13/14 on old) | **YES** (see Q-5) |
| **R-3** (LOW) a feed sent by a reply that fails post-send reconciliation writes no audit row | `ReplyUnavailable(sent=…)`. `_unified_venice` writes the row when `exc.sent` is set; `PRE_CALL_CODES` is deleted, with no remaining reference | `laura_register.py:138-140`, `:438`, `:564`, `:591-595`, `private_context.py:540`. Every raise after `_send` carries `sent=True`. Every explicit pre-call refusal leaves it False (PoC: `REGISTER_OFF sent False`). The catch-all wrapper sets `sent=True`, so it over-reports (Q-4); that is by design ("over-reports, never under") | Yes (`ValueError: not enough values to unpack`: no row on old) | **YES** (Q-4 note) |
| **R-10** (INFO) docstring; overlapping *mixed* offer keeps "the personal part stays between us" | Docstring corrected. `kind in ("business", "mixed")` → `personal` on overlap, and the source turn is excluded from the overlap set | `boundary.py:57-58`, `private_context.py:443-452`, `:568-575`. The `exclude_turn` change is safe: a one-tap offer requires `label == business`, and business turns were already outside `_private_texts`, so excluding the source turn can never remove a step-up. It changes only the *wording* for mixed and draft offers. Without it, every mixed offer would be relabelled (the mixed-wording test fails 53/54 when it is reverted). **But** reverting the mixed relabel itself still passes 54/54 (Q-3) | n/a (no new test) | **YES in code**, untested → Q-3 |
| R-4 … R-9 (INFO) | Not assigned (LAURAONE §10c) | `api.py`, `store.py`, `w4_pl_harness.py`, `test_cert_spend_hosts.py` and `venice.py` are unchanged. `laura_register.py:571-573` (R-6) is unchanged | — | **OPEN** (unchanged) |

### Earlier verified fixes: intact

| Fix | Evidence at 2c29b42 |
|---|---|
| B-1 | `test_review_b1_*` pass. `plan_brief` still sends only `render_structured` output automatically (`laura_unified.py:536-541`). Q-1 is the owner-tapped path only |
| H-1 | `test_review_h1_…` passes. `_laura_reply` → `_venice_context(with_feed=False)` is unchanged |
| M-1, M-2 | `test_review_m1_…`, `test_review_m2_…` and `test_review_n11_…` pass |
| L-1 … L-6 | `test_review_l1_n3_…`, `l2`, `l4`, `l5` and `l6` pass. `store.py` and `api.py` are untouched |
| N-1 … N-11 | All `test_review_n*` pass. N-1 → R-1 → Q-1/Q-2. N-4 → R-3 is now closed by the `sent` flag |
| **@3 Venice-only (INTEG5)** | `laura_register.py:483-491` is unchanged (`REGISTER_NEEDS_VENICE` / `UNIFIED_NEEDS_VENICE` come before any reservation). `test_integ5_…` and the pl_reply INTEG5 case pass |

---

## 2. New findings

### Q-1 (LOW): one tap is still offered for personal text joined by a dash, ellipsis, slash or "so"

**Where.**
- `gateway/laura_unified.py:486`: `_CLAUSE` splits on `. ! ? ; : , \n` and before and/but/then. It does not split on `—`, `–`, ` - `, `…`, `/`, "so", "because" or "since".
- `gateway/laura_unified.py:479-484`: `_FIRST_PERSON` is a keyword list. Subject-dropped openers are only "can't/cannot/couldn't/barely/been/feeling/felt/throwing/crying/missing".
- `gateway/laura_unified.py:545`: `tap = clean_business and one_tap_business(...)`.

**Scenario.** End to end through the N-1 test's own harness: `unified_turn` with Laura routing to `business.ask`, then `unified_crossing(approve=True)` **with no credentials**. Each of these got `label: business`, `screen: []`, `requires_stepup: False` and `kind: business`, was approved by one tap, and the verbatim sentence reached the business transport (`biz.blob()`):
- "Mark's overdose wrecked the week — what were sales overnight?"
- "Still grieving Mark so how are shop orders this week?"

The same result at the rule level (`one_tap_business` true and screen empty):
- "Still grieving Mark — / - / … / / how are shop orders this week?"
- "Grieving Mark since the overdose — how are shop orders?"
- "Mark hit Sarah again — how are shop orders?"

The comma and semicolon variants of these *are* refused now, because the personal clause has no business word. That is the real improvement in R-1.

**Mitigation in place.** This is unchanged from R-1:
- Nothing crosses automatically.
- The owner sees the exact text under "Check this is only business".

**Fix.**
- Add `—`, `–`, ` - `, `…`, `/`, `(` and the conjunctions so/because/since/while/after to `_CLAUSE`.
- Alternatively, and more robustly, invert the rule: allow one tap only when the business text matches a *closed* grammar of business questions. The structured renderer already defines most of it. Do not try to enumerate personal phrasings.
- Add these sentences as regression samples, with `screen == []` asserted (see Q-2).

### Q-2 (INFO, test quality): the N-1 test no longer exercises the R-1 rule change

**Where.** `tests/test_w4_laura_unified.py:1527`. The f87e430 assertion `out["intent"]["screen"] == []` was removed.

**Effect.**
- All five samples now hit the new screen words (fever, sleep, moved out, left me). Step-up therefore comes from `clean_business = … and not screen` (`laura_unified.py:540`), and `one_tap_business` is never consulted.
- **Discrimination check:** in a scratch copy I restored f87e430's `_CLAUSE` and `_FIRST_PERSON` but kept the new screen words. The N-1 test still passes.
- The only remaining direct assertion on the rule is the positive case `one_tap_business("How are my shop orders this week?") is True`.
- A regression in the clause split or the first-person rule would therefore go unnoticed.

This is the one assertion in the delta whose removal loses coverage.

**Fix.**
- Keep the screen-hitting samples.
- Add a second sample set that passes the screen and must still be refused by `one_tap_business`, with `screen == []` asserted. For example: "Still grieving Mark, how are shop orders?", "We had a terrible night, how are shop orders?", plus Q-1's sentences once fixed.

### Q-3 (INFO, test gap): the R-10 mixed→personal relabel is untested

**Where.** `private_context.py:574`.

**Check.** I reverted it to `kind == "business"` in a scratch copy, and `test_w4_laura_unified` still passed **54/54**.

**Fix.** Add a test with an earlier private turn, then a mixed turn whose business sentence repeats words from it. Assert `kind == "personal"` and that the question does not contain "stays between us".

### Q-4 (INFO): the R-3 flag over-reports for pre-send failures caught by the wrapper

**Where.**
- `laura_register.py:436-438`: any non-`ReplyUnavailable` exception raised anywhere in `_reply` becomes `PROVIDER_ERROR, sent=True`. That includes `check_budget_cad`, `estimate_for`, `_venice_live`, `provider.payload` and `provider.key`, all of which run before `_send`.
- `:552-564`: a `_send` failure before any byte leaves (DNS, connection refused) is also `sent=True`.

**PoC.** Feed ON, Venice mocked, `anthropic.check_budget_cad` made to raise `RuntimeError`. The result was `reason: PROVIDER_ERROR`, **0** Venice requests, and **1** `laura.venice_context.sent` row (`outcome: PROVIDER_ERROR`).

**Impact.**
- The direction is the safe one (over-reporting, which the code comment states).
- But runbook U8 treats the row as proof the pack left. An operator could count a crossing that never happened.

**Fix (optional).**
- Set `sent=True` only after `_send` is entered. For example, flip a local flag immediately before the call and pass it from the wrapper.
- Alternatively, have U8 say that `outcome = PROVIDER_ERROR` means "possibly sent".

### Q-5 (INFO, operational): OFF now also turns the CEO briefing deterministic, and OA-LCEO-1 does not say so

**Where.**
- `laura_briefing.py:181`.
- `LAURAONE.md:179` (OA-LCEO-1). The OA-LCEO-1 row lists "model conversation, executive reasoning and tick ranking" and costs "converse 8%, executive 5%, exec_rank 2%".

**Effect.**
- Before 2c29b42, the model-synthesised briefing (the owner's production question of 2026-10-11, `test_w4_laura1_briefing`) ran whenever `laura` had a daily budget and a key existed.
- After deploying this branch with the switch unset, that briefing becomes the deterministic fallback.
- This is correct under the owner's "no activation without approval" rule, and it is what R-2 asked for. However, it is a visible behaviour change to a previously owner-approved feature.

**Fix.** Add the briefing synthesis to the OA-LCEO-1 row, both to the paths it covers and to the cost and consequence columns, so that setting the switch is a deliberate re-enablement.

### Q-6 (INFO): minor items

- **More step-ups for ordinary business questions.** These now need step-up: "Show me sales for the shop" (`me`), and any "we/us" question that does not use a business noun after "our". This fails safe and affects usability only.
- **Module-level environment change in tests.** `test_w4_laura1_briefing.py:37`, `test_w4_laura1_budget.py:34` and `test_w4_laurafix_truncation.py:45` set `BRAMBLELOOP_LAURA_CEO_MODEL=1` at import and never restore it. Today each suite runs in its own process (`H.run`; there is no CI workflow), so this is harmless. Under a single-process runner it would leak ON into later modules. `test_w4_laura_ceo`'s OFF test pops it itself, so the OFF proof is not affected.
- **Long docstring line.** `boundary.py:58` is 117 characters, against the file's ≤100 style.

### Reviewed, no finding

- **`_private_texts(exclude_turn=…)`** (`private_context.py:443-452`, `:568-571`).
  - It cannot remove a step-up. One tap needs `label == business`, and business turns were never in the overlap set.
  - Laura's own reply turns, other turns, notes and pending crossings still count.
  - The approval-time leak guard in `_unified_business` still uses the full set.
- **The position of the R-2 gate.** It returns before `laura_daily_permission`, `record_refusal` and `gateway_for`, so OFF writes no refusal row and makes no reservation. This matches the converse gate's behaviour.
- **Other Laura model paths with every switch OFF.**
  - `laura_phrase` is behind `BRAMBLELOOP_LAURA_PHRASING`, default off.
  - `laura_converse.call` is behind `available()`.
  - `laura_register.reply` stops at `REGISTER_OFF` with `sent=False`.
  - `/laura/unified/*` returns `UNIFIED_OFF`.
  - The Venice credential-health read (`credentials.py:344`) is the unauthenticated public `/models` metadata GET, not a model call, and this delta does not change it.

---

## 3. Test assertions: weakened?

Every `-` line in `git diff f87e4303..2c29b425 -- brambleloop/tests` was checked.

| Change | Assessment |
|---|---|
| N-1: `out["label"] == "business" and out["intent"]["screen"] == []` → `out["label"] == "business"` | **Weakened. Coverage is lost** (Q-2). The samples now pass by the screen alone |
| N-1: 2 samples → 5 (`len(samples) == 5`) | Stronger in outcome. The three R-1 PoC sentences are now regression samples |
| `test_ceo_model_switch_off_makes_no_model_call`: adds two briefing questions over HTTP with an Anthropic key set; `assert sent == []` covers them | **Stronger.** It fails on f87e430 |
| `test_review_r3_…` (new) | Discriminates: no row on f87e430 |
| `laura1_briefing`, `laura1_budget`, `laurafix_truncation`: `os.environ["BRAMBLELOOP_LAURA_CEO_MODEL"] = "1"` at module level | **Confirmed present.** Each is set after the imports and before `DB = H.DB` and any test body, and `ceo_model_enabled()` reads the environment at call time. The line is load-bearing: when it is removed, the suites pass only 11/19, 1/4 and 3/8. None of their assertions changed |

---

## 4. Tests run (offline, `nice -n 19`, `PYTHONPATH=src:tests`, venv from both locks)

| Suite | 2c29b42 |
|---|---|
| test_w4_laura_unified | **54/54** |
| test_w4_laura_ceo | 14/14 |
| test_w4_laura1_briefing / laura1_budget / laurafix_truncation | 19/19, 4/4, 8/8 |
| test_w4_venice | 19/19 |
| test_w4_pl_reply / plact / pl_leak / pl_auth | 3/3, 8/8, 2/2, 2/2 |
| test_w4_pl_budget / pl_continuity / pl_boundary | exit 0 (no summary line) |
| test_w4_credhealth | 13 passed, 0 failed |
| test_cert_spend_hosts / close5_vision_timeout / fluxapi | exit 0 |
| test_w3_priv_firewall / test_w3_laura_cc_private | exit 0, 7/7 |
| test_route_auth_default_deny / test_v11_cc_auth | 7/7, 16/16 |
| Other suites touching the briefing (`w3_laura_presence`, `w4_ccrel`, `w4_integ3_defects`, `w4_mjs_findings`) | all pass (none depends on model synthesis) |

**2c29b42's tests run against the f87e430 source:**
- `test_w4_laura_unified` passes 52/54. The two failures are N-1 (the comma sample gets one tap) and R-3 (no audit row).
- `test_w4_laura_ceo` passes 13/14. The failure is the OFF test (the briefing called `_send`).

**Discrimination checks** (scratch copy, reverted):

| Mutation | Result |
|---|---|
| Restore f87e430's `_CLAUSE` and `_FIRST_PERSON`, keep the new screens | N-1 test **passes** → Q-2 |
| Revert the mixed relabel (`kind == "business"`) | unified **54/54** → Q-3 |
| Revert `exclude_turn` | unified 53/54 (the mixed-wording test fails, as expected) |
| Remove the ON line from each briefing suite | 11/19, 1/4, 3/8 → the switch is load-bearing |

**Behaviour PoCs** (outside the repository, with `_send` replaced):

| PoC | Result at 2c29b42 |
|---|---|
| Every switch OFF, dummy Anthropic and Venice keys, `laura` at CA$0.50/day. Sweep: `talk.converse` and `ceo_chat.converse` × 8 intents, `/laura/ask` × 4, `/laura/converse` × 4, `/laura/unified/turn`, `laura_register.reply`, `executive.tick` | **0** Anthropic and **0** Venice sends. Briefing `synthesis.source: unavailable`. `/laura/converse` returns `model.source: not_called` (now true). Unified returns 404 `UNIFIED_OFF`. Register: `REGISTER_OFF`, `sent=False`. Tick ranking: `deterministic` |
| R-1's seven sentences | all refused one tap (step-up) |
| Q-1: two dash/"so" sentences, end to end | one tap, `approved` with no credentials, verbatim to the business transport |
| Q-4: `check_budget_cad` raises before the send | 0 Venice requests, 1 `sent` audit row (`PROVIDER_ERROR`) |
