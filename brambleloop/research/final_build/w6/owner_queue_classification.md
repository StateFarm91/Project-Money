# Owner-queue classification under D-OWNER-STANDING-INTERNAL (ENG-APPROVALS, 2026-11-19)

The owner directive of 2026-11-19 (recorded verbatim in `DECISION_LOG.md` as
`D-OWNER-STANDING-INTERNAL` and in `authority/standing_internal.DIRECTIVE_TEXT`) replaces the
~106-card owner queue. It does this with standing authorisations, automatic closure of
redundant, stale or satisfied requests, and one batch of genuine exceptions.

The table below is generated from the live classifier
(`authority.standing_internal.classify`) over every OwnerAction kind the producer inventory
found. The test `tests/test_eng_approvals.py::INVENTORY` pins it: no inventoried kind may fall
to the fail-closed default.

## Sources of owner cards

1. **OwnerAction rows.** These are about 60 producer sites and about 90 kinds. Each is listed
   below with its producer.
2. **Command Center Approvals cards** (`app/command_center/approvals.py`):
   - executor gate cards and standalone OwnerAction cards (`build2.executor.approval_inbox`);
   - `PUBLICATION`, `ACTIVATION`, `STANDING_POLICY`, `policy_review` (#39) and
     `RELEASE` cards.
3. **Incidents routed to the owner.** These are not cards. The P0 board lists them, and
   halting incidents hold *publication*. A policy-change incident (#39) is the
   `policy_review` card's own source.
4. **Holds that wait on an owner decision:**
   - policy reviews (`ops.policy_watch` #39 → `policy_review` card);
   - launch decisions (`listing_fees`, `brand_clearance`, `phase`);
   - brand clearance;
   - children's decisions (`childrens-decision:<slug>`);
   - standing-policy holds (`standing_policy.hold:`).

   All of these are classified below or in the card-kind table.

## Dispositions

- **ROUTINE_INTERNAL**: covered by the standing authority. The sweep (`ops.owner_queue_consolidate`,
  hourly) moves the card to `superseded` and writes an `owner_action.standing_authority` audit
  row that cites the directive. The work proceeds inside every existing gate and ceiling.
- **AUTO_CLOSE**: redundant, stale or already satisfied. The card is closed with the rule's reason
  (`superseded`, `withdrawn` or `expired`) and gets the same audit row.
- **GENUINE_EXCEPTION**: stays with the owner. Only the directive's eight classes qualify. An unknown
  kind is `unclassified_fail_closed`, which stays with the owner and is counted on the P0 board.

Nothing is deleted. Each row keeps its `state`, `state_at` and `state_reason`, plus the
`owner_action.lifecycle` audit row and the `owner_action.standing_authority` audit row (retention:
lifetime).

## OwnerAction kinds

| kind (placeholders filled as in the test) | producer | disposition | class / rule | why |
|---|---|---|---|---|
| `etsy.auth:reauthorise` | runtime/etsy_ops.py:285 | GENUINE_EXCEPTION | grant_signature_or_step_up | OAuth consent by the account holder |
| `reauthorise_transactions_r` | store_foundation/store_readiness.py:571 | GENUINE_EXCEPTION | grant_signature_or_step_up | OAuth consent by the account holder |
| `store:etsy.openapi_review` | runtime/etsy_ops.py:1673 | ROUTINE_INTERNAL | engineering | covered by D-OWNER-STANDING-INTERNAL: research/engineering -- the weekly re-verification is company work |
| `etsy_surface:messages_watch` | intel/etsy_surfaces.py → runtime/etsy_ops.py:401 | GENUINE_EXCEPTION | external_policy_attestation | the owner's message-watch attestation |
| `etsy_surface:policy_violations_check` | intel/etsy_surfaces.py → runtime/etsy_ops.py:401 | GENUINE_EXCEPTION | external_policy_attestation | a Policy Violations check |
| `etsy_surface:etsy_ads_off` | intel/etsy_surfaces.py → runtime/etsy_ops.py:401 | GENUINE_EXCEPTION | paid_ads_or_subscriptions | Etsy Ads stay off unless the owner says |
| `etsy_surface:offsite_ads_fee_readout` | intel/etsy_surfaces.py → runtime/etsy_ops.py:401 | GENUINE_EXCEPTION | physical_evidence | a Finances reading |
| `etsy_surface:first_monthly_statement` | intel/etsy_surfaces.py → runtime/etsy_ops.py:401 | GENUINE_EXCEPTION | physical_evidence | the monthly statement file |
| `etsy_surface:payment_settings_setup` | intel/etsy_surfaces.py → runtime/etsy_ops.py:401 | GENUINE_EXCEPTION | kyc_legal_banking | Etsy Payments onboarding |
| `etsy_surface:legal_and_tax_setup` | intel/etsy_surfaces.py → runtime/etsy_ops.py:401 | GENUINE_EXCEPTION | kyc_legal_banking | identity, legal and tax |
| `etsy_surface:apps_none_installed` | intel/etsy_surfaces.py → runtime/etsy_ops.py:401 | GENUINE_EXCEPTION | external_policy_attestation | no third-party app attestation |
| `etsy_surface:info_and_appearance_setup` | intel/etsy_surfaces.py → runtime/etsy_ops.py:401 | GENUINE_EXCEPTION | publication_or_activation | a change in the live Etsy shop |
| `etsy_surface:shared_access_empty` | intel/etsy_surfaces.py → runtime/etsy_ops.py:401 | GENUINE_EXCEPTION | external_policy_attestation | Shared Access attestation |
| `etsy_surface:policy_settings_paste` | intel/etsy_surfaces.py → runtime/etsy_ops.py:401 | GENUINE_EXCEPTION | publication_or_activation | a change in the live Etsy shop |
| `etsy_surface:subscription_none` | intel/etsy_surfaces.py → runtime/etsy_ops.py:401 | GENUINE_EXCEPTION | paid_ads_or_subscriptions | no paid Etsy subscription |
| `etsy_surface:webhook_order_paid` | intel/etsy_surfaces.py → runtime/etsy_ops.py:401 | GENUINE_EXCEPTION | grant_signature_or_step_up | a webhook signing secret |
| `etsy_surface:developer_portal_quota` | intel/etsy_surfaces.py → runtime/etsy_ops.py:401 | GENUINE_EXCEPTION | physical_evidence | a Developer Portal reading |
| `search_visibility:launch_week` | runtime/storefront_watch.py:78 | GENUINE_EXCEPTION | physical_evidence | a Shop Manager reading |
| `storefront:write_authority` | runtime/storefront_ops.py:117 | GENUINE_EXCEPTION | grant_signature_or_step_up | signed storefront grants |
| `storefront.asset:ICON_MISSING:shop` | store_foundation/asset_health.py:319 | GENUINE_EXCEPTION | publication_or_activation | an upload in Etsy Info & Appearance |
| `store:OA-OBS` | store_foundation/store_readiness.py:571 | GENUINE_EXCEPTION | external_policy_attestation | what the live shop shows, observed by the owner |
| `store:OA-B` | store_foundation/store_readiness.py:571 | GENUINE_EXCEPTION | grant_signature_or_step_up | account settings and 2FA |
| `store:OA-BANNER` | store_foundation/store_readiness.py:571 | GENUINE_EXCEPTION | physical_evidence | a phone screenshot of the banner crop |
| `store:OA-C` | store_foundation/store_readiness.py:571 | GENUINE_EXCEPTION | publication_or_activation | a change in the live Etsy shop settings |
| `store:OA-D1` | store_foundation/store_readiness.py:571 | GENUINE_EXCEPTION | publication_or_activation | a change in the live Etsy shop settings |
| `store:OA-E` | store_foundation/store_readiness.py:571 | GENUINE_EXCEPTION | publication_or_activation | a change in the live Etsy shop settings |
| `store:OA-F` | store_foundation/store_readiness.py:571 | GENUINE_EXCEPTION | publication_or_activation | a change in the live Etsy shop settings |
| `store:OA-G1` | store_foundation/store_readiness.py:571 | GENUINE_EXCEPTION | external_policy_attestation | an Etsy shop-option attestation |
| `store:OA-G2` | store_foundation/store_readiness.py:571 | GENUINE_EXCEPTION | paid_ads_or_subscriptions | Offsite Ads enrolment (15% fee) |
| `store:OA-LIVE-title` | store_foundation/store_readiness.py:571 | GENUINE_EXCEPTION | publication_or_activation | a change in the live Etsy shop settings |
| `store:etsy.ui_drift_review` | commerce/surface_inventory.py:348 | ROUTINE_INTERNAL | engineering | covered by D-OWNER-STANDING-INTERNAL: research/engineering -- the surface inventory is company work |
| `etsy_shop` | launch/readiness.py → runtime/release.py:5231 | GENUINE_EXCEPTION | kyc_legal_banking | identity verification and seller terms |
| `payout` | launch/readiness.py → runtime/release.py:5231 | GENUINE_EXCEPTION | kyc_legal_banking | payout bank account and tax details |
| `listing_fees` | launch/readiness.py:183 → runtime/release.py:5231 | GENUINE_EXCEPTION | spend_beyond_approved_budgets | fees beyond the CA$6 opening budget need the owner |
| `physical_calibration` | launch/readiness.py:305 (not raised today) | GENUINE_EXCEPTION | physical_evidence | a physical sample |
| `model_credits` | launch/readiness.py:364 | GENUINE_EXCEPTION | kyc_legal_banking | a payment by the account holder |
| `benchmark_challenge` | launch/readiness.py:383 | GENUINE_EXCEPTION | spend_beyond_approved_budgets | buying benchmark patterns (CA$300) |
| `brand_clearance` | launch/readiness.py:405 | GENUINE_EXCEPTION | kyc_legal_banking | legal risk acceptance / trademark |
| `artifact_storage` | launch/readiness.py:428 | GENUINE_EXCEPTION | paid_ads_or_subscriptions | an object-storage subscription |
| `phase` | launch/readiness.py:443 | GENUINE_EXCEPTION | publication_or_activation | a phase move out of shadow |
| `first_public_listing:approve` | publish/first_listing_card.py | GENUINE_EXCEPTION | publication_or_activation | the first public listing and its fee (step-up) |
| `benchmark_observation` | launch/access.py:229 | GENUINE_EXCEPTION | grant_signature_or_step_up | developer credentials of the account holder |
| `model_provider` | launch/access.py:272 | GENUINE_EXCEPTION | grant_signature_or_step_up | a provider key set in the host by the owner |
| `credential_rotation:ANTHROPIC_API_KEY` | ops/credential_register.py:140 | GENUINE_EXCEPTION | grant_signature_or_step_up | rotating an exposed credential |
| `image_benchmark_budget` | runtime/release.py:9156 | GENUINE_EXCEPTION | spend_beyond_approved_budgets | raising a provider budget |
| `canonical_model_selection` | runtime/release.py:9328 | GENUINE_EXCEPTION | grant_signature_or_step_up | an owner approval record (never forged) |
| `canonical_model_approval` | runtime/release.py:10006 | GENUINE_EXCEPTION | grant_signature_or_step_up | an owner approval record (never forged) |
| `model_provider_balance` | ops/funding.py:104/207 | GENUINE_EXCEPTION | kyc_legal_banking | a payment by the account holder |
| `model_provider_balance:bfl` | ops/funding.py:104/207 | GENUINE_EXCEPTION | kyc_legal_banking | a payment by the account holder |
| `model.vendor_switch_routed_only` | gateway/providers.py:99 | ROUTINE_INTERNAL | engineering | covered by D-OWNER-STANDING-INTERNAL: engineering -- routed to Main (configuration), not an owner decision |
| `model.routes_invalid` | gateway/providers.py:191 | ROUTINE_INTERNAL | engineering | covered by D-OWNER-STANDING-INTERNAL: engineering -- routed to Main (configuration), not an owner decision |
| `laura.voice.listen_shortlist` | laura/agency/voice_selection.py:106 | GENUINE_EXCEPTION | paid_ads_or_subscriptions | a voice provider account / paid trial |
| `creative.reengineer:owner_choice` | runtime/engineering_ops.py:270 | ROUTINE_INTERNAL | product_development | covered by D-OWNER-STANDING-INTERNAL: product development -- which legacy products to re-engineer |
| `childrens-decision:demo-mat` | runtime/release.py:10413 | GENUINE_EXCEPTION | certification_construction_safety_authority | children's-safety decision (A1-R) |
| `listing.live_update:demo-mat@v` | runtime/release.py:2273/2322 | GENUINE_EXCEPTION | publication_or_activation | changing a live listing |
| `physical_size_conflict:demo-mat@v:row` | runtime/release.py:3658 | GENUINE_EXCEPTION | certification_construction_safety_authority | lifting a physical size halt |
| `physical_review:demo-mat@v:row` | runtime/release.py:3928 | GENUINE_EXCEPTION | physical_evidence | a partial physical sample |
| `physical_evidence:demo-mat@v:abcdefabcdef` | runtime/pipeline.py:1539 | GENUINE_EXCEPTION | physical_evidence | an independent tester make / swatch |
| `chain-deadend:pricing:demo-mat@v` | runtime/chain_successors.py:112 | ROUTINE_INTERNAL | product_development | covered by D-OWNER-STANDING-INTERNAL: pricing / product development before publication |
| `standing_policy.hold:demo-mat@v:abcdefabcdef` | ops/standing_issuer.py:714 | GENUINE_EXCEPTION | publication_or_activation | a release outside the standing policy |
| `standing_policy.withdrawal_unconfirmed:listing` | ops/standing_withdrawal.py:226 | GENUINE_EXCEPTION | publication_or_activation | deactivation on Etsy |
| `autonomy:store_commerce:publication_review` | autonomy/generators.py:241 → orchestrator.py:149 | AUTO_CLOSE | redundant | each certified release has its own publication card carrying this decision |
| `listing_package:demo-mat@v:abcdef` | publish/listing_package.py:486 | AUTO_CLOSE | redundant_withdrawn | the publication grant previews and binds the same listing content; nothing reads a closed package card as approval |
| `draft_reconcile:abcdef` | publish/draft_resolver.py:219 | GENUINE_EXCEPTION | publication_or_activation | binding an Etsy draft to a release |
| `etsy.exercise.stranded_draft.listing` | integrations/etsy_exercise.py:294 | GENUINE_EXCEPTION | publication_or_activation | deleting a draft in Shop Manager |
| `taxonomy_drift:snap` | integrations/taxonomy_drift.py:269 | ROUTINE_INTERNAL | recovery | covered by D-OWNER-STANDING-INTERNAL: recovery -- re-certifying drifted listings is internal work |
| `portfolio.retire:demo-mat` | growth/portfolio_act.py:289 | GENUINE_EXCEPTION | publication_or_activation | deactivating a live listing |
| `portfolio.rework:demo-mat` | growth/portfolio_act.py:289 | ROUTINE_INTERNAL | product_development | covered by D-OWNER-STANDING-INTERNAL: product development -- a new design version |
| `ads.scale:demo-mat` | runtime/growth_ops.py:515 | GENUINE_EXCEPTION | paid_ads_or_subscriptions | paid advertising |
| `ads.proposal:abcdef` | growth/ads_readiness.py:784 | GENUINE_EXCEPTION | paid_ads_or_subscriptions | paid advertising |
| `etsy_ads_eligibility_evidence` | growth/ads_readiness.py:227 | GENUINE_EXCEPTION | paid_ads_or_subscriptions | an Etsy Ads reading (no activation) |
| `creators.graduate:tester` | runtime/growth_ops.py:784 | GENUINE_EXCEPTION | kyc_legal_banking | an agreement with a real person |
| `club:launch_decision` | runtime/commerce_readings.py:216 | GENUINE_EXCEPTION | publication_or_activation | launching a buyer-facing club |
| `spend.ceiling.2026-11` | runtime/pipeline.py:3688 | GENUINE_EXCEPTION | spend_beyond_approved_budgets | raising a monthly spend ceiling |
| `reinvestment:2026-11` | commerce/order_readings.py:315 | GENUINE_EXCEPTION | spend_beyond_approved_budgets | reinvesting revenue |
| `knowledge_gap:line` | intel/knowledge_gaps.py:279 | GENUINE_EXCEPTION | spend_beyond_approved_budgets | buying a reference pattern |
| `benchmark_refresh:trigger:subject` | intel/benchmark_refresh.py:222 | GENUINE_EXCEPTION | spend_beyond_approved_budgets | buying a benchmark pattern |
| `etsy.dashboard:order:ref` | integrations/etsy_dashboard.py:151 | GENUINE_EXCEPTION | publication_or_activation | contact with a buyer |
| `etsy.dashboard:renewal:listing` | integrations/etsy_dashboard.py:151 | GENUINE_EXCEPTION | spend_beyond_approved_budgets | a renewal fee outside the opening budget |
| `correction_notice:demo-mat@v` | commerce/buyer_trust.py:878 | GENUINE_EXCEPTION | publication_or_activation | a message to buyers |
| `legal_review:etsy.policy_violation:item` | commerce/policy_violations.py:130 | GENUINE_EXCEPTION | kyc_legal_banking | an IP/account notice; legal advice |
| `policy_violation_overdue:etsy.policy_violation:item` | commerce/policy_violations.py:192 | GENUINE_EXCEPTION | external_policy_attestation | an Etsy policy-violation item |
| `support.first_response:case:one` | support/response_watch.py:227 | GENUINE_EXCEPTION | publication_or_activation | a reply to a buyer |
| `support_defect_decision:support.defect:sig` | support/defects.py:362 | GENUINE_EXCEPTION | certification_construction_safety_authority | a reader-reported pattern defect: only the owner's ruling releases the withholding (review M1; never superseded) |
| `improve.retirement:weekly_review` | improve/director.py:481 | ROUTINE_INTERNAL | agent_coordination | covered by D-OWNER-STANDING-INTERNAL: agent coordination -- the weekly retire/merge review |
| `improve.architecture:add` | improve/evolution.py:290 | ROUTINE_INTERNAL | agent_coordination | covered by D-OWNER-STANDING-INTERNAL: agent coordination -- specialist agents |
| `improve.architecture:revise_metric` | improve/evolution.py:290 | ROUTINE_INTERNAL | agent_coordination | covered by D-OWNER-STANDING-INTERNAL: agent coordination -- department metrics |
| `improve.stop_list:weekly` | improve/evolution.py:290 | ROUTINE_INTERNAL | scheduling | covered by D-OWNER-STANDING-INTERNAL: scheduling -- the weekly STOP list |
| `improve.upgrade:one` | improve/upgrades.py:429 | GENUINE_EXCEPTION | certification_construction_safety_authority | a gate-tier improvement (cells approval) |
| `improve.league:one` | improve/upgrades.py:429 via improve/league.py:807 | GENUINE_EXCEPTION | grant_signature_or_step_up | promoting a challenger is a step-up owner act |
| `improve.challenger_run:one` | improve/challenger_runs.py:119 | ROUTINE_INTERNAL | learning | covered by D-OWNER-STANDING-INTERNAL: learning -- one league run (<= CA$2) inside the approved CA$100/month model ceiling, which SpendGuard still enforces |
| `laura:growth:seo.cycle` | laura/executive/loop.py:438, laura/agency/followon.py:144 → autonomy/orchestrator.py:149 | ROUTINE_INTERNAL | autonomous_class | covered by D-OWNER-STANDING-INTERNAL: seo.cycle (DRAFT) is autonomous work |
| `laura:store.publish:demo-mat` | laura/executive/loop.py:438, laura/agency/followon.py:144 → autonomy/orchestrator.py:149 | GENUINE_EXCEPTION | publication_or_activation | store.publish is PUBLISH, a gated class the directive does not cover |
| `decision.api_vision_equivalence` | app/command_center/approvals.py:679 (record row) | GENUINE_EXCEPTION | certification_construction_safety_authority | the acceptance-wording ruling |
| `etsy.oauth.reauthorise` | legacy; adopted by commerce/orders_ingest.py:1295 | AUTO_CLOSE | redundant | legacy key superseded by etsy.auth:reauthorise (no producer raises it) |

### Kinds whose class is decided by `authority.classes`

`laura:<...>:<job_type>` and `dag:<...>:<job_type>` are requests for authority over a named job
type:

- **ROUTINE_INTERNAL** when every job type named is in an autonomous class (OBSERVE, RESEARCH,
  BUILD, TEST, DRAFT).
- **GENUINE_EXCEPTION** otherwise, with the class mapped from the gated action class:
  - PUBLISH, CUSTOMER-REMEDY and DEPLOY → publication;
  - SPEND → spend;
  - LEGAL-TAX → KYC/legal;
  - CREDENTIALS → grant/step-up.
- A key that names no known job type is **fail-closed**.

## Executor gates (gate cards)

Every gate the owner can be asked to open is a genuine exception. The executor still filters
out gates that are open, data-gated, external, company-opened, unblock nothing or are not yet
askable before any card exists.

| gate | exception class |
|---|---|
| `etsy_shop` | kyc_legal_banking |
| `etsy_api` | grant_signature_or_step_up |
| `transactions_r` | grant_signature_or_step_up |
| `insights_access` | physical_evidence |
| `benchmark_observation` | physical_evidence |
| `second_market_benchmark` | physical_evidence |
| `physical_proof` | physical_evidence |
| `model_provider` | paid_ads_or_subscriptions |
| `image_generation` | paid_ads_or_subscriptions |
| `image_vision` | paid_ads_or_subscriptions |
| `rendered_pages` | paid_ads_or_subscriptions |
| `offsite_storage` | paid_ads_or_subscriptions |
| `ad_authority` | paid_ads_or_subscriptions |
| `benchmark_purchases` | spend_beyond_approved_budgets |
| `acceptance_ruling` | certification_construction_safety_authority |
| `canonical_model` | grant_signature_or_step_up |
| `production_window` | publication_or_activation |
| `live_listings` | publication_or_activation |
| `tester_roster` | publication_or_activation |
| `owned_surfaces` | publication_or_activation |

## Command Center card kinds that are not OwnerAction rows

| card kind | exception class |
|---|---|
| PUBLICATION | publication_or_activation |
| ACTIVATION | publication_or_activation |
| STANDING_POLICY | grant_signature_or_step_up |
| policy_review | external_policy_attestation |
| RELEASE | publication_or_activation |

A `PUBLICATION` card whose gated sections do not all pass (`executable: false`) is not an
ask. It is counted as `publication_not_ready` under the standing authority, because rebuild,
recertify, PDF, gallery, SEO and listing-package work continue automatically. It returns to the
batch when it is ready.

## Notes on judgement calls

- **Canonical model selection and approval** are kept with the owner as grant/step-up. The gate
  reads an *owner approval timestamp*, and the directive excludes forging owner records.
- **`improve.upgrade:`** (gate-tier improvement) stays with the owner as certification authority.
  **`improve.league:`** stays with the owner as a step-up act (`challenger.approve`).
- **`improve.challenger_run:`** (≤ CA$2 a run) is routine. It falls inside the approved
  CA$100/month model ceiling, which SpendGuard still enforces.
- **`listing_fees`** stays a genuine exception on the card. The approved CA$6 is enforced as a
  standing budget in `finance.listing_costs`. Any fee beyond it needs the owner.
- **`model.vendor_switch_routed_only` / `model.routes_invalid`** are routed to Main (deploy
  configuration), not the owner. The producers close them when fixed and re-raise them if they
  are still wrong; the sweep closes each re-raise with a new audit row.
- **Superseding is not approving.** No reader treats a superseded or withdrawn routine card as
  owner approval. The only `done == True` readers are `store:OA-*` (genuine and untouched),
  knowledge-gap suppression (genuine) and event wakes. This was checked by grep and is listed
  in the review request.
