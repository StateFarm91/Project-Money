# W-AGENTS: the Storefront Director, as an operational agent

Branch `claude/w4-AGENTS`, cut from `origin/claude/final-candidate-b997efd` (f19b264e line). Date 2026-10-21 (UTC).
No deploys, no Etsy calls or writes, no spend. Audit input: `AGENT_AUDIT.md` (3546be8).

## 1. Requirement trace

Sources:
- the Master Plan v1.2 (`spec/01_*.pdf`, extracted with pdftotext);
- the FINAL Master v1.0 F-rows (`research/final_build/master_registry.json`) and the v1.1 rows (`master_registry_v1_1.json`);
- the Build 2 ledger (`src/brambleloop/build2/requirements.json`).

The board status is taken from `build2/final_master_closure.json` (completion/maturity).

### Rows that name the roles

| Row | Acceptance criterion (abridged) | Board | What the audit found exists |
|---|---|---|---|
| MP v1.2 §6 | "Storefront Director owns banner, icon, About, policies, sections, announcement, thumbnails and grid coherence." | (spec, no F-id) | No agent. `brand/storefront.py` is a static copy library. |
| MP v1.2 §16 | Org: Creative (Creative Director, Collection Architect, category specialists); Brand/Publishing (**Storefront Director**, Brand Model Consistency, PDF/Charts, Visual Director, Asset Truth, Listing, Thumbnail Warfare, Etsy SEO); Commercial/Growth (Promotion, Pinterest, Social, Email, SEO, Video, Attribution…) | (spec) | Creative: `creative_director`, `crochet_engineer`. Storefront Director, Branding and Marketing: none. Growth: `growth` and `ads`. |
| F-454 | Department agents, including SEO/Marketing | POST-LAUNCH / DEPLOYED | registry only |
| F-890 (v1.1) | 24/7 department agents, including Store/Commerce and Growth/Marketing | COMPLETE / INTEGRATED | charters exist; no storefront agent |
| F-892 (v1.1) | Role charters: no silent authority expansion | COMPLETE / INTEGRATED | `autonomy/charters.py` |
| F-601 | Permanent AI company, with Visual/Creative and Marketing/Growth departments | POST-LAUNCH / INTEGRATED | charters |
| F-613 | Marketing & Growth Department | POST-LAUNCH / INTEGRATED | growth agent; `content.draft` has no handler |
| F-737, F-745 | "Visual/Brand agents" improve the canonical model | POST-LAUNCH / DEPLOYED | under `creative_director` / `publishing` |
| F-799, F-828 | Learn/Content department; Marketing/SEO packages discovery | COMPLETE / POST-LAUNCH | learn agent |
| B2 #76 | The Creative Director maintains the benchmark set | covered | `intel/benchmark_set.py` |

### Storefront surface rows (owned by the Storefront Director per §6)

| Row | Criterion | Board | Exists |
|---|---|---|---|
| F-233 | Storefront Completion Gate: icon, banner, title, announcement, About, policies/FAQ, identity, sections, featured | COMPLETE / INTEGRATED | the check exists (`brand/storefront.check_storefront`); no agent fills the gaps |
| F-239 | Mobile Storefront QA | GATED / MISSING | none (no browser worker) |
| F-241 / B2 #131 | Seasonal Storefront Takeover, with start/revert | COMPLETE / INTEGRATED | planner only; there is no write path |
| F-279 | Storefront-to-listing continuity | COMPLETE / INTEGRATED | seasonal/daily.py |
| F-293 | Storefront Visual Inspection | GATED / MISSING | none |
| F-515 | Shop Completeness Gate, checked continuously | GATED / DEPLOYED | check only |
| F-502 | Storefront Continuous Optimization | POST-LAUNCH / INTEGRATED | growth_ops (listings) |
| F-526 | Shop Home Merchandising (sections, featured) | POST-LAUNCH / INTEGRATED | static SECTIONS; no section writes |
| F-527 | Brand Asset Health, routing fixes to Brand/Visual | POST-LAUNCH / DEPLOYED | static |
| F-584 | Shop Appearance Optimizer: announcement, title, About… | POST-LAUNCH / INTEGRATED | static |
| F-597 | Storefront Change Budget | POST-LAUNCH / none | none |
| F-814 | Content Constellation | POST-LAUNCH / INTEGRATED | `growth/content.py` via `marketing.schedule` |

**Conclusion.** The authorised work in priority order is:
1. Implement the §6/§16 Storefront Director as a registered agent, inside the existing `store_commerce` charter (no new department: the charters fix eleven).
2. Make it read, evaluate and draft continuously (F-233/F-515/F-584/F-526), as proposals.
3. Give its proposals a gated write path, which is the only change to Etsy authority. It is refused in SHADOW and without an owner grant.
4. Let Laura delegate to it.

Branding and Marketing as *separate* agents are **not** authorised by any row: §16 puts storefront and brand under Brand/Publishing, and F-613 puts marketing under the existing Growth department. Inventing them would be a new workforce architecture, which the owner directive forbids.

## 2. What was built

Everything below reuses existing pieces: the job queue, `Registry.authorize`, the action classes, the charters, the COO enqueue boundary, the constitution, the effect guard and the sealed grant ledger. No new department and no new workforce architecture was added.

| Gap (audit) | Closed by |
|---|---|
| E-1 no storefront agent | `agents/registry.py`: `storefront_director`. GREEN, CA$0 daily ceiling (deterministic, no model). It holds `storefront.review` and `content.draft`, and is structurally forbidden everything the COO is, including `store.update`. Cadence `storefront_review`, daily (`runtime/worker.py`). Charter: Store / Commerce (`agents` + `storefront.` prefix + generatable `storefront.review`, with a SAFE_GENERATED reason). There are still exactly 11 departments. |
| (role logic) | `store_foundation/director.py`. `review()` reads the stored getShop and shop_sync readings and the owner observations, and classifies every surface as AGENT_PROPOSAL (an API exists), OWNER_STEP (no API) or PROTECTED (owner-configured title, About, bio; the EU-only `policy_additional`). `build_proposals()` makes deterministic drafts from our own copy modules only, each naming its source. Validation: the truth lint, `BANNED_EVERYWHERE`, D-FB-18 (no empty categories), Etsy's limits (24-character section names, 20 sections, the announcement cap) and `write_refusal`. Proposals are rows (`operating_readings` kind `storefront.proposal`, keyed by the change digest). |
| E-5 `content.draft` and `store.update` had no handlers | `runtime/storefront_ops.py`:<br>• `storefront.review` writes the review row and queues `content.draft` when the agent can fix a gap.<br>• `content.draft` records the proposals and queues one `store.update` per valid API proposal, keyed (proposal, phase, grant). A held proposal therefore retries only when the phase or the grant changes.<br>• `store.update` (store_operator, PUBLISH, protected). In SHADOW it records the proposal as **held**, and no Etsy client is even constructed. Outside SHADOW without a grant it holds and raises one deduplicated card, `storefront:write_authority`. Only with a verified grant does it call the client, inside `ctx.effect("etsy.storefront")`.<br>Both job types are removed from `test_roles.DECLARED_BUT_UNBUILT`. |
| E-2/E-3 no updateShop or section methods | `integrations/etsy.py`: `update_shop`, `create_shop_section`, `update_shop_section`, `delete_shop_section`. Each is gated in this order:<br>1. a publishing phase on the client;<br>2. every field through `live_state.write_refusal(field, grant=, change=)`;<br>3. the `OwnerGrant.STOREFRONT` grant, re-verified for the exact change.<br>The SHADOW draft lane does **not** reach them. `etsy_oauth.SCOPES_REQUIRED` gains the three section operations (shops_w). |
| E-4 no authority lane | `ops/storefront_authority.py`: sealed (HMAC under the ops credential), content-bound to one proposal's exact change, 24 h expiry, revocable, chained (`GrantLedger`), with a deny-only kill switch `BRAMBLELOOP_STOREFRONT_WRITES_AUTHORISED`. Owner API: `app/storefront_authority_api.py` at `/api/owner/storefront/{proposals,preview,approve,{id}/revoke,rebase}`, authenticated by the ops credential, returning 403 on refusal like the other grant routers. It never contacts Etsy or enqueues a job. `write_refusal` with no grant is unchanged, and refuses everything in SHADOW. |
| (d) Laura | `laura/executive/loop.py` PROVIDERS gains `storefront` (`director.summary`). An unreviewed or gapped storefront becomes a priority. That priority goes through the constitution review and `orchestrator._enqueue_mission`, which yields a `storefront.review` mission for `storefront_director`. Conversational delegation (`laura/agency/delegation.py`): "storefront / brand / branding" maps to Store / Commerce, and storefront tasks become a `storefront.review` mission. Price and discount wording stays protected, and replacing the banner or logo stays refused (D-FB-17). |
| (e) store owner cards | `store_readiness.sync_owner_actions`:<br>• `store:OA-D1` (sections) and `store:OA-E` (buyer messages) are agent work. They are no longer asked, and an open row moves to **SUPERSEDED**, not satisfied, with the reason.<br>• `OA-C` drops C5 (announcement, now agent work).<br>• Banner, icon, About, bio, policy texts, location/order/visibility, KYC and banking stay owner cards.<br>`launch/readiness.py`, `intel/etsy_surfaces.py` and `runtime/etsy_ops.py` are untouched (W-LISTREADY owns the closing logic). |

The autonomy map was regenerated (`python -m brambleloop.autonomy.map --write`). The decision index is unchanged, because no DECISION_LOG entry was added.

## 3. Tests

`tests/test_w4_agents.py` (13 tests) covers:
- the agent and its permissions;
- the charter;
- no request sent in SHADOW even with a grant;
- no request sent without a grant, or with an unverified one;
- the title and `policy_additional` refused even with a verified grant;
- a request sent only with a verified grant in a publishing phase;
- a real `OwnerGrant` refusing in SHADOW and on a different change;
- review → draft → `store.update` end to end in SHADOW, with zero Etsy clients built;
- outside SHADOW without a grant: held, with one card;
- sections proposed only for populated categories;
- an untruthful draft rejected;
- the Laura priority, mission and delegation routes;
- store cards superseded.

**Focused regression runs** (venv-integ4, through testslot; all pass, 0 failures):

| Suite | Result |
|---|---|
| test_vacuity | 8 |
| test_launch | 28 |
| test_cost_governance_wave2 | 39 |
| test_search_hero_publish | 4 |
| test_cert_listing_frames | 7 |
| test_v11_autonomy_timeline | pass |
| test_roles | 35 |
| test_w3_k11_authority | 19 |
| test_etsy | 17 |
| test_w4_store_live_state | 12 |
| test_w4_gatesb | 10 |
| test_w4_shopsync | 13 |
| test_v11_autonomy_orchestrator | 15 |
| test_v11_wiring | 15 |
| test_w3_laura_core_executive | 8 |
| test_w3_laura_core_constitution | 8 |
| test_w3_laura_core_wiring | 7 |
| test_w3_laura_cc_delegation | pass |
| test_w3_laura_cc_followon | pass |
| test_rc1_auth | pass |
| test_w4_finhealth | pass |
| test_route_auth_default_deny | pass |
| test_w3_k7_owner_queue | pass |
| test_w4_credhealth | pass |
| test_w3_decision_index | pass |
| test_w4_agents | 13 |

**Test changes, none of them weakening:**
- `test_roles.DECLARED_BUT_UNBUILT` drops `content.draft` and `store.update`, which are now handled.
- `test_w4_store_live_state`: the "no update_shop method" pin is replaced by a stricter check. No banner or icon write exists, and every shop write sends nothing in shadow, without a grant, or for the title or `policy_additional`.
- `test_w4_finhealth` lists `storefront_director` as a declared CA$0 no-spend agent.
- `test_route_auth_default_deny` lists `/api/owner/storefront/` among the 403-contract owner routers.

## 4. Remaining owner and permission gaps

- **P-1 (owner decision).** Approve storefront writes per proposal via `/api/owner/storefront/approve`, and set `BRAMBLELOOP_STOREFRONT_WRITES_AUTHORISED=1`. Both are needed together with a phase out of SHADOW (P-3, card #7). Until then every proposal is held. No new OAuth scope is needed (shops_w was granted 2026-09-25). Cost CA$0.
- **P-2.** The shop title stays owner-configured (`OWNER_CONFIGURED`), so the agent never proposes it.
- **P-4 (no Etsy API).** These stay owner steps: banner, icon, About, member bio, the delivery/returns/privacy/FAQ texts, location, listing order, sold visibility, digital prints, Offsite Ads, KYC, banking and tax. For the blank delivery policy the Director records a ready-to-paste proposal (`OWNER_STEP`). `policy_additional` is not a check (LISTREADY E3): Etsy holds its value, the company never writes it, and the Director never asks to clear it (fixed after the LISTREADY merge).
- **Not built.**
  - `store.update` for live *listing* edits: there is no proposal source. It returns `ran: false` with the reason.
  - Separate Branding and Marketing agents: no requirement authorises them (see §1).
  - Storefront experiments and rollback (E-9).
  - Seasonal takeover execution through updateShop: proposals use the takeover-aware announcement, but there are no start/revert jobs.
  - Mobile visual QA (F-239/F-293, needs a browser worker).
  - `sale_message` has no live reading field (it is not in `live_state.FIELDS`), so its state is UNKNOWN and it is drafted but never proposed until it is read.
- **Coordination.** `store_readiness.py` changed in `sync_owner_actions` (the `_AGENT_WORK` skip) and in the OA-C text. W-LISTREADY's closing-logic changes should be merged on top of this.

## 6. Independent review of b5226f7: fixes for M-1 and M-2 (2026-10-26)

The review (`INDEPENDENT_SECREVIEW_AGENTS_b5226f7.md`) passed with no Critical or High findings. Its two Mediums are fixed below, each with tests in `tests/test_w4_agents_secfix.py`.

**M-1: storefront grant approval had only the operator bearer token.**
- `app/command_center/approvals.ACTIONS` gains four actions, all behind the owner session, CSRF and nonce:
  - `storefront.preview` (read);
  - `storefront.approve` (**step-up required**);
  - `storefront.revoke` (deny-only);
  - `storefront.rebase` (**step-up required**).
- `ops.storefront_authority.approve` and `rebase` take no `authorization`, require `stepped_up=True`, and record principal `owner:command-center`, the actor and `stepped_up`. `_check_one` refuses a grant row made without a step-up.
- The bearer router now offers proposals, preview and revoke only. **There is no `/approve` and no `/rebase`.**
- The `storefront:write_authority` card points at the Command Center action.
- Tests:
  - `test_m1_approve_and_rebase_need_owner_session_csrf_and_fresh_stepup` (no CSRF: refused; stale step-up: 403 `STEP_UP_REQUIRED`; fresh step-up: grant recorded);
  - `test_m1_the_operator_bearer_has_no_approve_or_rebase_route`;
  - `test_m1_the_owner_card_points_at_the_command_center_route`.

**M-2: the approval credential was also the sealing key, and the worker held it.**
- Rows are now signed with **Ed25519**:
  - `BRAMBLELOOP_STOREFRONT_SIGNING_KEY` holds the private key and is set **only on the web process**;
  - `BRAMBLELOOP_STOREFRONT_VERIFY_KEY` holds the public key and is set on the worker, plus the web process for previews and validation.
- Neither key is the approval credential (the owner session) or the ops token, and no key is in the repository. `storefront_authority.generate_keypair()` produces a pair for the operator.
- `core.sealed_chain.GrantLedger` accepts an optional `verify` callable, so an asymmetric family verifies without being able to seal. The HMAC families are unchanged.
- Tests:
  - `test_m2_the_worker_verifies_with_the_public_key_and_cannot_sign` (the worker validates a grant, refuses a different change, and cannot mint a grant even holding the ops token);
  - `test_m2_a_row_signed_with_another_key_never_verifies` (a foreign key can neither append to the chain nor validate an existing grant: fail closed);
  - `test_m2_no_worker_side_module_calls_approve_rebase_or_reads_the_signing_key` (an AST scan of runtime/, agents/, laura/, store_foundation/, autonomy/ and queue/).

**Operator setup (new, before any storefront write).** This is an owner/operator step and costs CA$0:
- generate a key pair;
- set the signing key on the web service only and the verify key on both services;
- writes still also need the kill switch (`BRAMBLELOOP_STOREFRONT_WRITES_AUTHORISED=1`), a publishing phase and a per-proposal owner approval.

Until then every storefront write stays held.

**Regression:** test_w4_agents, test_route_auth_default_deny, test_v11_cc_actions, test_r2_security_actions, test_rc1_auth, test_w4_listready and test_w4_finhealth pass.

**Not changed:** L-1 (Laura's delegation ordering) is Laura code, frozen at 2c29b42; L-2 is not yet addressed. Both are Low.

**L-2 (Low), fixed (2026-10-26): a DIFFERS proposal overwrote the owner's text without showing it.**
- `storefront_authority.snapshot` now carries `replaces` (`live_replaced`):
  - for updateShop, per field: the live value, its state, source and observed_at (UNKNOWN when no reading holds it);
  - for createShopSection: the live section titles it adds to.
- The preview therefore shows exactly what would be overwritten, and the signed digest the owner approves binds it.
- At execution, `store.update` compares the granted `replaces` with the newest **stored** reading of the shop, not a fresh read (wording corrected in §8). If the owner edited the text after approving, nothing is sent: the proposal is held and the owner card is raised.
- Tests (`tests/test_w4_agents_secfix.py`): `test_l2_the_preview_shows_and_binds_the_live_text_it_replaces` and `test_l2_execution_holds_when_the_live_text_changed_after_approval`.
- L-1 stays open because it is Laura code (frozen).

## 7. Independent review of a14c9ef: M-2R and the Low findings (2026-10-26)

**M-2R (Medium), fixed: "signing key on the web service only" separated nothing.**
The embedded worker (`BRAMBLELOOP_EMBEDDED_WORKER`, default `1`, as deployed) runs job handlers inside the web process, so a job could read the signing key and mint a grant. Closed in code three ways:
- **Signing refuses in any process that runs jobs.** `storefront_authority._seal` refuses while `BRAMBLELOOP_EMBEDDED_WORKER` is on, and in any process marked by `mark_job_process()`.
- **Startup scrub.** `app.worker_entry.main` and `app.runner.start` (embedded) call `mark_job_process()`, which removes `BRAMBLELOOP_STOREFRONT_SIGNING_KEY` from `os.environ` before the first handler runs. The process then never signs, even if the key is put back.
- **Owner-request context.** `approve` and `rebase` require the `owner_request` context. Only the Command Center action route sets it, after the session, CSRF/nonce and step-up checks. The session id is recorded in the signed row.

**Correction to the §6 operator setup.** "Web service only" is not enough while the embedded worker is on. A storefront grant can be minted only when the worker runs as its own service and the web service sets `BRAMBLELOOP_EMBEDDED_WORKER=0`. That is a Railway service split, which is an owner spend decision. Until the owner makes it, approval refuses, so every storefront write stays held. This is recorded as a precondition, not a step to perform.

**Tests (`tests/test_w4_agents_secfix.py`):**
- `test_m2r_a_job_in_the_embedded_worker_cannot_mint_a_grant`: a real `store.update` job runs through `Worker.run_once` with the embedded worker on, the signing key set and a forged owner-request context. It is refused, and no APPROVED row is added.
- `test_m2r_worker_startup_scrubs_the_key_and_the_process_never_signs_again`
- `test_m2r_minting_needs_the_owner_request_context_set_only_by_the_cc_route`
- The AST scan now covers the whole package, except the action executor and the authority module.

**The Low findings of the a14c9ef review (each with a test):**
- **L-2:** re-verification incident signatures use aliases (`gate.policy` becomes `listing-rules`), so a detection-only incident never matches scale readiness's `LIKE '%policy%'`. Test: `test_w4_departments.test_l2_a_policy_reverify_incident_does_not_read_as_an_open_policy_risk`.
- **L-3:** the snapshot carries `benchmark_alias(key)` (`bm-` plus 10 hex digits of a SHA-256, so deltas still line up), never the key itself. Pod, seasonal and product-type values are allowlisted to our own labels or digits; anything else becomes `other`. `_assert_no_content` checks the inner values too. Test: `test_l3_snapshot_aliases_the_benchmark_and_allowlists_inner_values`.
- **L-4:**
  - a later pass resolves the open incident, including one under the pre-alias signature;
  - a release counts as fresh only when all four checks have a reading (an UNKNOWN reading counts as run, never as a pass);
  - a check that raises is recorded as a finding (a P2 non-halting incident).
  - Tests: `test_l4_a_later_pass_resolves_the_reverify_incident`, `test_l4_a_check_that_raises_is_recorded_as_a_finding`, and the stricter `test_quality_sweep_reaches_the_coo_and_lauras_idle_priorities_without_laura_code`.
- **L-5:** OA-D1 is superseded only while `storefront:write_authority` is open, and closed only on a FRESH shop_sync reading showing every populated section. Otherwise it is still asked, and an earlier superseded row is reopened. Test: `test_w4_agents.test_agent_doable_store_cards_are_superseded_not_asked`, rewritten to the four cases.
- **I-3:** the revision is clamped with `max(0, …)` in `cir.revise` and in the compile hand-off. Test: `test_i3_a_negative_revision_input_cannot_lift_the_bound`.
- **I-4:** `validate_change` uses set membership in `OWNER_CONFIGURED` and `EU_ONLY` instead of message words. Test: `test_i4_validate_change_refuses_owner_and_eu_fields_by_set_not_wording`.
- **Carried L-1 (Laura delegation ordering):** deferred and still open, because Laura code is frozen at 2c29b42 (DECISION_LOG D-W4-AGENTS-L1-DEFER).


## 8. Delta review of b199cdb: Low and Info fixes (2026-10-26)

The review passed: M-2R is closed, and nothing is Critical, High or Medium. Each fix below has a test that failed against b199cdb's code (checked on a pre-fix copy of the tree) and passes now.

- **L-1, `store.update` replaced-text check.** It reads our last stored shop reading, not the live shop, and treated UNKNOWN = UNKNOWN or an unchanged STALE value as "unchanged". `_replaced_since_approval` now holds unless each replaced field has a FRESH reading **observed after the grant was approved**. UNKNOWN or STALE on either side holds, with "read the shop (store.shop_sync) and retry".
  - The §6 wording is corrected: the check compares against the newest stored reading. A getShop immediately before `update_shop` remains the stronger form once writes are enabled after the service split; that read is an Etsy call, which this lane does not make.
  - Tests: `test_b199_l1_unknown_or_stale_on_both_sides_is_never_unchanged`, and `test_l2_execution_holds_when_the_live_text_changed_after_approval`, now stricter: the approval-time reading alone holds, and a fresh post-approval reading with the same text passes.
- **L-2, salvage.** An unreadable radar portfolio or diversification now makes that gate UNKNOWN for every row, never FAIL or PASS. `rescue_candidate` now needs a known creative verdict. Test: `test_b199_l2_salvage_unreadable_shared_inputs_are_unknown_and_rescue_needs_creative`.
- **L-3, cross-sell graph.** Buyer-facing edges (`related`, `bundles`, `next_projects.in_catalogue`) now point only at certified products. Uncertified bundle seeds and planned family members move under `planned` (`internal: True`). The `rule` text names the buyer-facing fields. `test_f775…` now checks every buyer-facing field.
- **I-1, unverifiable checks.** `quality_ops.unverifiable` lists each (release, check) whose newest reading is UNKNOWN, with its count over 30 days. `gate.quality` reports it. Test: `test_b199_i1_a_check_that_can_never_read_is_reported_as_unverifiable`.
- **I-4, alias and delta.** The first delta after aliasing now lines up: a previous reading's raw key is aliased before comparing. Test: `test_b199_i4_the_first_delta_after_aliasing_lines_up_with_a_raw_key_reading`.
  - The alias's reversibility is **accepted** and recorded: it keeps the name out of stored readings, which is the aim, and is not anonymisation. An HMAC with a server secret is the upgrade if needed.
- **I-6, scorecard.** A period with unknown orders no longer adds 0 orders. Conversion is computed over periods with known orders only (orders and visits together). `winner` is True only on enough known orders, and False only when no period's orders are unknown. Test: `test_b199_i6_a_period_with_unknown_orders_never_adds_zero_orders`.
- **I-7, asset health.** A failure in the asset-health check no longer fails the storefront review; the health reading is UNKNOWN. Test: `test_b199_i7_an_asset_health_failure_does_not_stop_the_storefront_review`.
- **I-2, residual risk after the service split: recorded.** Once the web service holds the key, the `owner_request` ContextVar is defence in depth, and the static guard can be evaded by aliasing the import. The lasting fix is owner-device signing of the previewed digest, the prior review's option 2. That changes the owner's authentication device flow, so it is an owner decision and a precondition alongside the service split.
- **I-3, revocation: recorded.** Revoking appends a signed row, so it is unavailable wherever signing is refused (today: everywhere). That is harmless because no grant can exist there, and the kill switch `BRAMBLELOOP_STOREFRONT_WRITES_AUTHORISED` is a deny path that needs no key. Operators should use the kill switch to stop storefront writes in the single-container deployment.
- **I-5, contracts test: already done** at 5d138275 (W1): `tests/test_w4_contracts.py` runs `check()`, and six consumers call `require()`.
- **Carried L-1 (Laura):** still deferred, D-W4-AGENTS-L1-DEFER.
