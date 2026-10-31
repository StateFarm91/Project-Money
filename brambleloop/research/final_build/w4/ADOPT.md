# W-ADOPT: adopting a hand-made Etsy listing (`listing.adopt_manual`, E-4)

- **Branch:** `claude/w4-ADOPT`, cut from `origin/claude/w4-INTEG8-next` at `b0133916`.
- **Date:** 2026-10-27 (UTC).
- **Scope:** records only. Nothing was published, nothing was sent to Etsy or Railway. The tests run with sockets refused and an in-process Etsy transport.

## The gap

W-LISTING (`manual_listings/*/LISTING_PACKAGE.md` §10, on `claude/w4-LISTING1` at `5bf9aaf3`) found that a listing the owner makes by hand in Shop Manager had no path into Brambleloop's records:

| Before | Where |
|---|---|
| The census opened a P2 `etsy.unexpected_listing:<id>` and never adopted it | `runtime/etsy_ops._expected_listings` |
| Orders were recorded `"unmatched: no listing of ours carries this Etsy listing id"` | `commerce/orders_ingest.version_at` |
| The stats export matched only on slug, Etsy id or an exact title | `commerce/listing_outcomes._listing_index` |
| Once the gates cleared, `store.publish` would create a **second** listing for the release | `runtime/pipeline.handle_store_publish` refuses only when `Listing.etsy_listing_id` is set |

## The design

**Owner door.** `listing.adopt_manual` is a new entry in `app/command_center/approvals.ACTIONS`, with `requires_step_up = True`.
- It uses the existing route `POST /api/cc/actions/{action}`: owner session, CSRF, nonce and a fresh step-up, refused for the operator bearer.
- No route was added, so the API fingerprint `7f715ba78ff283a8` is unchanged. The new state values are declared in `ops/CONTRACT_CHANGES.md`.
- A reason is required.
- The route writes its usual `cc.owner_action.listing.adopt_manual` audit row, carrying the listing id, verification, repeat flag, audit id and review id.
- A small form, "Adopt a hand-made Etsy listing", is on the Approvals view (`static/js/views/approvals.js`). It runs through `guardedAction` with step-up.

**Input.** The Etsy listing id (numeric, from the URL), the slug, the version and the certified release hash.
- The release resolves exactly as the publication authority resolves it: a certified `PatternVersion` with that `release_hash`, and the drafted `Listing` bound to the same hash.
- If either is missing, adoption is refused.

**Verification** (`publish/manual_adoption.read_listing` and `compare`).
- It reads Etsy only, through `runtime.etsy_ops.build_client` with `owner_authorised=False` and the client's `Authority.READ` methods: `getListing` (with `includes=Images`), `getAllListingFiles`, and `getListingImages` as a fallback.
- **Recorded:** state, title, price (amount and currency), tags, taxonomy id, image count, file count, file names and sizes, URL and creation timestamp.
- **Compared** against the stored `Listing` and the release package:
  - title and description;
  - tags (as a set);
  - price, against the stored price and the Launch-0 plan band (`products.launch0.launch_price`);
  - taxonomy, against `commerce.category.publish_inputs` when it is CHOSEN;
  - disclosures, through `etsy_ops.disclosure_on_remote`;
  - digital files: expected names `{slug}-pattern-us/uk.pdf`, file count, and sizes against the `assets.built` byte counts for this release.
- **The file hash is NOT READABLE.** Etsy's `ShopListingFile` carries no hash, so byte identity with the certified PDFs is recorded under `not_verifiable` and never as matched. A size mismatch is reported as a difference.
- **Differences do not block adoption.** They are recorded in full and open (or restate) a non-halting P2 review incident, `listing.adoption_review:<slug>@<version>`. A later clean verification resolves it.
- **Outcomes:**
  - **VERIFIED** means Etsy was read, the listing exists, and its `shop_id` equals the shop of the credential. It does not mean the copy matched, and it never covers file bytes.
  - **UNVERIFIED** means no credential, any read error or auth failure, or no `shop_id` returned. The adoption is still recorded, so the duplicate guard holds, and the review item says UNVERIFIED.
  - **Refused:** Etsy answers 404, or the listing's `shop_id` is a different shop. There is nothing of ours to adopt.

**Effects**, in one transaction.
- `Listing.etsy_listing_id = <id>`. This is the field the automated path writes, in `draft_intent.checkpoint` and in `runtime/pipeline.py` after create.
- `Listing.state = "published_manually"`.
- A `DraftIntent` row with key `key_for(slug, version)`, state `ADOPTED_MANUAL`, `remote_id = <id>`, and a `detail` holding the whole verification record. That record includes `expected_remote_state`: the state read from Etsy, or `active` when unverified.
- This makes two independent guards against a duplicate:
  1. `store.publish` stops at its existing `already` check and returns `"already published manually"`;
  2. the unique (slug, version) intent makes `draft_intent.claim` refuse any automated create attempt.
- **Audit:**
  - `listing.adopted_manual` on every adoption and every repeat, with the full verification;
  - `listing.adopt_manual_refused` on every refusal.

**Idempotency and conflicts.**
- The same (id, slug, version, release) again is a repeat:
  - no new row, and no change if the earlier adoption was VERIFIED, in which case Etsy is not re-read;
  - if the earlier one was UNVERIFIED, Etsy is re-read and the same row is updated, which can turn it VERIFIED.
- **Refused:**
  - a different listing id for an adopted release;
  - a different release hash;
  - an Etsy id already linked to another release;
  - a release already linked by the automated path;
  - a release with an outstanding automated creation intent (that must be reconciled, not adopted over).
- A concurrent insert that loses the unique intent race is refused with an `IntegrityError` and changes nothing.

**Read-only against Etsy.** The module calls only `get_*` methods. The tests route every request through a transport that records the method, and assert that no request other than GET was made in any case.

## Downstream after adoption

| Reader | Change | Result |
|---|---|---|
| Census `_expected_listings` | A `published_manually` row's expected state is the adoption's `expected_remote_state` (otherwise it would default to `draft` and raise a false policy-violation suspicion) | The id is ours. `etsy.unexpected_listing:<id>` is no longer raised, and the existing one resolves on the next read census. Field drift and asset audits now run against the certified payload, as for any listing of ours |
| Orders `listing_history` | None needed to match (it keys on `Listing.etsy_listing_id`). The basis is labelled `listing.adopted_manual` | Sales attribute to the slug and version. The effective time is the listing row's creation |
| Stats `_listing_index` | None (it keys on `Listing.etsy_listing_id`) | Matches by Etsy id, even when the title was edited by hand |
| `store.publish` | The refusal says `"already published manually"` and audits `published_manually: true` | No second listing |

## Tests

`tests/test_w4_adopt_manual_listing.py`, 10 cases, all OK:

1. `listing.adopt_manual` requires step-up, and no new route exists.
2. **Unauthorised adoption is refused:**
   - no session (401/403);
   - operator bearer only (401/403);
   - a session without step-up (403 `STEP_UP_REQUIRED`);
   - in every case nothing is recorded and Etsy is not read.
3. A CC adoption with step-up returns VERIFIED and links the listing. A missing reason is refused (409). The fields observed are recorded, the file hash is NOT READABLE, and both audit rows are present.
4. **Duplicate adoption is idempotent:**
   - a verified repeat changes nothing and makes no Etsy read;
   - a different id or a different release is refused;
   - one Etsy id cannot be linked to two releases.
5. **An unreadable Etsy gives UNVERIFIED:**
   - no credential: UNVERIFIED with zero requests, and a non-halting review item;
   - a 503: still UNVERIFIED;
   - readable again: the same row upgrades to VERIFIED and the review resolves.
6. Differences (title, tags, price outside the band, a missing UK file) are recorded. A P2 non-halting review opens, and adoption still succeeds.
7. A 404, a listing from another shop, and a non-numeric id are each refused and audited.
8. **Census, orders and stats match:**
   - before adoption, the read census reports the listing unexpected;
   - after it, it does not, and the unexpected incident is resolved;
   - `version_at` returns the slug and `1.2.0` with basis `listing.adopted_manual`;
   - `_listing_index[id]` is (slug, `1.2.0`).
9. **Adoption blocks `store.publish`.** This uses the public handler in a recorded production phase, with the capability gates isolated as fixtures in the same way as `test_draft_creation_durability`. The result is `published: False` with reason `already published manually`, and zero creates. `draft_intent.claim` refuses a second intent.
10. **Zero Etsy write calls** across every transport used in the file.

Touched suites and their importers were each run separately at nice 19 (see the report for the list and results).

## Follow-up (W-ADOPT-2): accepted baseline, and every live reader

### 1. Hand edits no longer halt publication once the owner accepts them

- **New owner actions:**
  - `listing.baseline_preview`: a read, no step-up;
  - `listing.accept_baseline`: step-up, with a reason required.

  Both go through the same `POST /api/cc/actions/{action}` route, and there is a Preview / Accept form in the adoption card.
- **Preview:**
  - reads the adopted listing's live copy from Etsy (read-only);
  - snapshots title, description, tags, price and taxonomy, and returns its sha256 digest;
  - lists the differences from the certified copy;
  - runs the acceptance checks below.
- **Accept** must carry `expected_digest` equal to the digest of a fresh read, so the owner accepts exactly what they previewed. It records:
  - `accepted_baseline` (snapshot, digest, who, when, reason, accepted differences) on the adoption's `DraftIntent.detail`, with earlier baselines kept in `baseline_history`;
  - an audit row `listing.baseline_accepted`;
  - resolution of `listing.adoption_review:<slug>@<version>` and `etsy.listing_drift:<id>`.
- **Refused** (the review incident is kept open and restated, and `listing.baseline_refused` is audited) when the live copy:
  - **breaks Product Truth.** The live title, description and tags are checked against the certified CIR: the title promise (multiplicity), the assembly promise and the motif promise;
  - **drops a required disclosure.** That covers the buyer-trust set, run on the live copy, and the AI sentence `DISCLOSURES["ai_assisted_design"]` verbatim. Any other AI sentence the certified copy carried must also stay;
  - **cannot be read** from Etsy, or is not the adopted listing.

  Nothing is ever accepted automatically: adoption itself sets no baseline.
- **Census:** for an adopted listing with an accepted baseline, `_field_drift` compares Etsy with the baseline (`manual_adoption.baseline_drift`) instead of the certified payload. Only a change made after acceptance raises the P1 `etsy.listing_drift:<id>`. Without a baseline, the comparison is with the certified payload, as before.

### 2. Every "live on Etsy" reader counts `published_manually`

- **One helper.** `core/listing_state.py` defines `LIVE_ON_ETSY = ("published", "published_manually")` and `is_live_on_etsy(state)`.
- **Readers changed:**
  - `app/verify_checks.py` (/api/verify):
    - `nothing_published` already fails while an adopted listing carries an Etsy id; the evidence now names `listings_published_manually`;
    - in live phases, a `published_manually` listing is proven by a VERIFIED owner adoption (the step-up adoption is its grant, and the Etsy read at adoption is its read-back). An UNVERIFIED adoption is reported as unproven.
  - `app/main.py` `/api/catalogue`: `published` is computed and no longer hard-coded `False`. **This is W-READBACK's file.** The change is about eight lines in `api_catalogue` only.
  - `store_foundation/preview.py`: `live` / `published` are computed (`None` if unreadable).
  - `autonomy/kpis.py` (the shadow breach check), `runtime/growth_ops.py` (traffic destination and the ads gate), `growth/ads_readiness.py` (the `listing_live` gate), `finance/sustainability.LIVE_STATES`.
  - `scale/confidence.py`, `scale/evidence.py`, `scale/runrate.py` (twice).
  - `intel/etsy_scorecard.py` (live count), `intel/mission.py`, `intel/mission_runtime.py` (the launch rung and published_at).
  - `swarm/orchestrate._CLOSED_LISTINGS`, `creative/standard.py`, `products/lifecycle.py` (the LIVE / GROWING stage), `seasonal/benchmark_matrix.py`, and `runtime/pipeline.py` (`live_since`).
- **Deliberately unchanged:** readers of `store.published` audit rows, such as delivery evidence in `commerce/first_hundred`. A manual listing has no verified upload record, so counting it there would be a false claim.
- **Tests:**
  - a behavioural test that each of these readers counts an adopted listing;
  - a static guard that fails on any `state == "published"`, `state != "published"`, `by.get("published"` or `"published" in states` left in `src/`.

## Independent review fixes (SECREVIEW of `af042099`: F-1 to F-4)

The review is `INDEPENDENT_SECREVIEW_ADOPT_af04209.md` on `claude/w4-SECREVIEW-ADOPT-af04209`. Its Appendix A suite is ported as `tests/test_w4_secreview_adopt_adversarial.py`, with one fixture value changed (see that file's docstring).

- **F-1 (High): a baseline covers only the copy fields the owner reviewed.**
  - The fields are `BASELINE_FIELDS`: title, description, tags, price and taxonomy_id.
  - The census (`etsy_ops._field_drift`) compares those with the baseline, and **every other field with the certified payload**: who_made, when_made, is_supply, type, quantity, materials and properties.
  - Without a full certified payload (category or search certificate not yet PASS), it still compares the category-independent policy fields (`POLICY_FIELDS`) against the stored copy and the CIR's materials.
  - **Preview** lists `not_covered_by_baseline`: policy-field drift, package differences such as files, and properties left UNVERIFIED. These are shown to the owner and never accepted.
  - **`accept_baseline`:**
    - resolves `etsy.listing_drift:<id>` only when every drift line it records is in `BASELINE_FIELDS`; otherwise the incident is kept open (`incidents_kept_open`) and the census resolves it only by observation;
    - keeps the non-halting review item open, restated, while anything is not covered.
- **F-2 (Medium): live-phase proof requires a match.** `manual_adoption.proof_problems`, used by `verify_checks._published_rows_proven`, proves a manual listing only when all of these hold:
  - the adoption is VERIFIED;
  - the live listing matched the certificate, or every difference is a copy field under an accepted baseline;
  - nothing was left uncompared, apart from the file hash, which Etsy does not expose. An unknown category, unread properties or an unknown price band all count as uncompared;
  - no `listing.adoption_review` or `etsy.listing_drift` incident is open.

  Adoption now also reads and compares listing properties when the category is CHOSEN.
- **F-3 (Low): one Etsy id, one release, enforced by the database.**
  - A new table `manual_listing_claims` uses the Etsy id as primary key. It is written in the same transaction as the adoption and registered in `core/db.create_all`.
  - The write transaction also re-checks that no other `Listing` carries the id.
  - Tests: a threaded race (both reads complete, then both writes race, and exactly one commits) and a direct duplicate insert refused by the database.
  - The review item is now opened only after the adoption is actually recorded.
- **F-4 (Info): the static guard now matches its claim.**
  - It flags any comparison with the `"published"` literal in either operand order and whatever the variable is called, any membership tuple or `.in_(...)` that lists it, and `.get("published")`, unless the same line names `published_manually`.
  - Three non-listing uses are allowlisted, each with its reason.
  - Its docstring states what it does not cover: literals built at runtime, and tuples split across lines.

## Delta review fixes (SECREVIEW of `752950e4`: R-1, N-1 to N-5)

The review is `INDEPENDENT_SECREVIEW_ADOPT_752950e.md` on `claude/w4-SECREVIEW-ADOPT-752950e`.

- **R-1 (High, operational): retention runs again.** `listing.adopted_manual` is now classified as `lifetime_total` in `ops/retention.KNOWN_READ_ACTIONS`, the same entry as INTEG8 `42aa6a72`. `commerce.orders_ingest` reads every adoption, so pruning would change the answer. `test_w4_fmbatch1_retention_guard` passes.
- **N-1 (Medium): no payload stays halting.** For a baselined listing with no certified payload, the census now adds `properties: no certified payload ...; UNVERIFIED`. The halting `etsy.listing_drift` therefore stays open, and no census can resolve it until a certified payload exists and the listing compares clean. A baseline never relaxes a halting gate.
- **N-2 (Medium): nothing uncompared is ever dropped.**
  - The preview's fresh comparison returns `not_verifiable`, minus the structural file-hash note.
  - That list is carried into `not_covered_by_baseline` and stored on the baseline.
  - `proof_problems` always counts it. A baseline from before this field existed falls back to the adoption's notes, never to nothing.
- **N-3 (Low): the preview compares properties that were actually read.** The listing passed to the comparison now includes the properties read from Etsy (canonicalised), as the census and read-back do. Unread or unreadable properties produce an explicit line.
- **N-4 (Low): every proof clause is pinned.** `test_each_proof_clause_alone_makes_a_manual_listing_unproven` starts from a proven listing and breaks one condition at a time. Each of these alone makes it unproven:
  - UNVERIFIED;
  - a recorded difference;
  - a not-verifiable note;
  - `baseline.not_covered`;
  - `baseline.not_verifiable`;
  - an older baseline falling back to the adoption's notes;
  - an open review incident;
  - an open drift incident;
  - no adoption record.
- **N-5 (Info): repeat adoptions get a claim.** A repeat adoption backfills the `manual_listing_claims` row.
- **Appendix A.1 and A.2** are ported as assertion tests in `test_w4_secreview_adopt_adversarial.py`, with the review's suggestion that `materials=[]` is pinned as drift.
- **One ported precondition changed.** `test_after_acceptance_policy_fields_still_drift` now requires "no policy-field drift" before the change, instead of "no drift at all": after N-1, uncompared properties correctly keep the incident open.

**Launch-day consequence, stated plainly:** until the certified category and the search certificate are PASS, an adopted listing keeps one halting `etsy.listing_drift` line, for its uncompared properties, even after the owner accepts a copy baseline. Accepting stops the copy edits being reported. It cannot stand in for the missing certified payload.

## What this does not do (honest limits)

- **It does not verify file bytes.** Etsy exposes no file hash. Sizes are compared only when `assets.built` recorded them for this release.
- **It does not read listing properties or image alt text at adoption.** The daily census reads both for every listing of ours, adopted listings included.
- **VERIFIED does not mean "matches".** Until the owner accepts a baseline (W-ADOPT-2 above), an adopted listing is compared with its certified payload, and a hand edit raises the P1 `etsy.listing_drift`. Once a baseline is accepted, only drift after it does.
- **An UNVERIFIED adoption expects the remote state `active`.** If the owner left it as a draft, the next census with credentials will raise a policy-suspected incident. Repeating the adoption once Etsy is readable re-reads it and fixes the expected state.
- **The baseline fixes copy only:** title, description, tags, price and taxonomy. Images and files are still judged by the census's asset audit, and listing state by the state check.
- **Product Truth at acceptance is limited to the deterministic promises** (multiplicity, assembly, motif) and the disclosures. Size figures in free text are not re-measured against the twin.
- **Production use needs a deploy.** The owner action exists only after this branch is integrated and deployed.
