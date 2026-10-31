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

## Completion state (D-W5-OWNER-COMPLETION-METRICS)

Implemented: yes. Independently reviewed, integrated, certified, deployed, production verified,
end-to-end: **no**.
