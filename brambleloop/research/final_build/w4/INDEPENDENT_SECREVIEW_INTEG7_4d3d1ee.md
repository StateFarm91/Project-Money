# Independent review: INTEG7 follow-up 4d3d1ee (fixes for H1, M1, L1 of dbb4ebf)

| Item | Verdict | Why |
|---|---|---|
| **H1** S-2 retry hold deadlock | **CLOSED. SHIP** | The prior repro is now retried on day 1, day 2 and day 30. Every genuine hold I tried still holds: an unreviewed policy change, a product tamper incident, a customer pattern defect, a systemic halt with integrity evidence, and a systemic halt with a second widespread family. No safety gate is bypassed. The hold is a CA$0 enqueue throttle, and publication still reads every incident. |
| **M1** S-1 reuse key | **CLOSED. SHIP** | Reuse now requires identical bytes, certified job, exact claim (with families for identifying jobs), describer model and user prompt. An unclaimed or missing job never reuses. I could not construct a reuse that approves an image for a claim that was never judged. Residuals are L2 and L3 below (low, deploy-triggered). |
| **L1** failed grid reading reused | **CLOSED. SHIP** | A transient grid failure is asked again on the next run. A real `blocked` grid reading is still reused. |
| **Tests** (Q4) | **NOT WEAKENED** | Edits only add to tests. The new tests fail when H1, M1 (claim key, unclaimed guard) or L1 is reverted. Four sub-parts of the M1 fix survive mutation (L4). |
| **Paid paths and ceilings** (Q5) | **SAFE** | There is no new paid entry point and no ceiling or budget code in the diff. Every call that re-runs still goes through `gw.check_budget`. There is one bounded cost inefficiency (L5). |
| **Overall** | **SHIP** | No blocker. L2 to L5 are follow-ups. |

Reviewer: an independent reviewer who did not write the code. Date: 2026-10-27 (UTC). The review was read-only: no production calls, no secrets, no deploys, nothing spent. Stub providers only.

## Scope and method

- **Diff:** `git diff dbb4ebfe..4d3d1ee8` (branch `claude/w4-INTEG7`). It covers 5 files, +224/−26:
  - `publish/release_gates.py` (`retry_hold_reason`)
  - `visual/exported_review.py` (`review`, `_basis`, `review_state`)
  - `tests/test_w4_prodfix.py`, `tests/test_w4_disclosedqa.py`
  - `INTEG7.md`
- **Prior review read in full:** `INDEPENDENT_SECREVIEW_INTEG7_dbb4ebf.md` (branch `claude/w4-SECREVIEW-INTEG7-dbb4ebf`). I re-ran its repros.
- **Code also read:**
  - `ops/incident_lifecycle.systemic_evidence` / `kind_of` / `escalate_systemic`
  - `gates/incidents.IncidentTracker` (signature construction, `open_incidents`)
  - `ops/artefacts` (`SENTINEL_SIGNATURE`)
  - `visual/inspect.describe_image` / `identify_at_grid` / `describe_prompt`
  - `gateway/routing.route` and `gateway/anthropic.provider_for`
  - `ops/publication_authority` (the reader of `review_state`)
  - every `Incident(` / `open_or_restate` producer, checked for `stale-artefact:` signatures
- **Environment:** a fresh venv built from `brambleloop/requirements.lock` + `requirements-test.lock`. Each suite ran at `nice -n 19`, one at a time.

| Suite at 4d3d1ee | Result |
|---|---|
| `tests/test_w4_prodfix.py` | 8/8 OK |
| `tests/test_w4_disclosedqa.py` | 12/12 OK |

## Q1: is H1 closed?

**Yes.** `retry_hold_reason` (`release_gates.py:1318`) now reads the product's open halting incidents directly, plus `systemic-halt:%`. It drops:

- every `stale-artefact:` signature;
- `SYSTEMIC_SIGNATURE`, but only when the live `systemic_evidence` is staleness-only: no integrity failure, and the widespread families are exactly `{"stale-artefact"}`. Evidence and rows are read in one session, and unreadable evidence never waives.

The only producer of `stale-artefact:*` signatures is `ops/artefacts.sweep` (`:811`, `:828`). Customer defect signatures start with the product slug (`gates/incidents.signature`), so they cannot take on the prefix.

| Repro (`h1.py`, scratch) | Result |
|---|---|
| Prior repro: only `stale-artefact:visual_truth:a@1.0.0#1`, first rebuild ended | retried on day 1, day 2 and day 30, `retry_held` empty |
| Stale rows of every class + `stale-artefact:backlog` + staleness-only systemic halt over 3/3 products | not held |
| Unreviewed `publishing` policy change (alongside a stale row) | **held** (policy) |
| `authority_chain_tamper:a` (product) | **held** |
| Customer pattern defect `a@1.0.0:body:row4` (halting) | **held** |
| `release.version_immutable:a@1.0.0` | **held** |
| Systemic halt + `authority_chain_tamper:x` (slug-less) | **held** (`systemic-halt:publication`) |
| Systemic halt whose evidence is stale-artefact **and** a second widespread family | **held** |
| Staleness-only systemic estate + a **non-halting** tamper row elsewhere | **held** (the integrity evidence denies the waiver) |
| Lookalike signature `a@1.0.0:text:stale-artefact` (not a prefix) | **held** |
| Resolved tamper incident | not held |
| Publication while a sentinel row is open | still halted (`IncidentTracker.publication_halted`) |

**Can a real safety hold be bypassed? No.** I found no input that waives a non-staleness incident. More fundamentally, `retry_hold_reason` is not a safety gate. It only withholds a CA$0 `chain.rebuild` enqueue. Publication is still refused by `publication_gate` / `IncidentTracker`, which still count every halting row, the sentinel's included (`staleness()` keeps `halted`, `reasons` and `blocks` unchanged). The worst a wrongly-lifted hold can do is run a free rebuild that `store.publish` then refuses.

I3 below records two conservative or timing edges. Neither is a bypass.

## Q2: is M1 closed?

**Yes, for everything M1 named.** `_basis` (`exported_review.py:153`) records, per position: `sha256`, the certified `job`, and the exact `JOB_CLAIMS` dict (with `identifies_as: families` for `DESIRE`/`ANGLE`). It also records the describer: the routed model and a hash of `describe_prompt()`. It is normalised through JSON, so it compares equal to the filed copy.

Reuse requires all of the following:

- `filed.basis == basis`;
- every basis claim is non-null;
- the filed frame set equals the basis set;
- no frame is `unreviewed`, and no grid reading is undescribed.

`review_state` additionally refuses when the filed jobs differ from the certificate's (`:227`). Old rows without a `basis` never match.

| Attempt (`m1.py` / `m1b.py`, scratch) | `reused`, paid calls, `reviewed` |
|---|---|
| Baseline, nothing changed | reused, 0, True |
| **Prior repro A:** position 3 `DETAIL → LIFESTYLE` (unclaimed) | not reused, 6, **False** `{"3": "unclaimed"}`, and the same again on the next run (never reused). `review_state` is False even before `review()` runs. |
| `DETAIL → CONSTRUCTION` (a different job with an identical claim dict) | not reused, 7, True. `review_state` is False until it is re-judged. |
| `DETAIL → ANGLE` (now identifying, gains families) | not reused, 7 |
| Frame with an empty job | not reused, 6, False (unclaimed), and again |
| Claim removed from `JOB_CLAIMS` by a "deploy" | `review()`: not reused, `unclaimed`, False |
| Claim made stricter | not reused, 7 |
| Product families changed | not reused, 6, `{"1": "blocked"}` |
| Describer model changed (routing) | not reused, 7 |
| `describe_prompt()` changed | not reused, 7 |
| **`DESCRIBE_SYSTEM` changed** | **reused, 0, True** (L2) |
| **`GRID_PX` changed** | **reused, 0, True** (L2) |
| **Deterministic `compare()` made stricter** | **reused, 0, True** (L2) |
| `review_state` right after a claim is removed or changed, before `review()` re-runs | **True** (L3) |

**Could I make reuse approve an image for a claim that was never judged? No.** Every way of changing which claim a frame is judged against changes the basis:

- relabelling the job;
- adding, removing or altering a claim;
- changing the families;
- leaving a job missing.

A null claim is excluded outright. The residuals are different: the claim is the same, but the system prompt or the deterministic judging rules changed (L2); or the publish-side reader trusts an old verdict until `review()` next runs (L3). Both need a code deploy. Neither can be triggered by data or by re-certification.

## Q3: is L1 closed?

**Yes.** `entry["grid"]["described"]` is now filed (`:135`), and reuse refuses a frame whose grid reading has `described is False` (`:92`).

| Repro (`l1.py`, scratch) | Result |
|---|---|
| Hero grid call raises `TransientError("503")` | filed `{"1": "unjudged"}`, `grid.described: False` |
| Next `review()` | not reused, 7 calls, `reviewed: True` |
| Next `review()` after that | reused, 0 calls |
| A genuine `blocked` grid reading (`described: True`) | reused, 0 calls, still `blocked` (a real answer is not re-bought) |

Rows filed before this change have no `described` key and default to `True`. They also have no `basis`, so they never reuse anyway.

## Q4: was any test weakened? Do the new tests fail with each fix reverted?

**Not weakened.**

- `test_s1_changed_or_undescribed_frames_are_reviewed_again` now also rewrites the filed `basis` sha for position 1. This is necessary, because the basis is now the key. Without it, the "other bytes" setup would no longer represent other bytes. Its assertions are unchanged.
- `test_s2_a_staleness_only_refusal_is_not_held` gains the sentinel-row assertion.
- No assertion was removed or relaxed anywhere in the diff.

**Mutation results** (each fix reverted alone in a scratch worktree, then the touched tests run):

| Mutation | Caught by |
|---|---|
| `release_gates.py` reverted to dbb4ebf (H1) | `test_s2_a_staleness_only_refusal_is_not_held` **FAIL**, `test_h1_..._retried_not_held` **FAIL** |
| `exported_review.py` reverted to dbb4ebf | `test_m1_...` **FAIL**, `test_l1_...` **FAIL** |
| Claim dropped from the basis | `test_m1_...` **FAIL** |
| "Never reuse an unclaimed job" guard removed | `test_m1_...` **FAIL** |
| L1 `described` check removed | `test_l1_...` **FAIL** |
| Job dropped from the basis | **survives** (L4) |
| `identifies_as` families dropped from the basis | **survives** (L4) |
| Describer (model and prompt) dropped from the basis | **survives** (L4) |
| `review_state` job comparison disabled | **survives** (L4) |

## Q5: is there a new paid path or a ceiling bypass?

**No.**

- The diff touches no gateway, budget, reservation or ceiling code.
- `retry_hold_reason` does database reads only.
- In `exported_review.review`, every call that re-runs goes through `describe_image` / `identify_at_grid`, which both reserve with `gw.check_budget` (agent `quality_director`, purpose `asset_inspection`) before calling and settle afterwards. I observed the ceiling binding in the scratch harness: after many forced reviews on one database, calls were refused, frames were filed `unreviewed`, and nothing was spent.

The fixes do make re-judging more frequent than at dbb4ebf. That is intended, and it is no more frequent than the pre-INTEG7 behaviour of re-judging on every run. Two consequences are worth noting: L5, and the inefficiency inside L1 that it re-buys all six describes, not just the grid.

## Findings

### L2 (Low, Product Truth, fail-open after a deploy). The basis omits the system prompt, the grid size and the deterministic judging code

- **Where:** `visual/exported_review.py:153-179` (`_basis`). It hashes `describe_prompt()` only. It records neither `inspect.DESCRIBE_SYSTEM`, nor `commerce.thumbnail.GRID_PX`, nor any version of `inspect.compare` / `identification` / `parse_description`.
- **Scenario (reproduced):** file a clear review, then deploy one of these changes:
  - a new `DESCRIBE_SYSTEM`;
  - `GRID_PX` 230 → 120;
  - a `compare()` that flags an additional problem.

  In each case the next `review()` returns `reused: True, reviewed: True` with 0 calls, so the old verdict stands under rules that no longer apply. The filed frame keeps only the verdict, not the description, so the new rule can never be applied retroactively.
- **Impact:** the claim judged is the right one, but under superseded judging rules. Only a code deploy triggers it. Data and re-certification cannot.
- **Fix:** add `DESCRIBE_SYSTEM` (hashed), `GRID_PX` and a `JUDGE_VERSION` constant to the basis's `describer`. Bump `JUDGE_VERSION` whenever `compare` / `identification` / `parse_description` change. A hash of `inspect.py`'s source would also work. Add a test that changes each of these.

### L3 (Low, Product Truth, pre-existing, publish-side). `review_state` does not compare claims or the describer

- **Where:** `visual/exported_review.py:195-235` (`review_state`), read by `ops/publication_authority.py:206` and `store.publish` parity. It checks shas and (new) jobs. It does not check the claim or describer basis.
- **Scenario (reproduced):** file a clear review, then remove `JOB_CLAIMS["DETAIL"]` (or make it stricter) in a deploy. `review_state(...)["reviewed"]` stays **True** until something calls `review()` again. Only `listing.seo` does that (`runtime/release.py:1325`), and a deploy does not necessarily enqueue it. C-80 says a frame with no claim must block, and here the publish read passes it.
- **Not a regression:** `review_state` was equally blind before INTEG7, and the prior review only asked for `(sha256, job)`. Recorded because the brief requires every materially relevant input.
- **Fix:** in `review_state`, recompute `_basis(certified order, product_families(authoritative_cir))` (free and deterministic) and require it to equal the filed `basis`. Treat a row without a basis as not reviewed. This also makes the job comparison redundant.

### L4 (Low, test coverage). Four parts of the M1 fix survive mutation

- Dropping the job, the identifying families or the describer from `_basis`, or disabling `review_state`'s job comparison, leaves every test green.
  - `test_m1` relabels to `NO_SUCH_JOB`, which changes the claim to `None` too, so only the claim key is exercised.
  - The new claim-changed case covers claims only.
- **Fix:** add these cases to `test_m1`:
  - relabel to a different *claimed* job with an identical claim dict (`DETAIL → CONSTRUCTION`), and assert not reused and `review_state` False before re-review;
  - change `product_families`;
  - change the routed model;
  - change `describe_prompt`.

### L5 (Low, cost, bounded). A release with an unclaimed job re-buys every other frame's description on every run

- **Where:** `exported_review.py:87-88`. "Never reuse when any claim is null" re-runs the whole review, so every *claimed* frame is described again (6 paid calls in the repro), even though the unclaimed frame blocks deterministically whatever the model says.
- **Bound:** the daily retry runs at most once a day per product and passes `check_budget`. `test_every_job_the_certificate_exports_has_a_registered_claim` keeps today's catalogue clear of unclaimed jobs.
- **Fix:** when any basis claim is null, file or return the `unclaimed` block without calling the describer. Do the same for L1: re-ask only the failed grid reading rather than all frames.

### I1 (Info). An unknown describer can match a filed unknown describer

`_basis` sets `model = None` when routing raises. Its comment says this "never matches a filed one", but `None == None`. Reproduced only with an injected provider: in production `provider_for` would raise as well, so every frame files `unreviewed` and is never reused. Use a sentinel that never compares equal, or refuse reuse when `model is None`.

### I2 (Info, carried over from dbb4ebf). `**filed` is still spread last in the reuse result

`exported_review.py:94-97`. No current key collides. Spread `filed` first so the computed `reviewed` / `not_clear` / `why` always win.

### I3 (Info, S-2 timing edges, conservative or pre-existing)

- **A systemic row stays open after its evidence is gone.** `staleness_only` is False, so the retry is held until `escalate_systemic` reconciles the row. This fails closed, and it is short-lived.
- **A slug-less integrity incident filed before escalation.** `authority_chain_tamper:<ACTION>` is filed slug-less. It is not seen by the per-product hold until `escalate_systemic` opens the systemic row. The publication gate has the same scope, and the hold is not a safety gate.
- **The policy hold fails open.** An unreadable `unreviewed_changes` gives no hold. The publication path re-reads it.

## Repro scripts (scratch, not committed)

- **`h1.py`:**
  - stubs `rebuild_graph.rebuild_set = _plan` and `unreviewed_changes = []`, then seeds the incident sets in the Q1 table;
  - runs `rebuild_graph.enqueue(..., hold=retry_hold_reason)` across day 1, day 2 and day 30.
- **`m1.py` / `m1b.py`:**
  - use `test_w4_disclosedqa._certified()` and wrap `etsy_ops.certified_images` / `certified_frames` to relabel position 3;
  - mutate `JOB_CLAIMS`, `inspect.product_families`, `routing.route`, `inspect.describe_prompt`, `inspect.DESCRIBE_SYSTEM`, `thumbnail.GRID_PX` and `inspect.compare` in turn;
  - `m1b.py` re-runs the last three on a fresh database, because the scratch ceiling bound after about 15 forced reviews in `m1.py`.
- **`l1.py`:** a provider that raises `TransientError` only for the `grid_*.png` image, and a stub `identify_at_grid` returning a described `blocked` reading.
- **Mutation testing:** a scratch `git worktree` at 4d3d1ee, one string replacement per mutation, running the named test functions directly.
