# Review request: ENG-ETSY-PUBLISH slice 1 (the Etsy path, automatic and verified)

Branch `eng/etsy-publish`, base `claude/w6-INTEG3` @ 307c7e62. Builder branch: NOT reviewed,
NOT integrated, NOT deployed. Nothing here ran against production or real Etsy. Every Etsy
interaction below is against `tests/fake_etsy.py`.

## Why the first listing could not proceed, item by item

| Readback section | Cause found | Ours? | What this slice does |
|---|---|---|---|
| certification FAIL | stale-artefact halt | Batch 12 | nothing (Batch 12's) |
| **rollback FAIL** | The rehearsal read the PDFs from the newest **200 `assets.build` jobs across the whole catalogue**, so an older release on a busy factory read "no built PDF is recorded". It also read frames from **every stored ListingAsset**, so a stale frame no certificate names, not on disk, failed a fully restorable certified set. And no executed rollback existed at all ("no automated deactivation job exists", G5: a deleted draft could never be drafted again). | yes | fixed (below) |
| **listing_set FAIL** | `_judge_search_hero` issues the listing-set certificate only when `staleness().blocks` is false. A stale release gets no certificate, so this FAIL follows the certification halt. I found no independent cause in the code. Production cannot confirm it today: the readback emits no per-section detail. | downstream of Batch 12 | made measurable: `section_diagnostics.listing_set` (certificate_valid, frames, frames_may_export, reason_count) |
| policy FAIL | #39 | overridden (D-OWNER-POLICY39-OVERRIDE) | nothing. **No AI-policy gate added; the AI disclosure in copy, alt text and pixels is untouched.** |
| search FAIL | taxonomy UNKNOWN | ENG-SEO-PRICE | made measurable: `section_diagnostics.search` (category_status, failing check names) |
| **parity UNKNOWN** | `_parity` is UNKNOWN when any of the eight #75 dimensions is unjudged or the frames are not independently reviewed. The readback said only "UNKNOWN", never which dimension. | measurement ours; the verdicts are evidence-bound | made measurable: `section_diagnostics.parity` (unjudged/failed dimension names from `parity.DIMENSIONS`, frames_judged, frame_review_done, exported_frame_review_done/applies) |

The next production readback (`.first_listing_readiness.releases[].section_diagnostics`) names
the exact dimension, step or check behind each non-PASS. Only identifiers from a fixed
vocabulary, counts and booleans are emitted. Free text is dropped, never echoed (test pins it).

## What changed

| File | Change |
|---|---|
| `launch/rollback.py` | The rehearsal reads the PDFs certified for THIS release from every `assets.built` row (`deliverables.certified`, the source `secure_release` keeps). It reads frames from the valid listing-set certificate (what an upload sends), falling back to ListingAsset only when no valid certificate exists. Also new: **`withdraw_draft`**: read back, delete only while Etsy says `draft`, verify gone by a second read (a 204 alone is not proof), then restore the local listing to `draft` with no Etsy id, retire the creation intent (copied into the audit row), and resolve `store.publish_incomplete:` / `draft-create:` incidents. Live listings are refused ("deactivated, never deleted"). Every refusal changes nothing and is audited. |
| `ops/publication_authority.py` | `ROLLBACK_PATH.remove_draft` names the executable path. **This text is part of the evidence a grant digest binds, so grants recorded before this change are voided** (by design: changed evidence voids a grant). |
| `publish/draft_adoption.py` (new) | Before any create, the shop is read in every state. Outcomes: **none** creates as before. **adopt**: exactly one unbound draft with the certified title and price; the intent is checkpointed to it and no create is sent. **escalate**: two or more, another state, or a price mismatch; one halting incident, nothing created. **unread**: a failed, paging-limit or stateless read; TransientError, nothing created. |
| `runtime/pipeline.py` | The duplicate check runs before `draft_intent.claim`. Adoption completes the draft in place. New `_complete_draft` sends only what Etsy lacks: missing US/UK PDFs, the images (all, or re-sent rank by rank with `overwrite` when count or alt text differ; extra images are reported, never guessed at) and properties. A read-back that comes up short on files or images is completed and read again, at most `MAX_COMPLETION_ROUNDS = 2`. Field mismatches are not "completable" and end the loop. The tail of `_publish_and_read_back` moved into `_read_back_and_record` (shared by the create and adopt paths, unchanged otherwise). The first-listing card is refreshed after publish and after activation. |
| `runtime/etsy_ops.py` | `image_hash_checks`: per rank, the sent bytes' sha256 must equal the listing-set certificate's, and Etsy's `full_width`/`full_height` must equal the sent image's. `completable()`. `store.draft_reconcile` runs the publication scheduler. |
| `finance/listing_costs.py` | `PER_LISTING_FEE_USD = 0.20`: a single reservation above US$0.20 at the assumed rate (+1 cent) is refused, inside the same lock as the CA$6 cumulative check. |
| `publish/first_listing_card.py` (new) | ONE OwnerAction `first_public_listing:approve`, "Approve first public listing (step-up)". It is raised only with complete evidence: a verified read-back, both certified PDF hashes, every image rank's hash matching the certificate, and all seven gate results. The text names the listing, release, hashes and gates, and cites an audit row (`first_listing.card_evidence`) holding the full evidence. It is withdrawn when the evidence goes, and satisfied when a listing is live. Classified GENUINE_EXCEPTION / publication_or_activation. |
| `publish/publication_scheduler.py` (new) | Hourly inside `store.draft_reconcile`: for each certified release not on Etsy with an owner-recorded publication grant valid now (`publication_authority.resolve`), it calls `owner_execution.queue_publication` (the owner's door: grant, phase, kill switch, one job per grant). No grant, nothing queued. It never grants (static test). No new cadence. |
| `authority/standing_internal.py`, `owner_queue_classification.md` | rule `prefix:first_public_listing:` = GENUINE / publication. |
| `tests/fake_etsy.py` | `overwrite` on image upload replaces the rank (Etsy's documented behaviour). New knobs: `file_failures` (refuse the next file uploads) and `delete_is_noop` (204, nothing deleted). |
| `tests/test_etsy_publish.py` (new, fast), `tests/test_etsy_publish_e2e.py` (new, ~3 min) | below |
| `tests/test_eng_approvals.py` | rule tally 70→71 GENUINE. The fee boundary test is now reached one fee at a time, because one CA$5 reservation is now refused by the per-listing cap. |

## Not changed, and why

* **Publication authority.** Drafts still need the owner's sealed publication grant, and
  activation the owner's activation grant or Stage A. `STAGE_A_ENABLED` stays False. Nothing
  self-grants, and the kill switch is unchanged (`BRAMBLELOOP_PUBLISH_AUTHORISED`).
* **Byte-for-byte read-back of what Etsy holds is not possible, and is not claimed.**
  `getAllListingFiles` returns name and `size_bytes`, with no hash and no download.
  `getListingImages` returns Etsy's re-encode. So byte identity is proven at send: the
  sent sha256 must equal the certified sha256, for PDFs (existing) and images (new). Etsy's side
  is checked by name and exact byte size (files), and by rank, alt text and pixel dimensions
  (images). FakeEtsy records the hash of what it received, and the e2e asserts it equals the
  certified hash.
* **A live listing is not withdrawn by this path.** Deactivation stays with
  `ops.standing_withdrawal` (SP lineage) or the owner's Shop Manager. An owner-signed
  withdrawal grant for owner-path listings is not built here.
* The pre-existing failure `test_w4_readback_evidence::test_readback_evidence_cli_never_prints_the_token_and_keeps_unknown_apart`
  fails identically on base 307c7e62 (clean worktree), so this branch did not cause it.

## Please check specifically

1. **Intent retirement.** `withdraw_draft` deletes the `DraftIntent` only after a second read
   finds the listing gone (or `removed`), so the version may be drafted once more. That relaxes
   `draft_intent`'s "one create per version" rule, and only when no remote listing exists. Is
   that sound?
2. **Adoption on content.** One unbound draft with the exact certified title and price is
   adopted. A hand-made draft with the same title and price but different copy is adopted,
   then its read-back fails on the fields and it stays `incomplete_on_etsy` behind its incident
   (fields are not "completable"). It is not activated. Acceptable?
3. **UNREAD → TransientError.** A shop that cannot be read blocks every create, by retrying.
   That fails closed. Is retry-forever acceptable, or should it dead-letter after N?
4. **Overwrite.** The completion path relies on Etsy's `overwrite=true` replacing the image at
   a rank (FakeEtsy now models it from Etsy's schema description). That is not verified on real Etsy.
5. The grant-digest void caused by the `ROLLBACK_PATH` text change.

## Tests and mutants

* `tests/test_etsy_publish.py`: 16/16. Covers: rollback (withdraw/verify/restore; live refused; no authority; 500; 204-noop;
  soft delete; absent; local-state refusals); rehearsal (210 newer jobs plus a stale frame,
  and a missing certified frame); read-back hash and dimension compare; completable; grant guard
  (no recorded grant → client refuses, no create request); card never on empty evidence;
  diagnostics carry no free text; scheduler queues nothing without a grant; scheduler and card
  import or call no grant writer.
* `tests/test_etsy_publish_e2e.py`: 3/3, on the real certified fixture and FakeEtsy. The flow:
  - No grant: no create, and the scheduler queues nothing.
  - Grant: the first file upload is refused. One completion round sends both PDFs and all
    images in gallery order with alt text. The read-back is verified. The server-received
    sha256 equals the certified hashes. Exactly one create.
  - The card is raised with its evidence.
  - Rollback: deleted on Etsy, local restored, card withdrawn.
  - A matching draft is seeded with no intent. The scheduler (no button) queues once and a
    second tick queues nothing. The draft is adopted, with no second create, then completed
    and verified, and the card is raised again.
  - The door is closed and no fee is reserved.
  - Separate cases: escalation and unread verdicts; the fee cap (CA$0.50 refused; ⌊6/0.28⌋ = 21 reservations, then CA$6 refuses).
* Mutants (each in its own tree copy, both unmutated controls passing):
  - KILLED: grant guard (`OwnerGrant.refusal` → None), fee cap removed, read-back hash compare
    forced true, duplicate adoption disabled, rollback verify-gone skipped, completion rounds = 0.
  - `card_empty_evidence` survives the e2e alone. Its kill by the card unit test is reported
    in BUILD_STATE.
* `card_empty_evidence` is killed by `test_the_first_listing_card_is_not_raised_without_its_evidence`.
* 38 requested and related suites ran on the final tree; 35 pass. The 3 failures are identical on clean base 307c7e62: `test_w4_readback_evidence` (CLI row), `test_w6_listing_chain_e2e`, `test_ws4_stage_a_withdrawal`.
* The first run surfaced 6 regressions, now fixed:
  * The shop read preceded the before-create revalidation, which `test_publish_execution_gate` caught. The check now runs inside `before_create`, after revalidation, stock client only.
  * The rehearsal lost the job-only PDF record (`test_launch`). It now falls back to this slug@version's build job.
  * `test_w4_listready`'s write-site table now covers the new sites. It also gains a new pin: `_complete_draft` is reachable only inside the guarded publish path.
  * `test_etsy`'s order pin now follows the read-back into `_read_back_and_record`.
  * The durability `FakeRemote` now models an empty shop.
  * A legacy `order` shape is read as a mismatch, never a pass.
