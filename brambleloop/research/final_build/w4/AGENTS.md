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
- At execution, `store.update` compares the granted `replaces` with the live shop now. If the owner edited the text after approving, nothing is sent: the proposal is held and the owner card is raised.
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
