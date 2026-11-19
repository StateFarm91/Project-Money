# ENG-APPROVALS: review request, slice 1 (the owner queue under D-OWNER-STANDING-INTERNAL)

- **Branch:** `eng/approvals`.
- **Base:** `origin/claude/w6-INTEG2` @ `a35ad302`.
- **SHA:** the commit that adds this file. The full SHA is in the issue #28 comment.
- **Status:** not deployed and not merged. Nothing touches Railway, production, secrets, Etsy,
  spend, `BRAMBLELOOP_PHASE` or `STAGE_A_ENABLED`. No grant is signed.

## What this slice does

1. **Classification.** The table is `research/final_build/w6/owner_queue_classification.md`.
   - A search over every OwnerAction producer found about 90 kinds. Each one is classified by
     `authority.standing_internal.classify`:
     - 15 ROUTINE_INTERNAL;
     - 3 AUTO_CLOSE;
     - the rest GENUINE_EXCEPTION, under one of the directive's eight classes.
   - Unknown kinds fail closed to the owner (`unclassified_fail_closed`) and are counted on the
     P0 board.
   - `laura:`/`dag:` authority requests are decided by the named job type's
     `authority.classes` class: autonomous → routine; gated → exception.
2. **Standing authority in code.** This uses the existing model and adds no new framework.
   - `COVERED_CLASSES == classes.AUTONOMOUS`. A test pins this, and no gated class is ever
     covered.
   - The sweep (`ops.owner_queue_consolidate.sweep`) does three things:
     - it supersedes routine cards through `owner_queue.transition`, which writes the
       lifecycle audit row;
     - it writes an `owner_action.standing_authority` row that cites the directive (retention:
       `lifetime_total`, because the owner asked that the audit trail be preserved);
     - it closes AUTO_CLOSE cards with their reason.
   - Genuine exceptions are never touched, and no row is deleted.
3. **Scheduled job `ops.owner_queue_consolidate`.** It runs hourly as the orchestrator agent,
   class BUILD. It is fully registered in:
   - worker CADENCES;
   - WORK_KEYS (`work_done`);
   - the orchestrator `allowed_job_types`;
   - `classes.JOB_CLASS`;
   - the platform charter;
   - orchestrate JOB_BANDS (`housekeeping`);
   - a regenerated `autonomy_map.json`.

   `ops.retention.unknown_read_actions() == []`.
4. **The one owner batch.** `approvals.inbox()["owner_exceptions"]` shows only genuine
   exceptions, grouped by class. Covered cards are counted. A not-ready `PUBLICATION` card is
   not an ask: it is counted as `publication_not_ready`.
5. **P0 board.** A new `owner_queue` section shows:
   - owner exceptions open (by class);
   - unclassified open;
   - closed automatically in the last 24 h;
   - routine operations auto-approved in the last 24 h.
6. **CA$6 opening-catalogue listing-fee budget** (`finance.listing_costs`).
   - It is cumulative, and reservations count. An observed fee for a listing that was never
     reserved also counts; one for a reserved listing does not, so nothing is counted twice.
   - It is enforced in `reserve`, under the accounting lock, after the unchanged daily-ceiling
     check. It is also enforced early in store.activate, as an audited refusal.
   - It raises no other ceiling: the store_operator daily ceiling stays CA$1.00, and the
     standing policy's per-30-day ceiling stays CA$0.
   - It authorises no publication. A fee is reserved only after every activation gate has
     passed.

## Decisions to look at hard

- **Superseding is not approving.** I grepped every `OwnerAction.done == True` reader:
  - `store_readiness` (only `store:OA-*`, which are genuine and untouched);
  - knowledge-gap suppression (genuine);
  - event wakes (a close is a wake signal; harmless);
  - the brief;
  - `etsy_ops` auth.

  No gate reads a superseded routine card as an approval.
- **`listing_package:` closes as `withdrawn`.** The package job re-asks after a supersede it did
  not make itself (EF2-4), but treats a withdrawn card for the same fingerprint as answered.
  Superseding would therefore churn every hour.
- **These stay with the owner, deliberately:**
  - canonical model selection and approval: the gate reads an owner approval timestamp, and
    automating it would forge an owner record;
  - `improve.upgrade:` (gate-tier) and `improve.league:` (step-up);
  - `draft_reconcile:`, which binds an Etsy draft to a release.
- **`listing_fees` card.** It stays a genuine exception on the card. The approved CA$6 is
  enforced as a budget, not by sealing a launch decision. Making the readiness row read the
  standing budget is a slice-2 candidate for Main's ruling, because it feeds
  `transition_verdict`.
- **Re-raised routine cards.** A routine producer that re-raises its card every run gets one
  new row per run; the next sweep closes each one with a new audit row. That is idempotent per
  row, but not silent. For the kinds marked routine, the producers restate an open row rather
  than inserting a new one, so churn only happens after a close. The volume is bounded by the
  hourly cadence.

## Coordination with ENG-RECOVERY

ENG-RECOVERY (`eng/recovery` 2f79832e) scopes the #39 hold in
`release_gates.retry_hold_reason`/`staleness`. This slice does not touch those functions. It
adds one field to `approvals._gate_card`, and that is the only overlap: ENG-RECOVERY edits the
`policy_review` card text a few lines below. The two should merge cleanly.

My hold test asserts three things:
- internal job types still dispatch under an unreviewed `listing_image_rules` change and an
  open hold card;
- that card stays open after the sweep;
- `staleness` still names the change.

## Tests

`tests/test_eng_approvals.py` has 20 tests. It is added to `scripts/suite_final_segment.txt`
before `test_product_run`.

The full required suite list, run through `run_tests.sh`, is reported in the issue comment.

Mutation table (each mutant applied alone; the test file run against it):

| mutant | result |
|---|---|
| default disposition → ROUTINE | killed |
| `covers_job_type` ignores the class set | killed |
| `laura:`/`dag:` gated check removed | killed |
| `decide` stops refusing a genuine verdict | killed |
| `sweep` stops skipping a genuine verdict | killed |
| stale `<` → `<=` | killed |
| `if not moved["changed"]: continue` removed | survived. This is an equivalent mutant: an open or parked row moved to a closing state always changes. |
| budget epsilon 1e-9 → 0.05 | killed |
| `reserve` budget check removed | killed |
| observed fees never counted | killed |
| a reserved listing is no longer free in `opening_budget_refusal` | killed |
| a not-ready publication card is counted as an exception | killed |

## Item 4: publication holds and internal manufacturing

**Dispatch.**
- Dispatch never consults a hold. `authority.policy.check_dispatch` examines gated classes only.
- The test pins it: every internal job type the directive names dispatches with an unreviewed
  `listing_image_rules` change and an open `standing_policy.hold:` card. These are
  `chain.rebuild`, `gate.certify`, `assets.build`/`render`, `listing.package`, `listing.seo`,
  `seo.cycle` and `cir.compile`/`twin`.
- The two runtime callers of `staleness` are:
  - the rebuild retry hold, which ENG-RECOVERY scopes;
  - `_judge_search_hero`'s listing-set issuance.

**Deliberately NOT changed: listing-set issuance under an unreviewed listing-image change.**
- A listing-set certificate stamps the platform-policy versions (`policy_stamp`, release_gates
  :855/:1274).
- Issuing one while `listing_image_rules` is unreviewed would record the unreviewed version as
  the rules the images were certified against.
- That is a certification gate, and the directive does not let me weaken it. The listing images
  are exactly what that policy governs.
- Everything else in listing preparation proceeds.

## Slice 2 (continuing)
- A store.activate handler-level test of the early fee-budget refusal.
- A batch-view route test through the Command Center API.
