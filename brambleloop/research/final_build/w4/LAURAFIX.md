# W4-LAURAFIX: Laura's CEO briefing was cut off at the output cap

Branch `claude/w4-LAURAFIX` from `c498888` (the code running in production). No deploy, no
production POST, no spend. All model calls in the tests go to stub transports.

## Defect

The owner tested this in production. Laura's CEO briefing showed "Model synthesis unavailable:
model call failed (MalformedModelOutput)". It then fell back to a deterministic briefing that
listed hundreds of repeated technical incidents. The evidence pack held 231 records.

## Root cause (production numbers)

`/api/spend-report` shows that task `laura.ceo_briefing@3` made 1 call:

- **tokens_in 29,629**
- **tokens_out 600**, which is exactly `routing.TASKS["laura.ceo_briefing"].max_output_tokens`
- billed **CA$0.136905**
- Laura's CA$0.50/day cap held

The v3 prompt asked, for each component, for "the ids ... of the additional records that best
answer it". It set no upper bound, and the model could choose from up to 231 ids. About 200 of
those records were open incidents, and most of them repeated a few failures: one row per
occurrence, each with its own signature (for example ops.sentinel StringDataRightTruncation
x15, dead letters and image errors).

The JSON reply ran past the 600-token cap and was cut off. `parse_model_json` was right to
refuse it, but the error was reported as a generic `MalformedModelOutput`. The fallback then
printed every incident row as its own line.

**Reproduced.** I ran the new regression test against `c498888`. The pack had 232 records. The
stub reply was cut at 600/600 tokens with `stop_reason=max_tokens`. The briefing read "Model
synthesis unavailable: model call failed (MalformedModelOutput)", the same failure as
production.

## Fix (at the root)

1. **The request is bounded (prompt v4).** For each component, the prompt now asks for at most
   K ids, where K is the number of optional picks the renderer actually shows.
   `briefing.pick_limit(comp, CAP_LEVELS[0])` computes it, and `model_lines` uses the same
   function:
   - last_window: 6
   - departments: 6
   - blockers: 6
   - autonomous: 4
   - decisions and facts_unknowns: 0. Code renders these sections in full, so the prompt no
     longer asks for them.

   The prompt lists the ids that can be selected for each component, leaving out the mandatory
   records. `validate()` keeps the first K optional ids in a fixed way and records how many it
   `trimmed`.
2. **The output cap is computed.** See "Computed token bound" below.
3. **Truncation has its own name.** `ModelResponse.stop_reason` was added. The Anthropic
   provider reads `body.stop_reason`, and the replay encode/decode keeps it. When a reply fails
   to parse, the gateway checks whether the provider reported `stop_reason == "max_tokens"`, or
   reported no stop_reason while output_tokens reached the cap. In either case it raises
   `OutputTruncated`.
   - `OutputTruncated` is a subclass of `MalformedModelOutput`, so every existing handler still
     catches it.
   - The call is still billed.
   - The fallback label now reads: "Model synthesis unavailable: model output truncated at the
     1472-token output cap (stop_reason=max_tokens; 1472 tokens written)".
4. **Smaller input: incidents are grouped before the pack is built.** `incident_groups()`
   reads every open P0/P1/halting row, with no 200-row cap. It groups them by severity, by
   whether they halt publication, and by root cause. The root cause is taken from the first of
   these that exists:
   - the incident's own `root_key`, `dedupe_key` or `root_cause`
   - job_type plus error class
   - the signature and summary, with timestamps, uuids, hex ids and instance numbers masked

   Each group becomes one record:
   `open P1 incident (15 occurrences, first at ..., last at ...): <latest summary>`.
   Every mandatory incident still appears as its group, with its count. Lower-severity
   incidents are still counted in the "+N more" line.
5. **Fallback layout.** The fallback uses the same grouping and the existing section caps, so
   each repeated incident is one line.
   - The fallback still says it is deterministic and gives the exact reason.
   - Facts gain the fields `occurrences`, `first_seen`, `last_seen` and `examples` (up to 5
     example ids, each with its source and time). No field was removed.
   - `synthesis` gains `truncated` and `incidents` (`{raw, groups, lower_severity, open_total}`).
   - In the Command Center, the Laura evidence list shows a nested `<details>` for each group.

## Computed token bound

`gateway/laura_briefing.output_token_bound(PICK_LIMITS)` works it out as follows:

1. Start from the longest reply that still follows the v4 contract: all 6 components, K ids
   each, every id at the widest width (`E9999`), pretty-printed at indent 4, inside a ```json
   fence. That reply is **1,161 bytes**:
   - each id line takes 21 bytes
   - each section skeleton takes about 95 bytes
2. A token covers at least one byte under any BPE tokenizer, so the reply is at most 1,161
   tokens.
3. 1,161 x 1.25 headroom = 1,451.25, rounded up to a multiple of 64 = **1,472**.

The value 1,472 is set in three places: the `routing.TASKS` literal, `PROMPT.max_output_tokens`
and the computed value. A test fails if they ever differ.

On the production-shaped pack, the compliant stub reply measured **211 tokens** (`end_turn`).

## Prompt size, before and after

These figures are the gateway's own estimate (characters / 4) for the production-shaped test
data:

| | Records | Input tokens | Padded estimate |
|---|---|---|---|
| c498888 shape (`group_incidents=False`) | 232 | 12,649 | CA$0.1049 |
| v4, grouped | 51 | 3,966 | CA$0.0594 |

The input is 3.2x smaller. The padded estimate now mostly reflects the worst-case 1,472-token
output allowance; a real compliant reply is about 200 tokens.

Production's real summaries are longer, which is why production measured 29,629 tokens in. The
saving there scales with the number of repeated incidents. With 1,013 incident rows, the pack
stays at 51 records (7 groups), and the input is about 3,990 tokens, which is under the routing
table's `typical_input_tokens` of 6,000.

## Files changed

- `src/brambleloop/core/resilience.py`: `OutputTruncated` and `truncation()`
- `src/brambleloop/gateway/model_gateway.py`: `ModelResponse.stop_reason`; a reply that fails
  to parse and was truncated raises `OutputTruncated`
- `src/brambleloop/gateway/anthropic.py`: reads `stop_reason`; encode/decode keep it
- `src/brambleloop/gateway/laura_briefing.py`: prompt v4, the computed bound, the selectable-ids
  block, and the truncation reason
- `src/brambleloop/gateway/routing.py`: `laura.ceo_briefing` max_output_tokens changed from 600
  to 1472 (computed, with a comment)
- `src/brambleloop/laura/agency/briefing.py`: `PICK_LIMITS`/`pick_limit`, `selectable`,
  `prompt_values`, trimming in `validate`, incident grouping (`incident_root`,
  `incident_groups`), the fell-back count, and the new fact/synthesis fields
- `src/brambleloop/app/command_center/static/js/views/laura.js`: expandable group evidence
- `tests/test_w4_laurafix_truncation.py`: new, 8 tests
- `tests/test_w4_laura1_briefing.py`: the method pin changed from `@3` to `@4`. The version bump
  is part of the fix, and the assertion still pins the exact version. No other assertion
  changed.

## Tests (focused, via `testslot.sh`)

| File | Result |
|---|---|
| `test_w4_laurafix_truncation.py` | 8/8. Covers: reproduction; (a) bounded request + trim to K; (b) compliant reply under the computed cap; (c) truncation named, both by stop_reason and by inference, and billed; (c2) provider stop_reason plumbing; (d) the fallback groups repeats and keeps every mandatory incident; the cost estimate shrank; a 1,013-record set on both paths |
| `test_w4_laura1_briefing.py` | 19/19 |
| `test_w4_laura1_budget.py` | 4/4 |
| `test_w3_laura_*.py` (21 files) | all exit 0 |
| `test_w4_finhealth.py` | 11 passed |
| `test_vacuity.py` | passed |
| `test_cost_governance_wave2.py` | passed |

I also ran the gateway-adjacent tests because the gateway and provider changed:
`test_gateway.py`, `test_model_provider.py`, `test_rc1_spend.py`,
`test_w4_spend_paid_discipline.py` and `test_w3_spend_laura_phrase.py`. All exit 0.
