# IMAGE-BF — Laura gallery approval path (finding B) and the first-customer `imagery` gate on a generated gallery (finding F)

Branch `eng/image-bf`. It was cut from `claude/batch19c` (9757c1d) and merges `origin/eng/image-e2e`
(45a012be). The only merge conflict was BUILD_STATE, and both entries were kept.
- NOT merged and NOT deployed. Production is unchanged.
- Nothing ran against production, BFL, OpenAI or Etsy.
- No Railway variable was read.
- Laura (laura-r2-a42aeac7) is locked. Nothing here modifies, regenerates or substitutes her.
  Nothing approves her publication automatically.

Decisions: D-IMAGE-BF-LAURA and D-IMAGE-BF-IMAGERY (DECISION_LOG).

## B. A production approval path for Laura galleries

**Before:** `canonical.PUBLICATION_APPROVED` was an empty constant and the only approval source.
Every Laura frame therefore read `laura_publication` UNMEASURED, so no Laura gallery could be
certified.

**Now:** `visual/laura_approval.py`, plus a table `laura_gallery_approvals` in `visual/image_records.py`.

1. **One card per gallery.** `image_production._certify_route` calls `laura_approval.raise_card`
   when `certify_gallery` refuses.
   - "Verified" means the real gallery status has blockers, and the same gallery re-read with a
     review-only `review_only_assume_laura_approved` flag has none. That re-read is never
     certified or written; it only decides whether to raise the card.
   - The IMAGE-E2E probe showed why this approach is needed: the Laura frames' `exception_route`
     blocker says "publication_gates is FAIL" without naming Laura, so the decision cannot be
     made by reading blocker text.
   - The card is an OwnerAction with key `laura_gallery_review:<sha(run)[:16]>:<frame-set digest[:16]>`.
     Its `laura_gallery.card_raised` audit row lists every Laura frame: position, role,
     candidate id, sha256 and the `/api/cc/images/candidates/<id>/image` URL.
   - A key that was ever raised, open or answered, is never raised again.
2. **Owner step-up.** There are two ways to decide:
   - `POST /api/cc/laura-gallery/decide`. It needs an owner session, CSRF + nonce and a fresh
     `auth.require_stepup` (passphrase + TOTP).
   - "Approve all eligible". `approve_all.judge` marks the prefix eligible explicitly, before the
     classifier and the key guard. The preview carries the frames, and the MC view renders them
     as thumbnails. The execute step decides through `laura_approval._decide_in` in a savepoint,
     never as a bare close.

   `decide` also refuses:
   - a non-`owner:` actor;
   - a call that does not pass `step_up=True`;
   - an answered card;
   - a gallery whose Laura frame digest changed since the card was raised.
3. **Recorded per gallery and frame hash.** `laura_publication` reads through
   `laura_approval.publication_status` in `gallery_persist.frame_matrix`,
   `candidate_gates.publication_verdict` and `release_gates.generated_frame_verdict`.
   - It reads PASS when the canonical registry approves the frame, or when the latest decision
     for exactly that (run, sha256) pair is an owner `approved` made with step-up.
   - Anything else reads UNMEASURED. A rejection is recorded and leaves the frames UNMEASURED.
4. **Audited.** Every decision writes:
   - `laura_gallery.card_raised`;
   - `laura_gallery.decision` (actor, via, step-up, session, frames, note);
   - the `owner_action.lifecycle` row;
   - the route's `auth.record` action, or approve-all's per-row and batch rows.
5. **After approval**, the gallery is certified again immediately (`certify_gallery`) and
   `listing.package` is enqueued, exactly as the worker's stage does it.

## F. First-customer `imagery` accepts a certified complete generated gallery

`gates.first_customer.disclosed_imagery` now asks `generated_gallery_imagery` first. If the
current valid certificate carries `generated_render` frames, the area reads PASS only when all of
these hold:
- the certificate is bound to the release's certified hash;
- it has at least `CAMPAIGN_MIN_FRAMES` frames. Fewer reads "gallery incomplete";
- each generated frame is the selected gallery frame on file and re-judges as exportable now
  (`generated_frame_verdict`: truth, identity, Laura approval, provenance, the route's exception);
- each generated frame carries its AI-concept honesty label and alt text;
- the single other frame is the CONTENTS preview, re-verified on its bytes.

Any other certificate goes down the disclosed-set path unchanged.

## Tests — `tests/test_image_bf.py` (9)

The fixture is the IMAGE-E2E production-like DB with the real Worker, unaided, without the Laura
double. The doubles are the same labelled BFL transport and judge doubles. API calls go through the
real app with a real passphrase + TOTP login.

1. One card per gallery:
   - the worker's run raises exactly one card, with the lifestyle and size Laura frames and their
     image URLs;
   - `raise_card`, `_certify_route` and `certify_gallery` all run again and add nothing.
2. A gallery that fails a real gate raises no card.
3. The step-up is required:
   - with an expired step-up, both doors return 403 STEP_UP_REQUIRED;
   - a wrong TOTP is not a step-up;
   - `decide(step_up=False)` and a non-owner actor are refused;
   - nothing moves and nothing is audited.
4. **Mutation:** with `auth.require_stepup` replaced by a no-op, test 3's body fails, so the
   mutant is killed.
5. Approval covers exactly the approved hashes:
   - the route approval writes rows for exactly the gallery's Laura (run, sha) pairs;
   - the same sha under another run, a foreign sha, and earlier-attempt Laura bytes all read
     UNMEASURED;
   - the gallery then certifies with 7 frames;
   - the decision and lifecycle rows are audited;
   - a second decision gets 409, and no second card is raised.
6. A 7-frame certified gallery passes `imagery` (and `check_imagery`). A 6-frame valid certificate
   FAILs it with "gallery incomplete".
7. Truth and disclosure still bite:
   - a stripped honesty label FAILs;
   - a frame that no longer re-judges as exportable FAILs;
   - an uncertified Laura gallery falls back to the disclosed path.
8. "Approve all eligible" shows the frames, approves them with its step-up and certifies the
   gallery. The rows are `via=approve_all`, with one per-row audit.
9. A rejection is recorded. Laura stays UNMEASURED, there is no certificate and there is no
   second card.

## Results
Both runs used `run_tests.sh` with `JOBS=4 SUITE_REGISTRY=0` in a py3.13 venv built from
`requirements.lock` and `requirements-test.lock`.

**Run 1: `20261121T020425Z-1855`.** Commit a4b87a1, clean tree, 22 suites. Result: **335 passing,
2 suites failing.**
- Passed: test_image_bf, test_image_e2e_worker, test_owner_gallery_complete,
  test_mission_control2 (13/0), test_eng_approvals (34/0), test_first_customer_gate (12/0),
  test_canon_manifest, test_canon_store_brand_face, test_w3_b2_canonical_assets,
  test_w3_k12_model_photography, test_w3_wire4, test_opus2_laura_home,
  test_w3_laura_{memory_canonical,cc_integration,core_identity,presence},
  test_v11_pwa_static (87/0), test_compiler, test_reverse and test_twin.
- Failed: test_vacuity. It flagged a loop in test_image_bf test 5 that could run over an empty
  list. Fixed in daae8a2: the loop now always includes one extra record carrying unapproved
  bytes, and asserts the list is not empty.
- Failed: test_vis_gallery_e2e test_10, test_12 and test_13. These are **pre-existing**: they
  fail identically on this branch's merge base (the merge commit before any IMAGE-BF change,
  run in a separate worktree). They are the same three IMAGE-E2E recorded on 8204c93:
  `etsy_remote_state` no longer carries `publish_time`. Not caused by this branch and not fixed.

**Run 2: `20261121T023021Z-4118`.** Commit daae8a2, clean tree. Suites test_image_bf,
test_vacuity and test_image_e2e_worker. Result: **24 passing, 0 failing.** IMAGE-E2E test 2 now
asserts that the `imagery: FAIL` blocker is gone from the refreshed package.

**Mutation testing.** test_image_bf test 4 makes `auth.require_stepup` a no-op, and the step-up
test then fails, so the mutant is killed. Truth and disclosure tampers are covered by test 7.
The 6-frame tamper is covered by test 6.

## Open
- **Not on production.** No production gallery exists yet. The first real card appears only
  after the worker has produced a verified Laura gallery with real FLUX output and the real
  vision judges.
- **Owner action, when that card appears.** Review the frames in Mission Control → Approvals and
  approve or reject them. This costs CA$0 and takes about 3 minutes. Until then, that listing's
  gallery stays uncertified (D-OWNER-GALLERY-COMPLETE).
- **Static bundle.** It is now 399,984 of 400,000 bytes (16 B headroom). Two comments were
  shortened to make room for the frame thumbnails.
- **Not fixed here:** IMAGE-E2E findings A (vessel side view), C, D (PDFs do not embed the
  gallery under `PDF_LAYOUT="engine"`) and E.
