# Independent security review: release candidate 17bc373

**VERDICT: (in progress; written incrementally)**

Reviewer: W-SECREVIEW5, an independent reviewer who did not write any of the code reviewed,
including the B1 fix. Date: 2026-10-20 (UTC). The review was read-only. Nothing was deployed,
no request was sent to production and nothing was spent.

## Scope

- Production: `b931d17a738d6a5bcd96580f620069b669ca5f57`
- Previous review: `INDEPENDENT_SECREVIEW_7f6dbe8.md` (B1 BLOCKER, L1-L4 LOW, I1-I6 INFO).
- Candidate: `17bc373e` (branch `claude/w4-INTEG4`, "INTEG4: merge w4-CREDHEALTH @ 0b6e699").
- Diff reviewed: `git diff 7f6dbe89 17bc373e -- brambleloop/src
  brambleloop/tests/test_w4_integ4_secfixes.py brambleloop/tests/test_w4_integ4_deliverable_routes.py
  brambleloop/tests/test_w4_credhealth.py brambleloop/requirements.lock brambleloop/Dockerfile ops`
  (26 files, +1,684/−86). `requirements.lock`, `Dockerfile` and `ops/` have no changes in the
  range. Generated data (board snapshots, `final_master_closure.json`) ignored.

## Focus area 1: is B1 closed? **Yes. B1 is FIXED.**

Lines are in the candidate.

### The byte route: `app/main.py:2152-2234`

`GET /api/model-tournament/image/{sha256}` is still public, but now:

1. Lower-cases the digest and requires exactly 64 characters of `[0-9a-f]` (`:2166-2168`).
2. `tournament_image_refusal` (`:2206-2234`) is an allowlist that fails closed:
   - a digest with a `DurableArtifact` row is served **only** if `why_kept` equals the
     reference pack's `KEEP_REASON`; every other keep purpose (deliverable PDFs, certified
     frames, experiment outputs, image-production candidates) is refused, **even if a
     tournament package names it**;
   - a digest with no row is served only if one of the 50 newest `model.tournament` /
     `model.reference_pack` audit rows names it;
   - any exception → refused.
3. After loading, the bytes must start with a PNG, JPEG or WebP magic number
   (`image_media_type`, `:2195-2203`), else 404. A `%PDF` body is never served, whatever the
   allowlist says.
4. `Cache-Control` is now `private`, with `nosniff`.

Bypass attempts (in-process probe, scratch SQLite, sockets disabled; not committed):

| Attempt | Result |
|---|---|
| Kept paid PDF digest, also named in a `model.tournament` audit row | 404 (row exists, not reference-pack) |
| Same, digest in upper case | 404 |
| Certified listing frame (PNG, kept with a `deliverables` reason) named in a tournament row | 404 |
| A PDF whose row is (mis)labelled with the reference-pack `KEEP_REASON` | 404 (magic-number check) |
| An unkept PDF on disk named in a tournament row | 404 (magic-number check) |
| Leading `%20` / URL-encoded junk | 400 |
| Genuine tournament PNG (named, unkept), lower and upper case | 200 `image/png`, `private` |

Who can make a digest "named"? Only `ctx.audit(tournament.TOURNAMENT_ACTION | reference_pack.PACK_ACTION, …)`
inside worker jobs (`runtime/release.py:7867`, `:7881`, `:8696`). No HTTP route writes an audit
row with a caller-chosen action and detail. The substring match (`sha256 in json.dumps(detail)`)
needs the full 64 lower-case characters, so it cannot be widened by a prefix.

Other byte-serving routes: every other `ArtifactStore().get` reached from HTTP is under
`/api/cc/*` (owner session: `store/pdf/{slug}`, candidate and experiment images) or
`/api/continuity/export` (operator credential). The remaining public GETs return JSON or HTML;
`/api/model-asset`, `/api/storefront/preview`, `/api/build`, `/api/verify`, `/api/status` and
the dashboard return no artifact bytes. So a digest published anywhere else can reach only the
tournament route, which now refuses everything except reference-pack and tournament images.
B1's fix therefore does not depend on digest secrecy.

### The audit route: `app/main.py:4936-4975`

Without the operator credential, `detail` goes through `_shorten_digests`, which recurses
into dict keys and values and lists/tuples and cuts every **isolated** 64-hex run (either
case) to 12 characters. Verified on keys, nested lists, upper case and `sha256:<hex>`.
Gaps (defence in depth only, since the byte route no longer depends on it; **I7** below):
the `artifact` and `actor` columns are not shortened; a digest preceded or followed by a
hex letter (`blob<sha>`, `<sha><sha>` concatenations) is not matched because of the
look-arounds. I found no writer that puts a full digest in `artifact` today.

### The sweep test is sound and not vacuous

`tests/test_w4_integ4_deliverable_routes.py` enumerates every GET route of the app (routers
included, via `security.iter_api_routes`) plus every public mutating route, fills each path
parameter with the PDF digest, slug, slug@version, version and `1`, and requests each
without any credential (operator token configured, never presented), on disk and after a
simulated redeploy. It flags raw bytes, base64 and any `%PDF` body.

- On `17bc373e`: 4/4 passed.
- On the unfixed tree `263e94da` (the same test file copied in): **2/4 failed**, both sweeps
  naming exactly `GET /api/model-tournament/image/<sha>` → 200 raw bytes. The test catches B1.
- Limits (INFO): it does not vary query parameters (no current public GET takes a digest or
  slug by query and returns bytes), and it checks bytes, not digest publication.

## Focus area 2: L1-L4

- **L1 FIXED.** `api.py:493-495` `images_restart` calls `auth.require_stepup(db, request,
  "images.restart")` before reading the body; CSRF and nonce are still enforced by the gate.
  `test_l1_restart_requires_step_up` passes.
- **L2 FIXED.** `experiments/controlled.py:382-392` `_price_cad` now uses
  `images.render_estimate_usd(provider, size, refs)` (the gateway's own reservation price),
  converted to CAD, never below the table price. The cap check therefore uses the price the
  gateway bills.
- **L3 FIXED.** `runtime/etsy_ops.py:560-565` `certified_images` checks every certified
  frame's digest with `refuse_if_experiment_image`, after the product-level check. In
  `visual/experiment.py:471-485` the image check now fails closed: when no hit is found it
  re-reads the run table and raises `ExperimentRefused` if that read fails. This is correct and
  not a harmful regression: `ensure_tables` creates the table if it is missing, so only a real
  database error refuses, and in that state the publication path could not complete anyway.
  It applies to all three callers (Etsy upload, `gallery_persist.write_frames`,
  `image_production` approve), all publication paths. Residual (INFO): `candidate_gates` and
  `release_gates` still call the fail-open `is_experiment_image` directly, and the
  `disclosed_listing` export still checks only the product; the Etsy upload path is now the
  fail-closed choke point, which is enough.
- **L4 FIXED (narrowed).** `commerce/deliverables.py:419-431` recomputes `retention_plan`
  just before deleting and deletes only digests both plans would prune; a failed re-read
  prunes nothing. A write landing in the few milliseconds between the second plan and the
  delete is still possible; the comment states it and the consequence (re-kept by
  `secure_release`, never a wrong file) is unchanged. Acceptable.
- Tests: `test_w4_integ4_secfixes.py` 10/10 passed.
