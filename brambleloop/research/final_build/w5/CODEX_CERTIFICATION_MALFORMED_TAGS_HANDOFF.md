# Certification of malformed stored listing tags

Stacked on PR #115 (`ab61eec`), which itself builds on isolated quality/policy preview #112 and preserved safety candidate `6cb70e3`. The real certification Worker previously granted a synthetic release and said it examined a stored listing even though its JSON tags were an object converted silently into its keys.

The stored tag value is now preserved through `_certify_listing`; the shared policy check fails a non-list or non-string tag collection with `POLICY_TAGS_INVALID`. A valid list remains eligible for existing checks. This prevents the demonstrated new-certification path from treating malformed stored tags as attested copy. It does not resolve the duplicate-certification early return, authenticated Learning/physical/owner authority, concurrent listing mutation or A6 certification transaction fencing.

Synthetic real certification Worker tests cover object, string, null and non-string tag values; independent reviewer reran 4/4. No physical evidence, owner approval, purchase, publication or deployment was created. This change overlaps A6's critical shared `runtime/pipeline.py` and `gates/policy.py`; integrators must reconcile it with those branches and request independent review. PostgreSQL and production acceptance remain open.
