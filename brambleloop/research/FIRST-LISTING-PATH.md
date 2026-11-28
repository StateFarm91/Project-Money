# FIRST-LISTING-PATH: from a valid gallery to a published Etsy listing

Written 2026-11-28 on branch `eng/first-listing`, from `origin/claude/repository-setup-nc9x6o`
at 46908fe66 (what production runs). Traced from the code, then run end to end on a seeded
database (`tests/test_first_listing_path.py`; the Etsy half is `tests/test_first_listing_doors.py`
on a fake Etsy). Release in view: **hexagon-coaster-set@1.2.1**. Production rows were NOT read
for this document: every production state below is stated as UNVERIFIED unless a readback says
otherwise. Nothing here changes an image gate, a publication gate, SHADOW enforcement, an owner
signature or an Etsy safety check.

## 1. The sequence

| # | Step | Runs as | Trigger / schedule | Needs | Phase |
|---|------|---------|--------------------|-------|-------|
| 1 | Gallery becomes valid | `visual.image_production` (publishing) | stage chain, event-driven; each stage enqueues the next | the image gates (other agents' work, untouched) | any |
| 2 | Gallery stage | `sale.pipeline` stage `gallery` (listing) | (a) `image_run_ended` when the image run reaches an end state (`ready_for_owner_review`, `blocked`, `approved_for_publication`), key `sale:<slug>@<v>@<rh>:gallery:<state>:e<epoch>`; (b) **new:** `sale.pipeline_sweep` (hourly cadence `sale_pipeline`) once per listing-set certificate that reads complete (`:gallery:cert<record_id>`), and once per hour while an image run is assembled but uncertified (`:gallery:certify<YYYYMMDDHH>`); (c) the bounded stall re-drive (≤3, reset on progress) | `etsy_ops.certified_frames` ≥ 7 frames, no problem; or `gallery_persist.certify_gallery` issuing it | any |
| 3 | Premium PDFs | `sale.pipeline` `pdf_build` → `pdf_certify` | successor keys | gallery bytes in the template slots; both editions PASS `publish.pdf_standard` | any |
| 4 | Attach | `sale.pipeline` `attach` | successor key; **new:** the hourly sweep re-enters it once per changed listing-package fingerprint (`:attach:pkg<fp>`) when it blocked on `listing_gates` | `listing_package.for_release` → package READY, or BLOCKED only by publication-only blockers (sample photo) | any |
| 5 | READY | `sale.pipeline` `ready` | **now keyed by the package fingerprint** (`:ready:pkg<fp>`) | `ready_for_sale`: certified pattern, complete gallery, both premium PDF certificates PASS, package ready | any |
| 6 | Listing package | `listing.package` (listing) | event when image production certifies a gallery (`listing.package:gallery:<run>`), when `launch.plan` finishes; 6-hourly sweep cadence `listing_package` | the chain's stored outputs; blockers from `release_gates.for_publish(read_only, stage=activation)` | any |
| 7 | Owner card | Command Center inbox card `publication:<slug>@<v>` | read on every `GET /api/cc/approvals` | `publication_authority.evidence`: all of certification, parity, listing_set, disclosure, policy, search, rollback PASS; otherwise the card shows no buttons and says which sections are not passing | any (approve binds content, needs no phase) |
| 8 | Grant | `publication.preview` then `publication.approve` | owner press | owner session + CSRF/nonce + fresh step-up; signed Ed25519 inside the owner request (`owner_grant_keys`, explicit key pair or the Mode S key derived from `BRAMBLELOOP_SECRET_KEY`); the preview digest; valid 24 h | any |
| 9 | Phase | `POST /api/owner/phase/transition` twice (shadow → staging → limited_production) + the Railway variable `BRAMBLELOOP_PHASE=limited_production` | owner | ops credential; `readiness` = a `launch.assessed` row with `ready: true` (≤7 days) and `rollback` = a `launch.rollback_rehearsed` row with `ok: true` (≤3 days), both from the daily `launch.readiness` cadence; the live readiness verdict evaluated at transition time must be ready; **and a deployed build that carries a committed release record** (otherwise the boot guard forces SHADOW whatever the variable says) | — |
| 10 | Door | `publication.execute` | owner press | grant valid now, `BRAMBLELOOP_PUBLISH_AUTHORISED=1`, effective phase `limited_production` or `production`; one job per grant (`owner-publish:<slug>:<v>:<rh24>:<grant>`) | limited_production+ |
| 11 | Draft | `store.publish` (store_operator) | the door's job (no cadence; the launch-time job is refused in SHADOW and never re-driven) | handler re-checks: support holds, not an experiment, parity (#75), release gates, phase, Etsy client refusal (credentials, phase, kill-switch), PDF hash vs `assets.built`, search-grid (#126), certified images (F-524), `ready_for_sale` + premium PDFs, the grant at `pre_claim` and `before_create` | limited_production+ |
| 12 | Activation | `store.activate` | automatic after a verified draft (refuses: no approval id, but reads the draft back); then `activation.preview` → `activation.approve` → `activation.execute` | activation grant; read-back verified; sample photo unless the owner's publish-with-renders waiver stands; daily listing-fee ceiling (US$0.20 per listing) | limited_production+ |

Scheduler facts: `sale.pipeline_sweep` 1 h, `listing.package` 6 h, `ops.thrash` 1 h,
`launch.readiness` 24 h, `creative.blind_review` 24 h, `ops.policy_watch` 24 h,
`etsy.credential_health` 24 h, `etsy.probe` 6 h, `store.draft_reconcile` 1 h. `sale.`,
`listing.`, `visual.` and `launch.` are pipeline prefixes: the idle free-poll backoff never parks
them (D-OWNER-NO-PAUSE); only the error/paid-loop breaker (kind `suspended`) applies.

## 2. Blockers found, and what was done

**B1 (code, fixed) — a gallery made valid without a new image end state never re-entered the
chain.** The gallery event key is per (end state, epoch) and was already spent when the run first
ended invalid; the sweep's bounded re-drive count (3) resets only on progress, so after days at
the gallery stage it was exhausted. Reproduced: gallery valid, sweep runs, release stays at
`gallery_in_production` forever. Fix: `sale_pipeline._evidence_redrives` — the hourly sweep
re-enters the free gallery stage once per complete certificate (and asks the free certification
route once an hour while an image run is assembled but uncertified), outside the bounded count.

**B2 (code, fixed) — a stage blocked on the listing package was never re-entered after the
package changed.** `attach` blocked on `listing_gates` (one buyer-facing gate pending), the three
re-drives were spent; when the gate passed and the 6-hourly `listing.package` sweep recorded the
new package, nothing re-ran `attach`. Fix: the blocked attach records the package fingerprint it
judged, and the sweep re-enters it once per new fingerprint. The `ready` successor is keyed by
the package fingerprint, so a re-entered attach is not swallowed by an earlier package's key.

**B3 (code, fixed) — store.publish "suspended" outlived its cause.** The launch-time
store.publish is refused in SHADOW and dead-lettered; three identical refusals within 72 h trip
the thrash breaker (`swarm.orchestrate.thrash_sweep`, kind `suspended`), which lifts only on a
change to the handler's code or a resolved incident. After the owner's phase transition it would
still have read suspended, and the shadow-era dead letters still in the 72 h window would have
re-tripped it. In this build the suspension does not stop the owner door (store.publish is no
cadence) but it drives the readbacks, `useful_work.diagnose`, the daily ledger and a
`failing_loop` ECR. Fix: a breaker suspension tripped by closed-gate refusals (the queue's own
`classify_dead_letter == REFUSED`) lifts once a phase transition is recorded after it, and its
incident is resolved by the next `ops.thrash`; refusals that ended before the newest transition
are not observations. A failing loop (any other error) keeps its breaker across a phase change
(asserted), and refusals after the transition count again (asserted).

**Not code blockers (verified, documented):**

* **The boot guard.** A hosted build with no committed release record for its exact tree forces
  `BRAMBLELOOP_PHASE=shadow` at import (`ops.release_record.apply_at_import`). BUILD_STATE's
  production block says `release-record: NONE`. Until a release with a record (a plain, full,
  `REQUIRE_CLEAN=1` suite on the deployed tree, then `ops/deploy_guard.py record`) is deployed,
  the owner's phase transition has no effect. This is engineering's next release step, not the
  owner's.
* **The owner card's gated sections downstream of the gallery.** On the seeded world, after
  READY, the card was not executable on exactly: `parity` (the #75 assessment needs the daily
  `creative.blind_review` verdict and a described hero frame, plus the frame review in
  `assets.build` and the exported-frame review), `policy` (`ops.policy_watch` must have read every
  platform policy source within its window, none changed-unreviewed) and `rollback` (a
  `launch.readiness` rehearsal within 3 days). Each is produced by its own job; none is a gate to
  weaken. Read them on the card before signing.
* **The launch-time store.publish.** Refused in SHADOW and never re-driven; the
  `publication.execute` door is the only route to a draft (ENG-FIRSTLIST, unchanged).
* **`transactions_r`.** No publish, read-back or activation operation requires it
  (`etsy_oauth.SCOPES_REQUIRED`); drafts and activation are not refused for its absence. It is
  required for order ingest (first-sale evidence). If `etsy.credential_health` reports it missing
  (owner action `etsy.auth:reauthorise`), re-authorise once before activation so the first order
  is visible.

## 3. What the owner must do, and when

All are batched here; each one only when the row before it is true.

1. **Wait for READY** (no action). Watch `GET /api/readback/evidence` →
   `first_listing_readiness` (the release listed with `draft_candidate`, its blockers and
   `publication_sections`) and the Mission Control sale-pipeline row (`ready`). Expected within
   ~1 h of the gallery certificate (the hourly sweep is the longest wait).
2. **Etsy re-authorisation, only if the readback / owner queue shows `etsy.auth:reauthorise` or
   `missing_scopes` contains `transactions_r`.** Why: order ingest cannot see a sale without it
   (drafts do not need it). Cost CA$0, ~5 minutes. Consequence of waiting: the draft and
   activation still work; the first order stays UNMEASURED. Exact action: signed in to the shop's
   Etsy account, call `GET /api/etsy/oauth/start` with the operator credential
   (`Authorization: Bearer <ops token>`), open the URL it returns, approve every scope listed;
   Etsy redirects to `/api/etsy/oauth/callback`, which stores the grant.
3. **Read the card, then sign the publication grant (may be done while still in SHADOW).**
   Command Center `/cc/` → **Approvals** → card **"Create the Etsy draft for hexagon-coaster-set
   v1.2.1"** (`#/approvals/publication:hexagon-coaster-set@1.2.1`). It must say "Ready: every
   gated section passes". Press **Preview** (`POST /api/cc/actions/publication.preview` with
   `{slug, version, release}`), then **Approve** (`POST /api/cc/actions/publication.approve` with
   the preview's `expected_digest` and a reason), entering the passphrase + TOTP step-up when
   asked. Cost CA$0, ~5 minutes. The grant lasts **24 h**, so sign it on the day of steps 4–5
   (an expired grant needs a new press, nothing else).
4. **Move the phase out of SHADOW (after engineering has deployed a build with a committed
   release record).** Two calls, one step each, with the operator credential:
   `POST /api/owner/phase/transition` `{"to": "staging", "reason": "...", "evidence_refs":
   {"readiness": <launch.assessed id>, "rollback": <launch.rollback_rehearsed id>}}`, then the
   same with `"to": "limited_production"`. `GET /api/owner/phase/verdict` shows whether the move
   will be accepted first. Then set the Railway variable `BRAMBLELOOP_PHASE=limited_production`
   and ensure `BRAMBLELOOP_PUBLISH_AUTHORISED=1` (the global kill-switch; it can only deny).
   Cost CA$0 (the variable change restarts the service), ~10 minutes. Consequence of waiting:
   the release waits READY; nothing else does. `GET /api/owner/phase` must show
   `phase: limited_production` with `agree: true`.
5. **Create the draft.** Same card → **Create the Etsy draft now**
   (`POST /api/cc/actions/publication.execute` `{slug, version, release, approval_id, reason}`;
   step-up). The draft is inactive and costs nothing. The handler re-checks every gate; a refusal
   is recorded on the job with its reason.
6. **Activate (makes it public; Etsy charges US$0.20 ≈ CA$0.28).** Approvals → card
   `activation:hexagon-coaster-set@1.2.1` → **Preview** (`activation.preview`) → **Approve**
   (`activation.approve`, step-up) → **Execute** (`activation.execute`). Needs the draft read back
   verified, and the sample photograph unless the owner's publish-with-renders waiver stands.
   Maximum cost CA$0.29 per listing (the code's daily fee ceiling also applies).

## 4. Evidence

* `tests/test_first_listing_path.py` (new): B1 and B2 reproduced and fixed on the real handlers
  (gate.certify, assets.build, pricing.position, listing.seo, launch.plan, every sale.pipeline
  stage, visual.image_production on free stubs, listing.package), B3 on the breaker, and the
  owner card / grant / SHADOW refusal / kill-switch / door on the READY release.
* `tests/test_first_listing_doors.py`, `tests/test_etsy_publish_e2e.py`: the grant → door →
  store.publish → draft → activation path on a fake Etsy (unchanged, re-run).
