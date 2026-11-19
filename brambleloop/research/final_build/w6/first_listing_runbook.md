# First real Etsy draft, then the first public listing: the runbook

ENG-FIRSTLIST, 2026-11-19 (UTC). Traced on Batch 9 (`claude/w6-INTEG1` @ 6e47d9bb). The fixes
are on `eng/first-listing-runbook`. **Steps 6 and 10 need that branch, or an equivalent, merged
and deployed.** Without it there is no working Command Center path from a grant to a draft or to
a public listing (gaps G1 to G3 below).

What exists today, honestly: no real product draft and no public listing on Etsy, ever. Production
is SHADOW. The only real-shop writes so far are the exercise's marker drafts, each deleted at once.

---

## 0. The answers in one place

| Question | Answer from the code |
|---|---|
| Can a real **product** draft be created under SHADOW? | **No.** `store.publish` refuses in SHADOW and in STAGING (`runtime/pipeline.py:2116`, `PHASES_THAT_MAY_PUBLISH = ("limited_production", "production")`, `integrations/etsy.py:86`). The client's draft-only lane (`shadow_writes_authorised`) is built only by `integrations/etsy_exercise._client`. It creates a marker draft from a transport-test PDF and deletes it in the same run. It proves the credential, scopes, upload and taxonomy, but it is not a product draft and must not be called one. |
| Which phase does the first draft need? | `limited_production`, as **both** the owner's recorded, sealed phase transition and `BRAMBLELOOP_PHASE`. The more restrictive of the two wins (`core/phase.resolve`). |
| How is the phase change authorised? | Owner-only `POST /api/owner/phase/transition` (operator token). It moves one step at a time: shadow→staging, then staging→limited_production. Each step cites a `launch.assessed` id and a `launch.rollback_rehearsed` id, which must be *passing* for the move into limited_production. The **launch readiness verdict, evaluated at transition time, must be `ready`** (`core/phase.record_transition`). There is no Command Center button for this. `emergency.py` says the phase is never moved up from there. |
| Cost of a draft | **CA$0.** No fee path runs in `store.publish`. `finance.listing_costs.reserve` is called only from `handle_store_activate` (`pipeline.py:2839`). `integrations/etsy.py:679`: "Etsy charges the listing fee when a listing is *published*, not when a draft is created." |
| Cost of a public listing | **US$0.20**, about **CA$0.28** at `ASSUMED_CAD_PER_USD = 1.4154`. It is reserved against store_operator's CA$1.00/day ceiling before `updateListing(state=active)`. Etsy keeps the listing for 4 months. The create payload always sends **`should_auto_renew: false`** (`ListingPayload.to_dict`, WS4-8), and the F-542 read-back compares it: `true` is a MISMATCH and a missing field is NOT_RETURNED, so a renewing draft never reads as verified. Activation readiness checks it again; still confirm it in step 11. Etsy's transaction and payment-processing fees on a sale are separate and modelled in `commerce/pricing.fees`. |
| What proves the draft | `store.published` audit row and job output `read_back_verified: true`. That row exists only when an independent `getListing` and `getAllListingFiles` show every certified field, the draft state, the certified image count and alt texts, and exactly the certified US and UK files by name and size (`runtime/etsy_ops.read_back`, F-542). Anything else writes `store.publish_incomplete` plus a halting incident. |
| What proves the public listing | `store.activation_verified` (draft read back again, field by field) and then `store.activated` with `state_on_etsy: "active"` from a fresh `getListing` after the write. |

## 1. Which product goes first

**Readiness rule (the code's own).** A release can become the first draft only when all of these hold:

1. `PatternVersion.certified`, and a `Listing` is bound to the same release hash;
2. every gated section of `ops.publication_authority.evidence` is `PASS`: certification,
   parity, listing_set, disclosure, policy, search, rollback. This is the reading the Approvals
   card and the server-side `_require_publication_evidence` use, and UNKNOWN never counts as PASS;
3. the latest listing package (`publish/listing_package`) is `ready_for_owner_review` for that
   release;
4. not already on Etsy;
5. at execution, `store.publish`'s own gates: phase, kill-switch, sealed grant, a *usable*
   credential (an authenticated read within 26 h, every scope including `transactions_r`),
   creative parity, release gates, PDF hash identity with `assets.built`, the #126 search-grid
   verdict and certified image bytes.

**Recommendation:** `hexagonal-bread-basket` (small basket only). The owner already named it:
"The first listing sells the small basket only" (DECISION_LOG, D-W4-OWNER-BASKET-IDENTITY,
2026-10-27). It is a kitchen and home product, so no children's-product decision applies.
**Confirm it on production first.** If it is not a draft candidate, the next choice is the
`draft_candidates` entry with the fewest `package_blocker_sources`. Prefer `hexagon-coaster-set`,
then `nordic-star-ornaments`, then `winter-village-graphghan`, and take `cloudline-baby-blanket`
last because it is a children's product.

**Read-only confirmation (for Main, readback token).** This needs the ENG-FIRSTLIST
`first_listing_readiness` section, so it must run on a deploy that includes this branch:

```bash
curl -sS -H "Authorization: Bearer $BRAMBLELOOP_READBACK_TOKEN" \
  https://brambleloop-os-production.up.railway.app/api/readback/evidence \
  | jq '.first_listing_readiness | {draft_candidates, certified_with_listing,
        releases: [.releases[] | {release, release_hash_prefix, listing_state, on_etsy,
                    publication_all_gated_pass, publication_sections, package_state,
                    package_is_current_release, package_blocker_sources}]}'
# or: python3 ops/readback.py --evidence   (row "first Etsy draft candidates (Launch-0)", advisory WARN/PASS)
```

On a Batch 9 deploy *without* this branch, the readback token shows only
`.certification_pipeline.slugs_by_stage` (LISTING_READY = a draft listing with assets, which is
weaker than the rule above), `.certification_pipeline.halted_certifications`,
`.publishing_halt` and `.listing_package_releases`. Those narrow the field but cannot settle
rule 2. The settling reading then needs the owner's session: **Command Center, Approvals tab,
card "Create the Etsy draft for <slug> v<version>"**. That card's Recommendation says "Ready:
every gated section passes" or names the sections not passing.

## 2. Pre-flight (all CA$0, nothing published)

| # | Who | Action | Expected read-back |
|---|---|---|---|
| P1 | Main | Step 1 query | the chosen release is in `draft_candidates`; note `slug`, `version` and the full release hash (from the Approvals card params) |
| P2 | Owner/Main (ops token) | `GET /api/owner/phase/verdict` | `next: "staging"`, `verdict.ready: true`. **If false, `verdict.failing` is the real blocker list for the first draft, and this runbook stops here.** It is expected to include owner and physical items such as `listing_photography`, `physical_calibration`, `catalogue_depth`, `payout`, `seller_identity` and `brand_clearance`. |
| P3 | Owner/Main (ops token) | `GET /api/etsy/oauth/status` | credential healthy, scopes include `transactions_r`. If not, the owner re-runs `GET /api/etsy/oauth/start` (browser consent). A grant made before `transactions_r` was added refuses every real draft. |
| P4 | Owner/Main (ops token) | `POST /api/etsy/exercise?mode=full` (SHADOW; drafts only; activation unreachable by construction) | `ok: true`, `shop_is_clean: true`, `exercise.verified: true`, `owner_actions: []`, `costs` "CA$0". The marker draft is created and deleted, and the shop is read back clean. |
| P5 | Main | Pre-release backup, as for any deploy | `BK restore_ok` |

## 3. The first real draft (inactive, CA$0)

| # | Who | Screen / call | Expected read-back |
|---|---|---|---|
| 1 | Main | Railway: set `BRAMBLELOOP_PUBLISH_AUTHORISED=1` (the global kill-switch; it can deny, never grant) and `BRAMBLELOOP_PHASE=limited_production`. **Owner approval is required** for the deployment change. | `GET /api/owner/phase` → `env_phase: "limited_production"`, `phase` still `"shadow"` (no recorded transition yet), `mismatch: true` (a phase-mismatch incident opens and is expected until step 3) |
| 2 | Owner (ops token) | `POST /api/owner/phase/transition` `{"to":"staging","reason":"<why>","evidence_refs":{"readiness":"<newest launch.assessed id>","rollback":"<newest launch.rollback_rehearsed id>"}}`. The ids come from `GET /api/audit?action=launch.assessed&limit=1` and `?action=launch.rollback_rehearsed&limit=1`. | 200, `to: "staging"`, `readiness_at_transition.ready: true`, `effective_now: "staging"` |
| 3 | Owner (ops token) | same, `{"to":"limited_production", ...}`. Both cited rows must be passing (`ready: true` / `ok: true`) and under their age limits. | `effective_now: "limited_production"`, `env_agrees: true`; `GET /api/owner/phase` → `agree: true`, mismatch incident resolved |
| 4 | Owner | **Command Center → Approvals → "Create the Etsy draft for <slug> v<version>" → Preview** | the preview shows each gated section `PASS` and the digest |
| 5 | Owner | same card → **Approve** (reason, step-up). The fixed button now sends the previewed digest (G3). | toast "Approve recorded."; audit `owner.publication.approved` with a 24 h `expires_at`. The card now shows **"Create the Etsy draft now"**. |
| 6 | Owner | same card → **Create the Etsy draft now** (reason, step-up) = action `publication.execute` | result `queued: true`, `job_id`, `approval_id`; audit `owner.publication.queued`. The door refuses with the reason, and queues nothing, if the phase or kill-switch is not right. |
| 7 | (worker) | `store.publish` runs | `store.execution_revalidated` twice (`stage: pre_claim`, `before_create`), `store.pdf_hash_verified`, then **`store.published`** with `read_back.verified: true`, `files_attached_by_terminology: {US: true, UK: true}`, `images_uploaded`, the `etsy_listing_id`; job output `published: true, read_back_verified: true`. `Listing.state = "published"` (meaning a **verified draft**, see W3 below). |
| 8 | Owner | Etsy Shop Manager → Listings → Drafts | exactly one new draft with the certified title, price, 2 PDFs and the certified images, in Drafts and not Active. `/api/verify` `nothing_published` may now read false: a draft is a write. |
| 9 | (worker) | the automatic `store.activate` that step 7 queues | `store.activation_verified` (the draft read back again) then `store.activate_refused` with "recorded Launch-0 owner activation approval required" (or `SAMPLE_PHOTO_REQUIRED`). **Expected; nothing is activated.** |

Rehearsed locally on Batch 9 code plus this branch (`tests/test_first_listing_doors.py`, FakeEtsy,
scratch SQLite, the real certified `cloudline-baby-blanket` fixture). Steps 2 to 9 passed through
the real handlers: one `createDraftListing`, 12 of 12 fields matched, 6 images, both PDFs matched
by name and size, no fee row, and no socket outside the fake's loopback port.

## 4. The first public listing (US$0.20, about CA$0.28)

**Hard prerequisite (OWNER PHYSICAL ACTION): an unedited photograph of a sample made from this
exact release.** `release_gates.for_publish(stage="activation")` adds `SAMPLE_PHOTO_REQUIRED`
(Etsy Help 44297885802647 and 115015663347). The rehearsal hit exactly this. With every other
gate passing and a valid owner activation grant, activation was refused, nothing was activated
and no fee was reserved. The photograph must be of a passed, completed **full** physical make
bound to the release's content hash. It enters only through the photo intake, is attested
unedited by the owner in the Command Center (`physical_photo.attest_unedited`), and must be
**frame 1** of a re-certified listing set. The copy must then say a sample was photographed
(`sample_photo.copy_problems`). A render can never satisfy it.

**Consequence for ordering:** the photo changes the certified gallery (frame 1) and the listing
copy. A draft created *before* the photo no longer matches the certified listing, so its
activation read-back fails. A deleted draft cannot be re-drafted for the same `slug@version` (G5).
So:

* **If the goal is the first public listing soon:** do the sample photo first (§4a), then §3,
  then §4b.
* **If the goal is to prove the real draft path now:** do §3 now. The public listing will then
  come from a *new release version* after the photo, and this draft stays as an invisible,
  free draft (or is deleted by hand, see Rollback).

### 4a. Photo (before the draft)

| # | Who | Action | Expected read-back |
|---|---|---|---|
| A1 | Owner | Make (or commission) a full sample from the certified release PDF; record the make (`physical.record`, full make, passed) | a `physical_tests` row bound to the release's content hash |
| A2 | Owner | Upload the unedited photograph through the physical photo intake (`physical.record` with `photos`), then attest it in the Command Center: owner action `physical_photo.attest_unedited` (session and step-up; no dedicated button exists, so use `POST /api/cc/actions/physical_photo.attest_unedited {photo_id, confirm: <UNEDITED_CONFIRMATION, verbatim>, reason}`) | `physical.photo` row with `unedited: true`; `assets.physical_upgrade` queued, then `assets.photo_review` |
| A3 | (worker) | re-certification of the listing set | listing package becomes `ready_for_owner_review` again with `sample_photo` satisfied; `first_listing_readiness` lists the release in `draft_candidates` |

### 4b. Activation

| # | Who | Screen / call | Expected read-back |
|---|---|---|---|
| 10 | Owner | **Command Center → Approvals → "Make Etsy listing <id> public (<slug> v<version>)" → Preview**, then **Approve** (reason, step-up) | `owner.activation.approved` (24 h). The card now shows **"Make it public now"**. |
| 11 | Owner | same card → **Make it public now** (reason, step-up) = `activation.execute` | `queued: true`; audit `owner.activation.queued`. Refused, and nothing queued, unless a verified draft exists (`Listing.state == "published"`), the grant validates now, the phase is limited_production and the kill-switch is on. |
| 12 | (worker) | `store.activate` | `store.activation_verified` `ready: true`, `store.activation_authority_used`, a `CostEntry(kind="etsy_listing_fee", amount_cad≈0.28)`, then **`store.activated`** `state_on_etsy: "active"`; job output `activated: true`; `Listing.state = "active"` |
| 13 | Owner | etsy.com: open the listing logged out | visible, price and files as certified; check `should_auto_renew` in Shop Manager (renewal costs another US$0.20 each 4 months) |

One job per grant: if step 12 is refused (a gate changed), a further attempt needs a new
grant (steps 10 and 11). A double tap queues nothing extra.

## 5. Rollback

| Situation | Action | Read-back |
|---|---|---|
| Grant recorded, not used | Approvals card → **Revoke** (`publication.revoke` / `activation.revoke`) | `owner.*.revoked`; `store.publish` / `store.activate` then refuse at their boundary |
| Job queued, not run | Revoke the grant (the handler re-resolves it), or set `BRAMBLELOOP_PUBLISH_AUTHORISED=0` | `store.execution_refused` / `store.activate_refused` |
| Draft exists, should not | Etsy Shop Manager → Drafts → delete. There is no automated delete job for a product draft; `EtsyClient.delete_listing` (reads back first, refuses unless draft or inactive) has no product caller. | the draft gone from Shop Manager. **The local `Listing` keeps its `etsy_listing_id` (G5).** The census will report it missing, and this `slug@version` cannot be drafted again. |
| Public listing must come down | Etsy Shop Manager → deactivate (no automated deactivation exists); the release chain marks it `withdrawn` | listing not visible logged out. **The listing fee is not refunded.** Buyers keep downloads (Etsy behaviour UNKNOWN to this system). |
| Phase back | `POST /api/owner/phase/transition {"to":"staging"}` then `{"to":"shadow"}` (moving down never evaluates readiness), and set `BRAMBLELOOP_PHASE=shadow` | `GET /api/owner/phase` → `phase: "shadow"`, `agree: true` |

## 6. What can go wrong

* **Readiness is not `ready` (most likely).** The phase cannot leave SHADOW, so no product draft
  is possible. Nothing in this runbook routes around it. A draft-only phase or lane for certified
  releases under an owner grant (drafts are invisible and free) would be a new owner decision
  and a code change. It is not built, and nothing here weakens the gate.
* `store.execution_refused` `stage: credential`: the authenticated read is older than 26 h, or a
  scope is missing. Run `ops.provider_credentials` / `etsy.credential_health`, or re-consent (P3).
* `PDF_HASH_DRIFT`: the re-rendered PDF differs from `assets.built`. A rebuild is needed; never
  edit hashes.
* `store.publish_blocked` with release-gate reasons (stale artefact, superseded release, search
  certificate, listing-set certificate): the reasons are the to-do list; re-check step 1.
* `store.publish_incomplete` plus a halting incident: Etsy accepted but the read-back differs
  (for example a field Etsy transformed). The draft exists and is not activatable. Do not retry;
  read the incident, fix and re-release, and delete the draft by hand.
* `RECONCILE_REQUIRED` (a draft intent with an unknown outcome after a crash mid-create):
  `store.draft_reconcile` resolves it read-only. Never queue a second publish around it.
* **W3 naming hazard:** `Listing.state = "published"` means *verified draft*, but
  `core.listing_state.LIVE_ON_ETSY` counts `published` as live. After step 7, the dashboards,
  the lifecycle (LIVE stage) and `nothing_published` will describe an inactive draft as live
  or published. Read the Etsy state, not the label. Not changed here.
* Daily ceiling: store_operator has CA$1.00/day, so about three activations a day; a fourth is
  refused by the ceiling.

## 7. Gaps found, and what this branch does

| Id | Gap (Batch 9) | Blocking | Fix on `eng/first-listing-runbook` |
|---|---|---|---|
| G1 | A valid publication grant caused nothing. The only `store.publish` is the one `launch.plan` enqueues. In SHADOW it dead-letters, and `store.publish` is a `DELIBERATE_REFUSAL_TYPE` that `requeue_dead` never re-drives (`queue/durable.py:80`). No route enqueued another, so the 24 h grant expired unused. | draft | `ops/owner_execution.queue_publication` + Command Center action `publication.execute` (step-up). It queues one `store.publish` carrying `owner_publication_approval_id`, only for a grant valid now, with the phase in limited_production or production and the kill-switch on. The door refuses under SHADOW, so the grant is never spent on a dead letter. |
| G2 | Nothing put `owner_activation_approval_id` on a `store.activate` job (the only enqueue, `pipeline.py:2652`, has none), so `activation_authority.validate` refused every activation. There was also no inbox card offering `activation.approve`. | public listing | `queue_activation` + `activation.execute` (step-up) + an ACTIVATION card for each verified draft (preview, approve, then "Make it public now" when a grant is live) |
| G3 | The Approvals card sent `expected_digest: "<from publication.preview>"` verbatim, so every approval from that button was refused ("approval preview changed"). This affects publication, activation and launch decisions. | draft and public | `approvals.js` `fillPreviewParams` substitutes the digest the card's own preview returned. With none, it asks the owner to preview first. The preview's section list now renders. SW shell v30. |
| G4 | `/api/readback/evidence` could not say which release is a first-draft candidate | confirmation | read-only section `first_listing_readiness` (slug@version, a 12-character hash prefix, PASS/FAIL/UNKNOWN per gated section, package state, blocker source ids). The CLI row is advisory (WARN/PASS, never FAIL). |
| G5 | No path clears a deleted draft's local `etsy_listing_id`, so `slug@version` can never be drafted again | re-draft | **not fixed** (touches the release-state model); route around it with a new release version |
| G6 | A draft made before the sample photo cannot be activated (gallery and copy change) | ordering | **by design**; ordering advice in §4 |

No gate was weakened. Each door checks a subset of what the handler re-checks, and only adds
an earlier refusal. Neither door signs, sends to Etsy, spends or changes the phase.

## 8. OWNER ACTION REQUIRED (batched)

| Action | Why | Max cost | Minutes | If it waits |
|---|---|---|---|---|
| Approve the merge and deploy of `eng/first-listing-runbook` (after review) | without G1 to G3 no Command Center path reaches a draft or an activation | CA$0 | 5 | the first draft cannot be created from the Command Center at all |
| Read `GET /api/owner/phase/verdict` and work its `failing` list | the phase can only leave SHADOW on a ready verdict | varies by item (UNKNOWN until read) | 10 to read | no draft of any product |
| Make or commission a full sample of the first product and photograph it unedited | Etsy requires a real photo of a made sample; the activation gate enforces it | yarn and materials, UNKNOWN until the product is chosen (basket small: one skein class) | hours (physical make) | no public listing, ever |
| Authorise the Railway variables `BRAMBLELOOP_PHASE=limited_production` and `BRAMBLELOOP_PUBLISH_AUTHORISED=1` at step 1 | a deployment change that enables publication | CA$0 | 5 | no draft |
| Approve the activation (step 10) | spend: Etsy listing fee | US$0.20 (CA$0.28) per listing, per 4 months | 3 | the draft stays invisible; nothing is spent |
