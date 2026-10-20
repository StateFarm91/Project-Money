# Independent security re-review: W4-LAURAONE at c13e20d (delta from a4a6841)

- **Reviewer.** An independent Claude Code session. I did not write this code, and I fixed nothing; this file is the only change.
- **Date.** 2026-10-20 (UTC).
- **Scope.**
  - `origin/claude/w4-LAURAONE-freeze` @ `c13e20d`.
  - Reviewed diff: `git diff a4a6841..c13e20d -- brambleloop/src brambleloop/tests`, which is 22 files, +1,767/−215.
    - It includes the merge `b839321` of `origin/claude/w4-VENICE-adult-wip` @ `3cf3c8b`, so it covers the same code base the first review examined.
    - It covers the four commits after that merge: `3b7e6d0`, `3dc3ced`, `89860a1` and `c13e20d`.
  - **Baseline for "fails on a4a6841".** Commit `b839321` is `a4a6841` merged with `3cf3c8b`. That is exactly the tree the first review tested.
- **Documents read.**
  - The first review, `INDEPENDENT_SECREVIEW_LAURAONE.md` on `origin/claude/w4-SECREVIEW-LAURAONE` @ `003ffd8`.
  - `LAURAONE.md` at c13e20d, including the §10a review-response table and its residual risks.
- **Rules kept.**
  - No network access to production or Venice, no paid call, no secret, no deploy.
  - Every PoC ran offline, with the repository's harness (sockets refused, Venice and Claude mocked) or with loopback servers.
  - The PoC scripts are not committed, as the brief asks.

## Verdict

| Decision | Verdict |
|---|---|
| (a) Merge with every switch OFF | **NO BLOCKER** |
| (b) Activate Private Laura on Venice (OA-LCONT-3) | **NO BLOCKER** |
| (c) Activate the unified thread (OA-LCONT-1) and the business feed (OA-LCONT-2) | **NO BLOCKER**. Fix N-1 and N-2 (both LOW) before OA-LCONT-2, and N-1 before OA-LCONT-1 if practical |

- **The original BLOCKER B-1 is closed.**
  - The review's own PoC text now sends nothing when code routes the turn.
  - When Laura routes it, only a code-rendered request reaches Claude or any business table.
  - I re-ran the PoC with personal text the screen does not recognise. Even then, no owner word crossed automatically; only vocabulary parameters did.
- **H-1, M-1, M-2, L-1…L-6 and INTEG5 are closed.** I reproduced each one on `b839321` and confirmed it is gone on `c13e20d`.
- **Every named regression test fails on `b839321`** and passes on `c13e20d`. That was 14 of 14 in `test_w4_laura_unified`, plus the new INTEG5 case in `test_w4_pl_reply`.
  - Five tests fail on the old tree only because the API changed (`KeyError`, `TypeError` or `AttributeError`). For those I ran behaviour-level PoCs and confirmed the vulnerable behaviour on the old tree (see the table).
- **New findings.** None is a BLOCKER, HIGH or MEDIUM.
  - Three are LOW: N-1, N-2 and N-3.
  - Eight are INFO. Most are hardening or test-quality notes.

---

## 1. The original findings

"Fails on a4a6841" means: I copied c13e20d's `tests/` into the `b839321` tree (the harness pins `ROOT/src` on `sys.path`, so this runs the old source) and ran each named test. Where that failure came from an API change, I also ran a behaviour-level PoC against both trees with signature-compatible calls.

| Finding | Closed? | Evidence (c13e20d) | Named test fails on a4a6841? |
|---|---|---|---|
| **B-1** (BLOCKER) code fallback and keyword label sent the owner's verbatim words to Claude | **Yes** | See the B-1 notes below | **Yes** |
| **H-1** split route forwarded business and excluded turns after switch-off | **Yes** | See the H-1 notes below | **Yes**, at `:1210`: business exchange present |
| **M-1** truncated model list, so a silent pinned-row fallback | **Yes** | See the M-1 notes below | **Yes**, at `:1252` (sticky case) |
| **M-2** bearer key forwarded on redirect | **Yes** | See the M-2 notes below | **Yes**, at `:1319`: status 0 ≠ 302, so the redirect was followed |
| **L-1** login or opening step-up approved crossings | **Yes** | See the L-1 notes below | **Yes** (TypeError on the new kwarg); a behaviour PoC confirms the vulnerability |
| **L-2** TOCTOU double resolution | **Yes** | See the L-2 notes below | **Yes**: "a crossing resolved twice" |
| **L-3** an over-long crossing left half-approved | **Yes** | See the L-3 notes below | **Yes**; a behaviour PoC confirms |
| **L-4** mark-private blocked all later business | **Yes** | See the L-4 notes below | **Yes**: `('REFUSED','LEAK_GUARD',…)` |
| **L-5** deletion narrower than documented | **Yes** (database level documented) | See the L-5 notes below | **Yes** (TypeError); a behaviour PoC confirms |
| **L-6** Venice reply labelled business | **Yes** | See the L-6 notes below | **Yes**: the reply is labelled `business` |
| I-1 the owner's words always reach Venice | Yes (documentation) | ADD-LCONT-10 wording aligned; this is the design | n/a |
| I-2 global allow-list | **Partial** (residual negligible) | See the I-2 notes below | **Yes** (AttributeError: the function is new) |
| I-3 credential error bodies in audit | Open (documented) | Unchanged pattern; no conversation content | n/a |
| I-4 stale label | **Yes** | `PROVIDERS["venice"]["model"] = "venice-uncensored-1-2"` | n/a |
| I-5 reported model not compared | Open (deferred) | Unchanged | n/a |
| I-6 guard residuals | Superseded | Structured-first design; whole-store guard; short exact match | n/a |
| **INTEG5** @3 on a non-Venice transport | **Yes** | See the INTEG5 notes below | **Yes**: old returns `MALFORMED`, meaning the request reached Anthropic. The new pl_reply case gets `PROVIDER_ERROR` on old |

**B-1** (`test_review_b1_*`, 3 tests: `:1115`, `:1149`, `:1167`)
- The original PoC (CHEMO, router unreachable) now gives:
  - `routed_by: code (…)`;
  - `biz.seen == []` and no `laura_cc_turns` row;
  - an offer that requires step-up.
- All 5 code-routing causes are covered: unreachable, budget, malformed, not selected and register off.
- BIOPSY with Laura routing now gives:
  - screen `[health]`;
  - params `{}`;
  - Claude receives only "What is the company's current status?".
- Behaviour PoC on old: BIOPSY reached Claude and `laura_cc_turns` verbatim. So did the legal, contact (`+1 416 555 0199`) and credential (`hunter2`) samples.
- Behaviour PoC on new: none of them crossed, and every one of them now needs step-up.
- **Old-tree results:**
  - `:1142` failed, because `biz.seen` was non-empty: the CHEMO text was sent.
  - `:1158` and `:1190` failed with `KeyError 'screen'`.

**H-1**
- `_laura_reply` (`private_context.py:292`) now calls the shared `_venice_context(…, with_feed=False)` (`:463`):
  - excluded turns are skipped;
  - every business-labelled turn becomes a placeholder, regardless of the switch;
  - no feed is sent.
- PoC: unified ON (private turn, then excluded; business turn), then OFF, then "Good evening". Venice received the placeholder only, with no `S_PRIV`, `R[0]`, `STRUCT_BIZ` or `BIZ_ANSWER`.

**M-1**
- `credentials._http` (`:129`) reads up to 2 MB and refuses anything larger. `venice_model_reading` (`:363`) returns the newest *parsed* reading, or `{"unreadable": True}`, which fails closed in `venice.eligible`.
- **Real `_http` over loopback with an 11,520-byte list:**
  - old: got 2,000 bytes, which did not parse;
  - new: got 11,520 bytes, which parsed.
- Edge checks on new:
  - A contradiction followed by a list without the model gives `present:false`, so not eligible.
  - A body over 2 MB gives status 0, so the reading is unreadable and not eligible.
- **Test note.** `test_review_m1_…` injects its own `http`, so it never runs the real `_http` truncation. The old code still fails it, but only on the sticky case (see N-11).

**M-2**
- `venice.no_redirect_opener()` (`venice.py:115`) raises `HTTPError(3xx)` from `redirect_request`, before anything is sent to the new location. It is used by `VeniceProvider._post` and `credentials._http`.
- 301, 302, 303, 307 and 308 all go through `redirect_request`, and the handler replaces the default.
- **Test note.** The `got == []` assertion (`:1325`) is vacuous; see N-11. The `st == 302` assertion is what discriminates.

**L-1**
- The route (`api.py:1328`) passes `issued = stepup_until − STEPUP_WINDOW`. `_stepup_counts` (`private_context.py:669`) requires `issued > offer.created_at` **and** `issued > session.created_at`. A login sets `stepup_until = created_at + window`, so the login window never counts.
- Only `create_session` and `grant_stepup` write `stepup_until` (`auth.py:372`, `:442`).
- Behaviour PoC (login, open, mixed turn, approve with no further step-up):
  - old: **200, crossed**;
  - new: **403 `STEP_UP_REQUIRED`**.
- See N-3 for the residual: the step-up is not bound to the action.

**L-2**
- `store.resolve_crossing` (`store.py:460`) compare-and-sets on `(record_id, ciphertext, nonce)` in one UPDATE and checks `rowcount == 1`. AES-GCM nonces are random, so a stale reader can never match.

**L-3**
- `plan_brief` holds any offer over `MAX_OFFER_CHARS = 2000` (`held: too_long`). `unified_crossing` checks the length before resolving.
- Behaviour PoC with a 2,442-character mixed turn:
  - old: offer created, approval returned 500, status `approved`, nothing crossed;
  - new: no offer.

**L-4**
- Mark-private calls `boundary.redact` (`boundary.py:54`) on the `laura_cc_turns` row, linked through the sealed `business_ref`.
- Turns written before this revision carry no `business_ref`. Nothing is deployed, so this does not matter.

**L-5**
- Forget (`private_context.py:753`) also deletes the approval turn and its reply, and redacts the crossed text and the business row.
- Behaviour PoC after forgetting the source turn:
  - old: the approval turn and Business Laura's reply remain in the store, and `MIX_QUOTE` remains in business tables;
  - new: all gone or redacted.
- Rows at database level (free pages, WAL, backups) are documented as out of reach.

**L-6**
- `_unified_venice` labels every Venice reply `private`, or `everyday` (`private_context.py:539`), and the reply is in `_private_texts`.

**I-2**
- `_allowed_for` (`private_context.py:567`) now keeps only approved texts that the request carries as raw substrings.
- That changes little, because stripping a text that is absent was already a no-op. The scenario the first review described (an approved quote A plus a short private addition, both carried) still strips A.
- In my PoC the remainder was caught anyway by the shingle check. Under the structured-first design, a request carries free text only when the owner tapped it.
- Residual: negligible.

**INTEG5**
- `laura_register._reply:489` raises `REGISTER_NEEDS_VENICE` when `PROMPT_ is PROMPT` and the selected provider is not Venice. That happens before `_refuse`, `PROVIDER_NOT_SELECTED`, eligibility, the reservation (`:531`) and the request.
- `venice.selected` only ever returns `""`, `"venice"` or `"anthropic"`. An unset or unknown provider ends at `PROVIDER_NOT_SELECTED`, also before any reservation, so no non-Venice transport is reachable.
- Every caller of the @3 prompt goes through `laura_register.reply`; I grepped and found no other path.

### Test-harness change (Anthropic stub → Venice stub)

I compared every changed assertion in `test_w4_pl_budget`, `test_w4_pl_continuity`, `test_w4_pl_reply`, `test_w4_plact` and `w4_pl_harness.py`.

**Changes that are only names or figures:**
- provider and model names (`anthropic/claude-sonnet-5` → `venice/<pinned>`);
- the `NO_PROVIDER` key (`ANTHROPIC_API_KEY` → `VENICE_API_KEY`);
- budget figures re-derived from Venice's estimate (`0.001` → `est/2`; `0.395/0.499` → `cap − est/2`). The meaning is unchanged: the authorisation is below one estimate, or the day is already full.

**Strengthened:**
- The harness now makes `AnthropicProvider._send` raise unconditionally inside `enabled()`, where before it raised only with no stub.
- An INTEG5 case was added.

**Two weakenings, both minor (N-11):**
- `test_w4_pl_reply.py:59`, `set(req) == {model, max_tokens, system, messages}  # no tools`, is now a tautology, because the stub builds that dict itself. The real check on the Venice wire ("no tools", web search off, no Venice system prompt) still exists at `test_w4_venice.py:181-193`, so coverage is not lost.
- `test_w4_laura_unified.py:738`: the positive control `"laura.executive@1" in params` became the prefix check `"laura.co" in params or "laura.ex" in params`. It is a positive control only; `LR.PURPOSE in params` is kept.

**No-stub behaviour:**
- With no stub, the harness now leaves `VeniceProvider._post` as the caller set it, and sockets are refused.
- Every `PL.enabled(None)` site I checked asserts a specific pre-call refusal code (`PRIVATE_REFUSED`, 503, `JOB_SCOPE`, `SPEND_CEILING`). So a stray Venice call would still fail those tests, as a different code.
- Before this change, the old Anthropic `_refuse` assertion was swallowed into `PROVIDER_ERROR` by `reply()` anyway, so nothing was lost.

**Unified test file:**
- The removed assertions belong to behaviour the design withdrew:
  - business exchanges entering Venice's context with the switch on;
  - a `NEEDS_APPROVAL` crossing from the guard, which is now a `REFUSED` with a crossing only from `plan_brief`;
  - `brief_origin` values `owner_words` and `canonical`.
- Each of these has a stronger replacement.

---

## 2. New findings

### N-1 (LOW): personal content outside the screen's categories gets a one-tap offer labelled "Your own business words"

**Where.**
- `gateway/laura_unified.py:489` and `:502` (`plan_brief`): `stepup = not clean_business`, where `clean_business = label == BUSINESS and not screen`.
- `static/js/views/laura_unified.js:29`: the one-tap text.

**Scenario** (PoC, c13e20d). The owner writes:
- "Since Mark moved out I can barely sleep; how are shop orders this week?"
- "I've been throwing up all night with a fever; what were sales overnight?"

The result:
- Both are labelled `business`, and `screen == []`.
- Only the code request crosses automatically ("What did the company do this week? Focus on metrics: orders."). That part is correct.
- However, the offer has `requires_stepup: false`. The share dialog says "Your own business words: one tap shares exactly this", and one tap sends the full personal sentence to Claude and to `laura_cc_turns`.

The owner does see the exact text, so this is not an automatic leak. But it is the same weakness B-1 described, a keyword race deciding the label, now limited to the one-tap path. The UI wording also tells the owner the text is business.

**Fix.**
- Allow one tap only when the offered text's **every sentence** carries a business signal and no first-person personal signal. This is the per-sentence test the first review recommended in B-1(b).
- Otherwise require step-up.
- Reword the dialog, for example: "Check this is only business: one tap shares exactly this."
- Add the two sentences above as regression samples.

### N-2 (LOW): the feed truncates to 140 characters *before* the deny checks, so PII fragments pass

**Where.** `laura/agency/venice_context.py:234-246` (`_check_text`): `v = v[:max_len]`, then the `DENY` loop. Every `decision_title` value goes through it (`:292`, `:300`).

**Scenario** (PoC, c13e20d). A decision or priority title of about 150 characters whose PII crosses the 140-character boundary:
- "… write to jane.doe@gmail.com" is sent as "… write to jane". The untruncated title is refused as `email`.
- "… check order 48213377" is sent as "… check ord".
- "… for the customer Jane" is sent as "… for the cu".

The local part of an email, or the leading digits of an ID, reach Venice. They also become part of the owner's preview, so the owner sees them, but the validators the owner relies on did not fire.

**Fix.** Run `reject_private` and every `DENY` pattern on the **full** value, and truncate only after it passes. Alternatively, refuse any value over the cap (fail closed). Add a test with PII straddling the cap.

### N-3 (LOW): a step-up approves *every* pending offer, for 5 minutes, whatever it was performed for

**Where.** `private_context.py:669` (`_stepup_counts`) and `api.py:1328`.

The rule is "a step-up issued after this offer was created". Nothing binds it to the crossing id, and nothing consumes it. So:
- one step-up, including one performed for an unrelated protected action or for re-opening the conversation, approves every offer created before it, for 5 minutes;
- an offer made 1 second before an unrelated step-up is covered.

Exploiting this still needs the owner's live session, CSRF token and nonce. The setting is the same session-riding one as L-1.

**Fix.**
- Issue a single-use approval token bound to `crossing_id` on step-up from the share dialog, or consume the step-up window on the first approval.
- This matches the ADD-LCONT-05/09 "per approval" wording.

### N-4 (INFO): `laura.venice_context.sent` is written before the call

**Where.** `private_context.py:529`. `record_sent` runs before `laura_register.reply`.

A pre-call refusal still writes a "sent" audit row although nothing was sent: budget, `MODEL_NOT_ALLOWED`, `PROVIDER_DOWN`, `RELEASE_UNPROVEN` or `JOB_SCOPE`.
- This over-reports. It does not under-report, so it does not weaken privacy.
- It does make the U8 runbook evidence ambiguous.

**Fix.** Record after a successful send, or record the reply status in the row.

### N-5 (INFO): the crossing's `crossed_ref` is sealed only after the business call

**Where.** `private_context.py:722-726`. `boundary.record` runs first, then `_unified_business`, then `annotate_crossing`.

An exception between the first and last of these leaves the crossed text in `laura_boundary_crossings` with no sealed link. A later mark-private or forget then cannot redact it. Examples: a store error in `record_turn`, or a crash.

**Fix.** Annotate `crossed_ref` immediately after `boundary.record`, then add `business_ref` after the call.

### N-6 (INFO): a short private phrase can block business requests that contain it

**Where.** `laura_unified.py` `leak_check`, `short_exact`.

A private turn "this week", with the content token "week", gives a `short_exact` hit on "What did the company do this week? …" (PoC). The structured request is then refused with `LEAK_GUARD` for as long as that turn exists.
- This fails closed, so it is availability only.
- It joins the other noted case, where a business answer that was marked private blocks similar answers.

**Fix.** Exempt code-rendered structured requests from `short_exact`, since they contain no conversation text by construction. Keep the guard on history and on approved free text.

### N-7 (INFO): the feed reports 0 open decisions when the inbox is unreadable

**Where.** `venice_context.py:68-72`. `approvals.inbox` swallows errors and returns `status: UNKNOWN` with `cards: []`, so `open_owner_decisions = 0` and `owner_decision_titles = []`.

This breaks the module's own rule, "null = UNKNOWN, never 0".

**Fix.** Return `None` when `box["status"] != "OK"`.

### N-8 (INFO): redaction keeps the sha256 of the approved text

**Where.** `boundary.redact`. It keeps `sha256(approved_text)` "as proof". For a short or guessable text, that hash confirms a guess. The text is the owner's own words, which the owner then marked private.

**Fix.** Document this, or store an HMAC under a server key instead of a bare hash.

### N-9 (INFO): the redirect refusal is not used by the Anthropic and BFL API transports

**Where.** `gateway/anthropic.py:806` and `gateway/images.py:813`, `:840` still call `urllib.request.urlopen` with `x-api-key` or `x-key` headers, so they follow redirects.

- This predates the delta and is outside its scope.
- LAURAONE §10a correctly says the fix covers "the Anthropic and BFL **credential checks**". A reader could still take it to mean the API calls are covered.

**Fix** (separate change). Use `no_redirect_opener()` for every keyed request.

### N-10 (INFO): the test dependency is missing from the lock file

`requirements.lock` pins `starlette==1.6.0`. Its `TestClient` requires `httpx2`, which is not in the lock. Every `TestClient` suite fails at import from a clean install. That includes `test_w4_laura_unified`, `test_w4_venice`, `test_w4_pl_*` and `credhealth`. I installed `httpx2` separately to run them.

**Fix.** Add the test dependency to the lock, or to a test lock.

### N-11 (INFO): test-quality notes

- **M-1 test.** `test_review_m1_…` replaces `_http`, so the root cause (truncation in the real `_http`) is not exercised.
  - The "old truncation" case is simulated by truncating by hand.
  - **Add:** the real `_http` against a loopback server serving more than 2,000 bytes. My PoC shows old returns 2,000 bytes and new returns 11,520.
- **M-2 test** (`:1312`, `:1325`).
  - Server B binds `127.0.0.1`, but the redirect target is `127.0.0.2:<port>`, so B is unreachable either way. The `sb2 = … if False else sb` line is dead code.
  - So `got == []` cannot fail. Only `st == 302` discriminates, and it does: old returns 0.
  - **Fix:** bind B on `127.0.0.2` (or `0.0.0.0`), so the test shows the key would have reached it on the old code.
- **L-1 test.** The "login window alone never counts" check is wrapped in `if lsid:`. It does run today (the login body carries `session`), but if that response shape changes, the check silently disappears. **Fix:** assert `lsid`.
- **Harness.** See the two weakenings in the harness section above.

### Reviewed, no finding

- **Feed allowlist.**
  - Fields come only from `FIELDS`; unknown names are dropped.
  - Sources are declared read functions, with no raw table access and nothing under `laura_private_*`.
  - Numbers must be finite, non-negative and not booleans. Keys must be identifier slugs.
  - The list sizes are capped and the pack is capped at 3,000 bytes.
  - Any exception drops the whole field and records its name and validator, never the value. A read failure becomes `null`.
  - The feed goes only to the reply call (`with_feed=True`), never to the router or the split route, and only when the switch is exactly `"1"`.
  - The feed-preview route: anonymous gets 401, a session without CSRF gets 403, and an owner request with CSRF gets 200 with `no-store`.
  - Residual: personal names inside decision titles pass. For example, "Reply to Sarah Okafor about her shawl order" passes, while "Approve refund for Sarah" is refused by vocabulary. This is documented as residual #6. The owner previews every title.
- **Structured rendering.**
  - `extract_params` emits only code-vocabulary values, product slugs the company already has, a priority integer (at most 4 digits) and a count from 1 to 10.
  - `render_structured` builds from those values only.
  - Router drafts are always offers with step-up.
  - A screen hit or a non-business label means no parameters are taken from the turn.
- **Approval flow.**
  - The route sits behind the owner session, CSRF, a single-use nonce and the private grant.
  - The `stepup` flag is sealed in the store when the offer is created, so the client cannot change it.
  - The length check comes before resolution. Resolution is a compare-and-set.
  - Crossing ids are 128-bit random and the system has a single owner, so I found no IDOR.
- **Deletion and redaction.**
  - Mark-private and forget find derived records only through sealed refs: `business_ref`, `crossed_ref` and `approval_turn`. `annotate_crossing` refuses unknown ref keys.
  - Thread calls write no business memory (`allow_memory=False`).
  - The paid-call journal is written only inside a job scope, and the thread runs outside one.

## 3. Tests run (offline)

Every run used `PYTHONPATH=src:tests python tests/<file>.py` from a venv built from `requirements.lock`, plus `httpx2` (see N-10).

| Suite | c13e20d | b839321 (a4a6841 + 3cf3c8b) |
|---|---|---|
| test_w4_laura_unified | 40/40 | 21/21 (the old file) |
| test_w4_venice | 19/19 | 19/19 |
| test_w4_pl_reply / plact / pl_budget / pl_continuity | 3/3, 8/8, 5/5, 3/3 | 3/3, 8/8, 5/5, 3/3 |
| test_w4_pl_leak / pl_auth / pl_boundary | 2/2, 2/2, 4/4 | 2/2, 2/2, 4/4 |
| test_w4_credhealth / laura_ceo | 13/13, 13/13 | 13/13, 13/13 |
| test_w3_priv_firewall / laura_cc_private / test_cert_spend_hosts | 7/7, 7/7, 4/4 | 7/7, 7/7, 4/4 |
| **c13e20d's** `test_review_*` and `test_integ5_*` run on b839321 | — | **0/14 pass** (14 of 14 fail) |
| **c13e20d's** `test_w4_pl_reply` on b839321 | — | 2/3; the INTEG5 case fails (`PROVIDER_ERROR`: the request reached the Anthropic stub) |

**Behaviour-level PoCs.** These were run with the same script on both trees, outside the repository:

| PoC | b839321 | c13e20d |
|---|---|---|
| B-1, Laura-routed BIOPSY | verbatim to Claude and tables | code request only |
| B-1, legal / contact / credential samples | verbatim to Claude | code request, step-up offer |
| L-1, login window approves | 200, crossed | 403 |
| L-3, long offer | 500, left `approved` | no offer |
| L-5, forget | approval turn, reply and quote remain | all removed or redacted |
| M-1, real `_http` | 2,000 of 11,520 bytes, unparseable | full body, parses |
| N-1 | — | personal sentences get a one-tap offer |
| N-2 | — | truncated email, ID and vocabulary fragments pass the validators |
