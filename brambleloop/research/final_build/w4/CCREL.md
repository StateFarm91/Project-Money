# W4-CCREL: the owner's phone flows (release approval, Etsy Connect end to end, Laura briefing)

Branch `claude/w4-CCREL` from `origin/claude/w4-INTEG2` @ 85ec5d0. This is queue item (2) of the Command Center completion domain. Nothing deploys, publishes or writes to Etsy. Auth, CSRF, nonce and step-up are unchanged.

## 1. Release approval card (Approvals)

`app/command_center/release_card.py` reads the tracked release evidence that the deploy guard and boot guard already trust (`release/`, which is copied into the image). For the newest release record that has **not** been deployed, the card shows four things:

| Evidence row | Read from | PASS only when |
|---|---|---|
| Candidate SHA | `release/RELEASE_<sha>.json`, re-checked by `ops.release_record.check_record` | pinned suite record and log sha256s match, same SHA, full run, 0 failing suites |
| Full release suite | the tracked suite record | `passed`, `full`, `suites_failing == 0`; the card shows tests passing and suites failing |
| Security review | `release/SECURITY_REVIEW_<sha>.json` | it exists, names this SHA, verdict PASS, 0 open high findings. **Otherwise UNKNOWN, never assumed passed** |
| Rollback target | `release/DEPLOYED_HISTORY.json` | a previously deployed commit other than the candidate exists (the only kind a sanctioned rollback may use) |

A record counts as deployed when its SHA is in the deployed history, or when a deployed entry's evidence names its record. That second case covers a record-only commit on top of the SHA, which is how production 0417f35 runs record 5dfd1ac.

How the card appears:

- **Deploy decision open.** When the owner decision `production_window` ("authorise deploying the reviewed build") is open, the candidate's evidence, recommendation, uncertainty and reversibility are merged onto that card.
- **No deploy decision open.** A pending candidate gets its own read-only `RELEASE` card instead.
- **Always.** A "Release approval" section on Approvals shows the candidate with its four rows. When nothing is pending it reads "NO CANDIDATE" and names the build production runs.
- **Recommendation.** It is "Authorise" only when all four rows are PASS. Otherwise it names what is missing.

**Security review convention (new).** A reviewer records `{sha, verdict, open_high_findings, reviewer, reviewed_at}` at `release/SECURITY_REVIEW_<sha>.json`, committed with the release record. No such file exists today, so the card shows the security review as UNKNOWN. That is the truth.

**Today's repository.** Every tracked release record is deployed: 5dfd1ac runs as 0417f35. The card therefore says no candidate is pending. The frozen candidate 5ad94dd will show up as soon as its release record is committed.

## 2. Etsy Connect end to end (mock)

- The mock (`tests/fixtures/cc_mock/server.mjs`) now serves `GET /api/cc/etsy` in two states via `/__mock/etsy?ready=1`. It also serves `POST etsy/recheck`, and `POST etsy/connect`, which refuses with 403 without step-up, as the real API does.
- The browser check walks the whole flow:
  1. Connect is disabled while the key is refused and enabled once it is accepted.
  2. Re-check sends nothing before confirmation, then POSTs with CSRF and nonce.
  3. Connect asks for confirmation plus step-up, POSTs with CSRF and nonce, and the phone navigates to `https://www.etsy.com/oauth/connect?...`. Etsy is stubbed with `page.route`; nothing leaves the machine.
  4. An authorize URL on any other host (`evil.example`) is never followed.

## 3. Laura's CEO briefing on a phone

- A briefing (`laura.agency.briefing`) is one long sectioned answer with `[E#]` record ids. `views/laura.js` now shows it as one block per section, with the first two open and each line kept verbatim.
- Under each section is "Records cited here": every record that the section's lines cite (including multi-id references like `[E3, E4]`), each with its source link and status.
- Briefings in conversation history are recognised by `intent`.
- The parser follows `briefing.compose`'s own format. A Python test pins both sides, so a format change in one fails the test until the other is updated.

## Tests

| Test | Covers |
|---|---|
| `tests/test_w4_ccrel.py` (8 tests) | pending candidate: SHA, suite, UNKNOWN review, rollback; ready only with a PASS review; failed or tampered suite evidence is not a pass; no rollback target; deployed detection (by SHA and by record name); today's repo has no undeployed record; inbox attaches the evidence to the deploy decision or adds a standalone card; view wiring; briefing format alignment |
| `tests/fixtures/cc_mock/check.mjs` (new blocks "ccrel", "etsy connect", "laura briefing") | the release card at 390 px (4 rows, UNKNOWN review, read-only, evidence links); Etsy Connect end to end; briefing sections, open state, cited records, no horizontal scroll, no console errors |

The browser blocks wait until slots N ≥ 3, per WORKER_RULES. The Python tests run through `testslot.sh`.
