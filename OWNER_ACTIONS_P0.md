# OWNER ACTIONS — P0 (publishing halt and first Etsy draft)

_Written 2026-11-21 by the eng/publish-unhalt builder session. Production at the time:
2f7da291 (Batch 19a). Readback: FAIL `publishing_halt_clear`; WARN "no draft candidate among 7
certified Launch-0 releases with a listing"._

This file covers only blockers that code cannot clear. The code-level causes are fixed on
`eng/publish-unhalt` (see `w6/review_requests/PUBLISH-UNHALT.md`), but that branch is **not
deployed**. Deploying it is a separate owner approval through the normal release path. It is
not listed below because it is not new.

**Honesty note.** This session could not read the token-gated readback evidence. It did not
read Railway variable values, and it has no operator token. The public `/api/verify` gives
booleans only. So each item gives the code fact that makes it a blocker and says how to
confirm it. Nothing here claims what production holds. After the fix branch deploys, the
readback WARN line names each release's failing sections and blocker sources (U5).

No item asks for a grant, attestation or waiver to be forged or pre-filled. The kill switch,
fee cap, child-safety and grant gates are unchanged.

---

## P0-1 — Run the controlled Etsy exercise (one CA$0 round trip)

- **Exact action:** Run the full controlled exercise against the real shop, once:
  `POST /api/etsy/exercise?mode=full` with the operator credential
  (`Authorization: Bearer <BRAMBLELOOP_OPS_TOKEN>`). You can run it yourself, or tell a
  session that holds the operator credential to run it. If it returns 409 with a credential
  error, re-authorise the Etsy app in a browser first (`/api/etsy/oauth/start`, approve all
  five scopes). That grant dates from 2026-09-25, and its refresh token has a 90-day life.
- **Reason:** `gates.first_customer.check_etsy_remote_state` stays UNVERIFIABLE, and so blocks
  every publication, until a sealed, clean, live round trip against openapi.etsy.com is on
  record and less than 90 days old (`etsy_exercise.EVIDENCE_MAX_AGE_DAYS`). No scheduled job
  runs the exercise. The only door is the operator-authenticated endpoint, so no autonomous
  session can produce this evidence. Until it exists, every listing package reads BLOCKED with
  source `release_gates.for_publish` (area `etsy_remote_state`), and no release can be a draft
  candidate.
- **Maximum cost:** CA$0. The exercise makes one clearly marked draft and deletes it, and
  verifies the delete. It never publishes, so Etsy charges no listing fee. The client is built
  with `owner_authorised=False`.
- **Minutes required:** 5 (or 10 if the OAuth re-authorisation is needed).
- **Consequence of delay:** No Etsy draft candidate can exist, whatever else passes. Each day
  of delay is a day with no first listing.

## P0-1b — (2026-11-21, ENG-ETSY-RECOVERY) Decide on a second Etsy exercise budget

- **Exact action:** Choose one. (a) After `eng/etsy-recovery` deploys, call
  `POST /api/etsy/exercise?mode=recover`, then `?mode=full`, with the operator credential.
  This can be from a phone, or by a session you give the credential to. (b) Or reply with an
  explicit new instruction, for example "D-OWNER-ETSY-EXERCISE-2: up to 3 attempts in the next
  24 h, recovery first, at boot". A session then builds that boot runner.
- **Reason:** D-OWNER-ETSY-EXERCISE spent its 2 attempts, and both reported the shop not
  clean. Recovery code that removes only the exercise's own ledger-proven drafts now exists,
  but nothing runs it unattended. A fresh unattended budget for writes to the real shop needs
  your decision. It was not minted from earlier instructions.
- **Maximum cost:** CA$0. Drafts and deletes only; `owner_authorised=False`; nothing publishes.
- **Minutes required:** 2 for (a); 1 for (b).
- **Consequence of delay:** a marked test draft may stay in the shop as a draft (no buyer
  sees it, no fee). P0-1's evidence stays absent, so publication stays blocked.

## P0-2 — Record a fresh reading of the five etsy.com/legal policy pages

- **Exact action:** In the Command Center policy form (owner session, step-up, verbatim
  confirmation: `app.command_center.policy_readings.record`), open each page below in your own
  browser, read it, and record the reading. One reading per source:
  - `seller_policy`: https://www.etsy.com/legal/sellers/
  - `creativity_standards`: https://www.etsy.com/legal/handmade/
  - `advertising_rules`: https://www.etsy.com/legal/advertising/
  - `shilling_and_reviews`: https://www.etsy.com/legal/prohibited/
  - `children_and_baby`: https://www.etsy.com/legal/prohibited-items/children/
- **Reason:** The publication approval packet's `policy` section
  (`ops.publication_authority._policy`) is FAIL whenever any watched source's newest reading
  is more than 30 days old (`platform_policy.MAX_AGE_DAYS`). A draft candidate requires every
  gated section to PASS. The repository's own excerpt reading of these pages is dated
  2026-09-26 (`gates.policy_knowledge.READ_ON`), which is 56 days old today. Etsy refuses
  automated access to etsy.com/legal (DataDome), and the company does not evade that. The
  Help Center sources (`listing_image_rules`, `search_guidance`) are re-read automatically and
  are not on this list.
  **Confirm first:** if `/api/policy` (or the readback after deploy) shows these sources
  current because you recorded page readings after 2026-10-22, skip this item.
- **Maximum cost:** CA$0.
- **Minutes required:** about 25 (5 pages at about 5 minutes each).
- **Consequence of delay:** The `policy` section stays FAIL for all 7 releases, so there is no
  draft candidate. A source that goes stale again after 30 days blocks again, so a recurring
  monthly reading is the steady state.
- **Note:** The owner form compares a reading only with earlier page readings, so your first
  page reading becomes the baseline and does not open a new #39 review card. A later material
  change does open one, and that is correct.

## Not P0 today (listed so nothing is silently dropped)

- **Approve the first public listing** (`first_public_listing:approve`, step-up). The card is
  raised only once a draft exists with complete evidence. It is not actionable until P0-1 and
  P0-2 are done and a draft candidate exists.
- **Physical samples.** Under D-OWNER-ESTIMATE-CLAIMS, non-toy Launch-0 items pass
  `gauge_and_size_claims` as labelled calculated estimates. A physical use-and-abuse test is
  still required for stuffed toys, loveys and other items under the child-safety rule. That
  gate is unchanged and it is not on the Launch-0 critical path.
- **The fix-branch deploy.** It needs the usual release record and your deploy approval. The
  halt fixes (U1–U3) take effect only once deployed, and the systemic halt then closes at the
  next hourly `ops.sentinel` followed by `ops.health` (truth sweep), provided no other family
  holds 50% of the catalogue.
