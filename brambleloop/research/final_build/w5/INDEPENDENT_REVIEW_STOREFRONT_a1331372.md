# Independent review: P0-STOREFRONT-ASSET-FIX on fix-only, `origin/opus2/p0-storefront-asset-fix-fo` @ a1331372

## Scope
- **Diff reviewed:** `git diff 0f2de815 a1331372`, in full. It touches 4 files, +713/-4:
  - `store_foundation/asset_health.py` (+233);
  - `runtime/storefront_ops.py` (+9);
  - `autonomy/autonomy_map.json`;
  - `tests/test_p0_storefront_asset_fix.py` (+467).
- **Branch:** found with `git branch -r --contains a1331372`, which returns `origin/opus2/p0-storefront-asset-fix-fo`.
- **Trial merge:** onto `origin/claude/w6-INTEG1` @ 5913931f, in the throwaway worktree `/home/user/bl-runs/wt-rv-sf`. The merge was aborted and the worktree removed and pruned afterwards.
- **What I did not do:** no commits, no pushes, no `pkill`, no `git stash`.
- **Interpreter:** `/home/user/bl-runs/venv-integ4/bin/python`, run from `brambleloop/` with `PYTHONPATH=src:tests`.
- **Logs and repro scripts:** `/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/rv_sf2/`. The files are `repro_strand.py`, `repro_A.log`, `repro_B.log`, `repro_live.py`, `repro_live_ok.log`, `repro_live_block.log`, `mut.py`, `mut_results.log`, `mut/m*.log` and one `<suite>.log` per suite.

## Verdict: DO NOT SHIP (one HIGH, two MEDIUM)

The safety half is now sound:
- The rebuild uses the fix-only primitive.
- No live listing's state, price, Etsy id or copy changes.
- Nothing reaches `launch.plan`, `marketing.schedule` or `store.publish`.
- `store.update` is not touched.
- There is no paid path and no Etsy write.

The liveness half is broken. A release whose own `assets.build` **blocked** counts as "finished" (`asset_health.py:176` checks `status != DONE` only). So the storefront review sends that release through a fix-only rebuild, and the release's ordinary chain then never reaches `launch.plan` (H1). Two further problems:
- The live-listing image card goes to the owner before the rebuild's gates have run, and it is never withdrawn when they refuse (M1).
- A live listing's local gallery is rewritten and its finding clears, though Etsy still shows the old images (M2).

## Prior findings (STOREFRONT d8b2754b) at a1331372

I found no committed report for 1675bf23 on any remote branch (searched every remote for `*REVIEW*STOREFRONT*`). Only the d8b2754b report exists, at `origin/claude/w4-INTEG8-next:brambleloop/research/final_build/w5/INDEPENDENT_REVIEW_STOREFRONT_d8b2754b.md`.

| # | Prior finding | Status at a1331372 | Evidence |
|---|---|---|---|
| F1 HIGH | A live listing goes back to draft and its price is overwritten | **FIXED** | `fix_only: True` is in the rebuild inputs (`asset_health.py:257-261`). `repro_live_ok.log` shows a listing at `published`/`1234567`/`12.34` unchanged after the rebuild. Mutant M1 is killed. |
| F2 HIGH | The chain reaches `store.publish` | **FIXED** | `listing.seo` stops before `launch.plan` under fix_only. The test asserts no downstream job carries the token or the flag, and M1 is killed. |
| F3 MED-HIGH | A duplicate chain runs during a fresh certification | **FIXED for in-flight chains**, but there is a **new hole** for a *blocked* chain (H1) | `_chain_in_flight` (`asset_health.py:158-183`). M3, M12 and M15 are killed. |
| F4 MED | An owner photograph is overwritten | **FIXED (refused)** | `_foreign_frames` skips any gallery holding a non-render class. M4 is killed. |
| F5 LOW | LOW_RESOLUTION is unreachable and the rebuild erases the evidence | **FIXED** | It is no longer a rebuild code; it is reported `not_routed` with `LOW_RES_WHY`. |
| F6 LOW | Cards never close and re-open after done; the action text is vague | **FIXED** | Cards auto-close only on a measured reading (M7 and M13 killed). A card the owner closed is held until the evidence hash changes (M8 killed). The icon action is now exact (Shop Manager > Settings > Info & Appearance, 500x500). |
| F7 LOW | Test gaps | **Largely FIXED** | 16 of 18 mutants are killed (table below). The full owner-row set is pinned in the live test. |
| Fix-only R4 LOW | The copy card says the candidate "passed the listing gates", but the disclosure and terms checks are not run | **STILL OPEN; not touched by this branch** | `release.py:2184` (INTEG1). This branch does not edit that text, but its photo card now tells the owner to apply that copy card in the same edit (`asset_health.py:278`). R4 therefore now reaches the owner on every asset fix of a live listing. |

## Findings

### H1 HIGH: an asset fix on a release whose images blocked strands that product's launch path
- **Where:**
  - `asset_health.py:174-177`. `_chain_in_flight` treats a `DONE` `assets.build` as finished. A blocked build is `DONE` with `outputs.ok == False`, and so are its unapproved frames.
  - `chain_successors.py:198`. `_stage_succeeded` resolves the dead end on any successful `assets.build` with the same slug, version and release, including a fix-only one.
  - `chain_successors.py:85` with `incident_lifecycle.py:76`. A restate refreshes `detail.inputs` from whichever job refused, and keeps `fix_only`.
- **Scenario A (`repro_A.log`):**
  1. A fresh, never-launched release is certified, and its own `assets.build` blocks (job 5, `ok=False`). The chain-successors dead end is opened.
  2. The cause clears, for example a renderer fix.
  3. The storefront review sees HERO_MISSING and enqueues `asset-fix:` (job 7). That runs `pricing.position` and `listing.seo` with `fix_only`, and the fix-only stage creates the first local draft at 7.50.
  4. The sweep under a new commit then **resolves** the dead end, because the fix-only build "succeeded".
  5. Result: `ordinary launch.plan jobs: []`. Nothing will ever plan, schedule or launch this product, and no incident or owner card says so. `test_flow_health_does_not_read_a_fix_only_stop_as_a_stall` deliberately hides fix-only stops from flow health.
- **Scenario B (`repro_B.log`):**
  1. The cause persists through the asset fix (job 7 blocks again).
  2. The dead end's stored inputs become `fix_only: True`. Before the review, the stored-inputs flag read False; after it, True.
  3. Under the next commit, the sweep re-drives `assets.build` with `fix_only` (job 8), then `pricing.position` and `listing.seo`, and stops. Again `launch.plan` never runs.
  4. The remediation's bound has leaked into an ordinary re-drive: the re-drive path skipped `without_fix_only`. The leak is in the safe direction, but it permanently prevents the launch.
- **Before this branch:** the dead end would have re-driven the ordinary chain under the next deploy and launched normally.
- **Fix:**
  - In `_chain_in_flight`, treat the release's own `assets` (or `listing`) job as unfinished when it is `DONE` but `outputs.ok is False`, or when it has no downstream `price` key. Report it `not_routed` with "the release's own build was blocked; chain.successors owns it".
  - Optionally, make `chain_successors.record` refuse to overwrite an ordinary dead end's inputs with fix-only inputs.
  - Make `_stage_succeeded` ignore fix-only successes.

### M1 MEDIUM: the live-image owner card is raised before the rebuild runs and is never withdrawn when the gates refuse the images
- **Where:** `asset_health.py:265-288`. The card goes up immediately after `ctx.enqueue`, worded "When assets.build job N … is done (audit assets.listing_images_built), replace the photos of live Etsy listing …".
- **Scenario (`repro_live_block.log`):**
  1. The fix build runs and blocks (job 15, `ok=False`). Every frame is now `blocked_reasons=['FORCED_PLAN_BLOCK…']`.
  2. The `storefront.live_images:` card stays **open** with no change. The job *is* done, and the owner is invited to upload images the gates refused as misrepresenting the pattern.
  3. The second review reports `already_queued=1` and seven ASSET_BLOCKED `not_routed`. The card stays open indefinitely.
- **Contract gap:** this contradicts the fix-only contract the copy card follows: a refused candidate is never put to the owner, and a refusal withdraws an open card (review 9e8665c3 N2 and a5781649 R1).
- **No bound to one exact output:** the card does not name a frame sha, only "the rebuilt frames, in their order".
- **Fix:** raise the card from the fix build's outcome, not at enqueue. Alternatively, close the card as WITHDRAWN on the next review when the `asset-fix` job's outputs are `ok=False`. Name the hero sha (or the frame shas) the card offers.

### M2 MEDIUM: a live listing's local gallery is rewritten, so the finding self-clears while Etsy is unchanged
- **Where:**
  - `release.py` `_persist_frames` runs unconditionally under fix_only (INTEG1, around line 2789). It sets `approved=True` and replaces the sha and claims on the live listing's ListingAsset rows.
  - The branch's own test asserts the result (`hero restored`, `test_p0_storefront_asset_fix.py:445`).
- **Scenario (`repro_live_ok.log`):**
  - Review 1 rebuilds; review 2 reports `queued=0`, with HERO_MISSING gone.
  - F-527 now reads the live listing as healthy, though nothing reached Etsy. The only remaining signal is an open owner card that nothing verifies or closes.
  - In the blocked variant (M1), the opposite happens: a live listing's locally approved frames all become blocked.
- **Inconsistency:** the fix-only primitive's own rule for `_persist_listing` is that a live listing's local row never changes, "because the local row would then misdescribe what buyers see". The gallery rows break that rule.
- **Fix:** under fix_only on a live listing, write the rebuilt frames as a candidate set (audit plus stored files), not over the live rows. Keep the finding open until the owner's card is done.

### L1 LOW: the copy card raised by an image fix gives a false reason
- An asset fix on a live listing also drives `listing.seo` through `_fix_only_candidate`. That raises `listing.live_update:<slug>@<version>` with the reason "a remediation found this live listing's search copy weak" (`release.py` around line 2190).
- The copy was not judged weak; the trigger was images. The owner is asked to compare copy that is usually byte-identical to the live copy.
- The photo card hard-links to this card ("do both in the same Shop Manager edit"). When the copy candidate is refused, that card is WITHDRAWN and the photo card's reference dangles.
- **Fix:** either do not run the copy stage for an image-only fix, or have the photo card's text depend on whether the copy card is open.

### L2 LOW: test gaps (2 survivors)
- **M16** (FAILED no longer treated as in flight) survives. No test has a retrying (FAILED) own-chain job.
- **M18** (ICON_UNREAD routed as an owner card) survives. No test runs an UNKNOWN icon reading through `route()` and asserts that no card is raised. Today that would ask the owner to upload an icon that may already exist, which breaks the "UNKNOWN is never PASS or FAIL" rule.
- No test covers a **blocked** own chain (H1) or a **blocked** fix build on a live listing (M1).

### L3 LOW / informational: idempotency and keys
- `asset-fix:<slug>:<release_hash[:16]>` is correct: a rerun does nothing and a new release rebuilds (M9 and M10 killed).
- `chain_key` truncates the token to the constant `asset-health`. That is safe only because `release[:12]` is in every downstream key, and the asset-fix key allows one fix per release.
- The asset-fix key has no `CHAIN_VERSION`, so a chain-version bump never re-fixes the same release. That is acceptable.
- **Pre-existing, not this branch:** `chain_successors.sweep` uses `rebuild: deadend:{commit[:12]}`, and `chain_key` truncates it to the constant `deadend:dead`. A second dead-end re-drive under a later commit therefore collides on the downstream `price:`, `seo:` and `launch:` keys. This is visible in `repro_B.log` (`price:…:deadend:dead:c8`). Worth its own ticket.

## Spend, autonomy and determinism checks

| Check | Result |
|---|---|
| Which assets, how detected | HERO_MISSING and ASSETS_STALE trigger a re-render. ICON_MISSING and held brand-mark `storefront_director` fixes get owner cards. ASSET_BLOCKED, LOW_RESOLUTION and the UNKNOWN icon codes are `not_routed` with a reason. Detection is deterministic DB reads: there are no LLM calls in `check` or `route`, and the evidence hash is a sha256 of code, subject and why. |
| Autonomous change to the live listing on Etsy or to shop settings | None. `store.update` is not touched, there are no Etsy writes, and there is no `store.publish`. Locally, the live listing's state, price, id and copy are unchanged. The **gallery rows** of a live listing are rewritten (M2). |
| Paid image generation | `visual.image_production.trigger` is reached only from a successful fix build, once per slug@version@release (its own idempotency key), behind the V0 paid-provider gate. `test_w5_v0_paid_provider_gate` gives 52/52. Vision review runs only if `image_vision` is open, which costs at most one extra pass per release. |
| Owner cards: cost, minutes and consequence | Present on all of them: live images CA$0 / 15 min / "keeps showing its current images"; icon and brand CA$0 / 10 min / "keeps showing the asset as it is". The live card is pinned by test (M5, M6, M14 and M17 killed). The live card is raised too early (M1). |
| UNKNOWN never PASS | An unreadable health check routes and closes nothing (M2 killed). Stale or unread icon readings never close a card (M7 killed). An unread brand sweep never closes one (M13 killed). |
| pytest imports | None in the new test or the four named suites. All run as plain scripts. |
| autonomy_map.json | `test_the_committed_map_matches_the_generator` OK on the trial merge. |

## Merge
- **Onto `origin/claude/w6-INTEG1` @ 5913931f:** clean auto-merge, no conflicts.
- **Against portfolio `ee5dbeee` (`origin/opus2/p0-portfolio-act-fo`):** `git merge-tree` shows a conflict **only** in the generated `autonomy/autonomy_map.json` (`generated_at` and the `follow_on_edges` count, 86 vs 90).
  - There is no source overlap: portfolio touches `growth/portfolio_act.py` and `runtime/pipeline.py`.
  - Whichever lands second must regenerate the map with `python -m brambleloop.autonomy.map --write`, not hand-merge it.

## Tests (trial merge on INTEG1, run one at a time)

| Suite | Result | Time |
|---|---|---|
| tests/test_p0_storefront_asset_fix.py | rc=0, "0 failed" (13 tests) | 244s |
| tests/test_w6_fix_only_rebuild.py | rc=0, "0 failure(s)" | 914s |
| tests/test_w5_v0_paid_provider_gate.py | rc=0, 52/52 passed | 232s |
| tests/test_cert_rebuild_chain.py | rc=0, "PASS: 0 failing" | 562s |
| tests/test_w4_c3.py | rc=0, "0 failed" | 19s |
| tests/test_v11_autonomy_timeline.py | rc=0, "PASS: 0 failing" (committed map matches the generator) | 235s |

Repro results:

| Repro | Result |
|---|---|
| repro_strand.py A | H1 confirmed: dead end resolved by the fix-only success; `ordinary launch.plan jobs: []` |
| repro_strand.py B | H1 confirmed: dead end inputs gain `fix_only`; the re-drive stops before launch |
| repro_live.py ok | F1, F2 and F4 fixes hold; M2 confirmed (finding self-clears, card open) |
| repro_live.py block | M1 confirmed: the card stays open over gate-refused frames |

## Mutants (against test_p0_storefront_asset_fix.py): 18 run, 16 killed, 2 survived

| # | Mutant | Result |
|---|---|---|
| M1 | `fix_only` dropped from the rebuild inputs | KILLED |
| M2 | UNKNOWN guard removed (`storefront_ops.py:50`) | KILLED |
| M3 | `_chain_in_flight` disabled | KILLED |
| M4 | `_foreign_frames` disabled | KILLED |
| M5 | live-image card never raised | KILLED |
| M6 | live card minutes 15 -> 5 | KILLED |
| M7 | icon card closes on a stale reading | KILLED |
| M8 | owner-closed card always re-opened | KILLED |
| M9 | rebuild idempotency key made unique per run | KILLED |
| M10 | token from version only | KILLED |
| M11 | ASSET_BLOCKED added to REBUILD_CODES | KILLED |
| M12 | withheld-draft clause removed | KILLED |
| M13 | brand card closes on an unread sweep | KILLED |
| M14 | live card drops the copy-card pairing | KILLED |
| M15 | per-slug in-flight loop removed | KILLED |
| M16 | FAILED not treated as in flight | **SURVIVED** |
| M17 | icon card consequence emptied | KILLED |
| M18 | ICON_UNREAD routed as an owner card | **SURVIVED** |

## Required before SHIP
1. **H1:** do not route a release whose own `assets.build` or `listing.draft` is `DONE` with `ok=False` (leave it to chain.successors). Make `_stage_succeeded` ignore fix-only successes. Do not let a fix-only refusal overwrite an ordinary dead end's inputs. Add a test of a blocked own chain that asserts the ordinary `launch.plan` still runs after the cause clears.
2. **M1:** raise or keep the live-image card only after the fix build passed its gates, name the frame shas it offers, and withdraw it when the build is refused. Add a test.
3. **M2:** do not rewrite a live listing's ListingAsset rows under fix_only. Store a candidate set and keep the finding open until the owner acts.
4. **L1 and R4:** fix the copy card's reason and gates claim, or do not raise a copy card for an image-only fix.
5. **L2:** add tests that kill M16 and M18.
