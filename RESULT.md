GIT SHA: 05c735a7253cc55240f5497768906272bbf91bd3
TOTAL PASSING: 11643 ; suites failing: 1
ENVIRONMENT FAILURES: 0 of the 1 failing suites (ENOSPC/permission/network/provider; F-150)
RUN FINISHED: 2026-11-19T13:31:30Z
DURATION: 10790s
GIT SHA: 05c735a7253cc55240f5497768906272bbf91bd3 (tree clean at start)
RUN RECORD: artifacts/suite_runs/20261119T103140Z-1738.json (failed)

## Failing suites

### tests/test_w4_adopt_manual_listing.py

FAIL lines: none printed (12 OK, then the suite aborted on an uncaught AssertionError in test_no_code_compares_or_lists_the_published_literal_outside_the_helper)

```
   OK   test_acceptance_is_refused_when_the_live_copy_breaks_truth_or_disclosures
   OK   test_every_live_reader_counts_a_manually_published_listing
   Traceback (most recent call last):
     File "/home/user/Project-Money/brambleloop/tests/test_w4_adopt_manual_listing.py", line 959, in <module>
       fn()
       ~~^^
     File "/home/user/Project-Money/brambleloop/tests/test_w4_adopt_manual_listing.py", line 725, in test_no_code_compares_or_lists_the_published_literal_outside_the_helper
       assert offenders == [], offenders
              ^^^^^^^^^^^^^^^
   AssertionError: ['ops/owner_execution.py:168: if state != "published":', 'app/command_center/approvals.py:394: """ENG-FIRSTLIST: verified Etsy drafts (state \'published\', not active): activation', 'app/command_center/approvals.py:403: .where(Listing.state == "published", Listing.etsy_listing_id != "")']
```
