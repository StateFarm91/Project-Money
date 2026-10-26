# Independent security review: W4-AGENTS at b5226f7

- **Reviewer:** an independent Claude Code context. It did not write this code. It reviewed and reported only; nothing was fixed.
- **Date:** 2026-10-26 (UTC).
- **Scope:** `git diff origin/claude/final-candidate-b997efd..b5226f77 -- brambleloop/src brambleloop/tests` on `origin/claude/w4-AGENTS` (24 files, +1522/−62). The build record `research/final_build/w4/AGENTS.md` was read alongside it.
- **Method:**
  - Read every changed source file in full: the grant module, the router, the handlers, the director, the Etsy client writes, `live_state.write_refusal`, delegation, the executive loop, the charters and the registry.
  - Traced the code each change depends on: `OwnerGrant.refusal`, `EtsyClient._call` and `_require`, `queue.effects.guard` and `claim`, `orchestrator._enqueue_mission`, `followon` and `command_center.approvals`.
  - Ran focused tests, and an independent probe of the **real** sealed grant (no mocks of the grant itself).
- **Rules followed:** no network, no Etsy calls, no secrets, no deploys. Every test ran at `nice -n 19` in a scratch venv.

## Verdict

**PASS. No Critical or High findings.**

No path was found by which an Etsy storefront write is sent:
- in SHADOW;
- without a sealed grant bound to the exact change;
- with an expired, revoked, edited, hand-inserted or credential-rotated grant;
- or for the shop title, `policy_additional`, banner or icon.

There are two Medium findings. Both concern *who* the approving principal is, not whether the gates hold:
- **M-1:** the storefront grant can only be approved through the operator bearer token. There is no owner-session route with step-up and CSRF.
- **M-2:** the approval credential is also the sealing key, and it is resident in the worker.

I recommend fixing M-1 before any storefront write is enabled outside SHADOW, that is, before `BRAMBLELOOP_STOREFRONT_WRITES_AUTHORISED=1` is set in a publishing phase. Nothing in this branch is unsafe in the current SHADOW posture.

## Write call sites and gate order (verified)

There is only one runtime caller of the new client writes: `runtime/storefront_ops.py:handle_store_update`. `update_shop_section` and `delete_shop_section` have no caller. No grant can be minted for them either, because `ops/storefront_authority.snapshot` → `director.validate_change` refuses every operation except `updateShop` and `createShopSection` (`store_foundation/director.py:143`).

The order of the gates in `store.update` is:

1. `kind == "storefront"` and a recorded API-writable proposal exist (`storefront_ops.py:120-127`).
2. `director.validate_change` is re-run on the recorded change (`:140`).
3. `protected_phase(ctx) is SHADOW` → hold (`:143-145`). This is the more restrictive of the job's phase and the effective chained phase. **No client and no credentials are constructed in SHADOW.**
4. `storefront_authority.resolve(db, ident, change)` runs the kill switch and then each grant row (`:146-148`).
5. Client `_authorise_storefront_write` (`integrations/etsy.py:1403-1416`) checks:
   - the client phase is in `PHASES_THAT_MAY_PUBLISH`;
   - then, for each field, `live_state.write_refusal(field, grant=, change=)`. That refuses `OWNER_CONFIGURED` (title, icon, banner, About, bio, shop name), refuses the EU-only `policy_additional`, refuses anything outside `AGENT_WRITABLE`, and then calls `OwnerGrant.refusal`. That call checks the effective phase again, `self.change == change`, and `storefront_authority.validate` (kill switch → chain → seal → expiry → action → change digest).
6. Only then are credentials read (`_require(READ)`). `_call` re-requires `DRAFT_WRITE`, which with `owner_authorised` tied to the kill switch is a further check.
7. The send happens inside `ctx.effect("etsy.storefront", ident)`. The effect key is the change-digest prefix, so the same change can never be sent twice: `claim` raises `EffectAlreadyApplied` (`queue/effects.py:191`).

Banner and icon have no write method at all. `update_shop` rejects any field outside `SHOP_UPDATE_SCHEMA` before any gate (`etsy.py`, `EtsyRejected`).

## Independent probe of the real grant (no mocks)

The probe script is kept in the reviewer's scratch directory, not in the repository. It used:
- a temporary SQLite database;
- a recorded announcement proposal built by `director.build_proposals` from a blank-announcement reading;
- `storefront_authority.approve` with a 32-character test token;
- a phase monkeypatched to `production`;
- a recording transport.

| Case | Result |
|---|---|
| Same change, valid grant | `None` (allowed); exactly one PUT, carrying only `announcement` |
| Superset change (announcement + title) | refused: "does not cover this exact change" |
| `update_shop({"title"})` with the valid grant | refused: owner-configured |
| `update_shop({"policy_additional"})` with the valid grant | refused: EU-only |
| `update_shop({"image_url_760x100"})` (banner) | `EtsyRejected`: not in the schema |
| `delete_shop_section` with the announcement grant | refused: different change |
| Kill switch `!= "1"` | refused: no grant overrides it |
| Ops token rotated | refused: seal invalid, chain refused |
| Hand-inserted copy of the grant row with `expires_at` +30 days | refused: chain does not verify (fails closed for **every** grant) |
| Clock +25 h | refused: expired |
| Revoked | refused, by both `validate` and `resolve` |
| Approve with the wrong token | `OpsAuthRefused` |

## Findings

### M-1 (Medium): grant approval has no owner session, step-up or CSRF; operator bearer token only

- **Where:**
  - `app/storefront_authority_api.py:39-43` (`/approve`), `:45-47` (`/revoke`), `:49-52` (`/rebase`);
  - `ops/storefront_authority.py:88-107`;
  - the owner card text `runtime/storefront_ops.py:101-102`, which directs the owner to `POST /api/owner/storefront/approve`.
- **What:** the only approval path is `opsauth.check(Authorization: Bearer <BRAMBLELOOP_OPS_TOKEN>)`.
  - The publication and activation grants also have a command-center route (`app/command_center/approvals.py` → `/api/cc/actions/{action}`, `api.py:678-686`). That route sits behind the owner session, same-origin, CSRF, nonce and `require_stepup`.
  - `grep storefront_authority app/command_center/` finds no such route for the storefront family.
  - The module says so itself: "The principal is the holder of the ops credential, not a separately verified natural person."

  CSRF is not directly exploitable here, because the credential is a header bearer token, not an ambient cookie. The gap is step-up: a buyer-visible write is authorised by a long-lived shared secret with no fresh owner re-verification.
- **Scenario:** a leak of the ops token (operator tooling, logs or a heartbeat context) lets the holder, at any time:
  1. preview and approve any recorded, validating proposal;
  2. rebase the chain, voiding the owner's revocations.

  The blast radius is bounded by the gates above: only the announcement, the two buyer messages and new section titles can be sent, and only text drafted from repo sources that passes the truth lint. Even so, it is an owner-consent bypass for buyer-visible content.
- **Fix:**
  - Wire `storefront_authority.approve`, `revoke` and `rebase` into `command_center.approvals.ACTIONS` with step-up required, as was done for publication and activation.
  - Point the `storefront:write_authority` card at that route.
  - Consider restricting the bearer `/approve` and `/rebase` (for example, refused when a command-center owner exists), leaving the bearer route for preview and revoke only. Revoke is deny-only.

### M-2 (Medium, inherited pattern): the approval credential is also the seal key, and the worker holds it

- **Where:** `ops/storefront_authority.py:53-57` (`_seal` uses `BRAMBLELOOP_OPS_TOKEN`) and `:88-93` (`approve` accepts the same token).
- **What:** to verify a seal at the execution boundary (`store.update` → `validate`), the worker process needs `BRAMBLELOOP_OPS_TOKEN` in its environment. That same value is the approval credential, so any code running in the worker can call `approve(db, authorization=os.environ[TOKEN_VAR], ...)` and mint a valid grant. No in-repository caller does this today: `grep` finds approve called only from the router. Nothing structural prevents it, though, and no test pins it.

  This is the same design as `publication_authority` and `activation_authority`, extended to a new family, so it is not a regression introduced by this branch.
- **Scenario:** a future handler, or a compromised dependency imported by the worker, approves its own storefront proposal. Every downstream gate then passes, because the grant is genuine.
- **Fix:**
  - Separate the keys: seal with a key held only by the web process, or by an owner-session-derived secret, and verify with an asymmetric public key in the worker.
  - Or, at minimum, add a test asserting that no module under `runtime/`, `agents/`, `laura/` or `store_foundation/` imports `storefront_authority.approve` or `rebase`.

### L-1 (Low): Laura's storefront rule runs before the protected rules and captures some price or buyer-reply phrasing

- **Where:** `laura/agency/delegation.py:154-159`. It is evaluated before `_PROTECTED` (`:60-71`).
- **What:**
  - `_PRICE_WORDS` excludes only price, prices, pricing, discount and coupon.
  - `_PROTECTED` treats `sale` as `pricing.experiment`, and "reply/respond … buyer" as `support.reply`.
  - A task such as "run a 30% off sale on the shop home" or "reply to the buyer messages" now routes as a green `storefront.review` mission instead of an owner-action proposal.
- **Why only Low:** there is **no escalation**.
  - The job type is the fixed `storefront.review`, which is OBSERVE, read-only and deterministic.
  - It ignores the task text: the drafts come only from `copy_v2`, `shop_package` and `content`.
  - The mission still goes through `followon.green_allowed` and `orchestrator._enqueue_mission`, which refuses `PROTECTED_JOB_TYPES` (including `store.update`) and anything not generatable or `SAFE_GENERATED` (`autonomy/orchestrator.py:90-93`).

  The cost is misclassification: Laura reports that a pricing or reply request is "being worked on" when it is not, and no owner card is raised for it.
- **Fix:** evaluate `_PROTECTED` first, carving out only the literal phrases "sale message(s)" and "buyer message(s)" as nouns. Alternatively, add `\bsale\b(?!\s+messages?)`, `% off`, `reply` and `respond` to the exclusion. Add tests for both phrasings.

### L-2 (Low): a "DIFFERS" proposal overwrites the owner's own live text, and the grant preview does not show what is replaced

- **Where:**
  - `store_foundation/director.py:230`: the review says "live differs from the repo draft (owner's text stands)";
  - `:283-287`: `build_proposals` nevertheless emits an apply proposal for `DIFFERS`, with `replaces_live_text=True`;
  - `ops/storefront_authority.py:84-85`: `snapshot`, and therefore the approved digest, contains the new change but not the live value it replaces.
- **Scenario:**
  1. The owner edits the announcement on Etsy.
  2. The daily review sees DIFFERS.
  3. A `store.update` is queued and the generic `storefront:write_authority` card is raised.
  4. An owner who approves from the card or preview, without seeing the current live text, reverts their own wording to the repo draft.

  This is consent-quality, not a gate bypass, because the owner must still approve.
- **Fix:**
  - Do not queue `store.update` for `DIFFERS`. Record the proposal only, as live_state does for owner fields.
  - Or include `live_value` and `replaces_live_text` in `snapshot` (and so in the digest), and show them in the card.

### L-3 (Low, test gap): no committed test exercises a real sealed grant end to end

- **Where:** `tests/test_w4_agents.py`.
  - The positive-path tests use `_Grant`, a subclass whose `refusal()` the test controls (`:60-68`).
  - `test_real_owner_grant_refuses_in_shadow_and_on_a_different_change` covers only refusals with no recorded grant.
- **What:** nothing committed covers:
  - `approve` → `validate` succeeding;
  - expiry, revocation, a forged or extended row, token rotation, the kill switch with a real grant;
  - `resolve` choosing among several grants;
  - a second `store.update` for an already-applied change hitting `EffectAlreadyApplied`.

  The reviewer's probe shows all of these behave correctly today. They are not pinned against regression.
- **Fix:** commit the probe's cases (see the table above) as tests, plus one handler-level test in a publishing phase with a real grant, asserting one send and then no second send.

### I-1 (Info): `write_refusal` trusts any `OwnerGrant` subclass

`store_foundation/live_state.py:183` checks `isinstance(grant, OwnerGrant)`, so a subclass that overrides `refusal()` passes every check. The test suite relies on exactly this. It is not reachable from data or HTTP, and `store.update` constructs a real `OwnerGrant`. It is noted because it means the client gate is only as strong as its in-process callers. That is the same trust model as the publication lane.

### I-2 (Info): an applied change can never be re-sent, even under a new grant

The effect key is `("etsy.storefront", digest[:20])` with no grant component.
- If the owner later reverts and then re-approves the identical text, `claim` raises `EffectAlreadyApplied` out of `handle_store_update` (it is not caught). The job fails instead of holding.
- This is safe: it fails closed and prevents replay. The owner-facing message may be confusing.
- The grant itself is not single-use. Within 24 h it is the effect guard, not the grant, that prevents replay.

### I-3 (Info): `content.draft` is also allowed to `growth`

The handler docstring says "storefront_director or growth". Either can enqueue `store.update` for `store_operator`. This is acceptable, because `store.update` holds without a grant, but it widens the set of agents that can raise the owner card.

## Drafts: truthful sources only

`director.drafts()` (`director.py:163-190`) reads only:
- `store_foundation.content.build` (`copy_v2.ANNOUNCEMENT`, or an applied seasonal-takeover banner from our own planner);
- `commerce.shop_package.api_shop_fields()`, which already excludes the owner-configured fields and the EU-only ones;
- `copy_v2` policy texts;
- `navigation.public_nav`, which lists populated categories only.

The drafts make no model call, no network call and no competitor-derived input. Mission inputs from Laura (`question`, `brief`) are never read by the storefront handlers.

Every API proposal is re-validated three times: at drafting, at approval (`snapshot`) and at apply (`store.update`). The validation is the truth lint, `BANNED_EVERYWHERE`, D-FB-18 (no empty categories) and Etsy's length limits.

## Laura delegation and the constitution

- `PROVIDERS["storefront"]` yields only `storefront.review`.
- Conversational delegation yields only `storefront.review`, enqueued through `orchestrator._enqueue_mission`. That function refuses `PROTECTED_JOB_TYPES`, so `store.update` is refused, as is anything outside the charter's `generatable` ∩ `SAFE_GENERATED`.
- The new `SAFE_GENERATED["storefront.review"]` entry is accurate: OBSERVE class, no Etsy write.
- `storefront_director` is GREEN with a CA$0 ceiling. It inherits the COO's `FORBIDDEN_COMBINATIONS`, so `store.update` is forbidden, and `Registry.authorize` refuses it (`test_storefront_director_is_registered_green_cad0_and_cannot_write`).
- **No escalation path was found** (see L-1 for misrouting only).

## Changed tests: none weakened

| Test | Change | Assessment |
|---|---|---|
| `test_roles.DECLARED_BUT_UNBUILT` | drops `content.draft` and `store.update` | Correct: both now have handlers. The test still requires every permitted job type to have a handler or be declared. |
| `test_route_auth_default_deny._want` | adds `/api/owner/storefront/` to the 403 set | Consistent with `security._FORBIDDEN_PREFIXES`. The new router still refuses unauthenticated calls. *Not run by the reviewer:* the scratch venv lacked starlette's test-client dependency. |
| `test_w4_finhealth` | `declared_zero` gains `storefront_director` | Correct: the agent declares CA$0. `misconfigured == []` is still asserted. |
| `test_w4_store_live_state` | "no `update_shop` method exists" → "no ungated write" | A necessary rewrite, given that the owner directive adds the method. The new test is behavioural and stronger in one respect: it sends nothing in shadow *and* production, with `owner_authorised` and `shadow_writes_authorised` both on, for the announcement, title, `policy_additional` and section create. It still asserts that no banner or icon method exists. It does not cover `update_shop_section` or `delete_shop_section`; those are covered by `test_w4_agents` without a grant. |

## Tests run by the reviewer

All runs used `nice -n 19` in a scratch venv built from `requirements.txt`:
- `test_w4_agents`: 13 run, 0 failed.
- `test_w4_store_live_state`: 12 passed.
- `test_roles`: passed, 0 failed.
- `test_w4_finhealth`: 11 passed.
- `test_route_auth_default_deny`: not run. The environment was missing starlette's test-client HTTP dependency; this is not a code failure.
- Independent real-grant probe: every case behaved as tabled above.

## Summary of required and recommended actions

1. **Before enabling storefront writes outside SHADOW:** fix M-1 by adding a command-center owner-session approval with step-up and CSRF.
2. Fix M-2 by separating the seal and verification key from the approval bearer credential, or at least pin "no in-worker approve" with a test.
3. Fix L-1 by putting the protected delegation rules first.
4. Fix L-2 by not queuing an overwrite of the owner's live text, or by binding and showing the replaced value.
5. Fix L-3 by committing real-grant lifecycle tests.

---
_Generated by [Claude Code](https://claude.ai/code)_
