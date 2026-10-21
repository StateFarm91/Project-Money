# Independent security review: W4-LAURAONE + W4-VENICE (adult register)

- **Reviewer.** An independent Claude Code session. I did not write this code, and I fixed nothing; this file is the only change.
- **Date.** 2026-10-20 (UTC).
- **Scope.**
  - `origin/claude/w4-LAURAONE` @ `a4a6841`, merged locally with `origin/claude/w4-VENICE-adult-wip` @ `3cf3c8b`.
  - The code merged cleanly. Only `DECISION_LOG.md` and `spec/13_…` conflicted, and both are documentation.
  - Reviewed diff: `git diff 65317697...HEAD -- brambleloop/src brambleloop/tests`, which is 34 files and about +4,977 lines.
  - Base `65317697` is an ancestor of both branches. `origin/claude/w4-INTEG4` has since moved on to `b997efd`; that later work was not reviewed.
- **Design documents read.** `LAURAONE.md`, `VENICE.md`, `LAURACEO.md`, `spec/13_…`.
- **Rules kept.**
  - No network access to production or Venice, no paid call, no secret, no deploy.
  - Every proof of concept (PoC) ran offline, with the repository's own test harness (mocked Venice, scripted business model, sockets refused) or with local loopback servers.
  - PoC scripts were kept outside the repository and are not committed.

## Verdict

**BLOCKER, for activating the unified thread (`BRAMBLELOOP_LAURA_UNIFIED=venice`, OA-LCONT-1).**

- One finding (B-1) breaks the owner's binding rules 3–4 and 6: private content is excluded by default, and no private content goes into business tables. Ordinary turns trigger it with no adversary involved.
  - The owner's personal text is sent word for word to Claude and stored in plaintext business tables.
  - This happens automatically whenever Venice is unreachable, out of budget or not yet enabled.
- **Not blocked: merging with every switch OFF.** With the switch unset, the new routes answer 404/409 and behaviour is unchanged, which I verified.
- **Not blocked: Private Laura on Venice alone (OA-LCONT-3), outside the unified thread.** No BLOCKER was found there, but M-1 and M-2 should be fixed before activation.

## Findings at a glance

| ID | Severity | What |
|---|---|---|
| B-1 | **BLOCKER** (unified activation) | The current turn is protected by a keyword classifier only. A "business" label sends the owner's whole message word for word to Claude, stores it in `laura_cc_turns`, and auto-routes it when Venice is down |
| H-1 | HIGH | With the unified switch off again, the split private route sends business exchanges and **excluded** turns to Venice. This defeats OA-LCONT-2 and the Exclude control |
| M-1 | MEDIUM | The live model check never works: `_http` cuts the body at 2,000 chars, so the model list never parses and eligibility silently falls back to the pinned row |
| M-2 | MEDIUM | The Venice bearer key is forwarded on HTTP redirects, including to another host and on an https→http downgrade |
| L-1 | LOW | Crossing approval accepts the shared 5-minute step-up window: the step-up that opened the conversation, or the login itself, is enough |
| L-2 | LOW | `resolve_crossing` checks the status and writes it back in separate steps (TOCTOU), so two concurrent approvals can make a double crossing and a double paid call |
| L-3 | LOW | A crossing over 2,000 chars is marked approved, then fails with a 500, leaving inconsistent state |
| L-4 | LOW | "Mark private" on a business turn refuses all later business calls in the thread until that turn is deleted |
| L-5 | LOW | Deletion is incomplete: plaintext copies stay in business tables and business memory, and approval-path replies stay in the store |
| L-6 | LOW | A Venice reply to a business-labelled turn is labelled "business", which takes it out of the leak guard's corpus |
| I-1…I-6 | INFO | Documentation and assurance mismatches, and hardening notes |

---

## B-1 (BLOCKER for unified activation): the owner's verbatim words cross to Claude on a keyword label, and automatically when the router is unavailable

**Where.**

| Location | What it does |
|---|---|
| `brambleloop/src/brambleloop/gateway/laura_unified.py:110-125` (`classify`) | Labels a turn `business` when it has any business keyword and none of the private keywords |
| `laura_unified.py:304-309` (`code_intent`) | Picks `business.ask` for every business or mixed label |
| `laura_unified.py:324-325` (`plan_brief`, origin `owner_words`) | Sends the whole turn with `needs_owner: False` |
| `app/command_center/private_context.py:486-499` (`_laura_intent`) | Uses the code fallback when the register switch is off, Venice is not selected, or Venice fails for any reason, including `BUDGET`, `PROVIDER_UNREACHABLE` and `MALFORMED` |
| `private_context.py:549-560` (`_unified_business`) | The leak guard compares against *earlier* private turns, notes and requests only, never against the current turn's own content |

**Why it breaks the rules.**
- The private keyword list (`_PRIVATE`) is narrow. Health, legal, financial-personal, identity and contact details are not in it: "biopsy", "chemo", "pregnant", "divorce", "custody", "lawyer", "password", phone numbers and e-mail addresses all pass.
- The business list (`_BUSINESS`) is very broad: `store`, `shop`, `orders`, `price`, `reviews`, `products`, `ads`, `queue`, `launch`…
- So a large share of everyday sentences are labelled `business`. The guard never inspects the current turn, so it cannot catch any of them.

**Proof of concept** (offline, the repository's own harness `tests/test_w4_laura_unified.py`):

```
turn = "Heading to the store after my chemo appointment ZX-CHEMO-1, then the pharmacy."
Venice mocked as 503 (equivalently: laura_private budget spent, or register switch not yet on)
label: business
routed_by: code (Laura's router: PROVIDER_UNREACHABLE) | side: business
sent to Claude: True | stored in laura_cc_turns: True
```

With Venice working and the router choosing `business.ask`, the same thing happens to a message such as "My biopsy came back malignant, ZX-77, so what are this week's sales and orders?". The label is `business`, the full sentence goes to Claude, and the full sentence is stored in `laura_cc_turns`.

**Where the text then goes** (all business systems):
- Anthropic, in the request.
- `laura_cc_turns.question`, in plaintext.
- The business conversation history: the next 6 turns of `laura-unified-thread` resend it to Claude.
- The paid-call journal of the general gateway path. `laura_converse.call` uses `complete_json`.
- Possibly `laura.memory`, through the model's `remember` field (`ceo_chat._remember`). `reject_private` only refuses values tagged as private, and a plain string is never tagged.

**Severity rationale.**
- The fallback is designed to fire on exactly the situations the owner should expect: Venice down, the CA$0.50/day cap reached (about 300 turns), and the period before OA-LCONT-3 is done. In LAURAONE.md §8 the owner is told the thread "routes business by code" in that state.
- The UI does not tell the owner that code, not Laura, routed the turn. `routed_by` is never shown, and the toast appears only when the status is not `REPLIED`.
- The LAURAONE.md residual-risk text covers "the owner retyping private content". It does not cover *new* private content in a turn that happens to contain a business word, and that is the common case.

**Recommended fix** (any one closes the blocker; (a) plus (b) recommended):
- **(a) Fail toward privacy when Laura's router is unavailable.** `code_intent` must not send owner text. Either send nothing to the business side and say so, or send only the fixed `CANONICAL_BRIEF` request.
- **(b) Never send owner free text automatically.** Treat `owner_words` like `owner_quote`: show the exact text and require approval. Alternatively, allow automatic sending only for short turns that pass a strict business-only test. That means every sentence has a business signal, and a negative screen finds no personal signal (health, legal, relationship, identity, contact or PII patterns such as e-mail, phone, address and numbers that look like credentials).
- **(c)** Do not write `remember` notes to business memory from unified-thread turns, or require the owner to approve them.
- **(d)** Show `routed_by` in the thread whenever code, rather than Laura, made the decision.
- **(e)** Add tests: a business-keyword turn carrying personal content, with the router unavailable, must not reach the business model or any Base table.

---

## H-1 (HIGH): turning the unified switch off makes the split private route forward business exchanges and excluded turns to Venice

**Where.** `app/command_center/private_context.py:292-313` (`_laura_reply`, the split `/api/cc/private/turn` path).
- Its context is `store.conversation(...)[-12:]` with **no** filter on `label` or `excluded`.
- `unified_turn` writes to the same encrypted store and kind (`turn`). That includes:
  - the owner's business briefs (label `business`);
  - Business Laura's validated answers, which carry company records and figures (`model_ref business/...`);
  - turns the owner chose to exclude.
- `owner_turn` returns 409 only while `BRAMBLELOOP_LAURA_UNIFIED=venice` is set.

**Scenario.** The owner uses the thread, then switches it off. Switching off is the documented rollback, and runbook step U1 says "switch off: today's behaviour". The next private message sends the last 12 turns to Venice, business exchanges and excluded turns included, with `BRAMBLELOOP_LAURA_BUSINESS_TO_VENICE` unset.

**Proof of concept** (offline harness):

```
unified ON:  private turn (then "exclude"), business turn -> Claude answers BIZ_ANSWER
unified OFF: PC.owner_turn(db, sid, "Good evening")
split reply status: REPLIED
Venice got business brief: True | Claude's business answer: True | EXCLUDED private turn: True
```

**Impact.**
- **ADD-LCONT-10 is broken.** Company data flows to a new provider without OA-LCONT-2, which LAURAONE.md calls "a new company-data flow to a new provider [that] needs your separate approval".
- **ADD-LCONT-07 is broken.** The owner's "Exclude from context" control silently stops working.

**Fix.**
- Apply the same filter in `_laura_reply` that `_venice_context` applies: skip `excluded`, and replace business-labelled turns with the placeholder unless `business_to_venice()`.
- Better, have both paths build their context in one shared function.
- Add a test that switches off after unified use.

---

## M-1 (MEDIUM): the live Venice model check never works, so eligibility silently falls back to the pinned row

**Where.**

| Location | What it does |
|---|---|
| `gateway/credentials.py:123-137` (`_http`) | Truncates every response body to 2,000 characters, the success path included (`[:2000]`, line 133) |
| `gateway/credentials.py:326-344` (`_venice_models`) | `json.loads` on the truncated list raises, so it returns `{}` |
| `gateway/credentials.py:347-352` (`venice_model_reading`) | Returns `None` |
| `gateway/laura_register.py:485-487`, `gateway/venice.py:126` | With `live=None`, eligibility is decided by the pinned row alone |

**Proof of concept.**
- The real `_http` was given a 12-model list shaped like Venice's documented `GET /models`, with the pinned model reclassified as `anonymized`. That list is 9,083 bytes; Venice's real list is larger.
- `_venice_models` returned `{}`.
- `eligible()` returned `(True, 'verified Venice-hosted Private class …')`.
- The same reading, untruncated, returns `(False, "Venice now classifies it 'anonymized'")`.
- The unit test passes only because its two-model fixture is shorter than 2,000 bytes.

**More.**
- `venice_model_reading` looks only at the **latest** credential record. Suppose one check records a contradicting reading (fail closed), and a later check cannot read the model list (5xx, timeout, or the truncation above). Eligibility then reopens. That is fail-open on a transient.
- `check_venice` parses the `rate_limits` body through the same truncation. Venice documents per-model RPM/RPD/TPM there (VENICE.md F17), so in production the balance is likely to read UNKNOWN ("balance was unreadable"). That would fail runbook step P1. This part is functional, not security.

**Impact.** The claimed control ("a reclassification fails closed", ADD-PLV-02 eligibility by privacy class) does not operate. A Venice change that moves the model out of the Private class, for example to an anonymized upstream, would not stop private and adult text being sent.

**Fix.**
- Do not truncate before parsing. Cap the size with a generous limit, for example 2 MB, and refuse beyond it.
- Treat "selected, but no parseable live reading in the last N hours" as **not eligible**, or at least as a visible prerequisite that is not met.
- Keep the last *contradicting* reading sticky until a later successful reading clears it.

---

## M-2 (MEDIUM): the Venice bearer key is forwarded on redirects

**Where.**
- `gateway/venice.py:314-336` (`VeniceProvider._post`).
- `gateway/credentials.py:123-137` (`_http`, used by `check_venice`).
- Both use `urllib.request.urlopen` with the default `HTTPRedirectHandler`. That handler copies every non-content header, `Authorization` included, to the redirect target, even when the target is another host or the scheme drops from https to http.

**Proof of concept** (loopback only).
- Server A, the stand-in for the chat URL, answered `302 Location: http://127.0.0.2:<port>/steal`.
- Server B received `GET /steal` with `Authorization: Bearer sk-SECRET`.

**Scenario.** The URL is a constant, so this is not SSRF. Any redirect from `api.venice.ai` or its edge would hand the key to a third party, possibly in cleartext:
- a misconfiguration;
- a compromised or hijacked CDN rule;
- a captive or intercepting proxy that holds a trusted CA.

The task asked for "no host change before the key header is sent", and today that holds only while Venice never redirects.

**Fix.**
- Build an opener whose redirect handler refuses (raises), or send the request with `http.client.HTTPSConnection("api.venice.ai")`.
- Treat any 3xx as `PROVIDER_ERROR`.
- Apply the same change to `_http` for every credential check. Anthropic and BFL share this pattern, which predates this change.

---

## L-1 (LOW): crossing approval does not need a fresh, per-action step-up

**Where.** `app/command_center/api.py:1319-1327` and `auth.py:772-778`.
- `require_stepup` checks only that `stepup_until` (a 5-minute window) is in the future.
- `create_session` sets `stepup_until = now + 5 min` at **login** (`auth.py:371`).
- `/private/open` itself requires a step-up.

So for 5 minutes after login, or after opening the conversation, any number of crossings can be approved with no new authentication. The comment in `api.py` ("needs a fresh step-up of its own") and ADD-LCONT-05/09 suggest a separate step-up for each approval.

**Exploitability.** You need the owner's live session, with its CSRF token and a fresh nonce. That limits this to session-riding: a compromised browser, or a borrowed unlocked device.

**Fix.** Require a step-up issued after the crossing was created, or a single-use step-up token bound to the crossing id. At minimum, do not let the login-time window count.

## L-2 (LOW): crossing resolution is not atomic

**Where.** `laura/private/store.py:434-445` (`resolve_crossing`). `_load` reads `status == "pending"` in one session, and `_reseal` writes in another.

**Scenario.** Two approval requests in flight together (two tabs, or a double click with two nonces) both pass the check. The result is two `laura_boundary_crossings` rows and two Business Laura calls, each reserved and billed. A decline racing an approval can end with `declined` stored even though the approve path already crossed.

**Fix.** Compare-and-set inside one transaction: `UPDATE … WHERE record_id=? AND <version/status token>=?`, check `rowcount == 1`, or lock the row with `SELECT … FOR UPDATE`.

## L-3 (LOW): approving a crossing over 2,000 characters leaves inconsistent state

**Where.** `private_context.py:632-658`.
- `resolve_crossing` marks the request `approved`, then `boundary.record` raises `ValueError` (`boundary.py:16`, `MAX_TEXT = 2000`), which becomes a 500.
- Requests can be up to 16,384 characters. A long mixed turn, or a `business.delegate` on a private turn, quotes the whole owner turn.

**Proof of concept.**
- A mixed turn with a 2,442-character business span.
- Approval returned 500 `PRIVATE_ERROR`.
- The request was now `approved`, and 0 business calls were made.
- A retry returned 400 ("resolved once").

Nothing crossed, so this fails safe. But the owner is told nothing useful, and the approved text drops out of `_private_texts`.

**Fix.** Validate the length before resolving, or cap request text at `boundary.MAX_TEXT` when it is created. Write the status and the boundary row in one transaction.

## L-4 (LOW): "Mark private" on a business turn blocks every later business call in the thread

**Where.**
- `private_context.py:661-685` relabels the turn in the encrypted store.
- `laura_cc_turns` still holds the brief and answer, and `ceo_chat.history` (6 turns) renders them into every outbound request.
- The outbound guard (`private_context.py:567-571`) now matches them. A refused call is not persisted, so the history window never moves on.

**Proof of concept.** After marking one business turn private, three further business questions all returned `('REFUSED', 'LEAK_GUARD')`, with 0 business calls. Deleting the turn clears the block.

The guard is doing its job, but the result is an unexplained, permanent outage of Business Laura in the thread.

**Fix.** When a business turn is marked private, drop or tombstone its `laura_cc_turns` row from the business history window, and tell the owner what remains on the business side.

## L-5 (LOW): deletion is narrower than documented

**Where.** `store.py:237-256` (`forget`).

`forget` deletes the turn, rows whose `reply_to` is that turn, and sealed crossing requests that cite it. It does **not** delete:

| Kept | Where |
|---|---|
| The approved plaintext | `laura_boundary_crossings.approved_text` |
| The brief and result | `laura_cc_turns` |
| A `remember` note | business memory (`laura.memory`) |
| The approval turn, and Business Laura's reply to an approved crossing (that reply's `reply_to` is the approval turn, not the source turn) | encrypted store |
| Deleted rows in free pages, WAL, or database backups | database level |

LAURAONE.md §2 rule 8 and the "Marking private afterwards" residual cover part of this. The table row says "replies and crossing requests that quote it go too", which is true of the sealed request but not of its plaintext business copy.

**Fix.** Document the exact scope of deletion in the UI's Delete confirmation. Either cascade to the approval turn and its reply, or state plainly that crossed text is business data from then on.

## L-6 (LOW): a Venice reply to a business-labelled turn is labelled "business"

**Where.** `private_context.py:503-527`. `_unified_venice(..., label)` records Laura's **Venice** reply with the owner turn's label. When the router picks `none` on a business-labelled turn, the Venice reply is stored as `business`. It is then:
- missing from the leak guard's corpus (`_private_texts` skips business labels);
- dropped from Venice's own context.

That reply was written with up to 20 private notes and 12 private turns in context, so it can paraphrase or quote them.

**Fix.** Label every Venice-authored reply `private` (or `everyday`), whatever the owner turn's label. Only Business Laura's answers should carry `business`.

---

## INFO

- **I-1. The owner's business words always reach Venice.**
  - The router, and the reply path whenever the router picks `none` or a crossing is pending, receive the owner's newest message whatever its label, even with OA-LCONT-2 off.
  - The LAURAONE.md data-flow table says so. The ADD-LCONT-10 wording ("Business facts reach Venice only with the owner's separate approval") does not.
  - Align the spec text, or skip the router for clearly business-only turns.
- **I-2. Approved-text allow-list.**
  - `leak_check` removes *every* approved crossing text, the newest 200, before matching. So a later private text made mostly of an approved quote plus a short addition can slip past.
  - Older approvals fall off the list and start to produce false refusals.
  - Scope the allow-list to the crossing being sent, plus its own history.
- **I-3. Credential checks store the provider's error body.** On non-OK credential checks the redacted error body (≤300 chars) is stored in the audit row (`credentials.py:295`). That is not conversation content, and it matches the existing Anthropic/BFL pattern. The reply path discards bodies correctly (`venice.py:225-250`, `laura_register._sanitised`).
- **I-4. Stale label.** `credentials.PROVIDERS["venice"]["model"]` still names `zai-org-glm-5-2`, but the pinned default is `venice-uncensored-1-2`. The label is stale.
- **I-5. The reported model is not checked.** The `model` field of a Venice response is shown in `model_ref` but never compared with the requested model. A silent server-side substitution would go unnoticed.
- **I-6. Documented leak-guard residuals hold.** I confirmed the documented residuals as described: paraphrase with low token overlap, the 500-turn read window, and texts under 12 chars and 3 words. Its root weakness is the one in B-1: it never examines the current turn.

## Verified, no finding

- **Owner-only access.** Every new `/api/cc/laura/unified/*` route and `/laura/converse` sits behind the default-deny gate: owner session, same-origin, `X-CSRF-Token` and a single-use nonce on POST.
  - Anonymous requests get 401.
  - Content routes also need a live private grant, opened with step-up and lasting 30 minutes.
  - An expired step-up is refused (`require_stepup`). Status, `GET /laura/costs` and the views carry no content.
- **Crossings.**
  - A Venice draft (`laura_draft`) never crosses without the approval route.
  - A guard hit creates a request and sends nothing.
  - Replay is blocked by the nonce and by "resolved once", apart from the race in L-2.
  - Crossing ids are 128-bit random. Each grant is scoped to its session, and in this single-owner system I found no IDOR.
- **Injection.** Router output is reduced to a fixed tool enum, and any draft becomes a pending request. Neither router output nor a Venice reply can enqueue a job, publish, spend or take an owner-reserved action. Business proposals still go through `followon.create`, which needs owner confirmation, plus step-up when protected. The executive loop never reads the thread.
- **Spend.**
  - Every Venice call (router and reply) is reserved first through `anthropic.check_budget_cad` with agent `laura_private` and the owner's daily figure. Every Claude call goes through `laura_converse.call` and `complete_json`, with agent `laura`, purpose allocation stops and the month ceiling.
  - An exhausted budget means no call.
  - There is no fallback to another provider: `UNIFIED_NEEDS_VENICE`, and the intent prompt is refused on non-Venice transports.
  - Venice's own reported cost can only raise the bill. The ledger row is written before any refusal.
- **Venice adapter.**
  - The URL and host are constants.
  - An unknown, unverified, unpriced or env-selected ineligible model fails closed (subject to M-1 for live readings).
  - The key is read at call time and is in no exception, log or record (the `_sanitised` labels, failover rows and cost rows were checked).
  - Error bodies are reduced to a whitelisted code.
  - `include_venice_system_prompt: false`, and web search, scraping and citations are off.
- **Encryption.**
  - Labels, flags and crossing requests are sealed inside the AES-GCM payload.
  - `rekey` re-seals the `xing` kind with its own blind index.
  - `forget` issues real row `DELETE`s, subject to L-5.
- **Prompt registry.**
  - `laura.private_reply@1` has the same sha256 as base `65317697` (`e115c5c6…`).
  - `@2` has the same sha256 as the commit that introduced it, `2bc5e30` (`8a2ea11c…`).
  - The registry's immutability check would refuse any edit.
  - `@3` (`0a528251…`) states every hard limit:
    - minors, including age-play and young-seeming framing;
    - non-consent presented as endorsed or real, and exploitation;
    - any real person's name, likeness or voice, and impersonation;
    - anything unlawful;
    - Venice's Terms as the outer limit;
    - AI disclosure ("You are an AI…", "a clearly fictional adult AI… say plainly that you are a fictional AI");
    - no business decisions.
  - `laura.unified_intent@1` carries no register wording.

## Tests run (merged tree, offline)

`cd brambleloop && PYTHONPATH=src:tests python tests/<file>.py`. Results are in the table appended below. The PoCs in B-1, H-1, M-1, M-2, L-3 and L-4 are reproductions written for this review. They are not committed, because the brief limits this branch to this file.

| Suite | Result |
|---|---|
| test_w4_laura_unified | 21/21 |
| test_w4_venice | 19/19 |
| test_w4_laura_ceo | 13/13 |
| test_w4_plact | 8/8 |
| test_w4_pl_leak / pl_reply / pl_auth | 2/2, 3/3, 2/2 |
| test_w4_pl_boundary / pl_budget | exit 0 |
| test_w3_priv_firewall | exit 0 |
| test_w3_laura_cc_private | 7/7 |
| test_cert_spend_hosts | 0 failing |
| test_w4_credhealth | 13/13 |

All 13 suites pass. None of them catches B-1, H-1, M-1 or M-2, because every suite's fixtures stay inside the conditions those findings need to show: the router mock always works, nothing exercises switching the thread off again, the model-list fixture is under 2,000 bytes, and the transport is mocked so no redirect ever happens.
