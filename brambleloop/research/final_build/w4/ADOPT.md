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

## What this does not do (honest limits)

- **It does not verify file bytes.** Etsy exposes no file hash. Sizes are compared only when `assets.built` recorded them for this release.
- **It does not read listing properties or image alt text at adoption.** The daily census reads both for every listing of ours, adopted listings included.
- **VERIFIED does not mean "matches".** Differences, and any incident the census raises for them, are separate:
  - the census's existing `etsy.listing_drift:<id>` is P1 and halting for any listing of ours that differs from its certified payload, and an adopted listing is now one of ours;
  - so a hand-edited description such as the package's [PACKAGE EDIT] text will raise that P1 on the next census until the stored copy and the live listing agree.
  This is existing census behaviour, deliberately not weakened here.
- **Readers that count `Listing.state == "published"` do not count `published_manually`.** That includes the KPIs, the run-rate, `growth_ops` and `verify_checks._published_rows_proven`, which is W-READBACK's file and was not touched. In a live phase `/api/verify` will list an adopted listing as not proven through the gated path, which is true.
- **An UNVERIFIED adoption expects the remote state `active`.** If the owner left it as a draft, the next census with credentials will raise a policy-suspected incident. Repeating the adoption once Etsy is readable re-reads it and fixes the expected state.
- **Production use needs a deploy.** The owner action exists only after this branch is integrated and deployed.
