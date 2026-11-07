# Independent review: P0-STOREFRONT-ASSET-FIX, `origin/opus2/p0-storefront-asset-fix` @ d8b2754b

- Base: `claude/w6-INTEG1` @ f5c3976d. I reviewed `git diff f5c3976d d8b2754b` in full: 4 files, +220/-3 (`store_foundation/asset_health.py`, `runtime/storefront_ops.py`, `autonomy/autonomy_map.json`, the new test).
- Worktree: `/home/user/bl-runs/wt-rev-storefront`, detached at d8b2754b, left clean. I never committed or pushed.
- Interpreter: `/home/user/bl-runs/venv-integ4/bin/python`, run from `brambleloop/` with `PYTHONPATH=src`. Suites ran one at a time.
- Repro scripts and logs are in `/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/rev_sf/`:
  - `repro_live.py` / `repro_live.log`: a live listing goes through the rebuild chain.
  - `repro_photo.py` / `repro_photo.log`: an owner photograph is overwritten.
  - `repro_race.py` / `repro_race.log`: a duplicate chain runs during a fresh certification.
  - `mut_sf.py` / `mut_sf.log`: mutation testing.

## Verdict: DO NOT SHIP d8b2754b

This branch has the same defect as P0-PORTFOLIO-ACT.
- `route()` enqueues `assets.build` with a new rebuild token (`"asset-health:<hash>"`, `asset_health.py:144`).
- `chain_key` carries that token through every stage (`release.py:63-87`).
- So the rebuild does not stop at the images. It re-drives the whole chain: `pricing.position`, then `listing.seo`, then `launch.plan`, then `marketing.schedule` and `store.publish`.

The listing.seo stage moves a live listing back to local `draft` and overwrites its price. The chain reaches `store.publish` with no owner gate, which re-opens FMBATCH1 F-1 by a second door. Nothing changes on Etsy, because `store.publish` refuses a listing that already has an Etsy id (`pipeline.py:1990`). So the fix never reaches a buyer, and it damages local state.

## Test results (d8b2754b)

| suite | result |
|---|---|
| tests/test_p0_storefront_asset_fix.py | 3/3 OK, "0 failed" |
| tests/test_w4_c3.py | all OK, "0 failed" |
| tests/test_w4_c12_wiring.py | all OK, exit 0 |
| tests/test_v11_autonomy_timeline.py | "PASS: 0 failing"; includes `test_the_committed_map_matches_the_generator` OK |

## Findings

### F1 HIGH: an asset fix turns a live Etsy listing back into a local `draft` and overwrites its price
- **Where:**
  - `store_foundation/asset_health.py:141-145` enqueues the rebuild with `rebuild: asset-health:<token>`.
  - `runtime/release.py:607-609` then has `assets.build` enqueue `pricing.position` under `chain_key("price", ..., token)`. The token is truncated to `asset-health`, which is a new key, so the stage runs again.
  - `release.py:812` (`pricing.position`) enqueues `listing.seo`.
  - `release.py:2096-2098` (`_persist_listing`) sets `row.price_cad = copy.price_cad` and `row.state = "draft"` unconditionally.
- **Repro:** `repro_live.py`
  1. Certify hexagon-coaster-set through the real Worker in SHADOW.
  2. Set its Listing to `state="published"`, `etsy_listing_id="1234567"` and `price_cad=12.34`, standing for a later repricing.
  3. Give the hero a recorded 1000x1000 claim, which raises ASSET_LOW_RESOLUTION.
  4. Run `storefront.review`.
- **Result:**
  - Jobs 14-19 run `assets.build`, `pricing.position`, `listing.seo`, `launch.plan`, `marketing.schedule` and `store.publish` (DEAD in SHADOW).
  - The final line is `listing after: draft 1234567 price 4.0`.
- **Effect:**
  - Every reader of the live state now treats the listing as not live. That includes readiness, the catalogue, `days_live` and portfolio exposure, as in the portfolio review's F1.
  - Any later repricing is reverted. The price is recomputed, not taken from stale inputs, but it still overwrites the live price.

### F2 HIGH: an autonomous internal signal drives the chain to `store.publish` (a second regression of FMBATCH1 F-1)
- **Where:** `asset_health.py:144`, then `release.py:1422` (`launch.plan`), then `release.py:2254-2258` (`marketing.schedule` and `store.publish`).
- **History:** `integrations/taxonomy_drift.py:48-53` records that an autonomous re-queue carrying a rebuild token to `store.publish` is OFF unless the owner opts in. This branch has no gate, no env switch and no owner card.
- **Repro:** `repro_live.log`: `job 19 store.publish dead key=publish:hexagon-coaster-set:1.2.1:83b5db1f2cb4:asset-health:c8 err=capability not enabled ... SHADOW`. That is one DEAD job per rebuilt release, which is noise for dead-job monitoring.
- **Past SHADOW:** the only thing preventing a second Etsy listing is the `if already:` check at `pipeline.py:1990`. Images that were "fixed" are never pushed to the live listing, so the rebuild is buyer-invisible by construction.

### F3 MEDIUM-HIGH: a second, full chain is enqueued while a fresh certification's own chain is still in flight
- **Where:**
  - `asset_health.py:123` and `:127` treat "certified, no approved hero yet" as HERO_MISSING.
  - Every fresh certification is in that state until its own `assets.build` (`assets:<slug>:<ver>:<rel>:c8`) has run.
  - The `asset-fix:` key at `:145` does not dedupe against the normal chain key.
- **Repro:** `repro_race.py`
  1. Run `gate.certify` only.
  2. Run `storefront.review`.
  3. Drain the queue.
- **Result:** two chains run for one release:
  - `assets.build` x2 (jobs 5 and 6), `pricing.position` x2 and `listing.seo` x2;
  - `launch.plan` x2 and `marketing.schedule` x2, so marketing drafts are duplicated;
  - `store.publish` x2 (jobs 15 and 19).
- **Past SHADOW:** two `store.publish` jobs run for a listing that is not yet published. Only the `already` check, which reads the id after the first publish has committed, keeps this from becoming two Etsy listings.
- **Required:** skip any slug whose current release has a queued, running or recently failed normal `assets.build`.

### F4 MEDIUM: the rebuild overwrites an owner photograph in the listing gallery
- **Where:**
  - `release.py:2639-2655` (`_persist_frames`) writes each rendered frame by position and overwrites whatever row holds that position.
  - `publish/physical_upgrade.py:167-181` inserts the owner's PHYSICAL_PRODUCT_PHOTO first and renumbers the renders behind it.
  - `visual/gallery_persist.py:126` states the opposite contract: "a certified frame is never overwritten".
  - This branch makes that overwrite reachable from an autonomous daily review.
- **Repro:** `repro_photo.py`. Place the owner photo at position 1, with the renders at 2-7, plus the low-res trigger. Run `storefront.review`.
  - Before: `(1, 'PHYSICAL_PRODUCT_PHOTO', 'hero', 'OWNERPHOTO')`.
  - After: `(1, 'DIGITAL_TWIN_RENDER', 'hero', ...)` and a duplicate chart at positions 6 and 7. The photograph row is gone.
- **Laura's canonical identity files:** untouched. `assets.build` stores only under `<slug>/<version>/...`, and `visual.image_production` is deduped per slug@version@release, so it does not run again.
- **Gallery rows:** AI or Laura gallery `ListingAsset` rows are only safe when their positions do not collide with the render positions.

### F5 LOW: ASSET_LOW_RESOLUTION is unreachable for real listing assets, and the rebuild clears it by erasing the evidence
- **Where:** `asset_health.py` (base) reads `claims.width_px`/`height_px`. No production writer of `ListingAsset` sets them (`grep width_px`). `_persist_frames` (`release.py:2650`) replaces `claims` without them.
- **Effect:**
  - The code only fires on fixtures.
  - When it does fire, the rebuild "fixes" it by deleting the measured claim, not by verifying the new resolution.
  - A rebuild from the same release can also reproduce the same block (HERO_MISSING caused by a veto or gate). It is deduped once per release, so the cost is bounded but the work is futile.

### F6 LOW: owner cards are deduped, but they are never closed and they re-open after "done"
- **Where:** `asset_health.py:150-161`, using `owner_queue.ensure` (`ops/owner_queue.py:172-208`).
- **What works:**
  - The key is `storefront.asset:<code>:<subject>`, which is stable, so a rerun does not add a second open card. Verified by the test and by reading `ensure`.
  - Each card carries `max_cost_cad=0.0`, `minutes=10` and a consequence.
- **Problems:**
  - Nothing closes a card when its finding clears. Once the icon is added, the card stays open.
  - If the owner marks a card done while the finding persists (a stale reading, or a deliberate "no icon"), the next review opens a new card. This repeats every review.
  - The action text is the finding's `why` ("Fix the storefront asset shop_icon: the live shop has no icon (owner step in Shop Manager; no API)"). It does not name the exact upload: Shop Manager, then Settings, then the shop icon, with the required size. That is borderline against the "exact action" rule.

### F7 LOW: test gaps (mutation testing, `mut_sf.py`: 10 mutants run, 3 killed)
- **Killed:**
  - ASSET_BLOCKED added to REBUILD_CODES;
  - token from the version only;
  - wrong agent.
- **Survived:**
  - **An unrelated keyless owner row** (the author's own survivor). It still survives. `_cards()` filters `LIKE 'storefront.asset:%'`, and no test pins the full OwnerAction set.
  - **An extra keyed owner row** (`storefront.extra:x`). Survives for the same reason.
  - **The `state != "UNKNOWN"` guard removed** (`storefront_ops.py:49`). No test routes an unreadable health check.
  - **The card's `max_cost_cad`/`minutes` dropped**, and separately **the consequence dropped**. No test asserts the card's content.
  - **Held brand-mark routing removed.** No test exercises a `storefront_director` fix from `brand.asset_consistency`.
  - **`rebuild` token removed.** No test runs the enqueued `assets.build`, which is how F1-F4 escaped.
- **Not run:** the 11th mutant (version not current) did not apply. Its pattern did not match the source, so it was never tested. The assertion `old.inputs["version"] == "2.0.0"` should cover that case.

## Answers to the brief

- **Live listings altered?** Yes, locally: `state` goes to `draft` and the price is overwritten (F1), and an owner photo frame is overwritten (F4). Etsy itself is not written.
- **Reaches `store.publish` or an Etsy write?** It reaches `store.publish` with no owner gate (F2). It does so twice on a fresh certification (F3). There is no Etsy network write in SHADOW; past SHADOW it depends solely on `if already:`.
- **Stale inputs?** The `assets.build` inputs are fresh: the current certified version and `release_hash` from `certified_releases`. Downstream, the price is recomputed but clobbers a later repricing (F1). The wider stale-input issue in the portfolio review's F3 does not apply here.
- **Spend:**
  - No new paid path. `visual.image_production` is keyed per release, so it is not re-triggered, and it stays behind the `image_generation` gate and its caps.
  - Vision calls happen only if `image_vision` is open: in `_review_frames` (`release.py:1671`) and in `listing.seo`'s exported review, under the existing gateway ceilings.
  - The disclosed hero review is reused, because the CIR fingerprint is the same.
  - With vision open, one rebuild costs one more vision pass per release, and two when F3's duplicate chain also runs.
- **Per-release-hash dedup:** correct. The key is `asset-fix:<slug>:<release_hash[:16]>`; a rerun does nothing and a new release rebuilds. The edges:
  - it does not dedupe against the normal chain (F3);
  - with an empty `release_hash` it falls back to the version;
  - downstream `chain_key` truncates the token to the constant `asset-health`. That is harmless only because `release[:12]` is also in the key.
- **Owner cards:** they carry cost, minutes and a consequence, and they are deduped while open. They never close and they re-open after done (F6).
- **Laura's canonical assets:** the canonical identity files are untouched. The gallery overwrite risk is in F4.
- **`autonomy_map.json`:** generated by the tool. `python -m brambleloop.autonomy.map --write <tmp>` is identical to the committed file apart from `generated_at`, and the committed-map test passes.
- **Is the exact owner-row set pinned?** No (F7). Both the keyless and the keyed extra-row mutants survive.

## Required before SHIP

1. Do not let an asset-health rebuild re-drive the chain past the images. Either:
   - run the image rebuild with no rebuild token, so downstream keys dedupe against the original chain; or
   - stop it after `_persist_frames`.

   For a live listing, raise an owner card to push the new images to Etsy, following the taxonomy_drift pattern. Alternatively, put the whole re-drive behind an opt-in switch that defaults OFF.
2. Skip slugs whose normal `assets.build` for the current release is queued, running or not yet done (F3).
3. Do not overwrite a PHYSICAL_PRODUCT_PHOTO, or any non-render row, in `_persist_frames` on a rebuild (F4). Alternatively, refuse the rebuild when such rows exist.
4. Close `storefront.asset:*` cards when their finding clears, and do not re-open a done card unless the evidence changes (F6).
5. Add tests:
   - drain the enqueued `assets.build` on a `published` listing and assert its state, price, photo row and that no `store.publish` is reached;
   - pin the full OwnerAction set and the card's fields;
   - cover the UNKNOWN guard and a held brand-mark card.
