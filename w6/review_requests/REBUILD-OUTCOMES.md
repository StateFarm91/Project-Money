VERDICT: VISIBILITY ONLY. `factory_visibility.rebuild_outcomes` reports, per product, what the latest targeted rebuild attempt did: stage, chain, verify checks, artefact-class counts, refusal codes and parked gate. No behaviour changes. Ship this first so the next readback can show why attempts end unverified.

# Review request: eng/rebuild-outcomes

**Branch:** `eng/rebuild-outcomes`, cut from `claude/w6-release-19h9` (a391995, which records
19h9 ad57efc). Not merged, not deployed, no PR. The change is read-only: one new function and
one new key in `factory_visibility`. No handler, gate, queue or schema change.

## Why

Production 01ab8df3 at 15:01Z showed the following:
- `chain.rebuild` 7 d done rose from 199 to 260, so attempts run;
- unfinished 0 and `rebuilds_verified_24h` 0;
- 12 `rebuild-incomplete` rows and 18 products retry-waiting.

So attempts run on the fixed code and end unverified. The evidence carried no per-attempt
outcome, so nobody could say which stage failed.

## What it adds

`GET /api/readback/evidence` → `factory_visibility.rebuild_outcomes`:

```
{"window_days": 7, "products": N,
 "by_product": {"<slug>": {
   "attempt":  {"kind": sentinel|retry|hold_released|legacy_restart|other,
                "status": <job status>, "error_class": <class|null>, "age_h": h,
                "refused": bool},
   "stage":    {"enqueued": gate.certify|assets.build|pricing.position|none|other,
                "status": <status|not_found|null>, "error_class": <class|null>},
   "chain":    ["pricing.position:done", "listing.seo:done", "launch.plan:dead", ...],
   "chain_errors": {"launch.plan:KeyError": 1},
   "verify":   {"checks": n, "by_status": {...}, "last_check": n},
   "by_class": {"completed": {cls: n}, "outstanding": {...}, "retired": {...},
                "unbound": {...}},
   "outstanding_states": {"stale": n, "unproven": n, "no_row": n, ...},
   "verified_pass_seen": bool,
   "refusals": {"marketing.blocked": n, "gate.blocked": n, ...},
   "marketing_blocked_codes": ["#172", "#173"],
   "incident": {"open": bool, "held": bool, "attempts": n, "parked": <gate action|null>}}}}
```

- **The latest attempt** is the newest targeted `chain.rebuild` first pass of the slug in
  the window (a job with `artefacts` and no `verify`). Whole-catalogue scans are excluded.
- **Verify passes** are the jobs whose `requested_by` is that attempt.
- **The stage** is the attempt's own `outputs.stage` and `outputs.stage_job`.
- **The chain** is every `gate.certify`, `assets.build`, `pricing.position`, `listing.seo`,
  `launch.plan`, `marketing.schedule` and `listing.package` job of the slug from the stage
  job onward.
- **Refusals** are audits by the attempt's own chain (`job_id >=` attempt) on the slug's
  artefacts. An older attempt's refusal is not counted.
- **Bounds:** 7 days and 50 products, with 5 bounded queries per request. The section sits
  in the existing `factory_visibility` try/except, so a failure reads `{readable: false,
  error_class}`.

## Privacy

Only fixed vocabulary leaves: slugs (already in the evidence), job types, job statuses,
artefact class names, audit action names, exception class names (`error_class`, the
existing reader) and `#NNN` reason tags. No inputs or outputs, error text, reason text,
artefact keys, idempotency keys or incident text are returned. Unknown classes, stages,
actions and states read `unrecognised` or `other`.

## Tests

New suite `tests/test_rebuild_outcomes.py`, 3 tests, all passing:
- **End to end.** Two products. The first has a retry superseding a sentinel attempt; the
  retry's pricing ran, `launch.plan` died with KeyError, there were 3 verify checks, the
  last naming 2 marketing outstanding (one stale, one no row), 1 pricing completed and 1
  frame retired, plus a `marketing.blocked` (#172, #173), a `gate.blocked`, and a parked,
  held rebuild-incomplete row. An older attempt's refusal is excluded. The second product
  is a dead hold-released attempt whose stage job does not exist (`not_found`).
- **Privacy.** A secret placed in inputs, outputs, last_error, audit reasons, incident
  summary and held text appears nowhere in `factory_visibility` or in the evidence's
  `factory_visibility` section, and neither do keys, idempotency keys or tracebacks. Other
  pre-existing evidence sections (`stale_artefact_rebuilds.*_reasons`) already carry reason
  text by design. They are unchanged and not this branch's concern.
- **Empty, and unreadable.** An empty estate reads as an empty dict, and an exception
  reads as `{readable: false, error_class}`.

Also run, all passing (SQLite; dirty tree, so not a release-eligible record):
`test_factory_visibility` (2/2), `test_w4_readback_evidence` (23/23), `test_vacuity`,
`test_evidence_perf` (7/7). The new suite is not timing-sensitive
(`suite_checkpoint.detect_timing_sensitive` returns nothing), so it needs no
final-segment declaration.

## Reading it after deploy

For each of the 12 products, the question is which of these holds:
- `stage.status` is not `done`: the stage itself fails, and `error_class` says how;
- `chain` stops before `marketing.schedule`: the stage named by the last entry ended the
  chain, and `refusals` names the gate;
- `marketing.schedule:done` with `marketing_blocked_codes` present: it was refused;
- `outstanding_states` shows what the remaining names read.
