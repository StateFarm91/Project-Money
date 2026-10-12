# Independent security and release review: hotfix candidate aa1e76d

- Reviewed: 2026-10-12 (UTC)
- Scope: `git diff c498888e30829812794484f8a63653e93f0b616e aa1e76d` only. That is production c498888 plus `claude/w4-LAURAFIX` and `claude/w4-ETSYSHOPID` (21 files, +1707/-70).
- Method: I read the diff and the surrounding code at aa1e76d with `git show`. The W4-HOTFIX1 worktree was only read; I ran nothing in it. I made one import smoke check against a `git archive` copy of aa1e76d in a scratch directory. It imported the module chain `laura_briefing`, `briefing`, `etsy_shop_binding` and `etsy_ops` without error, and it printed `OUTPUT_TOKEN_BOUND = 1472 == routing literal == PROMPT.max_output_tokens`, `PICK_LIMITS = {last_window 6, departments 6, blockers 6, decisions 0, facts_unknowns 0, autonomous 4}`, and `routing.estimate_cad("laura.ceo_briefing") = CA$0.056`.
- Line numbers below refer to aa1e76d under `brambleloop/src/brambleloop/`.

## Verdict: NO BLOCKER

None of the seven checks fails. I have four findings, all LOW or INFO. None of them needs a change before this candidate is released.

## Findings, ranked

### L1 (LOW): grouping can merge different mandatory incidents into one rendered record
`laura/agency/briefing.py:299-320`, `:323-359`

The grouping key is `(severity, halts_publication, incident_root(...))`. `incident_root` tries three things in order:
1. a `root_key`, `dedupe_key` or `root_cause` value in the detail;
2. otherwise `job_type` plus the error class (`_ERR_CLASS_RX`);
3. otherwise the signature and summary with their instance-specific parts masked, truncated to 160 characters.

Two different P1 incidents can therefore land in one group, for example two different failures that share a `job_type` and both raise `TimeoutError`. Nothing is dropped:
- every row is read, and the query has no row cap (`:333-340`). The old path read at most 200 open rows through `readers.incidents`, so this is stricter than before;
- `severity` and `halts` are part of the key, so a halting or P0 incident is never folded into a lesser one;
- each group is a mandatory blockers record that is never capped (`:571`) and carries its occurrence count;
- the five most recent examples are attached (`GROUP_EXAMPLES`).

The drawback is that the owner sees only the latest row's summary as the headline. The other root causes in a group appear only in the expandable examples, and only the five most recent are there. Suggested follow-up, not urgent: include `signature` in the `job:` key.

### L2 (LOW): an unresolved binding is retried on every Etsy client build
`integrations/etsy_shop_binding.py:168-196`, `runtime/etsy_ops.py:124`

This applies when there is no `ETSY_SHOP_ID`, no binding is stored, and a token exists. In that state every `build_client` call (observation cadences, `listing_outcomes`, `pipeline` activation) runs `resolve`, which makes 1-2 Etsy GETs. On the mismatch path it also writes an `AuditLog` row each time. The incident is deduplicated by `open_or_restate`; the audit rows are not. Exposure is bounded by how often the cadences run, and the requests are read-only.

### I1 (INFO): the stored binding is not tied to a particular grant
`core/oauth_store.py:408-445`

The binding records `user_id`, but `bound_shop_id` checks only that `shop_name == "BrambleloopStudio"` (`etsy_shop_binding.py:40-53`). Suppose the owner later re-authorises from a different Etsy account. The old binding would remain and be paired with the new token. That cannot bind a different shop. At worst, Etsy returns 403 because the token does not own the shop. Optional hardening: re-resolve, or clear the binding, when the credential row is replaced.

### I2 (INFO): stale purpose label in a comment
`agents/registry.py:781` still says `laura.ceo_briefing@3`; the prompt is now `@4`. A search found nothing that filters spend on the `@3` string.

## Checks

### (1) Spend controls: PASS
- **CA$0 agents.** CA$0 agents are still refused before any call. `synthesize` records the refusal and returns when `permission <= 0` (`gateway/laura_briefing.py:184-195`), before `gateway_for`. `check_budget_cad` also refuses any positive estimate. Neither path changed.
- **Reservation before the call.** The reservation still happens before the provider call, outside the retry `try`. `ModelGateway` calls `gw.check_budget_cad(... estimate_cad=self._estimate_cad(prompt, provider, user) ...)` (`gateway/model_gateway.py:239-245`); that call covers the monthly ceiling, the agent's CA$0.50 daily permission and the reservation. The diff does not touch this.
- **The larger output cap is in the estimate.** `_estimate_cad` uses `prompt.max_output_tokens` (`model_gateway.py:404`), which is now `OUTPUT_TOKEN_BOUND` = 1472 (`laura_briefing.py:83, 122`). The pre-park estimate `routing.estimate_cad` reads `routing.TASKS[...]` = 1472 (`gateway/routing.py:218`). The two values are tested for equality, and I confirmed they match at import. Laura's `estimate()` also uses `PROMPT.max_output_tokens`.
- **No double billing.** `OutputTruncated` is raised inside the existing billing `try` (`model_gateway.py:251-258`). It is billed exactly once, through `_billing(e, response, reservation)` from the response's own token usage (`:267`, `:446-455`). It is not re-raised past the record. `synthesize` keeps `max_attempts_per_provider=1`.
- **No skipped reservation.** The new `except OutputTruncated` in `synthesize` (`:217`) only labels the reason and reports `gateway.spend_cad()`.
- **Replayed answers stay unbilled.** `_decode_response` defaults `stop_reason` to `""`, so cached entries from before this change still decode. A replayed answer stays `replayed_not_billed`.

### (2) Prompt injection: PASS
- **Records stay quoted.** Records still enter the prompt only through `ev_lines`, `dec_lines` and `prop_lines`, each escaped with `_data()` and wrapped in `DATA_OPEN`/`DATA_CLOSE` (`laura_briefing.py:133-151`).
- **Grouped text stays inside the data block.** The grouped incident is a normal pack item: its `statement` is a code-built prefix plus `summary[:300]`, and it is escaped like any other. Its `examples`, `group_key`, `first_seen` and `last_seen` are not sent to the model at all.
- **The new selectable line is code-made.** It sits outside the data block, but contains only component names and ids. Component names come from `parsed["components"]` and are filtered through `PICK_LIMITS`, so anything unknown counts as 0 and is skipped. The ids are `E#`/`P#` values generated by code (`briefing.py:886-902`).
- **Allow-list and K are enforced in code.** `validate` still rejects any id outside `_allowed_ids`, any duplicate, and any field outside the contract. It then trims the reply to K deterministically: `kept = [...][:PICK_LIMITS.get(comp, 0)]` (`:848`). `model_lines` renders at most `pick_limit(comp, cap)` ≤ K lines. Code still renders every line.
- **UI.** In `laura.js`, `groupDetail` builds the page only with `h()`, which creates text nodes only (`static/js/dom.js:23-56`). It has no `innerHTML` path, and the example `source` is text, not a link.

### (3) Mandatory incidents: PASS
- Every open P0/P1 and every publication-halting incident is selected with no limit (`briefing.py:333-340`).
- Grouping keeps `severity` and `halts` in its key.
- Each group is a blockers record in `mandatory()` and is never capped (`:571`).
- Lower-severity incidents are counted in `incidents_more`, using the true open total (`:376-378`).
- K applies only to optional picks: mandatory ids are removed before the trim (`:847-848`) and always render first.
- See L1 for the one caveat.

### (4) Etsy binding: PASS
- **Only the expected shop can be bound.** A shop is bound only if `shop_name == ETSY_HANDLE` ("BrambleloopStudio"), the `shop_id` is numeric, and any owner `user_id` that Etsy returns equals the grant's user (`etsy_shop_binding.py:149-155`). On any mismatch the code opens a P1 incident and an audit row, and stores nothing. When reading, `bound_shop_id` checks the name again (`:40-53`). If the reply lists more than one shop, `resolve` returns `unreadable`.
- **No secrets leak.** The access token is used only to parse its numeric prefix and is never stored or returned (`:130-131`). The audit detail, incident detail, return value and `log.info` carry only `shop_id`, `shop_name`, `user_id`, `how` and `expected`. The `log.warning` logs `type(e)` and `str(e)[:200]`; the Etsy exception messages I checked do not include token values. The binding payload in `operating_readings` holds no secret, and no endpoint was added or changed.
- **`ETSY_SHOP_ID` still wins.** The binding is consulted only `if not shop` (`integrations/etsy.py:369`). This holds in `shop_id_present`, `_configured` and `_env_presence` too.
- **No write path added.** The new code makes two GETs (`getMe` and `getShopByOwnerUserId`) with `Authority.READ` (`:139`). `getShopByOwnerUserId` requires `shops_r` (`etsy_oauth.py:121-123`).
- **Gates unchanged.** SHADOW, publication, activation and `owner_authorised` gating are unchanged. Once a shop is bound, the existing write paths see credentials exactly as if `ETSY_SHOP_ID` were set, and they are still behind those same gates. The executor gate still needs a recorded successful probe in addition to the id (`build2/executor.py:592`).
- **Refresh persistence intact.** The compare-and-set write on token refresh is unchanged: `_persisting_on_refresh(db, e, current_token=stored_token)` (`etsy.py:376`). `ensure_credentials` reuses the same provider through `dataclasses.replace` (`:196`), so there is no second refresh and the compare-and-set state stays current.
- **Scopes cannot widen.** `_refresh_now` copies the previous scopes only when the refresh response omits `scope` (`etsy_oauth.py:591-597`). A scope the response does return, including a narrower one, is used as returned. The provider's starting scopes come from the stored grant row (`etsy.py:395`, `oauth_store.stored_scopes`). The store updates the row with `scopes or row.scopes`. So nothing adds a scope that the grant did not have, and Etsy enforces scope on its side in any case.

### (5) Auth: PASS
No route, endpoint or auth code changed. The only UI change is `views/laura.js`, which renders extra fields returned by the existing, authenticated Laura endpoint. The new `synthesis.truncated` and `synthesis.incidents` hold counts and booleans only.

### (6) Schema: PASS, no change
No model or migration file changed. The binding uses the existing `operating_readings` table (`kind="etsy.shop_binding"`, which fits String(60), and `period_key="bound"`, which fits String(20)). The table's `UniqueConstraint(kind, period_key)` means a concurrent first insert raises inside `resolve`, which `ensure_credentials` catches and turns into `None` for that one build. The audit `action` strings fit String(80), and the incident signature fits String(200). This matters because the production defect fixed here was StringDataRightTruncation.

### (7) Production startup: PASS
- `laura_briefing` now imports `briefing` at module level. `briefing` imports `laura_briefing` only inside a function, so there is no import cycle; the smoke import confirms this in both orders.
- `prompts.register` for v4 succeeds.
- `OUTPUT_TOKEN_BOUND` is computed at import from constants only.
- No start-up path calls `build_client` or `resolve`.
- `ModelResponse.stop_reason` is a new trailing field with a default.
- `load_shop_binding` returns `None` on any error, so a missing table cannot crash anything.
