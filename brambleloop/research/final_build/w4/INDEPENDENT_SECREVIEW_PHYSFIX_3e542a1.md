# Independent SECREVIEW — `claude/w4-PHYSFIX-PHOTO` @ 3e542a17 (delta review 3)

- Reviewed: 2026-10-31 (UTC). Independent reviewer. No PR opened, nothing pushed except this file.
- Subject: `git diff 89eef1ec..3e542a17` (the non-merge delta) and
  `git diff origin/claude/w4-INTEG8-next...origin/claude/w4-PHYSFIX-PHOTO` (the whole branch).
- Prior review: `INDEPENDENT_SECREVIEW_PHYSFIX_89eef1e.md` (R5 digest hashed notation, R6
  tester independence opt-in, R7 two cost figures).

## Verdict: **DO NOT SHIP** (narrowly; three small fixes)

The R5–R10 fixes do what the author says, for the cases they target:

- The digest is built from compiled rows and the twin.
- A digest of None fails closed.
- The independence allow-list cannot be bypassed.
- The kit, the owner card and the gate card now all state CA$66.00.

No gate in the delta was relaxed, and I found no new fail-open in the code I read.

Three things still block shipping:

- **R11.** A purely cosmetic edit still moves the digest. That is the R1/R5 failure class: an
  edited release certifies past a size halt.
- **R12.** The physical evidence the independence rule protects is not tied to an independent
  tester. `physical.record` defaults `tester_ref` to `"owner"`, and the `physical_proof` gate
  opens on any completed test.
- **R13.** R7 is not closed in the committed owner-facing packet. It still says CA$185.00 and
  CA$59.65.

Each is a small change. R11 is latent: no Launch-0 CIR has holds today.

| # | Severity | Finding | Status |
|---|---|---|---|
| R11 | **Medium** (latent) | Renaming a hold is cosmetic but moves the digest, so the edited release certifies past a size halt | open |
| R12 | **Medium** | `physical.record` does not bind a sample to an agreed, independent tester; it defaults to `"owner"` | open (pre-existing, but contradicts the R6 claim) |
| R13 | Low–Med | The stale CA$185.00 and CA$59.65 figures remain in committed owner packets and the snapshot | open |
| R14 | Low (fails closed) | `Row.into`, the row being worked into, left the digest; it was in the 89eef1e digest | open (regression) |
| R15 | Low | The kit ceiling is only checked from below; any higher `max_cost_cad` builds | open |
| R16 | Info | `qualification` accepts any non-blank text, for example `"."` | note |
| R17 | Info | A second figure, CA$185, remains in dormant code: `launch/readiness.PHYSICAL_SAMPLE` | note |

## 1. Digest (R5)

### What I verified holds

I ran these probes against `market-basket-medium`, the cardigan benchmark and a synthetic
two-piece design with a hold.

| Change | Expected | Digest | |
|---|---|---|---|
| `[inc] x6` expanded to six `inc` (existing probe suite) | same | same | ok |
| gauge yarn weight upper-cased; gauge 13 vs 13.0 | same | same | ok |
| colour hex change; `finished_size_note`; `risk_class`; component rename | same | same | ok |
| reverse the order of the cardigan's pieces; rename all pieces and their assembly references | same | same | ok |
| `rows_per_10cm` +0.0001 | moves | moves | ok |
| `sc`→`hdc` in one round; drop a round; turning chain 0→1 | moves | moves | ok |
| loop `both`→`back`; `make` 1→2; foundation `magic_ring`→`chain` | moves | moves | ok |
| material yarn weight worsted→bulky, gauge unchanged | moves | moves | ok |
| invalid stitch `" SC "` or an undeclared colour | None | compile fails, digest None | ok (fails closed) |

**Twin rounding to 0.1 cm is sound, and it is redundant.** `build_twin` and `geometry.measure`
read only these inputs:

- `cir.gauge`: `stitches_per_10cm`, `rows_per_10cm`, `chains_per_10cm`, `stitch_type`;
- `comp.make`;
- `comp.construction`;
- the resolved rows;
- the code-side stitch table.

The digest already carries every one of these at full precision, rounded to 6 decimal places.
So two designs whose twins differ only below 0.1 cm still differ in their rows or gauge, and
get different digests. The rounding hides no real size change. It only makes the twin block
insensitive to float noise.

One caveat: `gauge.chain_gauge_uncertainty` is not in the digest. That is fine, because it
widens a tolerance band and moves no dimension.

### R11 (Medium, latent): renaming a hold moves the digest

In `design_geometry`:

- `_COSMETIC` drops `name` at every depth, so each hold's `name` is removed from `holds`.
- But `piece["resumes"] = _canon(spec.get("resumes"), names)` keeps the hold name as raw text.
  The `names` map only rewrites *component* names, and a resume names a *hold*.

So renaming a hold and its resume consistently is a cosmetic edit, and the digest changes.

Reproduce from `brambleloop/` with `PYTHONPATH=src`:

```python
from brambleloop.cir.model import CIR, Op, Row, Component, Hold
from brambleloop.cir.compiler import compile_cir
from brambleloop.cir.benchmarks import cardigan
from brambleloop.quality.physical import design_digest
def build(h):
    a = Component(name="panel", construction="flat", foundation=20, foundation_kind="chain",
        rows=[Row(index=1, ops=[Op("sc", 20)], declared_count=20),
              Row(index=2, ops=[Op("sc", 14)], declared_count=14, skips=6)],
        holds=[Hold(name=h, at_row=1, count=6, from_stitch=14)])
    b = Component(name="strap", construction="flat", foundation=0, foundation_kind="none",
        rows=[Row(index=1, ops=[Op("sc", 6)], declared_count=6)], resumes=h)
    c = CIR.from_dict(cardigan("XS").to_dict()); c.components = [a, b]; c.assembly = []; return c
for h in ("side", "other_hold"):
    c = build(h); print(h, design_digest(c, compile_cir(c))[:12])
# side 24eecb89c808   other_hold 029661d649c1   <- same object, different digest
```

How this fails open: `IncidentTracker.publication_halted(content_hash=digest)` returns halted
only when an open scoped halt has the *same* digest (`gates/incidents.py:125`). So the following
sequence publishes the object that was measured wrong:

1. A sample of design X measures the wrong size, and X's size is halted.
2. X is re-released with only a hold renamed.
3. The new digest differs, so certification is not halted, and the same physical object
   publishes again.

There is a second consequence. A later passing make of the renamed release would lift X's halt
through `resolve_halts_disproved_by`, even though it is the same object. Under R1, that case
should go to owner review instead.

Scope: none of the 11 Launch-0 CIRs has a hold today, so no current product is exposed. Any
future garment with an armhole division is.

Fix:

- canonicalise each hold to its position (`piece#i/hold#j`, after the pieces are sorted);
- write `resumes` as that position, never as the hold name;
- add a hold-rename probe that asserts the digest stays the same.

### R14 (Low, fails closed): `Row.into` is no longer in the digest

The 89eef1e digest listed `into` in `_ROW_KEYS`. `_compiled_rows` keeps `into_count` but drops
*which* row is worked into.

On `market-basket-medium`, rounds 13–35 are all 78 stitches. Setting round 15 to `into=13`
still compiles, and the digest is unchanged. The twin is unchanged too, because it does not
model `into`.

This is a real structural change: round 14 is left unworked. Because the digest only keys size
halts, the error is conservative. An `into`-only correction of a halted design stays halted,
and its passing make goes to owner review rather than lifting the halt. That is a false halt,
not a false clear.

Fix: add `"into_offset": row.index - into_index` (or the canonical row position) to each
compiled row.

## 2. Independence (R6)

**Can any production path record an agreement without passing the allow-list? No.**

- The only writer of `CreatorProfile` in `src/` is `tester_programme.record_agreement`.
  `growth_ops` only reads it.
- `record_agreement` now checks the relationship and qualification unconditionally.
- `/api/tester/agreement` passes both through, behind the operator credential.

**Can the allow-list be bypassed with unicode, whitespace or synonyms? No.**
`_norm_relationship` lower-cases the declaration and then deletes everything outside `[a-z]`.
I tested:

| Accepted (all still mean "none" or "acquaintance (declared)") | Refused |
|---|---|
| `'  NONE  '`, `'n o n e'`, `'N/O/N-E'`, `'None.'`, `'​none'`, `'noné'`, `'nonE\n'`, `'Acquaintance, declared'` | Cyrillic `'nоne'`, full-width `'ｎｏｎｅ'`, circled `'ⓝⓞⓝⓔ'`, `'None (my sister)'`, `'none of note, she is my wife'`, `'no relationship'`, `'n/a'`, `'friend'`, `'acquaintance'`, `'declared acquaintance'`, `'acquaintance(declared) — she is my sister'` |

Stripping characters can only remove text; it cannot add letters. So no accepted input means
anything other than the two allowed declarations. A JSON non-string such as `["none"]` becomes
`"['none']"` and normalises to `none`. That is harmless, because it still declares none.

### R12 (Medium): the evidence path is not tied to an independent tester

Independence is enforced where an agreement is recorded. It is not enforced where the
physical evidence is recorded, and that is the evidence the rule exists to protect.

- `runtime/release.handle_physical_record` builds
  `SampleReport(tester_ref=i.get("tester_ref", "owner"))`. It never checks that the tester has
  a `tester_agreement` permission, with its `independence` block, on file.
- `build2/executor._physical_proof_available` opens the `physical_proof` gate on *any*
  `PhysicalTest` with `completed_at` set.
- `_tester_recruited` opens `tester_roster` on any profile with `delivered > 0` or *any*
  permission. Agreements recorded before R6 had no `independence` field, and they still count.

Reproduce:

1. Submit a `physical.record` job with no `tester_ref`, or with `tester_ref` set to someone with
   no agreement on file.
2. The job is accepted, the sample is stored under `"owner"` (or that unvetted ref), and
   `physical_proof` reads as available.

The owner request text says "one independent tester (not the owner)"
(`launch/readiness.py:309`), and the R6 note says the rule is now "mandatory on every
production caller". Neither is true of this path.

This is pre-existing, not introduced by this delta. It still blocks shipping because this
branch is what prepares the first real sample.

Fix:

- `physical.record` must refuse a `tester_ref` that is missing, `"owner"`, or not a
  `CreatorProfile` whose permissions include `kind == "tester_agreement"` with an
  `independence.relationship` in `ALLOWED_RELATIONSHIPS.values()`;
- `_tester_recruited` should count only such permissions.

### R16 (Info)

`qualification` passes on any non-blank string, for example `"."`. The rule is self-declared
by design. Consider requiring a URL or a reference to a stored photo.

## 3. Cost (R7)

Code is consistent:

- `tester_kit.KIT["max_cost_cad"]` is 66.00;
- the `owner_queue` `tester_outreach` card is 66.00, read from `KIT` (None becomes UNKNOWN);
- the `gate_clearance` `physical_proof` card is 66.00, read from `KIT`;
- `BASKET_KIT_FOR_OWNER_APPROVAL.md` states one figure, CA$66.00. It mentions CA$59.65 only as
  the risk matrix's floor, and says so;
- `OUTREACH_POST` states CA$65.90, and `build` checks that it does;
- the coaster kit is 100.00, which covers its risk-matrix figure of 92.03.

### R13 (Low–Med): the stale figures are still in the committed owner packets

These artifacts were not regenerated:

- `research/final_build/w4/OWNER_ACTIONS.json` (lines 156–160) and
  `src/brambleloop/app/command_center/snapshots/OWNER_ACTIONS.json`: the `tester_outreach`
  decision says "max CA$59.65 incl. yarn", and its max cost is `185.0` / "CA$185.00".
  `physical_proof` is `59.65` (lines 247 and 338).
- `research/final_build/w4/OWNER_ACTIONS.md:16`: CA$59.65 in the text, CA$185.00 in the cost
  column.
- `research/final_build/w4/GATE_CLEARANCE_BUSINESS.md` (lines 8, 62 and 79): 59.65.
- The `tester_kit.py:16` docstring ("ceiling CA$59.65"). It is copied into
  `why_this_pattern`.

`company.owner_decision_batches` shows the committed packet whenever the live queue reports no
batches. The fallback text says "may be out of date", but it shows the owner three different
figures (CA$185, CA$59.65 and CA$66) for one decision.

Fix: regenerate the packets and the snapshot, and reword the docstring as the risk-matrix floor.

### R15 (Low)

`tester_kit.build` now checks only `max_cost_cad >= max(promise, risk-matrix ceiling)`. The old
equality check pinned the figure. Now a typo such as 660.00 builds silently and is quoted to
the owner as the ceiling.

Suggested fix: add an upper bound, for example
`max_cost_cad <= promised + PROCESSING_ALLOWANCE` (CA$0.10 for the basket, CA$0.04 for the
coaster). That would pin the figure to its stated basis.

### R17 (Info)

`launch/readiness.PHYSICAL_SAMPLE.max_cost_cad = 8*20+25` (CA$185) uses the same formula that
was removed from `owner_queue`. It is parked and surfaced nowhere: `owner_queue` reads only
`PHYSICAL_SAMPLE_PARKED`. Still, if the park were reversed it would re-introduce a second
figure. Point it at `tester_kit.KIT`.

## 4. Overall: gates relaxed or new fail-open paths?

I found neither in the code I read:

- `_non_finite` (R9) refuses NaN and infinite measurements as `SAMPLE_MEASUREMENT_INVALID`, and
  `release.py` lists that code as incomplete;
- `design_digest` returns None on any exception or failed compile, and every caller treats None
  as halted (`incidents.py:123`) or skips the lift (`:138`);
- `certificate.bind_physical_evidence` adds only `size_proven`, which is informational;
- `first_customer` adds only a coverage note;
- `readiness` is a text change.

The remaining fail-open is R11.

## 5. Suites

Each suite ran one at a time, from `brambleloop/`, with
`PYTHONPATH=src:tests nice -n 19 python tests/<f>.py`, at 3e542a17.

All 12 runs exited 0 (owner-queue race run twice):

| Suite | Result |
|---|---|
| test_physfix | 31/31 |
| test_secreview_physfix_adversarial | 12/12 |
| test_secreview_physfix_42eac69_probes | 8/8 |
| test_secreview_physfix_89eef1e_probes | 8/8 |
| test_w4_b2gates | exit 0, all OK |
| test_risk_matrix | exit 0, all OK |
| test_physfix_photo_first | 8/8 |
| test_w4_launchfix | 32 passed, 0 failed |
| test_vacuity | exit 0, all OK |
| test_first_customer_gate | 12 passing, 0 failing |
| test_w4_owner_queue_race (run 1) | exit 0, all OK |
| test_w4_owner_queue_race (run 2) | exit 0, all OK |

The green suites do not cover R11, R12 or R14: no existing probe renames a hold, records a sample under `"owner"`, or changes `Row.into`.

Probe scripts were run from `/tmp` and are not committed. The reproductions above are
self-contained.
