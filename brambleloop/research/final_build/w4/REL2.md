# W4-REL2: a25a377 security findings and October's model-spend waste

- Date: 2026-10-19 (UTC). Branch `claude/w4-REL2`, from `origin/claude/w4-INTEG2` (`9c3812bd`).
  Production is `1b21e81`, and this branch does not touch it.
- Sources:
  - Security: `INDEPENDENT_SECREVIEW_a25a377.md` on `origin/claude/w4-SECREVIEW-a25a377`.
  - Spend: the October model-spend review (729 `creative.concept_field` calls, CA$19). Its
    file:line references are on `origin/claude/final-candidate-a25a377`, whose `src` is
    identical to this branch's base.
- Regression tests: `tests/test_w4_rel2.py`, 23 tests. Each test is named after the finding
  it closes.
- Constraints honoured:
  - No limit was raised.
  - No model-selection policy or routing tier changed.
  - No capability was disabled.
  - No gate was weakened: #108, #110, the pre-engineering gate, the containment check and the
    HMAC verification are unchanged, and each is still the deciding check.
  - Prompt versioning stays pinned. `concept_field@2` is still registered, and `@3` is new.

## A. Security (independent review of a25a377)

| ID | Finding | Fix (file) | Regression test |
|---|---|---|---|
| M1 | Each unauthenticated webhook refusal inserted one `audit_log` row, and the public `GET /api/etsy` iterated them all in Python. | Each refusal is an **upsert** on one counter row per reason, in a new table `etsy_webhook_refusals`. The reasons are a closed, code-defined set, and any other reason is counted as `other`. At most **one sampled audit row per reason per hour** is written (`etsy.webhook_refusal_sampled`). The sample slot is claimed with a conditional UPDATE, so concurrent refusals write one row between them. `summary` aggregates in SQL: the counters, plus the legacy one-row-per-refusal audit rows `GROUP BY detail['reason']` (`integrations/etsy_webhooks.py`). | `test_m1_a_refusal_flood_is_counted_not_stored_per_request` (540 refusals give 2 counter rows and 2 audit rows), `test_m1_the_sample_reopens_after_the_window_and_unknown_reasons_cannot_grow_the_table`, `test_m1_summary_aggregates_legacy_refusal_rows_in_sql`, `test_m1_existing_refusal_semantics_are_unchanged` |
| L1 | The 64 KiB cap was checked only after `await request.body()` had buffered the whole body. | New `etsy_webhooks.read_body(stream, content_length)`. A declared `Content-Length` above the cap is refused (413) **before a byte is read**. A non-integer or negative length is refused (400). Otherwise the body is read from `request.stream()` with a running cap. The route counts the refusal through `refuse()`, and `verify` keeps its own size check as defence in depth (`app/main.py` webhook route). | `test_l1_a_declared_oversize_body_is_refused_before_a_byte_is_read`, `test_l1_an_undeclared_or_understated_body_stops_at_the_running_cap`, `test_l1_l2_the_route_refuses_oversize_and_non_ascii_cleanly` |
| L2 | `hmac.compare_digest(str, str)` raised TypeError on a non-ASCII signature header, which gave a 500. | The comparison is now on bytes. The header value is encoded with `utf-8`/`surrogateescape`, so it can never raise. The compare is still constant-time and any `v1,` entry may still match. | `test_l2_a_non_ascii_signature_is_a_refusal_not_a_type_error` (é, ÿþ, ☃ and a lone surrogate each give 401 `bad_signature`, and a valid entry next to one is still accepted). The route test sends latin-1 header bytes. |
| I3 | Attribution evidence had no length cap. | `finance/sources.MAX_EVIDENCE_CHARS = 2000`. Longer evidence is **refused**, not truncated. | `test_i3_attribution_evidence_is_capped` |
| I2 | A future code path could label generated imagery INFOGRAPHIC or PATTERN_PREVIEW and so skip the realism checks. | A test now pins the behaviour: `has_model` forces photographic, and so do unknown classes and roles. It also pins the reviewed set of source files that name those asset classes, so a new assigner fails the test and must be reviewed. | `test_i2_the_lighter_visual_path_is_chosen_only_by_deterministic_builders` |
| I1 | The refusal reason and `configured` are public. | No change. The review rated this acceptable: no secret material is disclosed. | n/a |
| I4 | The event-wake scan reads every order. | No change. This is a performance note only, and the fix is not trivial. Idempotency already prevents runaway enqueues. | n/a |

## B. Model-spend waste

Unit costs used below:
- From the October data: 729 `concept_field` calls cost CA$19, so CA$0.026 a call (the cheap
  ideation tier).
- From the code's own padded estimators:
  - `construction_reading` is CA$0.13 at the routing estimate and CA$0.25 padded with image
    tokens.
  - `gallery_observation` is CA$0.064 padded; the measured mean is about CA$0.034.

These are estimates from October's counts, not measurements of the new code.

### B1. Seasonal-sentinel tournaments re-asked the same question

There were 99 tournaments but only 22 distinct (arena, brief) pairs. The dedupe key was
`mjs.at_risk:{benchmark}:{event_id}:{day}`, which gave one tournament per MJs listing, and
every listing in an arena was asked the same brief.

**Fix:**
- `runtime/release.py` (`mjs.seasonal_sentinel` handler) groups the events that need a
  tournament by `mission_runtime.tournament_group(pod, arena, target event)`. It enqueues one
  tournament per group, keyed `mjs.at_risk:{pod}:{arena}:{target}:{ISO year}-W{week}`.
- The job carries `mjs_event_ids` and is attached to **every** event in the group. If the key
  is already queued this week, the existing job is looked up and attached.
- `intel/mission_runtime.seasonal_sentinel` (formerly :1758): an at-risk event with no
  tournament borrows its group sibling's tournament instead of asking for a new one.
- Pending-job reprioritisation also matches `mjs_event_ids`.
- The tournament's `advance_pipeline` walks every event in the group.

**Tests:**
- `test_b1_a_sibling_with_a_tournament_lends_it_to_its_group`
- `test_b1_the_handler_buys_one_tournament_per_group_per_iso_week`: 6 events in 2 groups give
  2 tournaments, every event is bound, the key is exact, and the next day buys nothing.

**Saving:** about 77 of 99 sentinel tournaments were repeats, roughly 78 %. If sentinel
tournaments carried most of October's concept_field spend, this is about **CA$12-15/month**.
Downstream judging and intake of the duplicate winners is avoided as well.

### B2. Winners refused by free gates after the field was paid for

In October, 46 winners failed #110 ("declared no motifs") and 29 failed #108 ("generic form").

**Fix:**
- **Prompt (pinned bump).** `gateway/prompts.py` registers `creative.concept_field@3`, and
  `prospecting.PROMPT` points to it. v3 adds two lines:
  - `Season motif grammar`: the season's non-cliché motifs, spelled the way
    `intake.motifs_for` reads them, plus the clichés that never count on their own.
  - `Silhouette`: for a generic form, the qualifier-carrying constructions buildable in the
    slot and the premise words `intake.qualifiers_for` reads; for an outline form, "no
    qualifier is required".

  v2 stays registered, and the immutability guard still refuses edits in place.
- **Slot skip.** `prospecting.qualifier_possible(slot)` is false for a generic form when none
  of its buildable, engine-routed constructions carries a qualifier. `field()` (formerly
  :1143) and `expedition()` skip such slots, and `field` reports them as
  `skipped_generic_slots`. In today's tables every generic form has at least one
  qualifier-carrying construction, so this is a guard for future vocabulary changes.
- **Selection.** `creative/ideation.select(..., free_gates=)` with
  `intake.free_gate_check(concept, arena=)`, used at `release.py` (formerly :5002/:5009) and
  in the expedition path:
  - `free_gate_check` builds exactly the brief fields `brief_for` would (`motifs_for`,
    `season_of`, the new shared `qualifiers_for`). It then runs the **same**
    `preengineering._silhouette` and `_motif_grammar` gates.
  - The winner is the best shortlisted concept that passes those gates, in the existing order
    of preference: skill gap, then the role/window pool, then the rest of the shortlist.
  - If none passes, the old order stands and intake's gate refuses as before.
  - The screen is recorded in `free_gate_screen`.

**The gates are unchanged:**
- The #108 and #110 code was not touched.
- `brief_for` now calls the extracted `qualifiers_for`, which is the identical expression.

**Tests:**
- `test_b2_concept_field_v3_names_the_motif_grammar_and_the_qualifiers`
- `test_b2_a_generic_slot_no_construction_can_qualify_is_skipped`
- `test_b2_free_gate_check_is_the_gate_itself`
- `test_b2_selection_picks_the_best_shortlisted_concept_that_passes_the_free_gates`

**Saving:** this is waste avoided rather than cash cut. In October 75 of 99 winners were
refused, so about CA$14 of the CA$19 bought nothing usable. After B1 the remaining field spend
is about CA$4/month, and B2 should turn most of it into gate-passing winners. That is roughly
**CA$3/month** of spend that becomes useful, plus the repeat tournaments that refused arenas
used to trigger. The input grows by roughly 150 tokens per call, which adds less than
CA$0.01/month at the cheap tier.

### B3. Repeat runs asked the same questions

`asked` (formerly `prospecting.py:1157`) restarted at 0 in every run. As a result,
`_crosses_for` (formerly :708) walked the same first pairings every day.

**Fix:**
- A new table, `prospecting_brief_cursors`, holds one row per (event, pod, form).
- `brief_offset` and `advance_brief_offset` persist the walk with an upsert.
- `field()` seeds `asked` from the table and advances it after each batch.
- `expedition()` passes the persisted offset and advances it.
- The start index stays stable, so the walk is still deterministic.

**Test:** `test_b3_repeat_runs_ask_new_questions`. Three runs ask three different briefs, the
offset is 18, and run 2's brief equals `_brief_for(slot, 6, offset=6)`.

**Saving:** no direct cash cut. It removes repeat fields that the research stage kills as
`sameness`, which were 58 of 78 deaths in the first tournament. It compounds with B1.

### B4. construction_reading crashed daily and re-bought readings

**Fix (`creative/reference.py`):**
- **Refused readings are recorded and not re-bought.**
  - A `ReferenceRefused` from `read_listing` is recorded as an audit row
    `creative.construction_reading_refused`. This covers containment, non-JSON, closed
    vocabulary and empty answers, all of which occur after the call has been paid.
  - The row keeps only the refusal class and the image key, never the refused text.
  - `run()` skips a listing that has such a row (`skipped_refused_readings`).
  - Transient or provider errors are not recorded, so they are still retried.
- **The refusal is now per department.** `brief()` is wrapped per department, and a refusal
  is reported in `decompositions_refused` instead of ending the job.
- **Breakdowns are stored again.** `primitives()` checks each value against the same
  containment check. A depicting value is **withheld** (listed in `withheld`, never stored)
  instead of refusing the whole decomposition. The joint check on what remains still runs.

**Tests:**
- `test_b4_a_refused_reading_is_recorded_and_not_bought_again`: the second run makes no new
  call, and the refused text is not stored.
- `test_b4_one_departments_depiction_refusal_does_not_stop_the_others`: both departments are
  stored, the depicting value is withheld, and a forced refusal in one department leaves the
  other stored.

**Saving:** each refused listing bought daily cost about CA$0.13-0.25 per day, so
**CA$4-7.5/month per listing**. At the cap of `READS_PER_RUN = 6`, the worst case was about
**CA$23-45/month**. The bigger gain is the department decompositions, which were not being
refreshed at all and are now stored daily again.

### B5. gallery_observation parse failures

Assistant prefill is rejected by the current models (it returns a 400 on Sonnet 5), so this
fix uses **structured output**:
- `AnthropicProvider.see(..., json_schema=)` sends
  `output_config.format = {type: json_schema, schema}`.
- `intel/vision.observation_schema()` is the closed vocabulary:
  - every field is optional;
  - `shot_type` is an enum;
  - `additionalProperties: false`.
- `analyse` passes the schema to any provider whose `see` accepts it. Test fakes and other
  callers are unchanged.
- `parse_observation` still checks every answer, and the parser is not loosened.
- The schema is part of `method_version()`, so the F-309 systematic-failure breaker treats
  this as a new method.

**Test:** `test_b5_gallery_observation_requests_json_schema_output`. It covers the payload
shape, the absence of prefill, unchanged behaviour without the schema, and capability
detection.

**Saving:** each parse failure was a paid image, about CA$0.034 measured. With F at the
monthly count of parse failures, the saving is about **CA$0.034 × F**. Each failure also
re-queues the image until `FAILED_ATTEMPTS`, so up to that multiple of F is avoided. F was not
available in this worker's evidence, so it is not stated here.

## Totals (estimated, CA$/month)

| Item | Estimate | Basis |
|---|---|---|
| B1 | 12-15 | 77/99 repeated sentinel tournaments × October's concept_field spend |
| B2 | about 3 made useful (waste avoided, not cash) | 75/99 refused winners on the post-B1 spend |
| B3 | 0 direct | fewer repeat (sameness) fields; compounds with B1 |
| B4 | 4-7.5 per refused listing; worst case 23-45 | 30 days × padded or routed reading cost |
| B5 | 0.034 × F (×up to FAILED_ATTEMPTS) | measured cost per image |

## Unresolved, and what this branch does not claim

- **Estimates only.** None of the savings is measured. They need a month of production
  ledger after the merge, compared by purpose against October.
- **Two counts were not available to this worker:**
  - the gallery parse-failure count F;
  - the split of concept_field spend between sentinel and other tournaments.
- **I4 (the event-wake scan) is not changed.**
- **Older refusal rows are kept.** The legacy `etsy.webhook_refused` audit rows stay as they
  are (the audit log is append-only), and `summary` still counts them in SQL.
- **No production writes or deploys.** The new tables (`etsy_webhook_refusals`,
  `prospecting_brief_cursors`) are created by `create_all`/`checkfirst` on first use.
