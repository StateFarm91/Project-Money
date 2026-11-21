VERDICT: NO STAGE FAILS ON THE CURRENT CHAIN, BECAUSE NO ATTEMPT EVER REACHED IT. The deploy retry that 19h4 made possible reused that UTC day's retry key. The earlier ~12:57Z retry, which ran on pre-marketing code, already held that key. So 01ab8df3's 14:57Z sentinel got DuplicateJob, swallowed it and reported "retry_waiting": enqueued 0, waiting 18, unfinished 0. FIXED: each deploy that reopens the window gets its own retry key. Reproduced on the real chain in production's shape. Production rows were NOT read; that this is what production did is inferred from the readback figures and the code, and the post-deploy check below settles it.

# Review request: eng/halt-380-live

**Branch:** `eng/halt-380-live`, cut from `eng/rebuild-outcomes`, which is cut from
`claude/w6-release-19h9` (a391995). It therefore contains the visibility change
(REBUILD-OUTCOMES.md). Deploy that branch first if it should go alone. Not merged, not
deployed, no PR.

**Evidence basis:** the brief's 15:01Z figures, `release/DEPLOYED_HISTORY.json` and the
code. I read no production rows, no token-gated readback and no Railway variable values.

## Reading the 15:01Z figures exactly

| Figure | Reading |
|---|---|
| `last_propagation` enqueued 0, retry_waiting 18 | The 14:57Z sentinel on 01ab8df3 enqueued no attempt and no retry for any product. |
| unfinished 0 | No first pass or verify pass is pending. A retry enqueued at 14:57Z would still be pending (its verify runs 20 min later), so none was enqueued. |
| `rebuilds_verified_24h` 0 | No verify pass bound a rewritten row in 24 h. This is consistent with the last attempts having run before eng/halt-380-marketing. |
| chain.rebuild 7 d done 199 → 260 | That count is every `chain.rebuild` job, **including the hourly whole-catalogue `chain_rebuild` cadence and verify passes**. It does not show a targeted attempt after 14:45Z. `rebuild_outcomes` (eng/rebuild-outcomes) will show the latest targeted attempt's age and kind per product. |
| stale incidents unchanged at 112 | Nothing was rebuilt after the marketing fix went live. |

## The mechanism (code facts)

1. `rebuild_graph.enqueue` (per product): the product's first-attempt key is taken, so it
   takes the retry path, `_retry_key` → `job_key(f"{key}:retry", now.date())`. That is one
   key per UTC day.
2. 19h4 (12:21:43Z) changed `_recent_rebuild_slugs` to count RETRY_AFTER from the current
   commit's first boot, "so each deploy gets one immediate retry per product". The key was
   left daily.
3. The 2026-11-21 sequence:
   - The chain moved at 19b (02:06Z), and the first attempts ended unverified.
   - The first sentinel after 19h4 (~12:57Z) retried every product under
     `…:retry:2026-11-21`. That retry ran on 19h4–19h8 code, before
     eng/halt-380-marketing (19h9, 14:35Z / 01ab8df3, 14:45Z), and ended unverified.
   - 01ab8df3's sentinel (14:57Z) found the window reopened, since the retry had ended
     before this deploy. It computed the same `…:retry:2026-11-21` key, which raised
     DuplicateJob, which hit `except DuplicateJob: pass`. The product was not in flight, so
     it was reported as `retry_waiting`.
4. Nothing else enqueues an attempt at an unchanged change. The next retry would have come
   at 2026-11-22 00:00Z+ (a new date), so **no attempt could run on the marketing fix
   before tomorrow**.

This also answers "which stage fails". On the current chain, the attempt
(`pricing.position` → `listing.seo` → `launch.plan` → `marketing.schedule`) never starts.
When it does run, test_halt_380_marketing and the new suite show every stage completing in
production's shape.

## Fix

- **`rebuild_graph.retry_stamp(db, now)`:** the UTC date, plus the running commit (first 12
  alphanumerics) when that commit's first boot is inside RETRY_AFTER. A deploy's retry
  therefore has a key of its own.
  - A re-run within one deploy (another sentinel, a boot sweep, a restart of the same
    commit) is idempotent: the first boot counts.
  - With no deploy inside the window, or with an unknown or `dev` identity, the key is the
    plain daily one, unchanged.
  - It is computed once per `enqueue` call.
- **`retry_spent`:** a retry key that is already used is now named (`retry_spent`, which is
  a subset of `retry_waiting`) in the result, in the `ops.rebuild_propagated` audit
  (`rebuild_retry_spent`) and in the evidence (`last_propagation_retry_spent`). "Spent" can
  now be told apart from "waiting out RETRY_AFTER".

**Not touched:**
- RETRY_AFTER and REBUILD_MAX_ATTEMPTS. Every retry is still an attempt at the same change,
  so a third failed attempt holds the product with its named reason, as before. The new
  test asserts this for the published-copy product.
- the rebuild-incomplete hold, the binding rule, verify attempts and delay;
- parking;
- the systemic thresholds and denominator;
- release_gates, the kill switch, budgets, child safety, the PDF standard and every
  certification gate.

Published content is never retired (eng/halt-380-marketing is unchanged). No test was
weakened or skipped.

**Trade-off, stated:** each deploy now gets its one retry per product, as 19h4 intended. On
a day with many deploys, a product whose rebuild genuinely fails will use its 3-attempt
budget sooner and be held sooner, with the named reason. That is the designed outcome for a
rebuild that cannot succeed.

## Tests

New suite `tests/test_halt_380_live.py` (declared in `scripts/suite_final_segment.txt`; the
real chain reads today):

- `test_retry_stamp_is_per_deploy_only_when_the_deploy_reopened_the_window`:
  - no identity, never booted, and a deploy older than RETRY_AFTER all give the plain date;
  - two deploys on the same day give two distinct keys;
  - a restart of the same commit keeps its first boot's stamp;
  - a stamp is stable within one deploy, and keys fit the column.
- `test_production_sequence_a_second_deploy_the_same_day_retries_and_converges`, on the
  real chain with production's 12-product marketing shape, replays:
  - the chain move: first attempts end;
  - a 19h4-like deploy: every product retried, ended, `rebuild-incomplete` at 2 attempts,
    systemic halt open;
  - a second deploy the same UTC day, then its sentinel.

  It asserts:
  - all 12 are retried, none is spent, and a second sentinel in the same deploy enqueues
    nothing;
  - after the drain, `rebuild_outcomes` shows for every product a `retry` attempt,
    `pricing.position` done, `marketing.schedule:done` in its chain, no `marketing.blocked`,
    and a verify pass with nothing outstanding;
  - the one exception is the product with published out-of-plan copy, which keeps 1
    marketing name outstanding and is held at 3 attempts;
  - the only open rebuild-incomplete row is that product's, and the systemic halt resolves.

  On base, the third sentinel retries nothing.

RESULTS_PLACEHOLDER

## Post-deploy readback check (inferred vs observed)

At the first sentinel after deploy (at most about 1 h, sooner with the boot sweep):
- `last_propagation_retried` should be about 18 and `last_propagation_retry_spent` 0.
- unfinished should be > 0 for about 1 h.

After about 1–1.5 h (stage chain plus up to 3 × 20 min verify):
- `rebuild_outcomes.by_product.<slug>` should show `attempt.kind` `retry`, `age_h` < 2,
  `chain` reaching `marketing.schedule:done`, and an empty `by_class.outstanding`;
- `rebuilds_verified_24h` should rise;
- `stale_incidents.by_class.marketing_asset` should fall after the next sentinel.

**If it does not:**
- if `retry_spent` is non-zero on the first post-deploy sentinel, the stamp did not change:
  read `runtime.started` for the commit;
- if attempts run and stay unverified, the per-product `rebuild_outcomes` names the stage,
  status, error class, refusal codes and outstanding states, which is the next defect.

## Open

1. `chain.rebuild 7 d done` mixes cadence scans, first passes and verify passes. It cannot
   show attempt progress. `rebuild_outcomes` is the reading to use.
2. The 2 core-stale products: whether their core stage is refused by a real gate is still
   unknown. Their `rebuild_outcomes.refusals` and `incident.parked` will name it.
