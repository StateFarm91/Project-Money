# Independent security review OPUS2D: `opus2/p0-revenue-workforce` @ fb52cb9e (delta from 9c1a0037)

**Reviewer:** independent, 2026-10-31 (UTC).

**Scope.** The opus2 commits after 9c1a0037 that this review was asked to cover:
- **1cc31974** fixes OPUS2B2. Its merge of Batch 4 base f4c3899b is excluded; the diff was read
  against first parent 9b8f842.
- **fb52cb9e** fixes OPUS2C.

Two further opus2 commits lie in the same range, 3232862 and 9b8f842 (DRAFT-CONSTRUCTIONS parts
2 and 3). They were not named in scope and were not reviewed, except where fb52cb9e changes the
same code.

The prior reviews are at `origin/claude/w5-SECREVIEW-OPUS2B2-9c1a003` and
`origin/claude/w5-SECREVIEW-OPUS2C-9c1a003`.

## Overall verdict

**ACCEPT for Batch 5 integration.** Every OPUS2B2 and OPUS2C finding is closed:
- F2-1 (HIGH) is closed at the root.
- F3.1 (MEDIUM) is closed on the path the review reproduced.

Nothing found here is CRITICAL or HIGH, and nothing publishes, spends or contacts a customer.
Four LOW items follow (R1–R4), plus INFO notes on how strong some tests are. I recommend fixing
them alongside integration, but none of them blocks it. Every opus2 part reviewed under
OPUS2B2 and OPUS2C is now ACCEPT.

## Verdicts

| Finding | Origin | Verdict | Mutation test |
|---|---|---|---|
| F2-1 HIGH: photo-led certificate accepted a photo `qualifying_photos` rejects | OPUS2C | **ACCEPT** (root fix; R4 test gap) | 3 of 4 killed (`ok=True`; `owner_attested` removed from `PHOTO_ATTESTATION`; "SHA ignored" combined with "always match"). **Survived:** removing only the SHA-256 comparison (R4) |
| F2-2 LOW: `camera_provenance` read from the frame's own claims | OPUS2C | **ACCEPT** (moot: attestation now comes from the rule) | covered by the F2-1 mutations |
| F3.1 MEDIUM: refused-since-success shop reported "scanned" | OPUS2B2 | **ACCEPT** (R1 residual on the anchor) | 3 of 3 killed (`failing=False`; refused/outage collapsed; anchor reverted to the old rule) |
| F1.1 LOW: pricing owner action not closed | OPUS2B2 | **ACCEPT** | killed |
| F1.2 LOW: parity row version default | OPUS2B2 | **ACCEPT** (static test only, INFO) | killed |
| F2.1 LOW: re-certification drops the withhold | OPUS2B2 | **ACCEPT** (R3 test gap) | carry disabled: killed. **Survived:** removing the `gate.quality` enqueue (the test is a source-text check) |
| F2.2 INFO: texts said "nothing blocked" | OPUS2B2 | **ACCEPT** | `certificate_changed` reverted: killed. Note wording reverted: survived (no assertion; INFO) |
| F4.1 LOW: overlapping exports double-count | OPUS2B2 | **ACCEPT** | killed |
| F5.1 LOW: no cap shared with `benchmark_refresh` | OPUS2B2 | **ACCEPT** (R2: cap is one-sided) | cap removed: killed; double ask allowed: killed |
| F5.2 LOW: declined lines come back; priceless pick | OPUS2B2 | **ACCEPT** | suppression removed: killed; priceless pick allowed: killed |
| N1.1 LOW: size-claim forms that got through | OPUS2C | **ACCEPT** (new false positives, R5) | new patterns disabled: killed; `[2-6]XL?` reverted: killed |
| N1.2 LOW: "two hook sizes" false positive | OPUS2C | **ACCEPT** | killed |
| N2.1 INFO: categories with no decoy entry | OPUS2C | **ACCEPT** | killed |
| N3.1 MEDIUM: trio drafted as one basket | OPUS2C | **ACCEPT** (wiring test gap, INFO) | refusal removed: killed. **Survived:** the pipeline passing `slug=""`, `rationale=""` |
| N3.2 LOW: flat route takes shaped categories | OPUS2C | **ACCEPT** | new words removed: killed; ornament/flower removed: killed |
| N3.3 LOW: build failures crash instead of refusing | OPUS2C | **ACCEPT** | killed |
| Test gap: vessel twin and reverse | OPUS2C | **ACCEPT** (`build_twin` and `reverse.compare` now asserted) | n/a |

## 1. F2-1 is closed at the root

`release_gates.sample_photo_lead` no longer builds any attestation of its own. It calls
`sample_photo.qualifying_photos(db, slug, version)`, the publish gate's own predicate, and the
lead qualifies only when that result lists the frame's `physical_photo_id` **and** its SHA-256.

`qualifying_photos` requires:
- an owner Command Center attestation of these exact bytes. The attestation's `by` must start
  with `owner:cc:` and its `sha256` must equal the photo's, which only
  `physical_upgrade.attest_unedited` writes;
- intake `unedited`, and not edited or AI-processed;
- not a system-made file (`_synthetic_shas`);
- a `first_customer.physical_binding` to a passed full make of this release's content hash;
- a rights basis;
- bytes on file.

Nothing of this is copied. A static test (`test_the_photo_lead_takes_its_attestation_from_the_one_rule_only`)
pins that `PhysicalTest`, `physical_class_of` and `pdetail.get("unedited")` are absent from the function.

If `qualifying_photos` raises, the lead qualifies nothing: a fail-closed `except`.

- **Intake-unedited but not owner-attested can never lead.** This is case (a) of
  `test_review_opus2c_f21_only_a_qualifying_photo_may_lead`. The certificate is invalid, no
  frame is `physical_photo_lead`, and the reason carries the rule's own words. Cases (b)
  (attestation of other bytes) and (c) (a provider-recorded SHA) are refused as well. The
  positive fixture is now attested through
  `PU.attest_unedited(actor="owner:cc:…", confirm=UNEDITED_CONFIRMATION)` and bound by content
  hash. The test no longer monkey-patches `risk_matrix`.
- **Disclosure is unchanged on the render-only and mixed paths.** fb52cb9e's only change to
  `listing_set.py` is the `PHOTO_ATTESTATION` tuple (`owner_attested` added) and the refusal
  text. `certify_disclosed`, `_with_supplements`, `certify_photo_led`'s handling of the
  render frames, and the per-frame `export_check` are untouched.

  With no lead (`sample_photo_lead` → None), `ls.certify_disclosed(**common)` runs exactly as
  before. `test_cert_listing_frames` and `test_search_hero_publish` pass.

  One behaviour to note: a frame claiming `leads_gallery` whose photo does not qualify makes
  the whole set refuse. It does not fall back to a render-only gallery. That is fail-closed and
  acceptable.

- **R4 (LOW, test gap): the SHA-256 match is the only guard against swapped bytes, and no test
  exercises it.** With the comparison `q.get("sha256") == lead.sha256` removed, all suites still
  pass.

  Probe (`/tmp/probe/sha.py`, outside the repo):
  1. Qualify and attest a photo.
  2. Point the leading `ListingAsset`'s `sha256` at other stored bytes. `qa.bytes` checks the
     frame against its own SHA, so it still passes.

  Results:
  - At fb52cb9e: `valid: False`, refused.
  - With the comparison removed: `valid: True photo_led: True`. Bytes that are not the attested
    photograph would lead the gallery as a photograph.

  The code at fb52cb9e is correct. Add this probe as a test so the line cannot regress silently.

## 2. F3.1 and the LOW items

**F3.1.** `_watched` now derives the state from the latest attempt:
- `_failed_since_success`: the state is not `ok` and the last attempt is newer than the last
  success.
- A refusal (`credential_refused` or a recorded limitation) is reported as `not_accessible`.
- An outage is reported as `attempted_not_scanned`.
- `last_successful` is kept, and `failure_reason` is always given.

The reviewer's repro is now a test (MadelineMaeCo with 40 refusals → `not_accessible`; ZKB
outage → `attempted_not_scanned`), and both shops reach `not_scanned`. The state strings match
what `watchlist.scan_member` actually writes (`credential_refused`, `source_outage`, `ok`).

- **R1 (LOW): the anchor is still reported as "scanned" while a retry is queued or running.**
  `_anchor` applies the new rule only when `fail is attempted`, where `attempted = jobs[0]` is
  the newest `mjs.scan` job *of any status*.

  Probe (`/tmp/probe/anchor.py`): a success 60 days ago, then a `ran: False` "HTTP 403" an hour
  ago, then a `PENDING` retry. Result: `state: 'scanned', failure_reason: 'ping returned HTTP 403'`.

  This recurs in every daily window between enqueue and completion. It persists indefinitely if
  the worker is down, which is exactly when failures pile up.

  Fix: choose `attempted` from finished jobs only (done, failed or dead), or test
  `fail["id"] > ok["id"]` instead of `fail is attempted`.

  This does not affect the watchlist path, which is the owner-facing majority.

**F1.1.** The resolve branch closes the matching `chain-deadend:pricing:<slug>@<version>`
`OwnerAction` through `owner_queue.close(..., SATISFIED, ...)`. No enqueue is added.

**F1.2.** `"version": ctx.job.inputs.get("version", "1.0.0")`. INFO: the test is a source-text
assertion. It discriminates, but a behavioural test would be sturdier.

**F2.1.** `withholding.carry_reverification` carries `REVERIFY_FAILED`, the `QUALITY_REVERIFY`
record (marked `carried_across_recertification`) and `SUMMARY` onto the new certificate, and a
pass on the new content clears them. This is tested behaviourally.

`_persist_release` then enqueues `gate.quality` under the idempotency key
`reverify-after-recert:<slug>@<version>:<hash16>`.

- **R3 (LOW, test gap):** that enqueue is pinned only by a source-text assertion. Removing it
  passes every suite. Add a test that drives `_persist_release` through re-certification and
  asserts exactly one `gate.quality` job.

**F2.2.** The note and `certificate_changed` (now `held["changed"]`) are corrected. The
`certificate_changed` change is tested. The note wording is not (INFO).

**F4.1.** `_non_overlapping` keeps the widest period first, per product, and drops rows whose
periods overlap. Rows with unparseable dates are kept as recorded.

**F5.1 and F5.2.** `knowledge_gaps.assess` holds back when knowledge-gap plus `benchmark_refresh:`
open actions are at least `MAX_PURCHASE_REQUESTS_OPEN = 3`. It skips a listing that
`benchmark_refresh` already asks about. It rests a line the owner closed for 56 days, and never
raises a pick with no observed price. Previously such a pick was shown as `max_cost_cad=0.0`.

- **R2 (LOW): the shared cap is one-sided.** `intel/benchmark_refresh.py` (unchanged here)
  checks only its own `MAX_OPEN = 2`. If knowledge gaps open 2 first, `benchmark_refresh` can
  still open 2, for 4 open purchase requests.

  These are owner-approval requests. Nothing is bought, so there is no spend exposure. Fix:
  have `benchmark_refresh` count `knowledge_gap:` rows against the same constant.

**N1.1 and N1.2.** All OPUS2C probe rows are pinned, and each mutation of the new patterns is
killed.

- **R5 (LOW): the new patterns over-refuse.** The failure is closed, so a correct listing is
  refused, not a false one published. Each phrase below PASSES at 1cc31974 and FAILS at
  fb52cb9e (`/tmp/probe/fp.py`, `fp2.py`):

  | Phrase | Pattern it trips |
  |---|---|
  | "Materials: 4 mm / 4.5 mm hook" | `dimension_slash` (`"Hook: 5 mm / 6 mm"` also) |
  | "You will need 2 bags of yarn." | `vessel_count` (`bags`) |
  | "Store 2 tote bags in it." | `vessel_count` |
  | "Holds 3 plant pots on a shelf." | `vessel_count` |
  | "A small and a large hook help." | `article_named` (no hook exclusion) |
  | "Repeat 2x to 4x as needed." | `named_range` (`_TOK` under `re.I` matches `2x`) |
  | "Worked from small to large rounds" | `named_range` |
  | "A tote bag pair of handles" | `vessel_group` |

  The release's own writer emits `"5mm hook"`, so generated PDFs are not affected. Listing copy
  and materials lines could be.

  Fix:
  - Apply `_HOOK_BEFORE` / `_TOOL_BETWEEN` to every pattern, not just `count`.
  - Exclude `of yarn` after `bags`.
  - Make `_TOK` case-sensitive inside `named_range`.

**N2.1.** `KNITTED_OR_CROCHETED` is applied for every category, including those with no decoy
entry.

**N3.1, N3.2 and N3.3.**
- `FC.plan` refuses a several-sizes promise found in the slug, title or rationale, reusing
  `size_claims.claims_in`.
- Ornament and flower are in `NEEDS`, and granny, hexagon, hexie and bed are in `_SHAPED_WORDS`.
- `ValueError` and `KeyError` from a construction are an audited `cir.draft_refused`
  (gate `construction`), not a crash.
- INFO: the handler's `slug=` / `rationale=` wiring is untested. The trio fixture is diverted
  upstream as a retired alias, and mutating the wiring passes. A concept whose size promise is
  only in its slug or rationale would then be drafted. Add a handler-level test with a
  non-alias seed.

## 3. No regression

- **Chain successors: no job storm.** 1cc31974 adds only an owner-action close inside the
  existing resolve branch: no enqueue, still bounded by `SWEEP_LIMIT`.

  The re-certification `gate.quality` enqueue is idempotent per release hash, and
  `handle_gate_quality` keys its four checks per slug, hash and day. One re-certification adds
  at most four new jobs, for the re-certified release. Other releases deduplicate against
  today's keys.
- **SHADOW and spend.** No new outward path: no network, publish, upload, message or purchase.
  `knowledge_gaps` writes only `OwnerAction` rows, now never priced at CA$0. The
  `test_shadow` and `test_w4_fmbatch1_retention_guard` suites pass.
- **Batch 4 merge.** `test_w4_owner_queue_race` passes. The merged `_serialise_owner_queue` is
  not opus2 code.

## Suites run

Each was run one at a time with
`cd brambleloop && PYTHONPATH=src:tests nice -n 19 python tests/<f>`, in a venv built from
`requirements.lock` and `requirements-test.lock`, at fb52cb9e. All pass.

| Suite | Result | Time |
|---|---|---|
| test_opus2_chain_deadends | 0 failed | 8 s |
| test_opus2_commercial_lessons | 0 failed | 7 s |
| test_opus2_draft_constructions | 0 failed | 9 s |
| test_opus2_knowledge_gaps | 0 failed | 5 s |
| test_opus2_laura_home | 0 failed | 12 s |
| test_opus2_photo_led_gallery | 0 failed | 308 s |
| test_opus2_reverify_withhold | 0 failed | 6 s |
| test_opus2_rim_negative | 0 failed | 1 s |
| test_opus2_scan_evidence | 0 failed | 5 s |
| test_opus2_size_claims | 0 failed | 31 s |
| test_cert_listing_frames | 0 failing | 56 s |
| test_search_hero_publish | 4/4 | 121 s |
| test_w4_launchfix | 32 passed | 27 s |
| test_vacuity | OK | 10 s |
| test_shadow | OK | 858 s |
| test_w4_fmbatch1_retention_guard | OK | 32 s |
| test_w4_owner_queue_race | OK | 49 s |

Each mutation was applied in a separate detached worktree at fb52cb9e, the named suite was run,
and the file was restored. The harness and probes are in `/tmp/probe/` (`mutate.py`,
`mutate2.py`, `anchor.py`, `sha.py`, `fp.py`, `fp2.py`) and are not committed.

## Recommended before or alongside integration (none blocking)

1. **R4:** add the swapped-bytes probe as a test of the photo-led certificate.
2. **R1:** derive the anchor's state from its latest *finished* attempt.
3. **R3:** add a behavioural test for the `gate.quality` enqueue after a carried
   re-certification.
4. **R2:** have `benchmark_refresh` honour `MAX_PURCHASE_REQUESTS_OPEN`.
5. **R5:** extend the hook and tool exclusion to the new size patterns, exclude "bags of yarn",
   and make `named_range` tokens case-sensitive.
6. **INFO:** add a handler-level test that `slug` and `rationale` reach `FC.plan`.
