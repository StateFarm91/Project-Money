# Quality re-verification of listing tags

Based on isolated Batch 6 safety preview `6cb70e3`. The actual `gate.asset_truth` Worker previously rechecked the CIR title and stored listing title and description, but skipped the stored customer-facing tags. A synthetic listing with an unsupported `bobble` tag passed despite the existing technique checker rejecting that tag.

Re-verification now checks each tag using the same existing shape and technique checks, refuses malformed tag collections, and uses the existing durable quality withholding on failure. It clears only that check's hold when a subsequent recheck passes. If the listing disappears, the result is unknown and cannot clear a prior hold. `null` or malformed tag data is not silently interpreted as an empty list; the policy recheck also fails closed if it cannot parse such data. No new vocabulary or proof authority is introduced.

The real Worker test uses a synthetic certified release, exercises a tag-only defect, withholding and recovery, and checks malformed tag data. This does not establish evidence authority, prevent concurrent listing edits, cover every possible misleading term, or certify publication. PostgreSQL, integration and production acceptance remain open. No physical evidence, owner approval, purchase, publication or deployment was created.

Python 3.11 tmpfs SQLite department, withholding and actual Worker regressions passed 27/27. The department test's old expectation that an absent listing is a clean asset-truth check was corrected to expect unknown; the new real-Worker test verifies an existing hold survives that unknown state. Independent reviewer reran the final Worker cases 2/2.
