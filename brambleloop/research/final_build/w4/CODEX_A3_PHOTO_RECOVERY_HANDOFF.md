# A3 photo-gallery continuation — review requested

Source branch: `opus2/p0-photo-asset-review`, exact base `c21749471d000c0baf0c83e5530f7d6a59e89700`. Independent A3F review reported that a terminally excluded first photograph could block a different qualifying photo from leading forever, and a position-one photo without the leader flag could churn.

This continuation preserves the existing attestation, byte-hash and independent owner holds. The sweep rechecks every approved physical photo, holds them when evidence is missing or a claim fails, and can promote a qualifying already-approved supplement when the current leader has been excluded; it reviews the new leader after the reorder. Excluded photographs move after effective frames, so the listing set keeps contiguous positions. A position-one qualifying photo missing its leader flag is re-marked for review; moving a photo never clears other reasons such as an owner veto. Unknown qualification is not a promotion.

Python 3.11: `test_opus2_photo_asset_review.py` passed 27/27, including real database recovery from an excluded leader, position-one recovery without repeated work, preservation of an owner veto, and an independently identified withdrawn-photo case through re-attestation, revoked/unknown evidence, unsupported claims and truthful work counts. `test_physfix_photo_first.py` passed 8/8. Physical-upgrade, listing and release regressions are listed in the review PR. No photo, publication, deployment, or external provider was touched.

This is a stacked continuation, not independent acceptance. A newly excluded non-leading photo can leave a position gap, which holds the listing until reordered. Existing A3F-3 unlocked-writer race and PostgreSQL advisory-lock testing remain unresolved. Qualification checks also read evidence through independent sessions; concurrent PostgreSQL evidence writers need review. The decision and downstream gallery boundaries need independent review; a second full system integration/production verification has not run.

The photo hold and listing-set certificate invalidation now commit together, so a
failed subsequent recertification cannot leave an older certificate valid. The independently
reproduced issuance race remains open: a concurrent issuer can insert a fresh certificate
from a stale photo snapshot after that invalidation. This branch is DO NOT INTEGRATE until
issuance and evidence writers share an independently reviewed fence.
