# ADMIT-TO-BUILD: why admitted pool concepts never reach `cir.draft`

Branch `eng/admit-to-build`, from `claude/w6-release-19h13` (production 0aeb81d2).

## Production at 20:40Z

- The pool admitted 5 concepts at 19:56Z. 20 more were capped by the allowance and 7 were waiting on research.
- Forty-five minutes later there was no `cir.draft` for any of them. `products_in_flight` was 1 (`launch.plan`) and `offers_waiting` was 0.
- The daily ledger for 2026-11-21 shows `concepts_approved` 24, `concepts_admitted` 0 and `products_started` 0.

## Where they stop (root cause)

The path from admission to a draft is:

1. pool `admit_ready` attaches a proposal to an answered research task;
2. `radar.concept_intake` approves it, which is the ledger's `concepts_approved`;
3. `radar.score`, which applies `promotion_verdict` and then the **pre-engineering gate**;
4. `supply.offer`;
5. `supply.admit`;
6. `cir.draft`.

The gate's `premise_thumbnail` and `jury` checks need the `image_vision` capability. That
capability opens only with an **active Anthropic vision activation** (`anthropic-vision:vision`)
plus a successful vision probe under it (`gateway.anthropic.vision_usable`). D-OWNER-APPROVE-ALL
activated only `flux-3-image:generation` and `openai-vision:vision`. So every approved concept is
recorded as `concept.gate_waiting` with `waiting_on ["image_vision"]`. It is "not engineered:
waits, unpassed". Nothing is offered, so nothing is drafted.

This is reproduced in `tests/test_admit_to_build.py`. On production's fixture state, without a
vision activation, the deploy pass hands 40 concepts to `radar.score`: 30 wait on `image_vision`,
10 are refused and 0 are promoted, so there are 0 pool drafts. With a vision judge that is
activated and probed (a FIXTURE provider, never a real call), the same concepts pass the gate,
are offered and admitted, and their `cir.draft` jobs run.

### Why no further admissions happened after 19:56

`admit_ready` runs only inside `radar.concept_pool`, which runs every 6 hours (and once at boot).
The 15-minute `supply.admit` admits *offers*, and there are none. So the next pool admission is
due about 6 hours after 19:56. This is by design (allowance 5 per pass) and is not a defect. The
20 capped concepts are admitted over the next passes. Each one will then wait on the same gate
until vision opens.

## Fix in this branch

- **Readback** (`ops/production_evidence.after_admission`, under `factory_visibility.supply.after_admission_24h`): it reports, for the last 24 hours, the audit counts for intake approved, refused and withdrawn, score handoff, gate passed, waiting and refused, offered, and admitted to engineering. It also reports `radar.scored` promoted vs not promoted, the capabilities the gate waited on (keys of `build2.executor.GATE_BY_KEY`, anything else reported as `unrecognised`), and `cir.draft` jobs enqueued. It carries counts and the gate-key vocabulary only: no slug, title or reason text. After the next deploy this confirms the stop in production.
- **No gate is opened in code.** Unmeasured is never pass. Opening `image_vision` takes a paid-provider activation, which is the owner's spend authority. D-OWNER-APPROVE-ALL deliberately covers exactly two triples, and widening `ops/owner_directives.ACTIVATIONS` would mint spend authority the decision log never recorded. That decision belongs to the coordinator or the owner, not this lane.

## What unblocks P0 supply (owner or coordinator)

Activate `anthropic-vision:vision` through the normal Mission Control step-up path (passphrase
plus TOTP), with ceilings matching the existing vision activation: about CA$2/day, CA$10/month
and CA$1 per gallery, inside the CA$100/month company ceiling. The cadenced capability probe
(`capability.probes` → `gw.vision_probe`) then opens `image_vision`. `creative.regate` presents
the waiting concepts to the judge again, and the pass/refuse verdicts become offers and then
drafts within the 4-slot WIP limit.

An alternative is code work: route the gate's vision checks through the already-activated
`openai-vision` judge (`visual.d_judge`). That changes which model judges concept boards and
touches every `image_vision` consumer. It is not done here.

## Tests

The new suite `tests/test_admit_to_build.py` passes 3 of 3:
- it reproduces production;
- it shows that with vision the concepts are drafted and the drafts run;
- it checks privacy.

These suites were run with a private TMPDIR and JOBS=2: test_admit_to_build, test_supply_research, test_supply_feed, test_supply_lane, test_new_product_flow, test_factory_visibility, test_w4_readback_evidence and test_vacuity. All pass after two fixes. test_supply_lane's pinned `supply` key set now includes `after_admission_24h`, and that field's vocabulary is pinned by test_admit_to_build. The new suite's pass lines were changed to the runner's format.
