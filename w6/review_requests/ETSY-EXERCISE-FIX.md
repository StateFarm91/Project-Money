# Review request: ETSY-EXERCISE-FIX (branch `eng/etsy-exercise-fix`, from `claude/w6-release-19h7`)

_2026-11-21, UTC. Not deployed. No PR. CA$0. `owner_authorised=False` is unchanged; no
activate or publish call was added._

## 0. What production recorded, and what it did not

D-OWNER-ETSY-EXERCISE-2, attempt 1 (a93635ce), ran against openapi.etsy.com:
`failed_steps [upload_image, verify_contract]`; `create_draft:create_accepted 1`,
`cleanup:delete_accepted 1`, `verify_cleanup:deleted_and_gone 1`; `read_back_ok false`,
`marked_drafts_in_shop 1`, `ledger_confirmed_gone 1`, `ledger_still_on_etsy 0`,
`owner_actions 0`; recovery had nothing to clean.

The `cause` vocabulary kept taxonomy outcomes only for sweep, create, cleanup and verify_cleanup.
**So the Etsy outcome of `upload_image` was never recorded**, and the Railway deploy logs hold
only `attempt N: ok=False`. This session read no Railway variable values. The upload cause
below is therefore a diagnosis from the code and Etsy's published material, not an observation.
Section 4 makes the next run record it.

## 1. upload_image

**Wire format: matches Etsy's contract.** It was checked against Etsy's OpenAPI document
(`https://www.etsy.com/openapi/generated/oas/3.0.0.json`, fetched 2026-11-21). For
`uploadListingImage`, `POST /v3/application/shops/{shop_id}/listings/{listing_id}/images`, the
only media type is `multipart/form-data`, with properties `image` (binary), `listing_image_id`,
`rank`, `overwrite`, `is_watermarked` and `alt_text` (max 500). The Listings tutorial on
developers.etsy.com uses the same part name, `image`.

What we send:
- `rank` and `alt_text` as text parts, then the binary in `image`, with a filename and a
  per-part `Content-Type`.
- Exactly one `Content-Type` header, `multipart/form-data; boundary=…`, whose boundary is the
  one in the body.
- The credential headers carry no Content-Type. The transport strips any that arrives.

The known community failure is a manual `Content-Type: multipart/form-data` with no boundary
(github.com/etsy/open-api/discussions/976: "Either a valid image file or a listing_image_id must
be provided."). It does not apply here. A new transport-level test pins all of this byte for
byte: `tests/test_etsy_exercise.py::test_the_upload_wire_format_is_exactly_etsys`. It captures
the `urllib` Request the real `UrllibTransport` builds during a full run. It asserts the URL,
the header set (exactly `authorization`, `content-type`, `x-api-key`), the boundary regex, each
part's exact header bytes and order, and the terminator. It then re-parses the body with
Python's `email` parser.

**Image bytes: the likely cause, now fixed.** The exercise sent a generated **1×1 PNG**. Etsy
publishes no hard minimum for listing photos. Its image article (help.etsy.com 115015663347,
read 2026-11-21) recommends at least 2000 px. It says the first photo "should have a width and
height of at least 635 pixels". It warns that files over 1 MB may not finish uploading. A 1×1
image is the one input outside every published guideline. Every upload example in Etsy's
tutorial is a JPEG. The other community error, "Unrecognized file format" (#1145), is a
decode refusal.

Changes:
- The exercise now sends `etsy_probe.exercise_image()`: a 2000×2000 baseline RGB JPEG, about
  40 KB, opaque and not animated, built by Pillow (already in `requirements.txt`) rather than
  stored.
- `exercise_image_refusals()` checks format against extension, the 635 px minimum, the 1 MB
  limit, the mode (no alpha) and animation **before a byte is sent**. A failure is the new
  `image_fixture_refused` outcome and no request is made.
- The step records the image's facts (format, width, height, bytes).
- Taxonomy additions:
  - `image_not_valid_or_missing`: Etsy's real message for a missing or undecodable part. It
    does not settle either claim. Before this, it fell to UNCLASSIFIED.
  - `image_format_refused` now also matches "Unrecognized file format".

## 2. verify_contract

`read_back` passed: fields matched and the state was draft. So `verify_contract` failed on its
whole-listing verdict, `verified`. That verdict requires an uploaded image, so it was **a
consequence of upload_image**. It is not a separate contract defect. The step had no finding
that said so. It now reports `blocked_by_image_upload` (`settles=False`, so no claim moves on
it).

The check is **not weakened**: no image still means no verdict, and the step stays `ok=False`.
Every other flag (taxonomy, tags, state, mismatches) is still classified on its own. If a
taxonomy flag also failed on attempt 1, the next run's recorded `step_outcomes` will name it.

## 3. Read-back

The production shape: Etsy confirmed the delete (`deleted_and_gone`) and the ledger closed it,
yet the `state=draft` listing still showed the marked draft. Two defects:
1. `shop_read_back` ran **before** `reconcile`, so it could not know the ledger had settled
   the id.
2. It judged by title alone.

Now:
- `reconcile` runs first. Then `shop_read_back(client, db)` queries `getListingsByShop` with
  `state=draft` only (the only state the exercise creates) and judges each marked row **by
  id**:
  - **Not in the ledger's verified-gone set** (`DRAFT_REMOVED` with `confirmed_by`): it
    remains, and the shop is not clean. There is no retry, because lag cannot explain it.
  - **In that set, and a fresh `getListing` answers 404 now**: it is index lag. The read
    repeats with backoff (`READ_BACK_WAITS = 0, 5, 10, 20, 40, 60, 60` s, at most 195 s) while
    such a row is listed. If the index never catches up, the row is reported under
    `index_lag_verified_gone`, not as remaining.
  - **In that set, but `getListing` still holds it, or cannot be asked**: it remains
    (`ledger_says_gone_but`). The ledger being wrong never makes the shop clean.
- Recovery gets the same rule. A marked draft whose ledger row is closed and which 404s now is
  `index_lag_gone` (a new `RECOVERY_OUTCOMES` entry), not `left_foreign`. Before this, the
  attempt-1 draft would have made the next attempt's recovery report `ok=False`.
- Recovery's post-delete check still requires **both** a `getListing` 404 and absence from the
  draft listing (ETSY-RECOVERY candidate C). It now waits out index lag within the same bound
  before calling a delete unverified. Candidate C itself is refuted by attempt 1: the
  pre-delete `getListing` returned the draft (the delete was accepted after its state check),
  and the same call then returned 404.

Cost: a run with lag takes at most about 3 more minutes. The boot attempt runs in a thread;
the operator endpoint runs inline.

## 4. What the next run records (fixed vocabulary only)

`cause` in `etsy.exercise_finished`, shown in
`factory_visibility.owner_etsy_exercise.last_runs[].cause`, now adds:
- `step_outcomes`: the taxonomy outcome of every other step, including upload_image and
  verify_contract;
- `failed_status_classes`: per failed step, for example `upload_image: http_400`;
- `image_sent`: format word plus integers;
- `index_lag_verified_gone` and `read_back_attempts`.

No id, title or Etsy message reaches visibility (a test asserts this).

## 5. The next attempt

D-OWNER-ETSY-EXERCISE-2 allows 3 attempts in its window (2026-11-21T12:20Z to
2026-11-22T12:20Z). It has used 1. `app/main.py` starts `maybe_run_2` at boot when
`RAILWAY_DEPLOYMENT_ID` is set and `due_2` holds, so **a deploy of this branch inside the window
makes attempt 2**. This session did not deploy: that is the release session's or owner's
action. After 12:20Z on 2026-11-22 no attempt will run under this directive.

## 6. Tests

New, in `tests/test_etsy_exercise.py`:
- the exact upload wire format;
- the fixture meets every published rule, and a 1×1 PNG does not;
- an out-of-rule image is never sent, and the refusal is recorded;
- verify_contract names a failed upload, stays failed, and `cause` and visibility carry the
  outcomes, the status class and the image shape;
- the read-back waits out lag, judges lag that outlasts the bound by id plus a fresh 404,
  never ignores a draft that truly exists, and queries only `state=draft`;
- a full run is clean under simulated index lag (attempt 1's shape);
- recovery classes a lagging row as `index_lag_gone`, and a ledger-gone id that Etsy still
  holds as `left_foreign`.

Run (each suite's own `__main__`): test_etsy_exercise 62/62, test_etsy_transport (probe) 44/44,
test_etsy (client) 17/17, test_owner_etsy_exercise 8/8, test_factory_visibility 2/2,
test_vacuity 8/8, test_w3_etsy_upload_readback 9/9, test_etsy_publish 19/19, plus the further
etsy suites listed in the commit.

## 7. Not known, stated plainly

- Etsy's actual reply to the 1×1 upload was not recorded. If Etsy refuses the 2000×2000 JPEG,
  the next run's `step_outcomes` and `failed_status_classes` will name the outcome instead of
  leaving it to inference.
- Whether a taxonomy flag also failed in attempt 1's verify_contract is unknown, for the same
  reason.
- `array_encoding_tags`, `form_encoded_create`, `multipart_image_upload` and
  `oauth_token_endpoint` stay unverified until a run is recorded clean and sealed.
