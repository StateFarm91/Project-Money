# Independent SECREVIEW — `claude/w4-PHYSFIX-PHOTO` @ e3fd0b0e (delta review 4)

- Reviewed: 2026-10-31 (UTC). Independent reviewer. No PR opened; nothing pushed except this file.
- Subject: the non-merge delta `git diff 3e542a17..e3fd0b0e` (author commits 1f98a40, bd73064,
  216785e; f4c3899 and 10a9d21 arrive from `claude/w4-INTEG8-next` and were read only for
  interaction), and the whole branch against `origin/claude/w4-INTEG8-next`.
- Prior review: `INDEPENDENT_SECREVIEW_PHYSFIX_3e542a1.md` (R11–R17).

## Verdict: **DO NOT SHIP** (narrowly; one latent Medium, two Lows)

R11–R17 are fixed for the cases they targeted. The tests listed below pass. No gate was
relaxed, and the delta adds no fail-open on a sale, bind, calibration or halt path.

Two things still block shipping:

- **R18 (Medium, latent).** The R11 fix makes hold *names* positional, but two cosmetic
  edits still move the digest:
  - reordering a piece's `holds` list;
  - reordering two identical pieces that resume different holds (left/right sleeve).

  This is the same failure class as R1/R5/R11. A cosmetic edit lets a re-release slip past a
  size halt. It is latent: no Launch-0 CIR has holds.
- **R19 (Low).** A non-evidence `owner_made` row still enters the tester roster and the
  tester planner. One owner-made row turns the owner card's roster to `OK, 1 tester`, and
  the planner assigns sample makes to `owner`. That contradicts F-071 and the R12 claim
  "owner make = non-evidence". It affects display and the audit only; no gate reads it.

| # | Severity | Finding | Status |
|---|---|---|---|
| R11 | was Med | Renaming a hold moved the digest | **fixed** (probe 1) |
| R14 | was Low | `Row.into` missing from the digest | **fixed**: relative `into_offset` (probes 6, 9) |
| R12 | was Med | Sample not bound to an independent tester | **fixed** on every write and gate path; see R19 for a reporting leak |
| R13 | was Low–Med | Stale figures in committed packets | **fixed**: only `tester_outreach` and its batch total changed |
| R15 | was Low | Kit ceiling checked from below only | **fixed** |
| R16 | was Info | `qualification` accepted `"."` | **fixed** (form check only; see R21) |
| R17 | was Info | CA$185 in `launch/readiness` | **fixed**: reads `KIT["max_cost_cad"]` |
| **R18** | **Medium (latent)** | Reordering holds, or reordering identical pieces, moves the digest | open |
| **R19** | **Low** | `owner_made` rows count in the tester roster and planner | open |
| R20 | Low | `_tester_recruited` still counts a non-dict or non-agreement permission, or `delivered > 0`, without independence | open (no production writer today) |
| R21 | Info | Residuals: format-only qualification; self-declared independence; legacy rows; one listing-package line still offers CA$59.65 | note |

## 1. Digest (R11, R14)

The probe script is `/tmp/probe/p.py`, below. It builds a flat panel with holds plus
resuming straps on the cardigan's gauge, and prints `design_digest(...)[:12]` for each pair.

| # | Change | Kind | Expect | Result | |
|---|---|---|---|---|---|
| 1 | rename hold `a`→`zz` and its resume | cosmetic | same | same `838a7bb86519` | ok (R11 fixed) |
| 2 | reorder the `holds` list `[a,b]`→`[b,a]`; resumes unchanged | cosmetic | same | `921e10a9ac33` → `b5aabbe2f220` | **R18** |
| 3 | reorder two identical straps `s1(a), s2(b)` → `s2(b), s1(a)` | cosmetic | same | `921e10a9ac33` → `2e3e03ee9a34` | **R18** |
| 4 | identical straps swap their resumes (same object as #3) | cosmetic | same | `→ 2e3e03ee9a34` | **R18** |
| 5 | hold `from_stitch` 8→14 | real | moves | moves | ok |
| 6 | `into=None` vs `into=index-1` | cosmetic | same | same | ok |
| 7 | `into` two rows back with a short row | real | refuse or move | compile fails (UNDERRUN) | ok (fails closed) |
| 8 | hold named the same as a component | cosmetic | same | same | ok |
| 9 | 20-st rows: row 4 `into` 3 → 2 | real | moves | `59715a1efcb9` → `24acfa4c10d9` | ok (R14 fixed) |
| 10 | distinct straps (1 row and 3 rows) swap their resumes | real | moves | moves | ok |
| 11 | reorder distinct straps | cosmetic | same | same | ok |

I found no real geometry change that keeps the digest. `into_offset` is relative, so it
survives renumbering. A hold keeps its row, count and offset, and only its name is dropped.

### R18 (Medium, latent): list order still leaks into the digest

`design_geometry` (`quality/physical.py`, around lines 970–1000) has two places where list
order reaches the digest:

1. **Hold order.** `piece["holds"] = [_canon(h) ...]` keeps the CIR's list order, and a hold's
   position `hold#j` is its index in that list. Holds are identified by name, so their list
   order is cosmetic. Reordering them changes `piece["holds"]` and every `resumes` that
   points at them (probe 2).
2. **Ties in the piece sort.** Pieces are sorted by `json.dumps(piece)` *before* `resumes` is
   filled in. Two pieces that differ only in what they resume tie, and the stable sort then
   keeps the CIR's component order. A left and a right sleeve resuming the left and right
   armhole holds are exactly this case. The output `pieces` list is not re-sorted after
   `resumes` is filled in, so swapping the two sleeves in the component list moves the
   digest (probes 3 and 4).

The impact is the same as R11. `IncidentTracker.publication_halted(content_hash=digest)`
matches halts by exact digest, so the following sequence publishes the object that was
measured wrong:

1. A size halt is raised on design X.
2. X is re-released with its sleeves or holds listed in a different order.
3. The new digest differs, so certification is no longer halted.

A later passing make of the reordered copy would also *lift* X's halt through
`resolve_halts_disproved_by`. Under R1, that make should go to owner review instead.

It is latent because none of the 11 Launch-0 CIRs has holds. Any garment with an armhole
division would be exposed.

Fix:

- Sort each piece's holds by their canonical geometry before assigning `hold#j`.
- After `resumes` is filled in, sort the final `pieces` list by its full JSON.
- Pieces that tie *and* hold stitches are interchangeable, so the circular dependency is
  harmless. Assert that in a probe.
- Add probes 2 and 3 to the probe suite.

Reproduce from `brambleloop/`:

```python
import sys; sys.path.insert(0, "src")
from brambleloop.cir.model import CIR, Op, Row, Component, Hold
from brambleloop.cir.compiler import compile_cir
from brambleloop.cir.benchmarks import cardigan
from brambleloop.quality.physical import design_digest
def panel(holds):
    return Component(name="panel", construction="flat", foundation=20, foundation_kind="chain",
        rows=[Row(index=1, ops=[Op("sc", 20)], declared_count=20),
              Row(index=2, ops=[Op("sc", 8)], declared_count=8, skips=12),
              Row(index=3, ops=[Op("sc", 8)], declared_count=8)], holds=holds)
def strap(n, h): return Component(name=n, construction="flat", foundation=0,
        foundation_kind="none", rows=[Row(index=1, ops=[Op("sc", 6)], declared_count=6)],
        resumes=h)
def mk(comps):
    c = CIR.from_dict(cardigan("XS").to_dict()); c.components = comps; c.assembly = []
    return design_digest(c, compile_cir(c))[:12]
H = lambda n, f: Hold(name=n, at_row=1, count=6, from_stitch=f)
print(mk([panel([H("a", 8), H("b", 14)]), strap("s1", "a"), strap("s2", "b")]))  # 921e10a9ac33
print(mk([panel([H("b", 14), H("a", 8)]), strap("s1", "a"), strap("s2", "b")]))  # b5aabbe2f220
print(mk([panel([H("a", 8), H("b", 14)]), strap("s2", "b"), strap("s1", "a")]))  # 2e3e03ee9a34
```

## 2. Independence (R12)

**The only writer.** `quality.physical.record` is the only `PhysicalTest(...)` constructor
in `src/` (`physical.py:783`). Its only caller is the `physical.record` job
(`runtime/release.py:3069`), which `POST /api/physical-test` enqueues (`app/main.py:5268`).

I found no other path that writes PhysicalTest or physical evidence:

- no route, job or seed that sets `.passed` or `.measured` on a PhysicalTest
  (`gates/originality.py:329` sets `passed` on a different model);
- no SQL migration that touches `physical_tests`.

**Refusals.** `record` refuses a missing, empty or `owner` `tester_ref`, an unknown ref and
a legacy agreement with no `independence` block. `test_physfix` exercises all of these at
lines 830–870, and I read the code path.

**`owner_made` rows.** They are written with `passed=False`, `size_proof=False` and
`evidence_role=owner_made_non_evidence`. Each downstream use is excluded:

| Use | Why an owner-made row is excluded |
|---|---|
| bind | `bind_physical_evidence` requires `passed is True` |
| size proof | requires a bound row; `size_proof` is also stamped False |
| calibrate | `stored_assessments` filters `passed == True` |
| lift a halt | `release.py:3089` requires `not owner_made` |
| owner review | `release.py:3077` requires `not owner_made` |
| `physical_proof` gate | `executor.py:257` excludes `owner_made` |
| proof ladder, moat, confidence, evidence | `t.passed` only |

An owner-made sample that measures the wrong size can still raise a size halt. That is
conservative, so I accept it.

**`_tester_recruited`.** A `tester_agreement` dict counts only if its relationship is on the
allow-list and its qualification passes `qualification_problems`. That is the same predicate
`independent_agreement` uses.

**`_physical_proof_available`.** A completed, non-owner-made row opens the gate. Because
`record` refuses unagreed testers, every such row now carries a `tester_agreement`. The gate
also opens on a *failed* make. That is unchanged and documented ("opens on the first
PhysicalTest row with a completion date"), and it unlocks no sale: binding still needs
`passed`.

### R19 (Low): owner-made rows enter the tester roster and planner

`quality/testers.from_db` and `testers.plan` read every PhysicalTest row and do not exclude
`measured.owner_made`. Consumers:

- `ops/owner_queue.tester_status` feeds the owner's physical-proof card;
- the `quality.tester_plan` audit (`release.py:7935`).

Reproduce: insert the row exactly as `record(owner_made=True)` writes it, then run
`/tmp/probe/roster.py`.

```
before {'status': 'NOT-YET-OBSERVED', 'testers': 0, 'tester_roster_gate_open': False, ...}
after  {'status': 'OK', 'testers': 1, 'tester_roster_gate_open': False, 'note': '1 tester(s) with recorded assignments'}
plan testers [{'ref': 'owner', 'specialties': ['home_decor'], 'accepted': 1, ...}]
assignments [{'tester': 'owner', 'product_slug': 'market-basket-medium', ...},
             {'tester': 'owner', 'product_slug': 'market-basket-small', ...}]
```

So the owner card reports a tester network that does not exist, and the planner schedules
the owner to crochet, which F-071 forbids. This is a reporting and audit leak only. The
`tester_roster` gate stays closed because it reads CreatorProfile.

Fix:

- skip `measured.owner_made` rows in `testers.from_db` and `testers.plan`;
- for defence in depth, also skip rows without `measured.tester_agreement`.

### R20 (Low, no live writer): `_tester_recruited` keeps three non-independent paths

216785e restores the counting of any non-dict permission (`return bool(p)`), so that
`test_executor`'s fixture `permissions=["test_pattern"]` keeps passing. Three paths still
count without the independence check:

- any non-dict permission;
- any dict permission whose `kind` is not `tester_agreement`;
- `delivered > 0`.

Today this is unreachable in production:

- the only writer of `CreatorProfile.permissions` is `tester_programme.record_agreement`
  (`tester_programme.py:246–250`), and it writes only allow-listed `tester_agreement` dicts;
- nothing in `src/` increments `CreatorProfile.delivered`.

So the fixture change is legitimate as a test of "a recorded permission counts". It does
leave the gate open to any future writer, such as a creator or UGC permission or a delivered
collaboration, which would open `tester_roster` without an independent tester. Such writers
are already shaped in the code:

- `growth/creators.py:247` serialises photo permissions as `{asset_ref, scope, ref}` dicts
  with no `kind`;
- `runtime/growth_ops.py:753` reads string permissions such as `testing_terms:...`.

Either one, persisted to a CreatorProfile, would open the gate.

Fix: count only `independent_agreement(...)`-shaped permissions, and change the
`test_executor` fixture to record through `record_agreement`, as bd73064 already does for
`test_physfix_photo_first`.

## 3. Owner packets (R13)

I compared the JSON structure of `3e542a17` and `e3fd0b0e` for both
`research/final_build/w4/OWNER_ACTIONS.json` and
`src/.../command_center/snapshots/OWNER_ACTIONS.json`. In each, the only changed paths are:

- `batches[go_live].items[tester_outreach]`: `decision`, `max_cost_*` and
  `clearance[0].detail`;
- `batches[go_live].max_cost_cad_total` and `max_cost_display`.

No other item or batch changed. The OWNER_ACTIONS.md changes are that row and its batch
heading.

Arithmetic and facts check out:

- 651.00 − 185.00 + 66.00 = 532.00.
- CA$66.00, CA$65.90, CA$55.90 and CA$10.00 match `tester_kit.KIT`, and the cost basis is
  marked ESTIMATED.
- The three `kit_files` hashes match the committed kit files (`e4bc8ad3…`, `59ea3c27…`,
  `bed9dbe2…`).
- The protocol and record rows are the kit's own (`GATE_CLEARANCE_BUSINESS.json`). I found no
  invented fact.

One small staleness, Info: the item's `evidence` string still says `tester_roster` opens on
"delivered > 0 or a recorded permission". It understates the new rule rather than overstating
anything.

## 4. R15–R17

- **R15.** `tester_kit.build` now refuses a kit whose `max_cost_cad` exceeds
  `APPROVED_CEILING_CAD[key]`, and also a key with no approved ceiling. It still refuses one
  below the promise or the risk matrix. Fixed.
- **R16.** `qualification_problems` requires an http(s) URL with a dotted host, or
  `photo:<sha256>`. `"."` and `https://ravelry/x` are refused. The same predicate is used at
  write time, in `independent_agreement` and in `_tester_recruited`. Fixed; see R21.
- **R17.** `readiness.PHYSICAL_SAMPLE.max_cost_cad = KIT["max_cost_cad"]`, so CA$185 is gone
  from `src/`. The only CA$59.65 left in `src/` is a comment naming the risk-matrix floor
  (`tester_kit.py:61`).

## 5. The rest

- **No gate was relaxed.** The delta only adds conditions: the `physical_proof` gate
  excludes owner-made rows, `tester_roster` adds the allow-list and qualification checks,
  `record` refuses unagreed testers, and the kit adds a ceiling check from above.
- **No new fail-open.** The `except` paths in `owner_queue.tester_status` were not touched.
- **f4c3899** (integration) serialises `seed_owner_queue` under the existing owner-queue lock.
  That is a concurrency fix with no gate impact.
- **Test fixtures** in `test_physical`, `test_physical_record_blocked`,
  `test_physfix_photo_first`, `test_risk_matrix` and `test_w4_gatesb` now agree the tester
  through `record_agreement` with a real-shaped URL, instead of using `tester_ref="owner"`.
  The `test_risk_matrix` assertion now checks the kit figure exactly. All of these are
  legitimate, and none weakens an assertion. `test_executor`: see R20.

## R21 (Info): residuals

- `qualification_problems` checks the *form*, not the substance. `https://a.b` passes, and a
  bare 64-hex string passes without checking that the photo is stored.
- Independence is self-declared. The owner could record an agreement for a second handle
  with `relationship="none"`. That is inherent to R6's opt-in design, and only the literal
  ref `owner` is refused.
- There is no migration that marks pre-R12 rows. A legacy row stored with the old default
  `tester_ref="owner"` and `passed=True` would still bind, because `bind_physical_evidence`
  does not require `measured.tester_agreement`. No production rows are known. Defence in
  depth: require `tester_agreement` or `legacy_unstamped` handling in binding.
- `research/final_build/w4/manual_listings/market-basket-small-1.2.0/LISTING_PACKAGE.md:386`
  still offers "or CA$59.65 with yarn reimbursed per metre" as an alternative.
  `PHYSICAL_SAMPLE_PACKAGES.md` keeps CA$59.65 as historical analysis.

## Tests

Run from `brambleloop/`, one at a time:
`PYTHONPATH=src:tests nice -n 19 python tests/<f>.py`, after
`pip install -r requirements.lock` and `pip install --no-deps -r requirements-test.lock`
(the container had no sqlalchemy or fastapi).

- test_physfix rc=0 26s :: 35/35 passed
- test_secreview_physfix_adversarial rc=0 9s :: 12/12 passed
- test_secreview_physfix_42eac69_probes rc=0 7s :: 8/8 passed
- test_secreview_physfix_89eef1e_probes rc=0 5s :: 8/8 passed
- test_risk_matrix rc=0 109s :: OK   test_the_parked_sample_request_is_a_tester_spend_approval_not_owner_crochet
- test_physical rc=0 84s :: OK   test_with_no_sample_the_estimate_stays_uncalibrated
- test_physical_record_blocked rc=0 5s :: 5/5 passing
- test_executor rc=0 24s :: OK   test_the_scheduler_condition_counts_cadences_rather_than_any_audit_row
- test_w4_b2gates rc=0 94s :: 12/12 passing
- test_physfix_photo_first rc=0 7s :: 8/8 passed
- test_w4_launchfix rc=0 27s :: 32 passed, 0 failed
- test_vacuity rc=0 9s :: OK   test_the_scan_sees_the_suite
- test_first_customer_gate rc=0 18s ::   12 passing, 0 failing

All 13 suites pass (rc=0). They pass while R18 and R19 are open: no suite probes hold/piece order or owner-made rows in the roster.
