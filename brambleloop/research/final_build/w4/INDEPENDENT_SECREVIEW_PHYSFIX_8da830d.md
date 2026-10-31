# Independent security and integrity review: PHYSFIX-PHOTO delta 7 (`8da830dc`)

- **Subject:** `claude/w4-PHYSFIX-PHOTO` at `8da830dc`, which includes `claude/w4-PHYSFIX` at `b53fba09`.
- **Delta:** `git diff 7282c470..8da830dc`:
  - `091e814d`: the R27 fix;
  - `b53fba09`: the vacuity follow-up;
  - two merge commits.
- **Whole branch:** `git diff origin/claude/w4-INTEG8-next...origin/claude/w4-PHYSFIX-PHOTO`. The merge base is still `8e9242c7`, so the integration base has not moved since the previous review.
- **Prior review:** `INDEPENDENT_SECREVIEW_PHYSFIX_7282c47.md` on `origin/claude/w4-SECREVIEW-PHYSFIX-7282c47`.
- **Reviewer:** independent. I opened no pull request and pushed only this report.
- **Date:** 2026-10-31 (UTC).

## Verdict: **DO NOT SHIP**, because of R28. The fix is small and fails closed.

**R27 is closed.** The interim now covers assembly. Every assembled design gets digest `None`, and a size halt on one applies product-wide. All 11 Launch-0 digests are byte-identical to `7282c470`. The vacuity follow-up is a real assertion, not an exemption.

**R28 is a new instance of the same class, and it is not latent.** It predates this delta and every earlier round missed it. Each of these is the same physical object, but they get different digests:

- a piece declared with `make: N`;
- the same piece written as N identically worked components.

So a release whose size halt is scoped to a digest escapes it by restating its quantity as separate pieces. Three Launch-0 products have `make > 1`:

| Product | `make` |
|---|---|
| `hexagon_coasters` | 4 |
| `snowflake_ornaments` | 6 |
| `placemat_pair` | 2 |

R22 and R27 were rated Medium (latent) and set the bar for "do not ship". R28 is the same failure, and it is reachable on Launch-0 products, so it meets that bar too.

| ID | Severity | Finding | Status |
|---|---|---|---|
| R27 | Medium (latent) | seam-list order, seam orientation and identical-piece naming moved the digest | **closed**: assembled designs get no digest |
| **R28** | **Medium (pre-existing; reachable on 3 Launch-0 products)** | `make: N` and N identical components give different digests, so a scoped size halt is escaped by restating the quantity | **open, blocks** |
| R29 | Low (latent) | `Component.gauge` (per-piece gauge, F-754) is not in `design_geometry`, and the twin ignores it, so a real change of a piece's gauge collides with the original digest | open; does not block |
| R25 | Low (latent) | the compiler accepts a resume cycle | acknowledged follow-up; does not block |
| R26 | Info | the vendored `gate_clearance_business.json` still holds 59.65 | acknowledged follow-up; does not block |

## 1. R27 is closed

**The fix.** `_has_holds(cir)` is now:

```
bool(getattr(cir, "assembly", None)) or any(c.holds or c.resumes for c in cir.components)
```

`design_digest` returns `None` when `_HOLD_DIGEST_INTERIM and _has_holds(cir)`. This check runs after `result.ok` and before `design_geometry`.

**Any design with assembly, holds or resumes gets digest `None`.**

- `CIR.assembly` is a `list[Seam]` that defaults to `[]`. Any seam, including a self-seam, makes it truthy. `None` is falsy and would also give `[]` in `to_dict`, so it is consistent.
- `design_geometry` reads its assembly from `cir.to_dict()["assembly"]`, the same field. No other field of `CIR` or `Component` carries a piece-to-piece join: `Component` has `holds` and `resumes`, and `CIR` has `assembly`.
- Every exception still returns `None`, so the check fails closed.

**Its size halt applies product-wide.** `release._halt_release_on_size` stores `design_digest=None`. `incidents.release_scope` reads that as `{}`. So:

- `publication_halted` returns `True` for every `content_hash`;
- `resolve_halts_disproved_by` skips an incident with no scope;
- `release.handle_physical_record` lifts nothing when `design` is falsy.

The new test checks this for the base design and the three variants A1, A2 and A3. I re-derived it from the code.

**No other path leaks a digest.** `design_digest` has two production callers:

- `pipeline._incoming_design`, for certify;
- `release.handle_physical_record` (`release.py:3082`), for halt and lift.

Both go through the interim. No other code in `src` calls `design_geometry`, or hashes geometry for a size scope. `gates.certificate._release_hash` is a different key: the whole CIR, used for certificates. It is not used for size scoping.

**Hold-free, seam-free digests are unchanged byte-for-byte.** I computed `design_digest` for all 11 Launch-0 builders at `7282c470` (in a separate worktree) and at `8da830dc`. The two sets are identical:

| Builder | Digest prefix |
|---|---|
| `basket_small` | `b65d57e9a6e0` |
| `basket_medium` | `c06d836a0bae` |
| `basket_large` | `0df999ef102d` |
| `hexagon_coasters` | `7c4d39e44569` |
| `cloudline_blanket` | `c2a756bca298` |
| `harvest_runner` | `daa8afdf3bed` |
| `snowflake_ornaments` | `d4e97ab1d0a0` |
| `snowfall_throw` | `629ef45c16a1` |
| `nordic_forest_baby` | `4eb1cf43a8e0` |
| `key_basket` | `76e4a0dfa67f` |
| `placemat_pair` | `d3d524cbe76f` |

The test pins three full digests, and they match what I computed:

- `basket_medium_sport`: `0552640f…`, the test's sport-weight variant;
- `basket_small`: `b65d57e9…`;
- `hexagon_coasters`: `7c4d39e4…`.

The test also re-derives each pinned digest from `sha256(design_geometry)`. So the pin cannot pass because of a stale constant. It would fail if the code drifted.

## 2. The test change is legitimate

`b53fba09` adds one line to `test_designs_with_assembly_are_halted_product_wide_until_seams_are_canonical`:

```
assert len(seamed) == 4 and all(seams for _, seams in seamed.values())
```

This is an **assertion**. It guards the `for` loop over `seamed` against an empty or seam-free table, which is the vacuity that `test_vacuity` flags.

It is not an exemption. `test_vacuity.py` is not touched in the delta (`git diff 7282c470..8da830dc -- brambleloop/tests/test_vacuity.py` is empty), and no allow-list entry was added.

The test is also not vacuous in substance:

- each variant is compiled and asserted `r.ok`;
- the halt loop runs `publication_halted` with each variant's real digest (`None`);
- the pins loop asserts `not c.assembly and not _has_holds(c)`, so the pinned fixtures really are on the digest path.

## 3. R28 (Medium, pre-existing, reachable): quantity is not canonical

`design_geometry` emits one entry per `Component`, with `make` as a field of that entry. So these two forms produce different `pieces` lists, and different digests:

- one coaster with `make: 4`;
- four coasters with `make: 1` and identical rows.

Each `make: 1` copy has the same twin as the `make: 4` piece (probe output: `same twin dims per piece: True`). It is the same object, and the same size claim.

**Reproduction** (at `8da830dc`, from `brambleloop/`, with the lock installed):

```python
import copy
from brambleloop.products import launch0
from brambleloop.cir.model import CIR
from brambleloop.quality import physical as P
from brambleloop.gates.incidents import IncidentTracker
from brambleloop.ops.incident_lifecycle import open_or_restate
import test_physfix as T

c = launch0.cir_for("hexagon_coasters"); d0 = P.design_digest(c)       # 7c4d39e4...
d = c.to_dict(); comp = d["components"][0]; n = comp["make"]; comp["make"] = 1
d["components"] = [dict(copy.deepcopy(comp), name=f"coaster_{i}") for i in range(n)]
d["version"] = "1.0.1"
c2 = CIR.from_dict(d); d1 = P.design_digest(c2)                         # 67994d6a... (compiles ok)

db = T._db(); slug = "hexagon-coasters"
with db.session() as s:
    open_or_restate(s, signature=f"physical-size:{slug}:x", severity="P1", product_slug=slug,
        halts_publication=True, summary="size",
        detail={"release_scope": {"slug": slug, "version": "1.0.0",
                                  "content_hash": "c" * 64, "design_digest": d0}})
t = IncidentTracker(db)
t.publication_halted(slug, content_hash=d0)   # True
t.publication_halted(slug, content_hash=d1)   # False  <-- escapes the size halt
```

Observed output:

- original halted `True`;
- split re-release halted `False`;
- `pipeline._incoming_design(c2)` = `67994d6a…`.

The same split moves the digest for the other two Launch-0 products with `make > 1`:

| Product | Before | After split |
|---|---|---|
| `snowflake_ornaments` | `d4e97ab1…` | `961d1e5a…` |
| `placemat_pair` | `d3d524cb…` | `7e80c210…` |

The behaviour is identical at `7282c470`, so R28 predates this delta.

**Impact.** This is the relabel escape that SECREVIEW F1 and R1 closed, and that R22 and R27 reopened through holds and seams. Here it comes through quantity. A coaster set with a P1 size disagreement can be re-released as "four coasters". It then certifies, and stays publishable, **without** the passing full make that F1 requires.

R22 and R27 were latent. R28 is not, because the affected products are in Launch-0. It still needs a structural re-authoring of the CIR: the Launch-0 builders emit `make: N` today. That is why I rate it Medium and not High.

**Fix (fails closed, keeps all 11 Launch-0 digests).** In `design_geometry`, after building `raw` and before sorting, fold content-identical pieces:

- group the pieces by their canonical content with `make` excluded;
- sum `make` within each group;
- emit one piece per group.

This is safe only while the interim holds. A design that reaches `design_geometry` has no holds, resumes or seams, so its pieces are independent and only their multiset matters. A design with no duplicate pieces is unchanged byte-for-byte, which covers all 11 Launch-0 builders: each has one component. A test should:

- pin the 11 digests again;
- assert that the `make: N` form and the N-component form share a digest;
- assert that a split which changes one copy's rows still moves the digest.

When the interim is lifted (TODO physfix-holds), the AHU encoding must fold quantity the same way.

## 4. R29 (Low, latent): a per-piece gauge is outside the digest

`Component.gauge` (F-754, a ribbed band worked at its own gauge) is used by `gates.stitch_scale` to size that piece. It is not one of the per-piece keys in `design_geometry`, and `cir.twin` reads only `cir.gauge`. So the twin, and the digest, are blind to it.

**Reproduction.** A one-piece design, then the same design with that piece's `gauge` set to 1.5× the stitches per 10 cm. Both give digest `e02486de…`. That is a **collision**: a real change hidden, in the R23 direction.

**Impact.** `resolve_halts_disproved_by` lifts halts scoped to the digest of a design whose full make passed. A passing make of a gauge-changed variant could therefore lift the halt on the original.

**Why Low and non-blocking:**

- no Launch-0 component sets `gauge`, `work_direction` or `feature`. I checked all 11;
- the builders that use a per-piece gauge (garments) have seams, so they get no digest under the interim.

**Fix.** Add `_canon(spec.get("gauge"))` (and `work_direction`) to the per-piece keys. This moves only the digests of designs that set them, and none in Launch-0 does.

## 5. Whole branch against integration

The merge base with `origin/claude/w4-INTEG8-next` is `8e9242c7`, the same as at `7282c470`. The three-dot diff (49 files, +6539/−462) differs from the one the previous rounds reviewed only by this delta. For everything outside the delta, I rely on the previous rounds' whole-branch review: no relaxed gate, no new spend path and no raised ceiling. I re-read only the delta and the size-scoping path (`design_digest`, `release_scope`, `publication_halted`, `resolve_halts_disproved_by`, `handle_physical_record`).

Outside the delta, my new work was the probes in §3 and §4. Both are in the `design_geometry` canonicalisation the previous rounds focused on.

Findings at Medium or above: **R28 only**. It blocks shipping. R25 and R26 remain acknowledged follow-ups. R29 is a non-blocking follow-up.

## 6. Tests run

Each suite was run one at a time, as `cd brambleloop && PYTHONPATH=src:tests nice -n 19 python tests/<f>.py`, after `pip install -r requirements.lock` and `pip install --no-deps -r requirements-test.lock`. These were installed without `--require-hashes`; the pins are the locked versions.

- `test_physfix rc=0 40s :: 39/39 passed`
- `test_secreview_physfix_adversarial rc=0 10s :: 12/12 passed`
- `test_secreview_physfix_42eac69_probes rc=0 9s :: 8/8 passed`
- `test_secreview_physfix_89eef1e_probes rc=0 6s :: 8/8 passed`
- `test_risk_matrix rc=0 105s :: OK   test_the_parked_sample_request_is_a_tester_spend_approval_not_owner_crochet`
- `test_physfix_photo_first rc=0 7s :: 8/8 passed`
- `test_w4_launchfix rc=0 26s :: 32 passed, 0 failed`
- `test_vacuity rc=0 8s :: OK   test_the_scan_sees_the_suite`
- `test_first_customer_gate rc=0 18s ::   12 passing, 0 failing`
- `test_executor rc=0 27s :: OK   test_the_scheduler_condition_counts_cadences_rather_than_any_audit_row`

All 10 suites exit 0. They pass because none of them covers R28. The reproduction in §3 is the missing test.
