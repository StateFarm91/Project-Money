# Learn malformed-input repair handoff
Base5d543ba; implementation610a8ad; branchcodex/final-learn-input-01. Scope ca6bad9. Only production change is learn/service.py validation; no API/router/curriculum/gate/status edits.

Authenticated PUT /api/learn/lessons/{slug} -> source-backed topic check -> save_lesson -> validate_spec now explicitly rejects non-object specs, malformed scalar/topic/assumption fields, non-list asset/step collections, non-object entries and malformed text fields. save_lesson raises ValueError before opening its write transaction, mapped by existing API to422. No broad exception swallowing. Existing semantic count, terminology, provenance, review, digest and independent-author rules remain.

A refused update preserves Lesson spec/revision/reviews/state. Existing approved_lesson/help_links consumers therefore retain the prior unchanged reviewed revision. A valid changed draft still invalidates its old review and withholds public/PDF consumption. Authentication, approval and source premises in new direct-endpoint controls are explicitly isolated fixtures, not proof of lesson truth.

Source-bound local results on610a8ad, unchanged source fingerprint:
- test_learn_launch:13/13, receipt20260928T162543062585Z (clean tree before).
- test_learn_publish_contract:3/3, receipt20260928T162554693651Z (only prior evidence files untracked).
- test_learn_input_shapes:3/3, receipt20260928T162619596066Z (only prior evidence files untracked).
All use bundled Python/runtime-build2/Poppler DejaVuSans; dependency lock not verified; release_eligible=false. No external calls, production state or paid spend. No curriculum completion claim. git diff --check passes.
