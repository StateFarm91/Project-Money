# OPUS2 handoff: the automatic listing-package job (INTEG-LISTING-JOB)

| Field | Value |
|---|---|
| Claim | `OPUS2-LISTING-PACKAGE-JOB` in `COORDINATION.json`, from the integrator's `INTEG-LISTING-JOB` (offered on PR #3, 2026-10-31T19:17Z) |
| Branch | `opus2/p0-listing-package`, cut from `claude/w4-INTEG8-next` `276a95a7` |
| Not touched | `publish/pdf.py` (W-PDF), `products/production_inventory.py` (W-INVENTORY), and the manual `LISTING_PACKAGE.md` files (W-LISTING) |

## What it does

`listing.package` runs as the `listing` agent in Store / Commerce. It is action class O,
six-hourly, costs CA$0, has work key `work_done`, and never publishes.

For every certified release with a drafted listing, it assembles the owner-review package and
records it. Every field is read from what the release chain stored, through the same functions
publication uses:

| Package section | Source |
|---|---|
| Blockers (run first, because they settle the listing-set certificate the gallery is read from) | `publish.release_gates.for_publish(read_only=True, stage="activation")`, every reason |
| Title, description, tags, price, taxonomy, properties | `runtime.etsy_ops.certified_payload` → `sent_fields`, exactly what `store.publish` would send. If it refuses, its reason becomes a blocker and no copy is guessed. |
| Gallery and disclosures | `etsy_ops.certified_frames`, in certificate order with each frame's honesty label |
| Files | the latest completed `assets.build` for this release: PDF SHA-256 per terminology, pages, size label |
| Identity | the certified `PatternVersion` (release hash, risk class), `launch0.childrens_decision`, and `launch0.product_truth` for a Launch-0 candidate |

**How it is recorded:**
- An `OperatingReading` of kind `listing.package`, keyed `<slug>@<version>`, rewritten only
  when the content fingerprint changes. An unchanged chain therefore reports no work.
- The Markdown render goes into the artifact store. Its sections follow the manual packages:
  title, description, category, tags, price, files, disclosures, gallery and outstanding
  requirements.

**The owner's review queue:**
- One `OwnerAction` (`listing_package:<slug>@<version>`, CA$0, "Publishing remains your
  decision") is raised only when the package has no blocker.
- If a blocker returns, the action is closed as `superseded`, and the reason is recorded.

## Evidence

`tests/test_opus2_listing_package.py` passes 5/5, on the real chain: `gate.certify` →
`assets.build` → a drafted listing, in SHADOW with sockets closed.
- The PDFs are the stored bytes.
- The copy equals `sent_fields(certified_payload(...))` wherever the builder answers.
- In SHADOW the package is **blocked** for real reasons:
  - taxonomy unchosen;
  - no listing-set certificate yet;
  - no search profile;
  - no bound physical sample;
  - unverified Etsy claims;
  - no sample photo.
- So no review is requested.
- Assembly is deterministic: a second run changes nothing.
- A ready package raises exactly one review request, and a new blocker withdraws it.

Regression: 76 suites, all exit 0. They cover every suite reading `for_publish`, `listing_set`,
`certified_payload`, `certified_frames` or `etsy_ops`, plus vacuity, retention, cost, autonomy
timeline, orchestrator, overnight, fmbatch1 departments, maturity, launchfix, resume runner,
shadow, roles and close5 rows3.

## Review OPUS2F fixes (2026-11-01)

| Finding | Fix | Test |
|---|---|---|
| A-1 HIGH: PDF hashes not bound to the release | PDFs come from `pipeline._certified_pdf_hashes(db, slug, version, release)`; an empty release hash binds nothing (blocker) | `test_review_opus2f_a1_*` |
| A-2 MED: a completed review re-asked | the request key carries the package fingerprint; no new request if any row (open or done) exists for that fingerprint | `test_review_opus2f_a2_*` |
| A-3 MED: stale request left open | a blocked or changed package supersedes (closes) the open request for the old fingerprint | `test_review_opus2f_a3_*` |
| A-4 MED: listing copy not bound to the release | "drafted listing was written for release X, not the certified Y" is a blocker; the two-row case cannot exist (unique product_slug, version), pinned by a test | `test_review_opus2f_a4_*` |
| A-5 LOW: alt text not shown | §8 renders each image's alt text | `test_review_opus2f_a5_*` |
| A-6/A-7 LOW: class and naming | `listing.package` is class B (internal writes); docstrings state the writes and the canonical-package naming | autonomy map regenerated; timeline test |
| A-8 LOW: one release error stops the sweep | each release's `record` runs under `_try` | `test_review_opus2f_a8_*` |
| (lock) | `record` takes `release._serialise_owner_queue` as its transaction's first statement (taking it after a read raised "cannot start a transaction within a transaction" on SQLite under SQLAlchemy 2.1.6 / Python 3.13) | A-2/A-3 tests |

`tests/test_opus2_listing_package.py` 11/11. Regression: the same 76 suites, all exit 0 (before the lock-order fix and the two added tests; the suite and the autonomy guards were re-run after them).

## Completion state (D-W5-OWNER-COMPLETION-METRICS)

Implemented: yes. Independently reviewed, integrated, certified, deployed, production verified,
end-to-end: **no**.

## Review OPUS2EF2 fixes (2026-11-01)

| Finding | Fix | Test |
|---|---|---|
| EF2-4 MED: READY → BLOCKED → READY never re-asks | Only an open request, or one the owner closed (satisfied or withdrawn), stands for a fingerprint. A request this job superseded itself counts as absent. | `test_review_opus2ef2_ef24_*` (mutation killed) |
| EF2-5 LOW: requests under the legacy key orphaned | The exact unfingerprinted key `listing_package:<slug>@<version>` is matched and superseded too | `test_review_opus2ef2_ef25_*` |

`tests/test_opus2_listing_package.py` 13/13; `test_vacuity` OK.

## Review OPUS2G (e93b16ed): ACCEPT; L5-1 fixed, L5-2 stated (2026-11-01)

- L5-1 LOW: a request the owner PARKED stays parked through a transient block, so it is not
  re-raised when the package returns unchanged; changed content still supersedes it
  (`test_review_opus2g_l51_*`).
- L5-2 INFO: a legacy-key request the owner SATISFIED is not carried over. It named no content
  (it carried no fingerprint), so the owner is asked once under the fingerprinted key.
- L5-3 INFO: the `LIKE` wildcard on `_` over-matches only keys of the same shape; this is left
  as it is.
