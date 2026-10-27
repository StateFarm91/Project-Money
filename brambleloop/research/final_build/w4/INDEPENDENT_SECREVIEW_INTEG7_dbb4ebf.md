# Independent review: INTEG7 follow-up dbb4ebf (S-1, S-2, S-4)

| Item | Verdict | Why |
|---|---|---|
| **S-2** daily rebuild retry hold | **DO NOT SHIP** | **H1.** The sentinel's own `stale-artefact:*` incident counts as "a halting incident other than staleness". Every product whose rebuild retry exists to cure staleness is therefore held, and stays held forever. Reproduced. |
| **S-1** exported-frame review reuse | **SHIP AFTER FIX** | **M1.** The reuse key is `position → sha256` only. The certified job, and the claim it is judged against, are not part of it. A frame whose job changes (on the same bytes) is reported `reviewed: True` without ever being judged against the new job, including a job with no claim, which C-80 says must block. Reproduced. **L1** (an `unjudged` verdict from a failed grid call sticks) is liveness only. |
| **S-4** anonymous-refusal assertions | **SHIP** | Adds assertions and weakens none. |
| Paid paths and ceilings (Q4) | **SAFE** | No new paid path. S-1 only removes calls. S-2 only suppresses CA$0 enqueues. No ceiling is touched. |
| **Overall** | **DO NOT SHIP as is** | Fix H1 (small) and M1 (small), then ship. |

Reviewer: an independent reviewer who did not write the code. Date: 2026-10-27 (UTC). The review was read-only: no production calls, no secrets, no deploys, nothing spent.

## Scope and method

- Diff reviewed: `git diff 6a9fa4dc..dbb4ebfe` (branch `claude/w4-INTEG7`). It covers 9 files, +209/−8: `ops/rebuild_graph.py`, `publish/release_gates.py`, `runtime/release.py`, `visual/exported_review.py`, four test files and `INTEG7.md`.
- I also read the code the change relies on:
  - `runtime/etsy_ops.certified_frames` / `certified_images`
  - `core/artifacts.ArtifactStore.get` / `_recover`
  - `ops/artefacts.sweep`
  - `release_gates._halting_other_than_staleness` / `staleness`
  - `ops/incident_lifecycle.systemic_evidence` / `escalate_systemic`
  - `visual/inspect.identify_at_grid`
- Environment: a fresh venv built from `brambleloop/requirements.lock` + `requirements-test.lock`. Every suite ran at `nice -n 19`.

| Suite | Result |
|---|---|
| `tests/test_w4_disclosedqa.py` | 10/10 OK |
| `tests/test_w4_prodfix.py` | 7/7 OK |
| `tests/test_w4_fmbatch1_mobile.py` | 3/3 OK |
| `tests/test_w4_fmbatch1_useful_work.py` | 5/5 OK |

All of these suites pass, yet both H1 and M1 reproduce against them. The repro scripts are summarised under each finding.

## Q1: can S-1's reuse accept a review of different or changed bytes?

**On bytes: no. This part is safe.** Frames are identified by digest, not by path:

- `certified_images` reads each frame with `ArtifactStore.get(sha)`, keyed by the sha256 the certificate recorded. `get` re-hashes the file it reads and refuses on a mismatch (`core/artifacts.py:115-119`). The Postgres fallback `_recover` re-hashes too (`:164`).
- `served["order"][i]["sha256"]` is therefore the digest of the bytes actually being served.
- Reuse requires the filed `frame_shas` to equal that `{position: sha256}` map exactly (`exported_review.py:81-86`). A missing, added, moved or changed frame forces a new review.
- If any frame fails its export checks, `certified_images` returns `problems`, and `review` returns early, before the reuse check (`:73-75`). A partial set can never be matched.
- Only the newest filed row is consulted (`_filed_review`). An older matching row is never resurrected over a newer, different one.

**On what the bytes were judged against: no, and this is finding M1.** A verdict is a function of `(bytes, job → claim, product families, describer)`. The reuse key carries only the bytes, so a byte-identical frame can be certified for a job it was never judged against.

## Findings

### H1 (High, liveness, S-2 does not do what it claims). The sentinel's own staleness incident holds the retry forever

- **Where:** `publish/release_gates.py:1335` (`retry_hold_reason`, reading `halting_other_than_staleness`) together with `:1297` and `:1307` (`own_marketing` / `_halting_other_than_staleness`). Wired in at `ops/rebuild_graph.py:305` and `runtime/release.py:6809`.
- **Cause:**
  - `ops/artefacts.sweep` files `Incident(signature="stale-artefact:<class>:<key>", product_slug=slug, halts_publication=True)` for **every** STALE artefact (`ops/artefacts.py:801-821`).
  - `_halting_other_than_staleness` waives only the `stale-artefact:marketing_asset:*` rows that appear in `publication_gate`'s `outstanding`, plus a staleness-only systemic halt.
  - Every other sentinel row is reported as "other than staleness": `visual_truth`, `listing_asset`, PDFs, and marketing rows the graph does not list. That helper was written for R4's marketing-only exception, where that is the intended meaning. Reusing it as the hold test inverts it.
- **Scenario (reproduced):**
  1. Product `a` has a stale `visual_truth` artefact, so the sentinel files `stale-artefact:visual_truth:a@1.0.0#1` (halting).
  2. The first rebuild runs and ends without delivering.
  3. On day 1, day 2 and day 30, `rebuild_graph.enqueue(..., hold=retry_hold_reason)` returns `retried: []` and `retry_held: {"a": "held: open halting incident(s) the rebuild cannot cure: stale-artefact:visual_truth:a@1.0.0#1"}`.
  4. The incident resolves only when the artefact is FRESH again, which needs the rebuild that is being held. The same happens for `stale-artefact:marketing_asset:a:pin:1` whenever the graph's `outstanding` does not list that key.
  5. The W4-PRODFIX daily retry is thereby disabled for exactly the products it exists for. Only a new upstream fingerprint, which is a first attempt rather than a retry, can unstick them.
- **Why the tests pass:** `test_s2_a_staleness_only_refusal_is_not_held` asserts `None` on a database with **no incidents at all**. It never seeds the sentinel's own row, which is the one case its name promises to cover.
- **Fix:**
  - Compute the hold from halting incidents for the slug **excluding every `stale-artefact:` signature** (`ops.artefacts.SENTINEL_SIGNATURE`), and excluding `SYSTEMIC_SIGNATURE` when its evidence is staleness-only. Do not reuse the marketing-specific helper.
  - Add a regression test that seeds `stale-artefact:visual_truth:a@1.0.0#1` (halting) and asserts both `retry_hold_reason(...) is None` and that the retry fires.
  - Keep the existing tamper-incident test. It is correct.

### M1 (Medium, Product Truth, fail-open). Reuse ignores the frame's job and the claim it was judged against

- **Where:** `visual/exported_review.py:81-91`. The key `current = {position: sha256}` is compared with the filed `frame_shas`. The filed `frames[pos]["job"]` is never compared with `served["order"][i]["job"]`, and nothing records which `JOB_CLAIMS` entry, product families or describer produced the verdict.
- **Scenario A, re-certification relabels a job (reproduced):**
  1. A clear review is filed. Position 3 is `DETAIL` (claim `shows_text`).
  2. The valid listing-set certificate is re-issued with the same bytes at position 3, but `job: "LIFESTYLE"`, which has no registered claim.
  3. `review()` returns `reused: True, reviewed: True` with zero calls, and its frames still say `job: "DETAIL"`. `review_state` also reads `reviewed: True`.
  4. A `fresh=True` review of the same state returns `reviewed: False, not_clear: {"3": "unclaimed"}`.
  5. The frame is certified for a claim it was never judged against. C-80 says an unclaimed job blocks.
- **Scenario B, a code deploy changes `JOB_CLAIMS` or the describer:**
  - Production never passes `fresh=True`. The only caller, `runtime/release.py:1325`, does not.
  - So a stricter claim, a removed claim, or a new describer model never re-judges an unchanged frame. The old `clear` verdict stands indefinitely.
  - The edited disclosedqa test that pops `MATERIALS` needs `fresh=True` precisely because of this. Its comment says "the claims changed: judge again", but no production path does that.
- **Pre-existing part:** before INTEG7, `review_state` was equally blind to jobs. But every `listing.seo` run re-reviewed and filed a new row, so the window closed on the next run. Reuse makes it permanent.
- **Fix (small, adds no paid calls in the normal case):**
  1. File a `basis` with each review: per position `{sha256, job, claim}` (the exact `JOB_CLAIMS` dict used, including `identifies_as` for identifying jobs), plus the describer `model` / prompt version.
  2. Reuse only when the current basis equals the filed one.
  3. Make `review_state` compare `(sha256, job)` against the certificate too.
  4. Add a test that relabels a certified frame's job and expects a re-review.

### L1 (Low, liveness, fail-closed). A transient grid failure is reused as a final `unjudged`

- **Where:** `exported_review.py:86-87` (only `unreviewed` re-runs) and `:126-133`. When `identify_at_grid` hits `TransientError` / `PermanentError` / `InspectionRefused` (a budget refusal included) / `OSError`, it returns `verdict: "unjudged", why: "no grid description: …"` (`visual/inspect.py:375-376`). The hero entry then becomes `unjudged`.
- **Scenario:** a single transient error, or a ceiling refusal, on the grid call. Every later retry reuses `unjudged`, and the release stays unreviewed until someone calls `fresh=True`, which no production path does.
- **Impact:** safe (it blocks), but it needs manual intervention. The same applies to a filed `unclaimed` after a claim is later registered (see M1 B).
- **Fix:** store the grid's `described` flag. Treat a hero whose grid was not described exactly like `unreviewed` (eligible to ask again).

### I1 (Info, S-2 design). The policy hold also holds non-publishing rebuild work

An unreviewed platform-policy change refuses `store.publish`. It does not make rebuilding stale PDFs and renders useless. Holding the whole chain is defensible (it avoids the dead-lettered `store.publish`), but it delays artefact freshness behind owner review. If that is intended, record it in the decision log. The hold does lift correctly when the change is reviewed: `test_s2_..._resumes_after` shows this, and I re-checked it by reading the code. A `systemic-halt:publication` row also self-resolves (`incident_lifecycle.escalate_systemic` reconciles it against live evidence), so it cannot pin the hold on its own.

### I2 (Info). The `**filed` spread comes last in the reuse result

`{"reviewed": ..., "not_clear": ..., "reused": True, "why": ..., **filed}` (`exported_review.py:89-91`). Today the filed detail carries no `reviewed` / `why` / `not_clear` keys, so nothing is overridden. A future field with one of those names would silently override the computed verdict. Spread `filed` first.

## Q2: do the `fresh=True` test edits keep their assertions meaningful?

**Yes. No test is weakened.**

- `_certified()` shares one database across the module, and `test_a_clear_blind_review_...` files a clear review first. Without `fresh=True`, the striped-rug and no-text cases would reuse that clear row and fail. With it, they still drive the real describe-and-compare path, and still assert `blocked` and `review_state(...)["reviewed"] is False`.
- `test_a_review_of_other_bytes_does_not_count` (unedited) now reuses rather than files. It then mutates the clear test's row instead of its own. It asserts on `review_state`, so its meaning is unchanged.
- The new S-1 tests are sound for what they cover (bytes and `unreviewed`). They do not cover job or claim changes (M1), and they rely on module test order through the shared database.

## Q3: can S-2 suppress a retry that should run, or hold one forever?

**Yes. See H1.** Every product whose retry is driven by its own stale-artefact incident (the normal case) is held. The hold persists until the artefact is rebuilt by some other route.

For the two reasons the change intends, the behaviour is correct:

- An unreviewed policy change, or a genuine non-staleness incident such as `authority_chain_tamper`, holds the retry. Clearing it resumes the retry on the next sentinel run.
- An unreadable gate does not hold, because `retry_hold_reason` catches the exception and returns `None`.
- Held rows are added to `already_queued`, so they are not re-enqueued as first attempts.

## Q4: is there a new paid path or a ceiling bypass?

**No.**

- **S-1:** the change adds a branch that *skips* `describe_image` / `identify_at_grid`. When the review runs, it goes through the same budgeted calls as before. `fresh` defaults to `False`, and only tests set it.
- **S-2:** the change only withholds `chain.rebuild` enqueues. `retry_hold_reason` runs `staleness()`, which is read-only database work.
- **S-4:** test-only.
- No ceiling, reservation or budget code is in the diff.

## S-4 check

- `test_w4_fmbatch1_mobile.test_mobile_owner_view` now asserts `security.requires_operator("GET", "/m")` and that `/m` is not in `PUBLIC_GET_ROUTES`.
- `test_w4_fmbatch1_useful_work.test_routes_and_cc_block` asserts the same for `/api/useful-work` and `/api/company/departments`.
- Both still keep the 401/503 status assertion. Both pass. They are additive.

## Repro summary (scratch scripts, not committed)

- **H1:** seed `Incident(signature="stale-artefact:visual_truth:a@1.0.0#1", product_slug="a", halts_publication=True)`, then run the `test_w4_prodfix` S-2 harness with `platform_policy.unreviewed_changes = lambda db: []`. The retry is held on day 1, day 2 and day 30.
- **M1:** use `test_w4_disclosedqa._certified()`. Run a fresh clear review. Set the valid certificate's position-3 job from `DETAIL` to `LIFESTYLE`. Then:
  - `review()` returns `reused: True, reviewed: True` with 0 calls, and `review_state.reviewed` is True.
  - `review(fresh=True)` returns `reviewed: False, not_clear: {"3": "unclaimed"}`.
