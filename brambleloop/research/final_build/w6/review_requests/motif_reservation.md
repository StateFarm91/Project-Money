# ENG-MOTIF — review request: reserve the motif-fidelity vision call

Branch: `eng/motif-reservation`, base `origin/claude/w6-INTEG2` @ `a35ad302`. The final SHA is
the commit that adds this file (see the issue #28 comment).

## The defect

`publish/motif_fidelity.py::check` called `provider.see` with no `check_budget`. The
paid-provider gate refuses a vision call that has no live reservation
(`no_budget_reservation`). The `except` swallowed that refusal as UNMEASURABLE, so
`motif_verified` was always False. Spend failed closed, but the quality gate was dead.
`tests/test_model_spend_paths.py` listed this site in `KNOWN_UNGUARDED`, with an out-of-date
note.

### A finding for Main: at this base the production callers cannot reach `check`

`owned_photography.make` (line 251) and `model_photography.make` (line 240) both begin with
`return redraw_refusal(cir.slug)`. That is F-852, from `e6b6d470`. The motif call
(`owned_photography.py:337`, `model_photography.py:343`) sits in the "historical V1
implementation retained for evidence, unreachable in production" below that return. So at
`a35ad302`:

- the release handlers (`runtime/release.py` owned handler and rung handler, and the
  model path through `listing_asset.make`) render nothing and do not reach `check`;
- `product_authority.structural_floor` never gives a generated frame `PASS`. It needs a
  qualified whole-product producer, which does not exist yet. So `usable_asset` cannot return a
  generated render whatever its motif verdict.

The defect is real and latent. It goes live as soon as `check` has a caller again: a
qualified renderer, or the V1 path being restored. The fix below is needed for that. But the
statement "every owned or model render, already paid for, comes out unusable" does not
describe production at this base, because no such render is being made. The renders that
were affected are the ones filed before F-852.

## The fix

1. **Reservation** (`motif_fidelity._call_judge`). This follows the pattern of the other vision
   judges (`photoreal.judge`, `inspect._call`, `reference.read_listing`):
   - `gw.check_budget(model, input_tokens=gw.input_tokens(system, prompt, images=2), max_tokens, agent="quality_director", purpose="asset_inspection")`.
     The same agent and purpose as `inspect_image`, which judges the same render in the same job.
     No new agent, no new allowance, no ceiling changed.
   - The estimate counts **both** images, so it is never smaller than the gate's own figure.
     Otherwise the gate would refuse with `reservation_underfunded`.
   - `check_budget` notes the reservation for the gate (`paid_provider_gate.note_budget`).
   - `release_reservation` runs on every path: at the bill on success, and without a bill on
     failure.
   - `spend_report.record` writes the cost under department `quality`. Before this, the call
     wrote no spend row at all.
2. **Fail closed with a coded reason.** Every UNMEASURABLE now carries `unmeasured` (a code) and
   `rejudge` (bool).
   - `rejudge=True` covers `budget_refused` (a `BudgetExceeded`, or a gate refusal about money),
     `gate_refused` (for example `not_activated_by_owner`), `no_accounting_store` and
     `call_failed_transient`. In each of these nothing about the picture was learned.
   - These stay `rejudge=False`: `answer_unreadable`, `call_failed`, `chart_unrenderable` and
     `image_missing`.
   - `rejudgeable()` also recognises the free-text refusals that production filed before this
     change.
3. **A paid render is re-asked about, not thrown away.**
   - Owned path:
     - `awaiting_motif(asset)` is true when asset truth is `clear`, the motif is rejudgeable,
       and `worth_rejudging` holds.
     - Such a render does not count in `ordinary_attempts`. Attempts now count once per render
       (`current_states` dedupes by the kept image's digest).
     - `what_to_do_next` returns `motif_rejudge_pending`. The handler calls `rejudge_motif`,
       which re-runs `check` on the kept bytes (`motif_fidelity.rejudge`, read through
       `ArtifactStore` by sha) and files a new `assets.owned_photography` row with
       `motif_rejudge` and `spent_cad: 0`.
     - If the call is still refused, nothing is filed and the render keeps waiting.
     - `_representative_slug` puts waiting products first, because a re-ask costs one vision
       call and a render costs an image.
   - Model path:
     - `sequence` re-asks about a frame that is waiting on its motif (`_rejudgeable_frame`)
       before it would render.
     - If the re-ask is still refused, it returns `waiting_on: motif_judgement` and renders
       nothing.
     - `attempts_for` does not count a sequence whose only open floor is product truth waiting
       on its question. It does count the `motif_rejudge_only` sequence that carries the
       answer.
   - `worth_rejudging(record)` means the structural floor, with the motif assumed to match,
     says `PASS`. At this base that never happens for a generated frame (F-852), so no vision
     call is ever spent re-asking about a redraw that could not be used. The retry path stays
     dormant until a qualified producer exists. Renders awaiting a re-ask are kept with
     `db`/`why`, so their bytes survive a restart.
   - No new audit action, so no new retention decision.

## Tests

`tests/test_motif_reservation.py` has 17 tests and is in `scripts/suite_final_segment.txt`,
before `test_product_run`, because it uses `now()`. The tests run the **real**
`AnthropicProvider` through the **real** paid-provider gate. The owner activation is the real
record, from `_paid_activation`. Only `_send` is replaced, so "nothing was sent" is counted at
the wire.

- With a reservation, the comparison is sent once and returns MATCH. The owned record carries
  `motif_verified` / `usable_as_listing_asset` from the verdict in both the MATCH and the
  mismatch case. The model frame is tested on MATCH only: `product_truth` becomes `pass` and
  the sequence becomes usable.
- With no budget (the `quality_director` day spent): UNMEASURABLE, `budget_refused`,
  `rejudge`, a `spend.refused` row, and zero sends.
- The reservation row and the `CostEntry` are `quality_director` / `asset_inspection`. The
  reservation is released at the actual cost, nothing is left outstanding, and the reservation
  covers the gate's two-image figure.
- In-test mutation: `check_budget` with `reserve=False` is refused by the gate
  (`no_budget_reservation`), with zero sends.
- `not_activated_by_owner` is coded `gate_refused`. With no db, nothing is built. An unreadable
  answer is not re-asked. Legacy production refusals are recognised.
- Owned path:
  - pending → re-asked → usable, and charged once;
  - a mismatch on re-ask is charged once;
  - still refused → nothing filed and still pending;
  - bytes gone → `image_missing`, and it stops waiting;
  - an F-852 redraw is not waited on.
- Model path:
  - a waiting detail frame is re-asked, not re-rendered (`make` is never called);
  - still refused → `waiting_on`, with zero renders;
  - an F-852 frame is charged and not waited on.

`tests/test_model_spend_paths.py`: `KNOWN_UNGUARDED` is now empty, with a note saying why. The
scan asserts `motif_fidelity._call_judge` is seen **and guarded**, and the agent/purpose/release
source check covers it. `test_cert_spend_hosts` needs no change, because `motif_fidelity`
addresses no provider host.

**Source mutation, run by hand** on a scratch copy. `check_budget` in `_call_judge` was replaced
by `{"reservation_id": None}`. 8 tests in `test_motif_reservation` failed, and 3 in
`test_model_spend_paths` failed (`..._without_the_ceiling_check`, `..._actually_there`,
`..._releases_its_reservation`).

## Suites

`cd brambleloop && JOBS=4 SUITE_REGISTRY=0 SUITES="..." PY=<venv> bash run_tests.sh`, with
venv from `requirements.lock` + `requirements-test.lock` and no PYTHONPATH. The run covered 44
suites: the required list, plus every suite that greps for `owned_photography`,
`model_photography`, `motif_fidelity` or `_representative_slug`.

**Result: TOTAL PASSING 811, suites failing 0, TMP leaked 0** (run record
`20261119T171410Z-22076`, 2026-11-19T17:31:13Z). The run started on `bb3bdd92`, with a working
tree whose uncommitted changes are exactly what `58ba3455` commits. This file's commit changes
only this file.

The first run found two problems, both fixed in `58ba3455`:
- `test_cost_governance_wave2`: the new `owned-rejudge-` work-directory prefix was missing from
  `ops.health.TEMP_PREFIXES`. It is now registered.
- `test_motif_reservation`: the harness could not read the suite's own output format. The
  tests passed, but the passes were not counted.

Suites: test_cert_design_pipeline test_cert_intel_wave test_cert_intel_wave2 test_cert_parity_copy test_cert_spend_hosts test_cost_governance_wave2 test_etsy_oauth_callback test_executor test_fb2_i_repairs test_final_visual_authority test_funding test_gallery_escalation test_launch test_model_identity test_model_photography test_model_spend_paths test_motif_fidelity test_motif_reservation test_owned_photography test_parity_realism_reader test_portrait_repair test_provider_trial test_reliability test_seasonal_cycle test_serp test_vacuity test_w3_spend_attribution test_w3_tmp_hygiene test_w3_visual_rnd_guard test_w4_c07_f441_handlers test_w4_c2_visual test_w4_close5_rows test_w4_controlled_experiments test_w4_department_work test_w4_departments test_w4_fmbatch1_providers test_w4_fmbatch1_retention_guard test_w4_fml_checkpoint_adoption test_w4_gatesi test_w4_resume_runner test_w4_spend_attribution test_w4_spenda_k5a test_w4_visref test_w4_wraptest

## Residual / not done

- The owned and model `make` functions stay unreachable (F-852). This change does not
  re-enable generative redraw.
- If an owned render's asset-truth *inspection* was also refused for budget (`verdict:
  unjudged`), the motif re-ask does not rescue it. That render is charged as an attempt. Only
  `clear` renders wait. Re-asking about inspection is `visual.inspect`'s own retry question.
- A run of `motif_rejudge_pending` keeps the owned cadence on one product while the
  `quality_director` day is spent. That is intended: rendering other products whose motif
  nobody can judge would buy unusable images.
