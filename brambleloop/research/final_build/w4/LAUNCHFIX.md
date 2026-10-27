# W4-LAUNCHFIX: engineering deadlocks on the path to the first Etsy listing

Branch `claude/w4-LAUNCHFIX`, from `origin/claude/w4-INTEG8-next` (`b0133916`). Source of the
defects: `research/final_build/w4/LAUNCH_PATH.md` §5 (branch `claude/w4-LAUNCH1`, `ae0c4aa8`),
rows E1 (D1), E2 (D2), E3, E4, plus the owner's scope additions (policy-readings form; three
separate brand facts; draft vs public listing).

**These are gate changes. Each needs independent review before release.** For each, the rule
is unchanged or stricter; what changed is that the evidence the rule asks for can now exist.

> **TEST STATUS: all touched suites and their importers pass.** Each ran one at a time at nice 19. The last batches went through `/home/user/bl-runs/testslot.sh`, and disk was checked above 6 GB before every run. Results:
> - `test_w4_launchfix` 22/22 and `test_etsy_exercise` 32/32;
> - `test_first_customer_gate` 12/12 and `test_launch` (all);
> - `test_vacuity`, `test_moat`, `test_rc1_own_closer`, `test_w4_owner_actions` 6/6, `test_w4_firstsale_view` 5/5, `test_w4_pipe_board`;
> - `test_w4_b2close` 18/18, `test_w4_b2gate2` 11/11, `test_cert_commerce` 14/14, `test_policy_intake` 9/9;
> - `test_w4_prodfix_policy_review`, `test_w4_b2gates` 12/12, `test_w4_agents_secfix`, `test_w4_c04_finance`, `test_w4_ccrel` 8/8;
> - `test_v11_pwa_static` 83/83, `test_w4_launch_review_card`, `test_route_auth_default_deny` 8/8, `test_w4_firstsale_taxonomy` 7/7;
> - `test_cert_publish_gates`, `test_search_truth` 32/32, `test_w4_cap1_gates_intact`, `test_w4_cap1_placemat_price`, `test_w4_fmbatch1_drift` 10/10, `test_w4_listready`, `test_originality_runtime`;
> - `test_disclosed_render` 27/27, `test_disclosed_render_runtime` 3/3, `test_disclosed_certified_upload` 7/7, `test_search_hero_publish` 4/4, `test_cert_listing_frames`;
> - `test_v11_autonomy_timeline`, `test_cost_governance_wave2`, `test_cert_intel_wave2` 15/15, `test_fb2_i_repairs`, `test_w4_ownerimg` 35/35, `test_upgrades`.
>
> Three suites failed on the first run, and each failure was a real finding, fixed and then rerun solo:
> - `test_launch`: brand_clearance attribution (§2);
> - `test_cost_governance_wave2`: the new audit actions needed retention decisions, now in `ops/retention.py` as `lifetime_total` (sealed chain, attestation history);
> - `test_search_hero_publish`: the new photo gate refused its fixture (§6).

---

## 1. D1: `etsy_remote_state` could never pass (LAUNCH_PATH E1)

**Requirements:** F-118 (the nine-area first-customer gate is read by the runtime, via
`publish.eligibility.product_publication`), F-594 (the Etsy round trip is proven by the
`etsy_exercise` breadcrumbs), F-542 (read-back), PRODREADY B5.

**Root cause.** `gates/first_customer.py:check_etsy_remote_state()` returned UNVERIFIABLE
whenever `publish.listing_schema.gaps()` was non-empty. That list is code: rows are never
deleted, even when a claim is verified, and four rows are internal or non-blocking. No run of
anything could shorten it. The check runs inside `release_gates.for_publish`, so
`store.publish` refused before the first draft that was supposed to clear it.

**Fix.**
- `integrations/etsy_exercise.py`: the `etsy.exercise_finished` row now also records
  `against_etsy` and `claims` (`[{claim, state_after}]`, taken from the run's own
  `etsy_probe.claims()`, after redaction, names and states only). New reader
  `remote_state_evidence(db)`.
- `check_etsy_remote_state(db=None)` now judges recorded evidence:
  - the claims that must be verified are every `gaps()` row with `blocks_launch` (today:
    `oauth_token_endpoint`, `form_encoded_create`, `multipart_image_upload`,
    `array_encoding_tags`). A blocking gap with no Etsy claim keeps it UNVERIFIABLE;
  - each claim must be VERIFIED_AGAINST_ETSY, either in the code matrix (an observation in
    `ETSY_VERIFIED_FACTS`) or in the **newest** full run that finished ok and whose status
    says it ran against openapi.etsy.com. `etsy_probe.claims()` promotes nothing unless the
    requests went to Etsy, so a local-model run can never count;
  - every draft the runs created must have a verified-removed breadcrumb;
  - any claim marked CONTRADICTED by that run or any later run makes it **FAIL**;
  - no database, no run, an old-shape row with no `claims`, a rotation-only run, a not-ok run
    or a stranded draft: UNVERIFIABLE (it still blocks).
- Callers pass their database: `gate_product` (both branches) and `launch/first_sale._remote`
  (whose FAIL now shows as FAIL rather than UNKNOWN).

**Draft vs activation (the owner's question).** No carve-out was added, and none is needed.
The evidence comes from the controlled exercise (`POST /api/etsy/exercise`, mode full), which
runs in SHADOW, costs CA$0 and creates only a "DO NOT BUY" test draft that it deletes and
verifies gone. It exists *before* any real draft, so the real `store.publish` stays fully
gated, as does `store.activate`. The separation that the owner asked for already exists, and
the tests pin it:

| Action | What it needs (code) |
|---|---|
| Private draft (`createDraftListing`) | the owner's own sealed, content-bound 24 h **publication grant** (`ops.publication_authority`, CC `publication.approve` under step-up), effective phase ≥ LIMITED PRODUCTION, kill-switch, every release gate (now including D1). The client refuses without an `OwnerGrant` (`EtsyClient._authorise_write`). |
| Public listing (`state=active`) | a **separate** sealed activation grant bound to the listing id (`ops.activation_authority`), `launch_authorisation` on the call, read-back, the daily spend ceiling, and the fee reservation. `update_listing` refuses `state` outright. |
| Renewal (fee-bearing) | No create payload sends `should_auto_renew`, and no source line sets it to true (test). |
| Test draft (exercise) | the narrow `shadow_writes_authorised` lane, only in a non-publishing phase; it can never activate (`refusal_for(ACTIVATE)`). The operator-token endpoint is the owner's word. |

**Is there a fee at draft creation?** Repo evidence: `integrations/etsy.py` ("Etsy charges the
listing fee when a listing is *published*, not when a draft is created"), and
`etsy_exercise` ("Its listing fee is charged at publication"). The only quoted Etsy text in the
repo is the fee reading (`gates/policy_knowledge.py`: "Your first item costs $0.20 USD to
list"), and it does not say when a draft is charged. **So this is UNVERIFIED by a quoted Etsy
source.** Following the owner's rule, the draft is treated as potentially fee-bearing. It is
already gated by its own explicit owner authorisation (the sealed publication grant), which is
the same strength of approval as a spend. The daily spend-ceiling check runs at activation only.
Adding it to the draft path would change `runtime/pipeline._revalidate_publish_effect`, and
that change could not be tested on this host, so it was **not** made. Recommended follow-up:
read Etsy's Fees & Payments Policy (person reading, CC `#/policy`), or observe the first
exercise's ledger. If a draft fee is confirmed, add the ceiling check there.

**Tests.** In `tests/test_w4_launchfix.py`:
- `test_d1_deadlock_*` (a): `gaps()` is still non-empty, and genuine evidence now gives PASS. Before the fix this was always UNVERIFIABLE (TypeError on the db argument).
- `test_d1_refuses_*` (b) and `test_d1_a_later_contradiction_*` (b).
- `test_d1_passes_*` (c).
- `test_d1_the_gate_is_wired_*`.
- `test_d1_refuses_a_draft_activation_or_fee_bearing_write_*`: a stub transport that fails on any byte.

In `tests/test_etsy_exercise.py`, `test_a_finished_run_records_its_claims_and_only_a_live_one_clears_remote_state` covers the real `run()` path, end to end against `tests/fake_etsy.py`. A local run is UNVERIFIABLE. The same run with `etsy_probe.against_etsy` reporting Etsy is PASS.

**Why nothing was weakened.** Before: never PASS. After: PASS only on a live, full, ok, clean
round trip that verified each launch-blocking claim against Etsy. The trust level of the
breadcrumbs is the same one `launch.readiness` `etsy_integration` already uses (F-594).
Non-blocking Etsy claims (`taxonomy_patterns_id`, `taxonomy_required_properties`,
`delete_removes_draft`) are no longer counted as open. They have no CONFIRMED outcome in
`etsy_probe.TAXONOMY`, so counting them was the deadlock. They are still covered elsewhere:
- a contradiction of any of them is now a FAIL;
- delete is covered by the clean round trip;
- the category is covered by the search certificate (E4).

---

## 2. D2: `listing_fees` and `brand_clearance` hard-coded unready (LAUNCH_PATH E2)

**Requirements:** Build 2 #54 ("brand/name clearance checkpoint" before live Etsy), Master
Plan v1.2 §29 and §14 (one owner queue), F-300 (`transition_verdict`), F-299 (phase),
F-870 (owner packet).

**Root cause.** `launch/readiness.py` built both requirements with `ready=False` and had no
evidence path, so `transition_verdict` was never ready and `core.phase.record_transition`
refused every move up.

**Fix: the existing sealed owner-authority mechanism.** New `ops/launch_decisions.py` is a
`core.sealed_chain.GrantLedger` family, the same mechanism as the activation, publication and
storefront grants:
- each row is HMAC-sealed under the operator credential and hash-chained;
- a forged, edited, replayed or deleted row breaks the chain, every decision then reads as unrecorded, and a P1 tamper incident opens;
- each decision binds the digest of exactly what the owner previewed;
- decisions are revocable.

It is written only through the Command Center:
- `launch_decision.preview` reads;
- `launch_decision.record` needs owner session, CSRF, nonce, step-up and a reason;
- `launch_decision.revoke` tightens.

The `listing_fees` and `brand_clearance` owner cards carry these actions (`approvals._gate_card`).

- **`listing_fees`.** Ready only on a valid sealed approval whose approved listing count is at
  least today's catalogue (listings not withdrawn), at today's per-listing USD fee. Otherwise it
  is unready, blocked on the owner, with the existing costed request.
- **`brand_clearance`.** Three facts are kept apart, as the owner directed:
  - **(a) knock-out screening.** This is company work, recorded as a reviewed code entry in
    `brand/clearance.py:KNOCKOUT_SEARCHES` (empty today), in the same style as
    `ETSY_VERIFIED_FACTS`. `problems()` validates each entry:
    - the shop name;
    - an ISO date no more than 365 days old;
    - the searcher;
    - all four §29 screens (the Canadian register (CIPO), the marketplace, domains, social handles), each with an https source, a query for the name, and an explicit hits list;
    - per-hit relevance and reason;
    - `conflicts` equal to exactly the hits marked conflict;
    - a conclusion.
  - **(b) the owner's acceptance of residual risk.** `brand_risk_acceptance`, a sealed decision bound to (a)'s digest. It is **required**.
  - **(c) formal registration.** `trademark_registration`, either `file` or `not_now`. It is recorded and reported, and **not required**.

  The row is ready only on (a) valid and (b) bound to that same (a). With no valid (a), it is blocked on BUILD (company work), and the owner card stays queued.

**Is registration required? No.**
- `spec/01_Brambleloop_Master_Plan_v1.2.pdf` §29: "Before commercial launch, perform marketplace/domain/social-handle screening and appropriate trademark clearance; escalate formal legal clearance to the owner/professional if needed." The same document lists "final brand/trademark decision" among owner-only setup.
- `spec/08_..._v1.4.3_MASTER.pdf` #54: "brand/name clearance checkpoint".
- No other spec PDF mentions trademark: 02, 03, 09, 10 and 11 were searched.
- `DECISION_LOG.md` has no trademark entry.
- `OWNER_ACTIONS.md`: "The free knock-out search is company work".

**Tests.** In `tests/test_w4_launchfix.py`:
- `test_d2_deadlock_*` (a).
- `test_d2_listing_fees_refuses_*` (b): no decision; a forged unsealed row; a smaller catalogue; revoked; credential rotated; an unbound digest.
- `test_d2_brand_clearance_keeps_*` (b): no screening; an invalid screening; an old one; an inconsistent one; no acceptance; a registration alone; an acceptance of a different screening.
- `test_d2_brand_clearance_passes_*` (c).
- `test_d2_the_command_center_door_*`.

**Why nothing was weakened.** Before: never ready. After: ready only on a sealed,
chain-verified, unrevoked owner decision bound to current content. The decision is unforgeable
without the operator credential, which only the CC (after step-up) or the operator holds.

**Next action (company).** Perform the knock-out screening (CIPO, Etsy, domains, handles) and
add the entry to `KNOCKOUT_SEARCHES` through review. Then the owner sees the risk card.

---

## 3. E3: the first person reading opened a halting P1 (LAUNCH_PATH E3)

**Requirements:** Build 2 #39 (policy freshness and material-change watch), #35 (new
classes), W4-GATESI (`compare_basis`), `rendered_pages` gate.

**Confirmed in code.** `record_page_reading` called `record_snapshot(..., basis=PAGE_BASIS)`
with `compare_basis=None`, so "previous" was the newest row of any basis, which is the
repository excerpt seed. That made `material_change=True` → `unreviewed_changes` → the
`policy_changed:<source>` P1 and a block on publishing.

**Fix.** It now passes `compare_basis=PAGE_BASIS`, as `policy_reader.read_help_center` has
since W4-GATESI. The first person reading is the baseline. A later page reading with a
different digest is still a material change and still blocks until reviewed. Stale readings are
recorded but stay not-current, and empty readings are refused, both as before.

There is no data migration. A production row already recorded as a change still needs its
review card, which is not auto-cleared.

**Tests.**
- `test_e3_deadlock_*` (a): the first reading after the seed is not a change. Before the fix it was.
- `test_e3_a_later_different_reading_*` (b, c): a different reading opens the review; stale and empty readings stay blocked.
- The form tests below cover baseline then change through the CC.

---

## 4. E4: no Etsy taxonomy node chosen (LAUNCH_PATH E4)

**Requirements:** F-004 / F-294 (search certification), W4-FIRSTSALE B2.

**Investigation.** The only committed evidence of Etsy's real tree is
`research/final_build/w4/evidence_FMBATCH1/prod_api_audit_taxonomy_refreshed_20261021T0242Z.json`.
The same file is on every branch, and no newer copy exists. It records:
- 3065 nodes;
- `pattern_subtree: 0`;
- names only, and **no ids**.

The relevant names:
- `Craft Supplies & Tools > Patterns & How To > Patterns & Blueprints`. **It has no children.**
- Crochet appears only in `Art & Collectibles > Fiber Arts > Crochet` (finished art) and in `... > Hooking > Crochet Hooks`.

**So a "Crochet" node under Patterns does not exist** in that read. The correct node by name is
**Patterns & Blueprints**. Crochet can only be confirmed as a property value of that node's
schema. The full tree, the node id and the schema are **not** in the repo.

This is not a code defect. The W4-FIRSTSALE property route (`commerce/category.py`, and the
refresh that reads candidate schemas) already handles this shape. The 2026-10-21 row predates
it (`properties_read: 0`, no `category_choices`).

New regression test `test_e4_on_the_real_names_*`. On a tree with exactly those names (ids
labelled illustrative):
- every category is UNKNOWN without the node's schema, and with a schema lacking Crochet;
- only Etsy's own "Crochet" value on that exact node chooses it;
- it is never `Fiber Arts > Crochet` or `Crochet Hooks`.

**UNKNOWN; exactly what is needed.** One read-only GET of production
`/api/audit?action=etsy.taxonomy_refreshed` (newest row, after `ee35a493`'s daily refresh) for:
- `category_choices` (status, `taxonomy_id`, `path_ids`, crochet basis per category);
- `property_candidates` (the id of Patterns & Blueprints);
- whether that node's stored schema offers a "Crochet" value.

Then run `tests/verify_w4_firstsale_taxonomy_live.py`. This worker's attempt at that GET was
refused by this session's permission policy (production reads), so it was not made. No node id
was invented.

---

## 5. Command Center "Policy readings" (`#/policy`), owner scope addition

**Requirements:** #35 / #39 (person readings of the etsy.com/legal pages), F-885/F-886/F-887
(evidence-backed inbox, one-tap owner actions, step-up), `rendered_pages` gate provenance.

**Files.**
- `app/command_center/policy_readings.py` (logic).
- `GET`/`POST /api/cc/policy/readings` in `app/command_center/api.py`: one block, next to `etsy/shop-observation`; `app/main.py` was not touched.
- `static/js/views/policy.js`, plus a `routes.js` entry, `api.js` endpoints, `sw.js` (shell `cc-shell-v28`), and links from Approvals and Completion.

**Behaviour.**
- **Authentication.** Owner session (passphrase + TOTP), CSRF, nonce and timestamp come from the CC gate. A fresh **step-up** is required to record. The ops token is not accepted.
- **Shown for each of the 7 `POLICY_SOURCES`:**
  - title, key and the official URL as a link;
  - state: never read (missing), fresh, stale (expired, with age), or changed-unreviewed (with a link to the review card);
  - the date and `read_by`;
  - the packet's questions as guidance; nothing is pre-filled;
  - a history of the last 10 person readings, each with baseline/change/same, reviewed state, fingerprint and the confirmation.
- **Recording** goes through the same `record_page_reading`, then writes the **same** `policy.page_reading_recorded` audit row (identical fields) and a second row, `policy.page_reading_attested`, which records:
  - the confirmation the owner gave, verbatim;
  - where the text came from;
  - the session;
  - baseline or change.
- **Owner confirmations are verbatim and differ by route:**
  - five etsy.com/legal pages: "I read this page myself and pasted its full text";
  - two Help Center articles: "I reviewed the article text the system fetched and wrote these answers".
- **Text.**
  - **Legal pages:** Select all → Copy → Paste, with no notes. Software may not fetch these pages (DataDome 403; robots.txt).
  - **Help Center articles:** the server fetches the article from Etsy's public article API, through the same reader production uses. The digest is of Etsy's own text, so the owner only writes and confirms the answers.
  - Only the SHA-256 is stored in either case.
- **Refused:**
  - empty answers (incomplete);
  - a wrong confirmation;
  - empty text;
  - an unknown source;
  - a version over 120 characters;
  - a future date;
  - fetching a legal page;
  - a replayed nonce (gate);
  - a duplicate (same text, same day, same owner) → 409, nothing added.
- **No bypass.** A later different reading is a change: it opens the existing `policy:<source>` card in `#/approvals` and blocks publishing until it is reviewed.

**Tests (`tests/test_w4_launchfix.py`).**
- `test_cc_policy_form_needs_*`: auth, CSRF, step-up, nonce replay; the ops token is refused.
- `test_cc_policy_form_records_*`:
  - the digest only;
  - the same intake row plus the attestation;
  - baseline, then change, then the review card;
  - a duplicate is refused.
- `test_cc_policy_form_refuses_*`.
- `test_cc_help_center_article_*`: the article is fetched; legal pages must be pasted.
- `test_cc_policy_view_is_in_the_spa_shell_*`.

**Public surface.** The routes sit under `/api/cc/`, which `security.operator_gate` → `auth.gate`
default-denies. `tests/test_route_auth_default_deny.py` walks `app.routes` and covers them
automatically. `test_v11_pwa_static` requires every shipped asset in the shell and no external
URLs. The view takes URLs from the server only.

**Proposal (not implemented): avoiding the paste.** A CC-provided bookmarklet, "Send this page
to Brambleloop", run by the owner on the open etsy.com/legal page in their own browser, would
POST `document.body.innerText` to the CC with the session's CSRF and nonce. That is the same
evidence as a paste: the person's own browser, the page as served to them, no bot evasion.
It is one tap. It needs a cross-origin design decision (CSP, SameSite cookies) and its own
review, so it is only proposed here.

---

## 5b. IMG: an unedited photograph of a made sample before a pattern lists (gate TIGHTENING)

**Source:** coordinator scope item, from `claude/w4-IMAGEPOLICY` f8b21390
(`research/final_build/w4/ETSY_IMAGE_COMPLIANCE.md`, with raw Help Center API JSON). Requirements
touched: #64 (physical upgrade path), #35 (asset roles), F-852 (generated media never exported),
D-FB-7 / D-FB-9 (render-only galleries, now overtaken for live sale).

**Etsy, verbatim (Help Center article API, 2026-10-27):**
- Help 44297885802647, edited 2026-10-16: "Craft patterns, recipes, seeds, or similar items: Include at least one real, unedited photo of something made using your product. AI-generated images cannot be the only images used to show the finished result."
- Help 115015663347, edited 2026-10-22: "If you sell functional guides like patterns, recipes, or instructions, you'll also need to show an actual result made using your instructions, not an AI-generated or simulated result, so buyers know what to expect." It also says: "Make your first listing photo the clearest, most realistic representation of the item buyers will receive."

**Before:** nothing in code required a real photograph. `platform_policy.classify` permits a deterministic render in a photograph-required role, and `physical_upgrade` was an optional upgrade.

**Fix.** New `publish/sample_photo.py`. `release_gates.for_publish`, which runs at `store.publish` (draft creation, both revalidation boundaries) and at `store.activate`, now adds `SAMPLE_PHOTO_REQUIRED` unless the certified gallery leads with a photograph that meets every one of these conditions:
1. It was recorded through the one photo intake, `physical_upgrade.intake`: bytes on file under its SHA-256 and a rights basis. There is no other path. An owner image upload is provenance `ai_generated_owner_submitted` and never enters it, and renders and generations never do either.
2. It was attested unedited at intake. `intake(..., unedited=True)` is passed through from the `physical.photo` job input `unedited: true`. Absent means not unedited. A row marked `edited` or `ai_processed` is refused.
3. It is of THIS release:
   - the photo row names this slug@version;
   - its `physical_test_id` is a passed, completed **full physical make** of this slug@version, bound to the release's content hash by `gates.first_customer.physical_binding`, the certificate's own binding.

   A swatch does not count, since it is not "something made using your product" in the sense of the finished result. A compatible-variant sample of another product does not count, and neither does a sample of an older text.
4. It is a frame of the valid listing-set certificate for this release (so it has been re-certified), and **the first frame**.

Renders, charts and the PDF page preview may follow.

**Disclosure copy is generated from facts:**
- `sample_photo.disclosure_copy(photographed_sample)`. With no qualifying photo, it is exactly the existing `DISCLOSURES["disclosed_render"]` ("... no sample has been photographed ..."), which stays true. With a photo, it says the first image is an unedited photograph of a sample made from the pattern, and that the captioned images are renderings. It keeps the render caption phrase that `disclosed_listing` checks.
- `platform_policy.classify_release(..., photographed_sample=)` emits the matching sentence. The listing writer (`runtime/release.py`) passes the measured fact; unknown is treated as not photographed, so the copy never over-claims.
- `for_publish` also refuses copy that contradicts the gallery: the no-photo sentence beside a photo, or the photo sentence without one.

**Not encoded:** whether Brambleloop patterns fall under Etsy's "AI-generated functional instructions, such as craft patterns" prohibition (Help 360024112614). That is an OWNER decision. Nothing here answers it.

**Known follow-up (engineering, before the first sample photo arrives).** `physical_upgrade.plan_upgrade` appends the photo frame at the last position, in role `proof`. For the photo to become the first certified frame, the gallery ordering and listing-set certification must place it first (hero/DESIRE job). Until that is built, this gate refuses even with a good photo, which is fail-safe. It is moot today, because no physical sample exists for any Launch-0 release (LAUNCH_PATH E7).

**Tests (`tests/test_w4_launchfix.py`):**
- `test_img_deadlock_free_and_a_render_only_gallery_is_refused`;
- `test_img_refuses_unbound_other_release_edited_or_not_first_photos`, covering:
  - an unbound sample;
  - a photo of another release;
  - a sample of another release;
  - a photo not attested unedited;
  - a photo that is not first;
  - a photo marked AI-processed;
- `test_img_a_bound_unedited_first_sample_photo_passes_this_gate_only`: it passes this gate, and the disclosure follows the facts both ways.

**Why this is a tightening only.** It adds one refusal to `for_publish`. It changes no other policy outcome. `classify`'s problems are unchanged, and only the disclosure sentence varies, from a fact.

## 6. Files changed

- `src/brambleloop/gates/first_customer.py`: D1, the check and its wiring.
- `src/brambleloop/integrations/etsy_exercise.py`: D1, claims on the finished row, and `remote_state_evidence`.
- `src/brambleloop/launch/first_sale.py`: D1, passes db.
- `src/brambleloop/launch/readiness.py`: D2, the two rows.
- `src/brambleloop/ops/launch_decisions.py` (new): D2, the sealed decisions.
- `src/brambleloop/brand/clearance.py` (new): D2(a), knock-out evidence and validation.
- `src/brambleloop/app/command_center/approvals.py`: D2 actions, card actions, messages.
- `src/brambleloop/gates/platform_policy.py`: E3.
- `src/brambleloop/app/command_center/policy_readings.py` (new) and `api.py`: the form.
- `src/brambleloop/publish/sample_photo.py` (new), `publish/release_gates.py`, `publish/physical_upgrade.py` (the `unedited` attestation), `runtime/release.py` (`_intake_photo` passes `unedited`; the listing writer passes the photographed fact), and `gates/platform_policy.py` (`classify` disclosure from facts): the IMG section.
- `static/js/views/policy.js` (new), `routes.js`, `api.js`, `sw.js`, `views/approvals.js`, `views/completion.js`: the form view.
- `tests/test_w4_launchfix.py` (new) and `tests/test_etsy_exercise.py` (one test added).

`tests/test_search_hero_publish.py`: its end-to-end publish fixture has no physical sample, and the real `store.publish` path refused it with `SAMPLE_PHOTO_REQUIRED`. That refusal is the end-to-end proof that the new gate is on the publish path. The fixture now holds `sample_photo.requirement` the same way it already holds parity, the search grid and the Launch-0 scope gate, with a stated reason. The gate's refuse and pass behaviour is tested in `test_w4_launchfix`. This test's own assertions are unchanged.

One existing test was edited, and it was made stricter, not looser. In `tests/test_launch.py::test_a_company_that_has_done_its_half_is_only_blocked_on_people`, `brand_clearance` is now expected among the company-side (`BLOCKED_BUILD`) items while no knock-out screening is recorded, and the test asserts that it is unready. The test pinned the old attribution (owner) for work that OWNER_ACTIONS assigns to the company. `test_nothing_blocked_on_build_is_ever_sent_to_the_owner` is unchanged. To keep it true, the trademark request is put to the owner only once a valid screening exists. No other test was weakened or edited except by addition. `test_first_customer_gate`'s
`check_etsy_remote_state()` assertion still holds: with no db it is UNVERIFIABLE and says
"authenticated".

## 7. What stays UNKNOWN or owner/company work

- D1: whether Etsy charges at draft creation (no quoted source); the first live exercise (owner's word, CA$0).
- D2: the knock-out screening itself (company work, not yet done); the owner's risk acceptance.
- E4: the node id and schema, which need the production readback in §4.
- Production rows already recorded as policy changes still need their review.

## 8. Suites to run (one at a time, nice 19, from `brambleloop/`, with `PYTHONPATH=src:tests PYTHONDONTWRITEBYTECODE=1`)

Run these first:
- `test_w4_launchfix`
- `test_etsy_exercise`
- `test_first_customer_gate`
- `test_vacuity`

Then the importers of the touched modules:
- `test_launch`, `test_moat`, `test_rc1_own_closer`, `test_w4_owner_actions`
- `test_w4_firstsale_view`, `test_w4_pipe_board`
- `test_w4_b2close`, `test_w4_b2gate2`, `test_cert_commerce`, `test_policy_intake`
- `test_w4_prodfix_policy_review`, `test_w4_b2gates`, `test_w4_agents_secfix`, `test_w4_c04_finance`, `test_w4_ccrel`
- `test_v11_pwa_static`, `test_w4_launch_review_card`, `test_route_auth_default_deny`
- `test_w4_firstsale_taxonomy`
- for IMG: `test_cert_publish_gates`, `test_search_truth`, `test_w4_cap1_gates_intact`, `test_w4_cap1_placemat_price`, `test_w4_fmbatch1_drift`, `test_w4_listready`, `test_originality_runtime`, `test_disclosed_render`, `test_disclosed_render_runtime`, `test_disclosed_certified_upload`, `test_cert_intel_wave2`, `test_fb2_i_repairs`, `test_w4_ownerimg`, `test_search_hero_publish`, `test_cert_listing_frames`, `test_v11_autonomy_timeline`, `test_cost_governance_wave2`
