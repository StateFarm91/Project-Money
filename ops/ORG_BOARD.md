# Brambleloop operator board

Company-wide execution state. The Visual Department is reported separately at the bottom,
because the owner asked for business progress and image progress not to be read as one
number. Maintained by the integrator at each integration point. Anything unverified says so.

---

## THE DEPENDENCY DAG, AND THE FINDING THAT SHAPES IT

Classified from `brambleloop/src/brambleloop/build2/requirements.json`, the authoritative
registry, cross-checked against the live board at `/api/build2`. 320 requirements:
**227 covered, 45 partial, 28 owner-gated, 20 data-gated. 70.9% complete.**

The parallelisation premise was that Visual is holding the company up. **It is not, and the
registry says so plainly.** Of the 45 remaining executable requirements:

| parked on | count | what it means |
|---|---|---|
| `customers` | 22 | needs real buyers. Cannot be honestly completed in Shadow Mode |
| `owned_surfaces` | 7 | needs a real website / Pinterest presence to exist |
| `live_listings` | 6 | needs listings actually live on Etsy |
| *(not parked)* | 4 | **all four are Visual-owned** — #72, #75, #130, #202, model identity and the parity gate |
| `rendered_pages` | 2 | Visual-dependent |
| `physical_proof` | 1 | needs a physical sample made by hand |
| `benchmark_purchases` | 1 | needs a purchased competitor pattern |
| `tester_roster` | 1 | needs real testers |
| `image_generation` | 1 | Visual-dependent |

**Only 3 of 45 are blocked on imagery.** 41 are blocked on the real world. And every one of
those 41 already HAS its system built — the `owned_surfaces` items are each backed by
existing code (`growth/pins.py`, `growth/clusters.py`, `growth/video.py`, `growth/tools.py`,
`growth/free_to_paid.py`, `commerce/preproduction.py`). They are partial because the
remaining half is real-world input, not unwritten code.

So the honest statement is the uncomfortable one: **parallelising around Visual does not
release a large backlog, because the backlog was never waiting on Visual.** The chain to
revenue is imagery -> listings -> customers -> the 22 customer-parked requirements. Visual
is on the critical path; the parallel work is real but smaller than the directive assumed.

That is why the departments below were dispatched against work the registry does NOT yet
contain — the children's category, deliverable QA, shop readiness, reliability — rather than
against parked registry items. Forcing a customer-parked item to "done" without customers
would manufacture completion, which is forbidden, and would also lie to us about how close
launch actually is.

---

## DEPARTMENTS

Wave 2 as authorised closed on 2026-09-25: **all four business lanes returned, were reviewed,
merged and re-verified, and the suite is green at 3,647 with 0 failing.** Wave 3 was dispatched
the same day rather than leaving a ready lane idle.

| department | active task | blocker | launch-critical | worktree | spend | state |
|---|---|---|---|---|---|---|
| **Visual** | Wave 3: Kaldor-2010 plastic rest-state migration, corrected recovery experiment, ASTM convergence and a re-derived B | Stage 0 DEFERRED by owner D7; Stage 1 not to begin on knit analogy alone | **YES** — critical path | isolated | CA$0 | RUNNING |
| **Children's Safety Deliverable** | Wave 3: render the required statement set in the customer document and gate it | fibre content is not a CIR field; may return a specified CIR change rather than make one | **YES** — the last deliverable gap on two of three Launch-0 products | isolated | CA$0 | RUNNING |
| **Etsy / Commerce** | Wave 2 complete: transport closed, `image` part-name defect found, `updateListing` has no price | **OWNER ACTION**: one browser OAuth, 15 min, CA$0 | **YES** | merged | CA$0 | MERGED 48d1be5 |
| **Pattern / PDF / Deliverable QA** | Wave 2 complete: both terminologies ship; UK gauge and UK method were wrong; licence had a fourth copy in the PDF | none | **YES** — it is the product | merged | CA$0 | MERGED 07c07aa |
| **Reliability / Cost Governance** | Wave 2 complete: cadence derived from the ceiling, per-agent permissions, durable reservations, retention | needs the deploy for one additive table | protects everything else | merged | CA$0 | MERGED (this branch) |
| **Catalogue / Product Planning** | NOT DISPATCHED | would collide with the children's lane in `products/launch0.py` | indirect | — | — | held |
| **Analytics / Learning** | NOT DISPATCHED | 0 genuinely ready; the rest needs real customers | no | — | — | dispatching would manufacture completion |

Two departments the owner listed are deliberately not running, on the owner's own rule against
agents that exist to look busy. Customer Experience stays folded into Etsy/Commerce.

---

## CONCURRENCY SAFETY, AS ENFORCED

- **Module ownership.** Visual owns `src/brambleloop/visual/**` and `src/brambleloop/cir/**`
  exclusively. Every department carries an explicit read-only instruction on those, and an
  instruction to STOP and report rather than change the CIR contract.
- **Isolation.** Each department has its own git worktree and branch. `.claude/worktrees/`
  is gitignored — it is working state, never repository content. (It was briefly committed
  as embedded gitlinks in 128e869 and removed immediately after.)
- **One merge queue.** The integrator is the only path into `claude/repository-setup-nc9x6o`.
- **Serialized production.** No department may deploy, redeploy, restart the service or
  change production variables. Production access is GET-only. Deployment is the integrator's
  alone and stays production-observed.
- **Shared ceilings.** Every department is dispatched at CA$0 with no spend authority, so
  the global ceilings cannot be raced. Reliability is specifically tasked with checking
  whether the ledger WOULD hold under concurrent spend, because that guard has never been
  exercised by more than one agent at once.
- **Single writer for the record.** Only the integrator edits `BUILD_STATE.md`,
  `DECISION_LOG.md` and this board; departments write to `brambleloop/research/`.

---

## VISUAL DEPARTMENT — reported separately, deliberately

Milestone D: **FAIL.** Unchanged and not weakened.

Verified: out-of-plane relaxation preserves Product Truth — 42/42 linked, 49/49 shaped, yarn
length change +0.0000%, cantilever agreeing with beam theory to within 6%, intrinsic width
invariant at -0.03% while projected width moves +2.76%. The fabric still reads as a
corrugated relief rather than cloth.

Current activity: RESEARCH ONLY per owner instruction. The hypothesis — that conformability
needs yarn sliding through loops, requiring material coordinates that move relative to
discretisation vertices — is explicitly NOT being implemented until the literature shows what
established methods actually do and the smallest bounded experiment is designed.

Two items closed honestly as NEGATIVE results:

1. **The recovery test was invalid as run.** Released with gravity off, intrinsic height
   stayed at +2.74% against +2.81% loaded. That is not evidence of permanent deformation:
   `rest_is_relaxed_shape` takes rest curvature from the shape at the START of the call, so
   releasing gravity left the DRAPED shape as its own rest state and there is no restoring
   force by construction. The experiment cannot detect recovery either way. It needs
   re-running against the original flat rest curvature, and until then the +2.81% extension
   is neither confirmed elastic nor confirmed permanent.
2. **ASTM D1388's 41.5 degree criterion is unreachable at this swatch size**, and the data
   say something worse than that:

   | overhang | 27.5mm | 39.4mm | 51.2mm | 63.0mm |
   |---|---|---|---|---|
   | tip angle | 7.7 deg | 6.8 deg | 5.8 deg | 4.9 deg |

   Tip angle FALLING monotonically as overhang grows is physically backwards — a longer
   cantilever must droop more, not less. It is the signature of under-convergence: a longer
   overhang has more material to move and 3000 iterations gets proportionally less of the
   way there. So the ASTM route is not merely unreachable here, it is not yet trustworthy at
   this iteration count. Every bending length quoted so far therefore rests on the
   small-deflection inversion, which is now named as an approximation rather than relied on
   silently.


---

## WHAT THE INTEGRATOR FIXED DIRECTLY, 2026-09-25

Three defects of the recurring family, each found while verifying somebody else's work:

1. **Make-time could not see `Component.make`.** A set of four coasters reported the make-time
   of one. Two separate corrections existed and both were wrong — `launch0.make_time`
   multiplied the FIRST component's twin by the total piece count, and
   `calibrate_from_samples`, the only route from assumed to *measured*, did not correct at all.
   The count is now required and cannot be defaulted.
2. **The claim checks never read the designer notes.** "No long floats for small fingers to
   catch" on a fabric with no floats in it — literally true, describing stranded colourwork,
   offered as child-safety reassurance for a hazard the product does not have. The checker
   existed and the twin held the fact; the text was never passed in.
3. **`motif_fidelity.chart_colours` counted stitch codes.** 13 of 16 catalogue patterns work
   two stitches and two colours, so the wrong instrument returned the right number; the three
   single-colour textured products reported 2, 4 and 3 colours. Every verdict now also carries
   `colour_test`, because both MATCH branches claimed the colours agreed even when the judge's
   description carried no count to compare.

## OWNER ACTION REQUIRED — one item, 15 minutes, CA$0, no fee

Authorise the Etsy app once in a browser: register the app, set the exact https callback, put
`ETSY_KEYSTRING` / `ETSY_SHARED_SECRET` / `ETSY_REDIRECT_URI` in the environment, open the
authorize URL the probe prints, capture `ETSY_REFRESH_TOKEN`. Detail in
`brambleloop/research/ETSY_TRANSPORT.md` section 5.1.

**Why it must be the owner:** Etsy has no key-only route to a write scope. **No fee is
involved** — Etsy charges on publication, which none of this work performs. Consequence of
waiting: every Etsy write stays unexercised against the real API, so three launch blockers stay
open on missing evidence rather than on missing capability.
