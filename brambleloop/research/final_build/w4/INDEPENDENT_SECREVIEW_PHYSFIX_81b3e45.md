# Independent security and integrity review: PHYSFIX delta 5 at `81b3e45c`

- **Subject:** `claude/w4-PHYSFIX-PHOTO` at `81b3e45c`. It contains `claude/w4-PHYSFIX` at `8c049934`, whose fix commit is `5f7ee773`, merged with `origin/claude/w4-INTEG8-next`.
- **Prior review:** `INDEPENDENT_SECREVIEW_PHYSFIX_e3fd0b0.md`, findings R18–R21.
- **Reviewed:**
  - `git diff e3fd0b0e..81b3e45c`, non-merge changes. The only source change is `5f7ee77`. Merge `8c04993` touches only `COORDINATION.json`. Merge `81b3e45` brings in test additions only.
  - The branch against integration (`git diff origin/claude/w4-INTEG8-next...origin/claude/w4-PHYSFIX-PHOTO`).
- **Date:** 2026-10-31 (UTC).

## Verdict: **DO NOT SHIP**, because R18 is not closed

The commit fixes the first half of R18 (hold order). The second half (identical pieces) is still open, in both directions:

- A cosmetic reorder still moves the digest (**R22**).
- The new multiset sort makes two physically different designs share one digest (**R23**).

This is the same failure class and the same severity as R18: Medium and latent. No Launch-0 CIR has holds today. The prior round required changes at this severity, so this round does too.

The fix is small. A fail-closed interim is given under R22. Once R22 and R23 are closed, the remaining findings are Low or Info, and **none of them blocks shipping**.

| ID | Severity | Finding | Status |
|---|---|---|---|
| R18 (a) | — | hold-list order leaked into the digest | **fixed** |
| R18 (b) → **R22** | **Medium (latent)** | reordering two identical pieces that *hold* stitches, and whose holds are resumed by different pieces, still moves the digest | **open** |
| **R23** | **Medium (latent)** | the final multiset sort maps a real geometry change onto another design's digest, so a real change is hidden | **open** (introduced by `5f7ee77`) |
| R19 → **R24** | Low | `growth_ops.creators_reading` still counts owner-made rows as a tester's delivered tests | open |
| R20 | — | `_tester_recruited` counts only independent agreements; the test change is legitimate | **fixed** |
| R21 | — | the CA$59.65 line in the listing package is gone | **fixed** |
| **R25** | Low (latent, pre-existing) | the compiler accepts a piece that resumes its own hold, which is a cycle | open |
| **R26** | Info | `physical_truth` shows the ref on an owner-made row as "tester"; the vendored `owner/gate_clearance_business.json` still holds `max_cost_cad: 59.65` | note |

## 1. R18: the digest under ordering and real changes

### Fixed: hold order

Each piece's holds are now sorted by `(at_row, from_stitch, count)` before `hold#j` is assigned, and the sorted list is fed into the hold-name map. The compiler's `HOLD_OVERLAP` check means two holds in one compiled piece cannot tie on that key, so the order is total. Probe 2 from the prior review now keeps the digest, and the author's test asserts it.

### R22 (Medium, latent): identical *holding* pieces still leak list order

The new code comment says:

> "Tied pieces that themselves hold stitches are identical, so which of them a resume points at is immaterial."

That is true of the object, but not of the digest:

- `names` and `holds` assign `piece#i` / `piece#i/hold#j` from the stable sort over pre-resume content. Among tied pieces, that is the CIR list order.
- A piece that resumes a tied piece's hold records that positional label.
- The final `pieces.sort(...)` re-orders the dicts, but it cannot change the labels already written into them.

So when two identical holding pieces are resumed by pieces that are *not* identical, swapping the holding pieces in the component list moves the digest.

Two common real constructions have exactly this shape:

- left and right fronts with armhole holds, picked up by sleeves that differ;
- a chain of identical joining strips.

The exploit is the same as R18: re-list the components of a halted design, and `publication_halted(content_hash=...)` no longer matches. A later passing make of the reordered copy can also lift the original halt through `resolve_halts_disproved_by`.

**Reproduce:** run `/tmp/probes/r18.py` (listed in the appendix) from `brambleloop/`.

| Probe | Construction | Edit | Expected | `81b3e45c` |
|---|---|---|---|---|
| P1 | identical panels `L(hl)` and `R(hr)`; `s1` (1 row) resumes `hl`, `s2` (3 rows) resumes `hr` | list `R` before `L` | same | `f998c69f17e8` → `f8a215466d30` **LEAK** |
| P1b | same as P1 | `s1` and `s2` swap holds (same object, because `L ≡ R`) | same | `f998c69f17e8` → `f8a215466d30` **LEAK** |
| P2 | chain `p → A → B → end`, where `A ≡ B` before resumes | list `B` before `A` | same | `33266f317f82` → `fcf939df96d7` **LEAK** |

The author's new test does not cover this. In it, the straps (the resumers) are identical, and the only holding piece is unique.

### R23 (Medium, latent): the multiset sort hides a real change

A piece's dict does not carry its own positional label. After the final sort, the digest therefore keeps only the *multiset* of `(content, resumes-label)`. It does not keep which tied piece owns which label. Two designs that differ only in which tied piece a third piece hangs from can then encode identically.

| Probe | Design | Digest |
|---|---|---|
| P5 D1 | panel holds `a` (stitch 8) and `b` (stitch 14). `X1` resumes `a` and holds `xa`. `X2` resumes `b` and holds `xb`. The long piece `W` (3 rows) resumes `xa`; `T` (1 row) resumes `xb`. | `535a73583f40` |
| P5 D2 | the same, except `W` resumes `xb` and `T` resumes `xa`. The long piece now hangs from stitch 14, not stitch 8: a **real** change. | `29779b6020fc` (moves, correct) |
| P5′ | D2 with `X2` listed before `X1` | **`535a73583f40`, equal to D1: a real change is hidden** |

Consequences:

- A size halt on D1 also blocks D2. That direction fails closed.
- A passing make of D2 (re-listed) **lifts D1's halt** through `resolve_halts_disproved_by`, although the measured object is different. That direction fails open.

R23 is introduced by `5f7ee77` itself: before the final sort, P5′ and D1 did not collide.

### Fix for R22 and R23

The resume structure is a forest:

- every hold is resumed by exactly one piece (enforced by `HOLD_ABANDONED` and `HOLD_CONTESTED`);
- every piece resumes at most one thing.

So the exact fix is a canonical tree encoding (AHU):

1. A piece's canonical form is its pre-resume content plus the sorted list of `(canonical hold geometry, canonical form of the piece that resumes that hold)`.
2. The design is the sorted list of the root pieces' forms.
3. Pieces resumed by component name rather than by hold are children in the same way.

No positional labels are needed, and both directions hold by construction. The cycle in R25 must be refused first, by the compiler, or by the digest returning `None`.

**Fail-closed interim** (acceptable, because no Launch-0 CIR has holds): `design_digest` returns `None` when two pieces tie on pre-resume content and either of them holds stitches. Callers already fail closed on `None`. The interim must keep the author's straps test green, because there the tied pieces hold nothing.

Add P1, P1b, P2 and P5′ as permanent tests.

### Other attempts that found nothing

- **Non-dict hold, or non-numeric `at_row`:** `h.get` or `float()` raises inside `design_geometry`. `design_digest` catches it and returns `None`, so it fails closed.
- **Hold renames, `into` offsets, distinct-piece reorders, and changes to `from_stitch` or row count:** behave as in the prior review. The author's test passes, and so do prior probes 5–11.

## 2. R19 and R20: every reader of testers and recruits

Readers checked:

- `quality/testers.from_db`, `quality/testers.plan`
- `build2/executor._tester_recruited`
- `ops/owner_queue.tester_status`
- `ops/truth` (the `tester_roster` section)
- `quality/physical_truth`
- `runtime/growth_ops.creators_reading`
- `growth/creators.scaling_decision`
- `quality/tester_programme.independent_agreement`
- `app/main` `/api/tester/agreement`

### R19

`testers._counts_as_tester` excludes a row when either of these holds:

- `measured.owner_made` is set;
- the row's ref is `"owner"`.

Both `from_db` and `plan` apply it, so R19 is fixed for the roster and the planner.

**R24 (Low).** `physical.record` stores `tester_ref = report.tester_ref or "owner"`. An owner-made make can therefore carry a real tester's ref, for example `tester-1`. `growth_ops.creators_reading` reads every `PhysicalTest` row with no filter and counts it as that tester's invited and delivered tests.

**Reproduce:** run `/tmp/probes/r19.py`. It records two `owner_made=True` makes with the fixture `tester_ref="tester-1"`. Then:

- the roster count stays 0, which is correct;
- `creators_reading()["graduations"][0]["reasons"]` no longer contains the reliability reason, because 2 of 2 delivered satisfies `invited ≥ 2` and `RELIABLE_AT` through non-evidence.

Graduation is still refused, because no testing, ambassador or consent terms are recorded. The result is only a zero-cost owner card. So this is Low and does not block shipping.

Fix, either of:

- apply `testers._counts_as_tester` in `creators_reading`;
- in `physical.record`, force `tester_ref="owner"` when `owner_made`.

`growth/creators.scaling_decision` reads `CreatorProfile.delivered` for UGC creators, not for testers, so it is out of scope.

### R20

`_tester_recruited` now returns true only for a `tester_agreement` permission whose independence relationship is in `ALLOWED_RELATIONSHIPS` and whose qualification has no problems. The gate description, `OWNER_ACTIONS` (both copies) and `patch_tester_outreach.py` now quote the gate's own `how`. **Fixed.**

### Is the tightened `test_tester_roster_counts_agreement_not_prospects` legitimate?

**Yes.** The old test asserted that `permissions=["test_pattern"]` and `delivered=1` each *open* the gate. That is exactly the behaviour R20 identified as fail-open, so those assertions had to be inverted.

The new test:

- keeps the prospect negative;
- adds negatives for:
  - a bare permission;
  - a legacy `{"kind": "tester_agreement"}` with no independence;
  - a photo permission;
  - a delivery count;
- keeps a positive, now through `record_agreement` with `relationship="none"` and a qualification URL.

No needed case was removed. The positive path is still exercised, and refusal of disallowed relationships or missing qualification is covered elsewhere (`test_w4_b2gates` and `test_w4_gatesb`, R6).

One gap worth adding: a `tester_agreement` with an allowed relationship but a qualification that fails `qualification_problems` should not open the gate. This is optional and does not block shipping.

## 3. R21

`market-basket-small-1.2.0/LISTING_PACKAGE.md` no longer contains `59.65`, and `test_the_kit_ceiling_is_checked_from_above_and_no_stale_figure_remains` now covers that file. **Fixed.**

Remaining `59.65` hits:

- historical build evidence and `COMPLETION_BOARD_FINAL.json` (archived);
- `PHYSICAL_SAMPLE_PACKAGES.md` and `BASKET_KIT_FOR_OWNER_APPROVAL.md` (analysis of the derivation);
- one comment in `quality/tester_kit.py` naming the risk-matrix floor.

**R26 (Info):** `research/final_build/w4/owner/gate_clearance_business.json` (lower-case, vendored) still has `max_cost_cad: 59.65` at lines 218, 309 and 636. It is a regeneration input for `OWNER_ACTIONS`, and `patch_tester_outreach.py` overwrites the figure after regeneration. Two options:

- refresh it;
- add it to the stale-figure test.

This is not owner-facing and does not block shipping.

## 4. The whole branch against integration

48 files, +6312 / −462. Delta 5 changes source only in:

- `executor.py`, which tightens a gate;
- `testers.py`, which tightens a filter;
- `physical.py`, which changes canonicalisation (R22 and R23).

I re-scanned the branch for assertions removed from tests. Every removed `assert` was reviewed in deltas 1–4 and is either inverted or replaced by a stricter one. This round's only test edit is the R20 inversion above.

Delta 5 makes no gate more permissive and adds no ceiling increase or new fail-open path, apart from R23. The merges `8c04993` (`COORDINATION.json`) and `81b3e45` (adding `test_physfix_photo_first`, plus the `test_w4_launchfix` import guard on `physical_upgrade`) only add assertions.

Apart from R22 and R23, nothing blocks shipping.

## 5. Tests

Each test was run one at a time with `cd brambleloop && PYTHONPATH=src:tests nice -n 19 python tests/<f>.py` at `81b3e45c`. The first attempt failed on missing `sqlalchemy` and `fastapi`; I installed `requirements.txt` and re-ran.

All 13 pass (exit 0). The tests do not catch R22, R23 or R25; the probes do.

```
test_physfix rc=0 35s :: 37/37 passed
test_secreview_physfix_adversarial rc=0 24s :: 12/12 passed
test_secreview_physfix_42eac69_probes rc=0 10s :: 8/8 passed
test_secreview_physfix_89eef1e_probes rc=0 6s :: 8/8 passed
test_executor rc=0 32s :: OK   test_the_scheduler_condition_counts_cadences_rather_than_any_audit_row
test_creators rc=0 1s :: OK   test_two_completed_collaborations_are_a_coincidence
test_risk_matrix rc=0 116s :: OK   test_the_parked_sample_request_is_a_tester_spend_approval_not_owner_crochet
test_physical rc=0 90s :: OK   test_with_no_sample_the_estimate_stays_uncalibrated
test_physical_record_blocked rc=0 5s :: 5/5 passing
test_physfix_photo_first rc=0 8s :: 8/8 passed
test_w4_launchfix rc=0 29s :: 32 passed, 0 failed
test_vacuity rc=0 11s :: OK   test_the_scan_sees_the_suite
test_first_customer_gate rc=0 20s ::   12 passing, 0 failing
```

## Appendix: probe scripts (reviewer-only, not committed as tests)

`/tmp/probes/r18.py`:

```python
import sys
from brambleloop.quality import physical
from brambleloop.cir.benchmarks import cardigan
from brambleloop.cir.compiler import compile_cir as _compile
from brambleloop.cir.model import CIR, Component, Hold, Op, Row

def panel(name, holds):
    return Component(name=name, construction="flat", foundation=20, foundation_kind="chain",
                     rows=[Row(index=1, ops=[Op("sc", 20)], declared_count=20),
                           Row(index=2, ops=[Op("sc", 8)], declared_count=8, skips=12),
                           Row(index=3, ops=[Op("sc", 8)], declared_count=8)], holds=holds)
def strap(name, hold, rows=1, holds=None):
    return Component(name=name, construction="flat", foundation=0, foundation_kind="none",
                     rows=[Row(index=i, ops=[Op("sc", 6)], declared_count=6) for i in range(1, rows+1)],
                     resumes=hold, holds=holds or [])
def digest(comps):
    c = CIR.from_dict(cardigan("XS").to_dict()); c.components, c.assembly = comps, []
    r = _compile(c)
    if not r.ok: return "COMPILE_FAIL:" + ",".join(f.code for f in r.findings if f.is_error)
    return (physical.design_digest(c, r) or "NONE")[:12]
H = lambda n, f=8, row=1: Hold(name=n, at_row=row, count=6, from_stitch=f)

print("P1 identical holding panels L,R resumed by distinct straps; swap panel order (cosmetic)")
a = digest([panel("L",[H("hl")]), panel("R",[H("hr")]), strap("s1","hl"), strap("s2","hr",rows=3)])
b = digest([panel("R",[H("hr")]), panel("L",[H("hl")]), strap("s1","hl"), strap("s2","hr",rows=3)])
c = digest([panel("L",[H("hl")]), panel("R",[H("hr")]), strap("s1","hr"), strap("s2","hl",rows=3)])
print(" ", a, b, c, "LEAK" if a != b else "ok", "| swap-resume (same object):", "LEAK" if a != c else "ok")

print("P2 chain through two identical holding pieces A,B (cosmetic reorder of A,B)")
x = digest([panel("p",[H("h0")]), strap("A","h0",holds=[H("ha",0)]), strap("B","ha",holds=[H("hb",0)]), strap("end","hb",rows=3)])
y = digest([panel("p",[H("h0")]), strap("B","ha",holds=[H("hb",0)]), strap("A","h0",holds=[H("ha",0)]), strap("end","hb",rows=3)])
print(" ", x, y, "LEAK" if x != y else "ok")

print("P3 self-resume cycle (should not compile or must differ from any chain)")
s = digest([panel("p",[H("h0")]), strap("A","h0"), strap("B","hb",holds=[H("hb",0)])])
print(" ", s)
print("P4 hold with non-numeric at_row/str hold in dict -> digest None? (fail closed)")
print("P5 HIDE: X1 on hold a(st 8), X2 on hold b(st 14); long W continues X1 vs X2 (real change)")
P = lambda: panel("p",[H("a",8), H("b",14)])
d1 = digest([P(), strap("X1","a",holds=[H("xa",0)]), strap("X2","b",holds=[H("xb",0)]), strap("W","xa",rows=3), strap("T","xb")])
d2 = digest([P(), strap("X1","a",holds=[H("xa",0)]), strap("X2","b",holds=[H("xb",0)]), strap("W","xb",rows=3), strap("T","xa")])
print(" ", d1, d2, "HIDDEN (collision)" if d1 == d2 else "ok, moves")
d2r = digest([P(), strap("X2","b",holds=[H("xb",0)]), strap("X1","a",holds=[H("xa",0)]), strap("W","xb",rows=3), strap("T","xa")])
print("P5' D2 with X2 listed before X1:", d2r, "HIDDEN: equals D1" if d2r == d1 else "ok")
```

`/tmp/probes/r19.py`: records two owner-made makes with `T._inputs(...)` (`tester_ref="tester-1"`) through `test_physfix` helpers, then prints `testers.from_db(db)["count"]` and `growth_ops.creators_reading(db)["graduations"]`.

## R25 (Low, latent, pre-existing): self-resume compiles

Probe P3 in `r18.py`: piece `B` (foundation 0) holds `hb` on its own row 1 and also `resumes="hb"`. It compiles `ok` with digest `9418513b69a7`.

A piece cannot take up stitches it has not made yet, so this is a cycle the compiler should refuse with a `HOLD_CYCLE` error, including longer cycles. A cycle is also one of the ways two different designs can collide under positional labels. Fix it together with R22 and R23.

---
_Independent reviewer; report only. Nothing was pushed to `claude/repository-setup-nc9x6o` and no pull request was opened._
