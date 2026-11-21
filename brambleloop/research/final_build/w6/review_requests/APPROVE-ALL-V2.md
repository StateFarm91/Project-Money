# APPROVE-ALL-V2: "Approve everything I can decide (N)"

Branch `eng/approve-all-v2`, cut from `claude/w6-release-19h3` 2eb0222, which already contains `eng/mission-control-2`.
- Status: NOT merged, NOT deployed. Production is unchanged.
- No production row was read. No Railway variable was read.
- Decisions: D-APPROVE-ALL-V2 and D-OWNER-PUBLISH-WITH-RENDERS (this base lacked the second; it is now added).

## The problem

The owner's screenshot (2026-11-21) showed "Approve all eligible (0)" over 98 open cards. The 62 "never approved in bulk" were:
- child safety: 1
- physical sample: 4
- spend above ceiling: 12
- public publishing: 5
- owner only: 13
- not an owner action row: 27

v1 approves only classifier-routine rows. The hourly sweep had already closed every one of those, so v1 can only ever show 0 in production.

## What was built

**Endpoints.** `GET /api/cc/approve-everything` returns the exact list. `POST` runs the press.
- `GET` returns `acted`, `kept` (each with a reason, and a link where the act happens outside the app), `counts`, `spend` and `digest`.
- `POST` needs:
  - the owner session, CSRF and a nonce (the existing gate);
  - `auth.require_stepup`;
  - the preview `expected_digest`;
  - `confirm: true`.
- The UI always asks for a fresh passphrase + TOTP step-up (`guardedAction({freshStepUp: true})`).
- The server spends the step-up after a press (`auth.consume_stepup`), so a second press needs another one.

**One transaction.** The existing single-card doors run inside the press's session (`_OneTransaction`). If anything is refused, every write is rolled back, including grants already signed in that press (tested).

**What each class gets:**

| Class | v2 behaviour |
|---|---|
| routine (v1) | unchanged |
| spend above ceiling | Approved at the stated `max_cost_cad`, in id order. Stops while month-to-date ceiling-governed spend (`routing.spent_this_month`) plus the approved amounts stays ≤ `spend_policy.ceiling_cad()` (CA$100). These stay open with a reason: over the cap, no stated amount, unreadable spend, and `spend.ceiling.*` raises. The cap is never written. Audit: `owner.spend.approved`. |
| owner only | Approved: `improve.upgrade:<id>` and `improve.league:<id>`, through `cells.record_owner_approval` / `league.record_owner_decision`. Kept as "Do it at <link>": OAuth, KYC, legal, banking, external policy attestation, credentials, readings. Kept as their own card: choices and rulings (acceptance ruling, support defect, model selection, storefront proposal, unclassified). |
| public publishing | Publication and activation grants signed through the existing path: `owner_grant_keys.owner_request`, `_require_publication_evidence`, then `publication_authority.approve` / `activation_authority.approve`. `expected_digest` is the digest of the content the owner previewed. A release named by an open child-safety row is never signed. `first_public_listing:` and `standing_policy.hold:` rows are marked covered by the grant and close themselves when the grant is used. Etsy-surface rows go to Shop Manager. Buyer messages and `phase` keep their own cards. |
| physical sample | `withdrawn`, `owner_directed_without_attestation`, `attested: false`, `sample_exists: false`. Never `satisfied`, so `owner_closed` is False. |
| child safety | Never moved. Caught by the classifier, the key guard, or the row's own text. |
| physical attestation | Never moved. Covers the physical key guard and `physical_size_conflict:`. |
| not an owner action row | Removed from the Approvals list, the badge and the counts. Folded under "Not owner actions: close through their own doors (N)" so the doors stay reachable. |

**Home.** Mission Control now shows "Approve everything I can decide (N)" (`owner_queue.can_decide`).

## Tests

- New suite `tests/test_approve_all_v2.py`: 15/15. It covers:
  - session, CSRF and a fresh, consumed step-up;
  - confirm and digest;
  - every class;
  - physical cards never read as attested;
  - grants bound to the previewed content and valid at the boundary;
  - changed content signs nothing;
  - a mid-press failure rolls everything back;
  - child-safety releases are never signed;
  - mutation tests: each defence is load-bearing and the others hold;
  - a tampered list is refused at the write;
  - the cap holds and is never raised;
  - every approval is audited;
  - the counts are right.
- Targeted run `20261121T111632Z-5788`, 24 suites including test_mission_control2, test_eng_approvals, test_owner_directive_approve_all, test_w3_k7_owner_queue, test_vacuity, test_v11_pwa_static, test_v11_cc_actions, test_route_auth_default_deny and test_w3_decision_index: 296 passing. Its only failing suite was test_approve_all_v2 itself, because of its output format; that is fixed and re-run green in `test_approve_all_v2 test_vacuity`.
- Baseline before the change: the 6 named suites passed 158/0.
- `test_first_listing_doors` and `test_w4_launchfix` fail identically on base 2eb0222 (gallery incomplete / sample photo). They are pre-existing and not touched.
- Browser check on the real backend at 390 px: the card renders the list, the kept reasons and the "Do it at" links.

## Open / honest limits

- **Static bundle.** The Command Center bundle was 42 B under the 400 KB test limit. To fit v2, CSS comments were removed (no rules changed) and the v1 card was replaced in the UI by the v2 card. The v1 endpoint remains. Headroom is now 45 B.
- **Not tested on production data.** The real 98 cards' keys are unknown here. The buckets above are by key and class. Some screenshot categories may split differently: for example, a "physical sample" that is really a Shop Manager reading goes to "do it outside".
- **The sample-photo gate still stands.** D-OWNER-PUBLISH-WITH-RENDERS closes the sample cards. It does NOT relax `SAMPLE_PHOTO_REQUIRED`, so publication evidence for those products may still not be ready, and then no grant is signed for them. Relaxing that gate is a separate decision.
- **Grants are signed, not executed.** The press stops at signing. Queueing `store.publish` / `store.activate` stays on each card's "now" button, behind the kill-switch and every gate.
- **Producers may re-raise rows.** A producer can re-raise a closed row if its condition persists (existing lifecycle behaviour).
- **"Decide first" count unchanged.** It still includes consolidated decision-batch items derived from gates. It was not changed.
