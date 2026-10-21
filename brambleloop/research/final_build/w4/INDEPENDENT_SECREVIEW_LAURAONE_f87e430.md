# Independent security re-review: W4-LAURAONE at f87e430 (delta from c13e20d)

- **Reviewer.** An independent Claude Code session. I did not write this code, and I fixed nothing. This file is the only change.
- **Date.** 2026-10-21 (UTC).
- **Scope.**
  - `origin/claude/w4-LAURAONE-freeze` @ `f87e430`.
  - Reviewed diff: `git diff c13e20d..f87e430 -- brambleloop/src brambleloop/tests`, which is 21 files, +610/−138, over commits `2c750a1`, `752cb53` and `f87e430`.
- **Documents read.**
  - `INDEPENDENT_SECREVIEW_LAURAONE_c13e20d.md` (N-1…N-11).
  - `INDEPENDENT_SECREVIEW_bcce679.md` (S-1…S-6).
  - `LAURAONE.md` @ f87e430, §10a and §10b, which hold the finding → fix → test tables.
- **Rules kept.**
  - No production writes, no paid calls, no secrets, no deploys.
  - Every suite and PoC ran offline under `nice -n 19`:
    - The repository's harness refuses sockets and mocks Venice and Claude.
    - Anthropic `_send` was replaced by a recorder that raises before any network access.
  - The venv was built from `requirements.lock` plus `requirements-test.lock`.
  - PoC scripts are not committed.

## Verdict

| Decision | Verdict |
|---|---|
| (a) Merge with every switch OFF | **NO BLOCKER.** Note R-2: with every switch OFF, a briefing question in the CC Ask box still makes an Anthropic call. This is the pre-LAURACEO briefing synthesis, bounded by `laura`'s CA$0.50/day. |
| (b) Activate Private Laura on Venice (OA-LCONT-3) | **NO BLOCKER.** |
| (c) Activate unified Laura (OA-LCONT-1) and the feed (OA-LCONT-2) | **NO BLOCKER.** Fix R-1 (LOW) before OA-LCONT-1 if practical. Fix R-3 (LOW) before OA-LCONT-2, because runbook step U8 relies on the audit row. |
| (d) Business Laura model switch `BRAMBLELOOP_LAURA_CEO_MODEL` (OA-LCEO-1) | **NO BLOCKER to activation.** The switch defaults OFF and gates converse, executive and exec_rank. However, OFF does not mean "no Business Laura model call": R-2 shows the briefing path still calls Anthropic, and the response says `not_called`. Correct that claim before anyone relies on OFF meaning zero spend. |

**Summary.**
- **Closed.** Of the 24 items, 17 are fully closed with a regression test that fails on c13e20d and passes on f87e430: N-2, N-3, N-6, N-7, N-8, N-9, N-10, N-11, S-3, S-4, S-5, I-5, the honest-wording change, the deletion and redaction items, and the UNKNOWN-not-zero item.
- **Partially closed.** N-1, N-4 (which also regressed in one path), N-5, S-1 and S-6.
- **Documented.** S-2.
- **Earlier fixes.** B-1, H-1, M-1, M-2, L-1…L-6 and INTEG5 (@3 is Venice-only) are intact.
- **New findings.** Three are LOW: R-1, R-2 and R-3. Seven are INFO.
- **Test assertions.** None was weakened in a way that loses coverage (§3). One harness-ordering defect is noted (R-8).

---

## 1. Closure table

"Fails on c13e20d" means this: I copied f87e430's `tests/*.py` over a copy of the c13e20d tree, so the tests ran against the old source, and ran the named test there.

| Finding | Claimed fix | Verified at f87e430 | Named test fails on c13e20d? | Closed? |
|---|---|---|---|---|
| **N-1** (LOW) one-tap offer for personal text | `one_tap_business`: every clause carries a business signal and no personal signal; the dialog is reworded | `laura_unified.py:470-487`, `:534`. Both review sentences now need step-up, and the wording is honest. **But see R-1:** personal text with no first-person word, or with a comma in place of a semicolon, still gets one tap | Yes (`requires_stepup` is False on old) | **PARTIAL** → R-1 |
| **N-2** (LOW) truncation before the deny checks | Deny checks run on the full value; an over-long value is refused (`over_length`) | `venice_context.py:239-253`: `reject_private`, then whitespace collapse, then every `DENY` pattern, then the length check that refuses. No truncation remains anywhere in `_check_text` | Yes ("a straddling fragment passed: …jane.doe@gmail.com") | **YES** |
| **N-3** (LOW) a step-up approves every offer for 5 minutes | The passphrase (and TOTP) travel in the approval request and are verified for that action | `api.py:1331-1350`, `private_context.py:714-717`. No window counts: a fresh, unrelated step-up gives 403. A wrong credential gives 401 and increments `failed_stepups`, and 5 failures revoke the session. `verify_owner(db=…)` consumes the TOTP step, so a code cannot be replayed. The verification is bound to `body["id"]` in the same request, and the request nonce is single-use. `_stepup_counts` is deleted and has no remaining caller. See R-5 for audit hygiene | Yes (old: 200 crossed after an unrelated step-up) | **YES** |
| **N-4** (INFO) audit row written before the call | Written only when the request left; `outcome` recorded | Pre-call refusals now write nothing, which is correct. **But** `BUDGET` is listed in `PRE_CALL_CODES` (`private_context.py:494-497`), and `laura_register.py:588` raises `BUDGET` *after* `_send`. The pack left and no row is written (PoC, R-3) | Yes | **PARTIAL / regressed** → R-3 |
| **N-5** (INFO) `crossed_ref` sealed after the business call | Sealed immediately after `boundary.record` | `private_context.py:725-730`. `annotate_crossing` merges (`payload.update`, `store.py:458`), so the three sequential annotations do not overwrite each other. A small window remains between two commits (R-4) | Yes (TypeError on the new kwarg; behaviour verified) | **MOSTLY**, residual R-4 |
| **N-6** (INFO) a short private phrase blocks structured requests | Structured requests are exempt from `short_exact` | `private_context.py:608-616`. Only `unified_turn`'s code-rendered `plan["send"]` passes `structured=True` (`:676`). The approval path does not. The outbound check on the full request still uses `short_exact=True`, with the brief stripped as allowed | Yes (`LEAK_GUARD`) | **YES** |
| **N-7** (INFO) unreadable inbox reported as 0 | `None` unless the status is OK | `venice_context.py:68-83`. `DEGRADED` (partial cards) also becomes `None`, which is correct: a partial count would under-state | Yes | **YES** |
| **N-8** (INFO) redaction keeps the sha256 | The hash is cleared | `boundary.py:76`. `private_context` never persists `crossed["sha256"]`. The docstring at `boundary.py:58` still says the sha256 stays (R-10) | Yes | **YES** |
| **N-9** (INFO) Anthropic and BFL follow redirects | `no_redirect_opener()` | `anthropic.py:806-810`, `images.py:813`, `:848`, `:832-837`. The unkeyed image download (`images.py:1239`) is unchanged, which is correct. Test gap: R-9 | n/a (behaviour verified by reading) | **YES** (test gap R-9) |
| **N-10** (INFO) the lock is missing the test dependency | `requirements-test.lock` | A clean venv from both locks runs every TestClient suite. Starlette 1.6.0 warns that `httpx` is deprecated in favour of `httpx2`, but it works | — | **YES** |
| **N-11** (INFO) test quality | M-2 B binds 127.0.0.2; L-1 has no `if`; the real `_http` is tested; the real wire is asserted | All four verified. `sb2 = sb` is now real. The L-1 `if lsid:` block was removed together with `_stepup_counts`; the stronger N-3 test covers it | n11 and pl_reply pass on old, as expected: M-1 was already fixed | **YES** |
| **S-1** (LOW) LAURACEO spends on deploy | `BRAMBLELOOP_LAURA_CEO_MODEL` defaults OFF and is checked in `laura_converse.available` | `laura_converse.py:29-41`, `:138`. `call()` calls `available()` first, so converse, executive and exec_rank (`loop.py:637`, `:649`) all stop, and `/laura/converse` falls back to `talk.converse`. **But** `talk.converse` → `briefing.answer` → `laura_briefing.synthesize` is an Anthropic call that the switch does not gate. The route then labels the turn `model.source: not_called` (PoC, R-2) | Yes (AttributeError; behaviour verified) | **PARTIAL** → R-2 |
| S-2 (LOW) rollback | Documented (LAURAONE §10b) | The four operator steps are accurate against the code | n/a | **DOCUMENTED** |
| **S-3** (INFO) feed preview without a grant | Requires the live private grant | `api.py:1352-1356` → `private_context.unified_feed_preview` → `_principal`. Owner without a grant: 403 | Yes | **YES** |
| **S-4** (INFO) Venice card shown before selection; fixed model name | Card omitted unless Venice is selected; `_effective_model` | `credentials.py:448-449`, `:463-470`, `:487` | Yes | **YES** |
| **S-5** (INFO) harness refusal swallowed | Recorded and raised on exit | `w4_pl_harness.py:91-111`. Works, but see R-8 (ordering) | n/a (harness) | **YES** (R-8) |
| **S-6** (INFO) whole-file declaration | Exact per-URL allowlist | `test_cert_spend_hosts.py:63-85`. The allowlist contains the bare base `https://api.venice.ai/api/v1`, and `venice.py` builds every endpoint as `f"{API_BASE}/…"`. A new billable endpoint composed the same way passes (R-7) | Passes on old (new test) | **PARTIAL** → R-7 |
| **I-5** model substitution | `MODEL_MISMATCH`: billed, text never used | `laura_register.py:568-590`. Verified with the substituted model `some-anonymized-upstream-model`. The `startswith(model + "-")` rule and an empty `model` field are accepted (R-6) | Yes ("a substituted model's answer was used") | **YES** (R-6 hardening) |
| **Honest wording** for mixed and personal approvals | Sealed `kind`, with wording for each kind | `laura_unified.py:232-250`, `store.py:43-44`, `:429`. `kind` is sealed and outside the client's control, and the dialog renders `x.question` as text (`h()`, no `innerHTML`). An overlapping "business" offer is relabelled `personal` (`private_context.py:574`). Minor: an overlapping *mixed* offer keeps "the personal part stays between us" (R-10) | Yes (`KeyError 'kind'`) | **YES** |
| **UNKNOWN, not zero** | = N-7 | — | Yes | **YES** |
| **Deletion and redaction** (L-4, L-5, N-8) | — | `test_review_l4/l5`, `test_marking_private_afterwards…` and `n5`/`n8` pass. Forget still cascades to the approval turn and reply, and redacts the crossed text, the business row and now the hash | Yes | **YES** |
| **Crash-safe crossing records** | = N-5 | — | — | **MOSTLY** (R-4) |

### Earlier verified fixes: intact

| Fix | Evidence at f87e430 |
|---|---|
| B-1 (code fallback, raw words, screen, classifier) | `test_review_b1_*` (3) pass. `plan_brief` still sends only `render_structured` output automatically. One-tap (R-1) concerns only the owner-tapped path, never automatic sending |
| H-1 | `test_review_h1_…` passes. `_laura_reply` → `_venice_context(with_feed=False)` is unchanged |
| M-1 | `test_review_m1_…` passes, and `test_review_n11_…` now exercises the real `_http` (>2,000 bytes) |
| M-2 | `test_review_m2_…` passes, with B now reachable on 127.0.0.2, so the `got == []` assertion now discriminates |
| L-1 | Superseded and strengthened by N-3: no session window approves at all |
| L-2 | `resolve_crossing`'s compare-and-set is unchanged (`store.py:463-488`); the test passes |
| L-3 | The length check still comes before resolution (`private_context.py:719-720`) |
| L-4, L-5, L-6 | Tests pass; code unchanged apart from N-5/N-8 |
| **@3 Venice-only (INTEG5)** | `laura_register.py:483-491` is unchanged. The I-5 check sits after the request and does not affect the pre-reservation refusal. `test_integ5_…` and the pl_reply INTEG5 case pass |

---

## 2. New findings

### R-1 (LOW): one tap is still offered for personal text that has no first-person word or no clause break

**Where.**
- `gateway/laura_unified.py:470-476`:
  - `_FIRST_PERSON` matches I/I'm/I've/I'd/I'll/myself/"my + non-business noun" only. It misses `me`, `we`, `us` and `our`, and sentences with the subject dropped.
  - `_CLAUSE` splits on `. ! ? ; : \n` only. Commas and "and" do not separate clauses.
- `:534`: `tap = clean_business and one_tap_business(...)`.

**Scenario.** PoC on f87e430, end to end through `unified_turn`, then `unified_crossing(approve=True)` **with no credentials**. Laura routes to `business.ask` and the screen returns `[]`. Each of these got `requires_stepup: false`, `kind: business`, and was approved by one tap:
- "Throwing up all night with a fever, what were sales overnight?" This is the review's own N-1 sample with "I've been" removed and the semicolon turned into a comma.
- "Can't sleep since Mark moved out, how are shop orders this week?"
- "Mark left me last night, how are shop orders this week?"

In each case the verbatim sentence reached Claude (`biz.seen`) and `laura_cc_turns`. Other phrasings that were also one-tap at the rule level:
- "We split up yesterday, …"
- "Me and Mark are done, …"
- "Crying all day about Mark, …"
- "Barely slept since the breakup, …"

The health screen also misses "fever" and "throwing up".

**Mitigation in place.**
- Nothing crosses automatically. The automatic request is still code-rendered (B-1 holds).
- The owner sees the exact text under the new honest heading "Check this is only business".

This is the same residual N-1 described, narrowed but not closed. It is still a one-tap path with no re-authentication, decided by a keyword heuristic.

**Fix.**
- Split clauses on commas and conjunctions as well. Alternatively, allow one tap only when the offered text is a single clause with no non-business content words.
- Add `me|we|us|our` (outside business nouns) to the personal signal.
- Add fever, vomit/throwing up, sleep and breakup terms to the health and relationship screens.
- Add the three PoC sentences as regression samples.

### R-2 (LOW): with `BRAMBLELOOP_LAURA_CEO_MODEL` OFF, briefing questions still call Anthropic and are reported as `not_called`

**Where.**
- `app/command_center/api.py:1113-1122`: the OFF branch calls `talk.converse` and stamps `"model": {"source": "not_called"}`.
- `laura/agency/talk.py:392-394`: the `briefing` intent → `briefing.answer`.
- `laura/agency/briefing.py:937`: `laura_briefing.synthesize`. This is gated only by `laura_daily_permission > 0` and the presence of an Anthropic key (`laura_briefing.py:183-196`), never by `ceo_model_enabled`.

**Scenario.** PoC, using the `test_w4_laura_ceo` harness. The switch is unset, `laura` has CA$0.50/day, a dummy `ANTHROPIC_API_KEY` is set, and `AnthropicProvider._send` is replaced by a recorder that raises.
- `POST /api/cc/laura/converse` with "Brief me on the last 24 hours" and with "Give me my morning briefing" both returned 200 with `model.source: "not_called"`.
- The recorder logged **two** `_send` attempts (`claude-sonnet-5`).
- `synthesis.cost_cad` was about 0.057 each, counted at the estimate.

**Impact.**
- This is the pre-LAURACEO `/laura/ask` behaviour, which is owner-approved and within the ceilings, so it is not a new spend path.
- However, the S-1 closure, the api.py comment ("no model call"), the test docstring, and LAURAONE OA-LCEO-1 ("stay off until you activate them") all state that OFF means no Business Laura model call. The response label is untrue, which conflicts with CLAUDE.md's "never claim … until verified".
- `test_ceo_model_switch_off_makes_no_model_call` only asks "Hello Laura" over HTTP, so it cannot see this path.

**Fix.** Either:
- gate `laura_briefing.synthesize` with `ceo_model_enabled()`; or
- state that the briefing synthesis is outside the switch, and derive `model.source` from the turn's `synthesis.source` instead of hard-coding `not_called`.

Either way, add a briefing question, with an Anthropic key set, to the OFF test.

### R-3 (LOW): N-4 regression: a feed sent by a reply that fails post-call reconciliation writes no audit row

**Where.**
- `private_context.py:494-497` lists `BUDGET` in `PRE_CALL_CODES`.
- `laura_register.py:588` raises `ReplyUnavailable("BUDGET")` from `gateway._record` **after** `provider._send` has returned. The request, and the pack inside it, left.

**Scenario.** PoC: feed ON, Venice mocked, `ModelGateway._record` made to raise `BudgetExceeded`. This stands for reconciliation, after the call, exceeding the day's room, for example when Venice's reported `cost.usd` is above the reservation.
- Result: `reason: BUDGET`, 1 Venice request whose body contains the feed fields, and **0** `laura.venice_context.sent` rows.
- Before f87e430 the row was written unconditionally, so this case over-reported. Now it under-reports.
- This is exactly the evidence runbook step U8 relies on ("one row whose sha256 equals the preview's").

**Fix.**
- Give the post-send budget failure its own code (for example `BUDGET_AFTER_SEND`), or have `ReplyUnavailable` carry `sent=True/False` from `_reply`.
- Classify by that flag rather than by a code list.
- Add a test that makes `_record` raise.

### R-4 (INFO): the N-5 crash window is narrowed, not closed

**Where.** `private_context.py:721-730`.

`resolve_crossing` (commit), then `boundary.record` (commit), then `annotate_crossing(crossed_ref)` (commit). These are three separate transactions:
- A crash between the second and third still leaves plaintext in `laura_boundary_crossings` with no sealed link. The window is now milliseconds rather than a whole Claude call.
- A crash between the first and second leaves the request `approved` with nothing crossed, and it cannot be re-approved. That affects availability only.
- `test_review_n5` simulates the crash later, inside `_unified_business`, so it cannot see the remaining window.

**Fix (optional).**
- Seal a provisional `crossed_ref` in the same transaction as the insert.
- Alternatively, let forget and mark-private fall back to matching `laura_boundary_crossings.approved_text` against the deleted `xing` text.

### R-5 (INFO): per-action re-authentication is not recorded on success and does not reset the failure counter

**Where.** `api.py:1339-1350`.
- `/auth/step-up` writes a `kind=stepup outcome=ok` security event and resets `failed_stepups` (`grant_stepup`). The crossing route does neither.
- Failures are recorded, through `refuse`, with `kind="stepup"`.
- As a result, the security timeline shows failed re-authentications for approvals but never the successful ones. Old failures keep counting towards the 5-strike revocation after a successful approval.

The verification also runs before the grant and unified-switch checks. I checked this: it adds no new passphrase oracle, because `/auth/step-up` is already reachable with the same session, CSRF, nonce and counter.

**Fix.** On success, call `auth.record(kind="stepup", outcome="ok", action="laura.crossing")` and reset the counter.

### R-6 (INFO): the I-5 comparison accepts any `<model>-…` id and a missing `model`

**Where.** `laura_register.py:571-573`.
- `served.startswith(model + "-")` accepts, for example, `venice-uncensored-1-2-anything`.
- An empty or absent `model` field skips the check entirely.

No current eligible id is a prefix of a non-eligible Venice id, so this is hardening only.

**Fix.** Accept only `model` itself, or `model` followed by a date or version suffix (`-\d{4}-\d{2}-\d{2}` or `-v\d+`). Treat an absent `model` as a mismatch, or record it.

### R-7 (INFO): the S-6 per-URL allowlist admits the bare Venice API base

**Where.** `test_cert_spend_hosts.py:71` (`"https://api.venice.ai/api/v1"`) and `venice.py:54-56` (`CHAT_URL = f"{API_BASE}/chat/completions"`).

A new constant such as `IMAGE_URL = f"{API_BASE}/image/generate"` contains no new literal URL, so the test passes. `test_w4_venice` pins only the existing constants.

**Fix.**
- Assert the set of module-level `*_URL` values in `venice.py` and `credentials.py` (import them and compare the resolved strings).
- Alternatively, forbid `API_BASE` interpolation outside a fixed list.

### R-8 (INFO): the harness raises before restoring its patches

**Where.** `tests/w4_pl_harness.py:110-111`. The `if refused: raise` runs before `laura_register.release_proven = orig_release` and before the environment restore loop.

**Effect.**
- After any refused call, the environment variables in `ENABLE` stay set for the rest of the process, and `release_proven` stays stubbed True. That includes the deliberate one in `test_review_s5_…`.
- The tests that follow it in `test_w4_laura_unified` (`n11`, `i5`) run with the stub leaked. Today this is harmless, because they set their own environment, but it can mask a `RELEASE_UNPROVEN` regression in a test added later.
- Raising in `finally` also replaces any original exception.

**Fix.** Restore everything first, then raise, and only if no exception is already propagating.

### R-9 (INFO): no test pins N-9; other keyed `urlopen` callers remain

- `test_w4_close5_vision_timeout` and `test_w4_fluxapi` patch **both** `urllib.request.urlopen` and `venice.no_redirect_opener` with the same fake. Reverting `AnthropicProvider._send` or BFL `_post`/`_get` to `urlopen` would still pass.
- **Fix:** add a test that serves a 302 from loopback to each keyed transport and asserts that the key never reaches the target, as M-2 does for Venice.
- **Outside N-9's scope (pre-existing):** `ops/provider_accounts.py:317` and `visual/d_judge.py:175` (OpenAI `Authorization: Bearer`) still use `urlopen` with credential headers.

### R-10 (INFO): wording and documentation nits

- `boundary.py:58`: the docstring still says "its sha256 stays as proof".
- `private_context.py:574` relabels an overlapping `business` offer as `personal`. An overlapping `mixed` offer keeps "Only the part below would go …; the personal part stays between us", although the quoted part itself overlaps private conversation. Step-up is still required, so this affects wording only. **Fix:** relabel overlapping `mixed` offers to `personal` as well.

### Reviewed, no finding

- **N-3 UI.**
  - `laura_unified.js` sends `passphrase` and `totp` only when `requires_stepup` is set, and uses the existing `confirmDialog` (password input, cleared after use).
  - The JSON body path is the same one `/auth/step-up` already uses.
  - Refusal messages are fixed strings and never echo the credential.
- **The `kind` field.**
  - It comes from a fixed vocabulary and is coerced to `personal` in `request_crossing`.
  - It is sealed inside the AES-GCM payload, so a client cannot change it.
  - `offer_kind` is added to `PrivateRecord.__slots__`.
- **The `outcome` field in the audit row.** It is a fixed reply code, cut to 40 characters, with no content.
- **The CEO switch parser.** Exact `"1"` after `strip()`. `true`, `yes` and unset are OFF.

---

## 3. Test assertions: weakened?

Every `-` line in `git diff c13e20d..f87e430 -- brambleloop/tests` was checked.

| Change | Assessment |
|---|---|
| `test_switch_off_means_behaviour_unchanged`: `status == UNAVAILABLE` → `model.source == "not_called"` | This follows the intended behaviour change under S-1. It is not weaker as a check, but it encodes the R-2 mis-label |
| N-8: `len(text_sha256) == 64` → `== ""` | Intended, and stricter |
| Feed audit row key set: `+ "outcome"` | Intended |
| Positive control `"laura.co" or "laura.ex" in params` → every billed `laura` purpose present | **Stronger** |
| `test_review_l1_…` removed; `test_review_l1_n3_…` added | The old cases (no step-up, the opening step-up, the login window) are subsumed. No window counts any more. The new test adds "a fresh unrelated step-up gives 403" and "a wrong passphrase gives 401 with no crossing" |
| `stepup_issued_at=_fresh()` → `verified_for_action=True` (7 sites) | An API rename. Same role: the "verified" precondition |
| `test_crossing_approval_over_http…`: a step-up call followed by a bare approve → approve with `passphrase` | Same strength, and matches the new contract |
| M-2: `sb` on 127.0.0.1 → 127.0.0.2; dead `sb2` removed | **Stronger.** `got == []` now discriminates |
| pl_reply: the tautological dict-key check → the real-wire assertions | **Stronger** |
| close5 and flux: also patch the opener | Neutral for their own behaviour; see R-9 for the gap it leaves |
| The `test_w4_laura_ceo` module sets `CEO_MODEL=1` globally; the unified `ON` adds `CEO_MODEL=1` | Required for the ON-path suites. OFF is proven separately, incompletely (R-2) |

None was weakened in a way that loses coverage.

---

## 4. Tests run (offline, `nice -n 19`, `PYTHONPATH=src:tests`, venv from `requirements.lock` + `requirements-test.lock`)

| Suite | f87e430 |
|---|---|
| test_w4_laura_unified | **53/53** |
| test_w4_laura_ceo | 14/14 |
| test_w4_venice | 19/19 |
| test_w4_pl_reply / plact / pl_leak / pl_auth | 3/3, 8/8, 2/2, 2/2 |
| test_w4_pl_budget / pl_continuity / pl_boundary | exit 0 (no summary line) |
| test_w4_credhealth | 13 passed, 0 failed |
| test_cert_spend_hosts / test_w4_close5_vision_timeout | exit 0 |
| test_w4_fluxapi | 13/13 |
| test_w3_priv_firewall / test_w3_laura_cc_private | exit 0, 7/7 |
| test_route_auth_default_deny / test_v11_cc_auth | 7/7, 16/16 |

**f87e430's tests run against the c13e20d source:**
- `test_w4_laura_unified` passes 33/53. The 20 failures are every new review test (n1, n2, n3/l1, n4, n5, n6, n7, n8, s3, s4, mixed wording, i5) plus the tests that use the renamed kwarg.
- The new tests that pass on old are expected to:
  - `s5` and `n11` cover harness and test quality only;
  - the S-6 allowlist is a new test.
- `test_w4_laura_ceo` passes 13/14: the S-1 test fails on old.

**Behaviour PoCs** (outside the repository, with Anthropic `_send` replaced):

| PoC | Result at f87e430 |
|---|---|
| R-1 three personal sentences | one-tap `approved`, crossed verbatim to Claude and `laura_cc_turns` |
| R-2 briefing via `/laura/converse` with the CEO switch OFF | 2 Anthropic `_send` attempts; response `model.source: not_called` |
| R-3 feed ON, post-send `BudgetExceeded` | 1 request with the pack left; 0 audit rows |
