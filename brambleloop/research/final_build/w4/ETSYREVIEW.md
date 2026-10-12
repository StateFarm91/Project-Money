# W4-ETSYREVIEW: F-599 owner review task as a batched, non-interrupting card

Branch `claude/w4-ETSYREVIEW` from `origin/claude/w4-INTEG2` 16e36ae. Row: F-599. This completes the
part W4-ETSYSURF left open.

## Ruling applied
The coordinator ruled on 2026-10-12: the "owner review task" is a batched owner-action card in the
existing owner queue. It must not interrupt (no push) and must carry the exact action, reason, cost,
minutes and consequence that CLAUDE.md requires.

## Change
`runtime/etsy_ops.reverify_openapi` opens one OwnerAction, `store:etsy.openapi_review`, when a weekly
reading of Etsy's OpenAPI document is DRIFTED or its fingerprint changed.
- Fields: max cost CA$0, 15 minutes, a stated consequence of delay, and
  `blocks = "Etsy surface registry review (not a first-sale blocker)"`.
- A later change restates the reason on the same open card, so there is never a second card.
- The `store:` key places it in the **Etsy account** batch (`owner_queue._store_batch`) beside the other
  Etsy decisions.
- The P2 drift incident and the P3 change incident from W4-ETSYSURF are unchanged.

## Criteria status
- Scheduled (weekly ≥ quarterly) fetch of the public document: met.
- `document_fingerprint` and `verify_absence` compared with the recorded registry: met.
- Owner review task on change: met, as a batched card.
- Shop Manager UI navigation drift: external. etsy.com returns 403 to this environment, so no observer
  is possible.

## Acceptance evidence (testslot)
`tests/test_w4_etsyreview.py` 3/3:
- an unchanged document queues nothing;
- a change queues one complete card, and a later drift restates the same card;
- the card is batched with the Etsy account decisions and marked not a first-sale blocker.

Regression suites green: test_w4_etsysurf 8/8, test_w4_fm2_surface_reverify 8/8,
test_w4_owner_actions 6/0, test_cert_owner_decision.
