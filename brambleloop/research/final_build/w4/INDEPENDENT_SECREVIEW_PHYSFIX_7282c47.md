# Independent security and integrity review: PHYSFIX delta 6 at `7282c470`

- **Subject:** `claude/w4-PHYSFIX-PHOTO` at `7282c470`. It contains `claude/w4-PHYSFIX` at `3d28b658`, merged with `origin/claude/w4-INTEG8-next`.
- **Prior review:** `INDEPENDENT_SECREVIEW_PHYSFIX_81b3e45.md`. Its findings were R22 and R23 (Medium, latent), R24 (Low), R25 (Low, latent) and R26 (Info).
- **Reviewed:**
  - `git diff 81b3e45c..7282c470`, non-merge changes. The only source change is `b3bf682`, in `quality/physical.py` and `runtime/growth_ops.py`. `8e9242c` changes only records.
  - Both merges, `3d28b65` and `7282c47`, are clean. `git show --cc` shows no change that neither parent made. `3d28b65` brings in `COORDINATION.json` only.
  - The whole branch against integration (`git diff origin/claude/w4-INTEG8-next...origin/claude/w4-PHYSFIX-PHOTO`): 17 source files and the tests.
- **Date:** 2026-10-31 (UTC).

## Verdict: **DO NOT SHIP**, because of R27. The fix is one line.

The interim does what it was asked to do. R22, R23 and R24 are closed, and the ". qualification" fix holds. For hold-free designs, every digest is byte-identical to `81b3e45c`.

The interim covers only holds and resumes. The same failure class exists in **assembly** (seams), and every earlier round missed it:

- A cosmetic edit to the seam list moves the design digest (**R27**).
- That lets a design halted for a size disagreement certify as if it were a "different design". It fails open.

This has the same severity and the same latency as R22: Medium, latent. No Launch-0 CIR has a seam today; all 11 builders give one piece with an empty `assembly`. The last round set this as the bar for "do not ship", so this round keeps it.

The fix: extend the existing interim to designs with assembly, by adding `or cir.assembly` to the `_has_holds` condition in `design_digest`. That is fail-closed. It changes no Launch-0 digest, and it makes every size halt on an assembled design product-wide. Once R27 is closed this way, nothing at Medium or above remains, and **the branch may ship**.

| ID | Severity | Finding | Status |
|---|---|---|---|
| R22 | Medium (latent) | a reorder of identical holding pieces moved the digest | **closed** by the interim (no digest) |
| R23 | Medium (latent) | the multiset re-sort hid a real change | **closed**: the re-sort is reverted, and hold designs get no digest |
| R24 | Low | `creators_reading` counted owner rows | **closed** |
| R20 opt. | — | a `tester_agreement` with qualification "." opened `tester_roster` | **closed** |
| **R27** | **Medium (latent, pre-existing)** | the canonical form of `assembly` depends on seam-list order, seam orientation and which of two identical pieces a seam names, so a cosmetic edit moves the digest and a halted design escapes its scoped size halt | **open** |
| R25 | Low (latent) | the compiler accepts a resume cycle | acknowledged follow-up; **does not block** (see §5) |
| R26 | Info | the vendored `gate_clearance_business.json` still holds 59.65 | acknowledged follow-up; **does not block** |

## 1. The interim (R22 and R23)

`design_digest` returns `None` when `_HOLD_DIGEST_INTERIM and _has_holds(cir)`. `_has_holds` is `any(c.holds or c.resumes for c in cir.components)`.

**Can a design with holds or resumes still get a digest? No.**

- **Nested components:** none can exist. `CIR.components` is a flat `list[Component]`, and `Component` has no child components. Every hold and resume lives on a top-level component, which `_has_holds` reads.
- **A resume without a hold, or a hold never resumed:** these fail compilation (`HOLD_UNKNOWN` and `HOLD_ABANDONED`). `design_digest` returns `None` on `not result.ok` before it reaches the check. Probes I1 and I2 confirm this.
- **`resumes=""`:** an empty string is falsy here, and it is falsy in the compiler, topology and writer too. It is not a resume anywhere, so the treatment is consistent.
- **Assembly references:** a `Seam` names pieces, not holds. A seam that names a hold name does nothing in the compiler. For a design with holds, the `holds` map used in `_canon(assembly, {**names, **holds})` is never reached. (Assembly is still a problem in hold-free designs: see R27.)
- **Exceptions:** any exception in `design_digest` returns `None`, which fails closed.
- **Callers:** there are only three: `pipeline._incoming_design` (certify), `release.handle_physical_record` (halt and lift), and the tests. No other code calls `design_geometry`, so reverting the sort cannot reach another consumer.

**Does a no-digest halt block every certification of that product, with no make able to lift it? Yes.**

- `_halt_release_on_size` stores `release_scope.design_digest = None`. `release_scope()` reads that as `{}`, so `publication_halted` takes `len(scoped) < len(halting)` and returns `True` for every `content_hash`: `None`, `""`, any digest, or a callable.
- `resolve_halts_disproved_by` skips any incident with `not scope`. The caller in `release.py` also requires `design` to be truthy before it tries to lift anything.
- So no make of any design, hold-bearing or hold-free, lifts the halt. The test `test_designs_with_holds_are_halted_product_wide_until_holds_are_canonical` asserts all of this, and I re-derived it from the code.
- The converse also fails closed. A hold design asking to certify past a *scoped* halt on a hold-free sibling gets `current = None`, so `return True` and it is halted.

**Is the behaviour for hold-free designs exactly as before? Yes.**

I computed digests at `81b3e45c` and `7282c470` in separate worktrees for all 11 Launch-0 builders, the test's sport-weight medium basket and the benchmark cardigan (which has seams). They are **byte-identical**.

My synthetic multi-piece, multi-seam designs (probe below) are identical across both revisions too. That is expected. For a hold-free design every piece gets `resumes: null`, and inserting an identical key into every piece cannot change the order of their sorted JSON. So removing the re-sort changes nothing for hold-free designs. A scoped halt still lets a different hold-free design certify; the test asserts this.

## 2. R24: owner makes

- `physical.record` now writes `tester_ref="owner"` whenever `owner_made` is true, even when the report names a tester's ref. Before, a supplied ref won.
- `creators_reading` now skips rows that fail `testers._counts_as_tester`. That function rejects both `measured.owner_made` and the ref `"owner"`, case-insensitively.

Every other reader of `PhysicalTest` either:

- uses the same filter (`testers.from_db` and the plan),
- excludes `owner_made` (`executor._physical_proof`), or
- filters on `passed == True`, and an owner row is never passed (R12). This covers `growth_ops` trust proof, `pipeline`, `readiness`, `moat`, `proof` and `sample_photo`.

`physical_truth` only *displays* the ref, which now reads "owner"; that was R26's display half. **Closed.**

## 3. The ". qualification" fix

- `_tester_recruited` counts a `tester_agreement` only when `independence.relationship` is in the allow-list **and** `qualification_problems(qualification)` is empty.
- `qualification_problems` accepts only an http(s) URL with a dotted host, or `(photo:)?<sha256>`. So ".", "https://x" and an empty value are refused.
- `test_executor` now adds an `unqualified` profile with qualification "." and still asserts the gate is closed. **Closed.**

## 4. The whole branch against integration

The branch touches 17 source files. Every test assertion it removes is replaced by a stricter one:

- `gate.open is True` became `False` for non-independent permissions.
- "notes surfaced without blocking" became "routed to the owner".
- A swatch no longer meets the first-customer floor.
- `usable_for_calibration` was dropped for PARTIAL.
- `max_cost_cad > 8×fee` became exact figures plus a 10× ceiling-refusal test.

I found no relaxed gate, no new spend path and no raised ceiling. The only fail-open path I found is R27, which predates this delta.

### R27 (Medium, latent, pre-existing): `assembly` is not canonical

`design_geometry` emits `"assembly": _canon(body["assembly"], {**names, **holds})`. That is the seam list **in list order**, each seam **in its stated a/b orientation**, with piece names replaced by their sorted position. Three cosmetic edits to a hold-free design each move the digest:

| Probe | Edit (same physical object) | Digest |
|---|---|---|
| A1 | two identical pieces A and B, A seamed to C and B to D; swap the list order of A and B | moves |
| A2 | reverse the order of two independent seams in `assembly` | moves |
| A3 | state a symmetric whipstitch seam as (C, A) with the edges swapped, instead of (A, C) | moves |
| A4 | the same as A1, written as "A to D, B to C" | moves |

**Impact.** Suppose a P1 size halt is scoped to digest *d*. The same design, re-released with its seams reordered, gets a different digest *d′*. Then `publication_halted(slug, content_hash=d′)` is `False`, so it certifies, and stays publishable, **without** the passing full make F1 requires. This is exactly the relabel escape that SECREVIEW F1 and R1 closed for versions and names, reached through assembly.

**Not reachable in Launch-0 today.** All 11 builders give one piece and `assembly == []`. The test basket is the same, and on it a seam reversal is a no-op. Several non-Launch-0 builders do carry seams (`garments.py`, `moment_candidates.py`, `builder.py:324/421`, `pipeline_board.py`), so it becomes reachable as soon as one of them is proposed into the catalogue.

A1 and A4 are the R22 failure exactly, through seams instead of resumes. I found no R23-style collision through assembly: without a re-sort, tied pieces are content-identical, so swapping their labels never maps a real change onto another design.

**Fix: the interim, extended.**

```python
def _has_holds(cir) -> bool:
    return bool(getattr(cir, "assembly", None)) or any(
        getattr(c, "holds", None) or getattr(c, "resumes", None) for c in cir.components)
```

(Or rename it `_not_yet_canonical`.) Add A1, A2 and A3 to `test_designs_with_holds_are_halted_product_wide_until_holds_are_canonical`, each asserting `design_digest is None`.

The permanent fix belongs with TODO(physfix-holds):

- sort the seam list by canonical content;
- orient symmetric seams canonically (whipstitch, slst, mattress or sew, with no `at_round`, `stitches_from_centre` or `mirrored`);
- treat seams as edges of the same piece forest, so tied pieces are distinguished by what they connect to.

**Reproduce** (`cd brambleloop && PYTHONPATH=src:tests python probe.py`):

```python
from brambleloop.quality import physical
from brambleloop.cir.benchmarks import cardigan
from brambleloop.cir.compiler import compile_cir as _compile
from brambleloop.cir.model import CIR, Component, Op, Row, Seam

def sq(name, n=10, rows=4):
    return Component(name=name, construction="flat", foundation=n, foundation_kind="chain",
                     rows=[Row(index=i, ops=[Op("sc", n)], declared_count=n) for i in range(1, rows+1)])
def dg(comps, seams):
    c = CIR.from_dict(cardigan("XS").to_dict()); c.components, c.assembly = comps, seams
    r = _compile(c); assert r.ok
    return physical.design_digest(c, r)[:12]
S = lambda a, b: Seam(method="whipstitch", piece_a=a, piece_b=b, edge_a="top", edge_b="bottom")
P = lambda first, second: [sq(first), sq(second), sq("C", 10, 2), sq("D", 10, 6)]
x = dg(P("A", "B"), [S("A", "C"), S("B", "D")])
print("A1", x, dg(P("B", "A"), [S("A", "C"), S("B", "D")]))   # differ
print("A2", x, dg(P("A", "B"), [S("B", "D"), S("A", "C")]))   # differ
print("A3", x, dg(P("A", "B"), [Seam(method="whipstitch", piece_a="C", piece_b="A",
                                     edge_a="bottom", edge_b="top"), S("B", "D")]))  # differ
```

Observed: `A1 e0263c7f9807 3c8f80e4f85a`, `A2 e0263c7f9807 23e1b9c0c5af`, `A3 e0263c7f9807 96ccf5f9f374`. I got the same values at `81b3e45c`, which shows R27 is pre-existing.

## 5. R25 and R26: do they block shipping?

- **R25 (the compiler accepts a resume cycle):** does not block. A cyclic design must have a resume, so under the interim it has no digest. Its halts are product-wide and no make lifts them, so a cycle can no longer cause a digest collision or a halt escape. What remains is that an unmakeable cycle could compile and certify. That is a correctness issue for hold designs only, and no Launch-0 CIR has holds. Fix it, with a `HOLD_CYCLE` refusal, before `_HOLD_DIGEST_INTERIM` is lifted, as the TODO already says.
- **R26 (vendored 59.65):** does not block. That input is overwritten when the patch runs and is not shown to the owner, and every owner-facing figure is pinned by `test_the_kit_ceiling_is_checked_from_above_and_no_stale_figure_remains`.

## 6. Tests

Each file was run alone with `cd brambleloop && PYTHONPATH=src:tests nice -n 19 python tests/<f>.py` at `7282c470`, after installing `requirements.lock` and `requirements-test.lock`.

_Partial report: the test run is in progress. Results so far: test_physfix 38/38, test_secreview_physfix_adversarial 12/12, both probe files 8/8 each, test_executor, test_creators and test_cert_growth_ops all pass._

The tests do not catch R27. The probe in §4 does.
