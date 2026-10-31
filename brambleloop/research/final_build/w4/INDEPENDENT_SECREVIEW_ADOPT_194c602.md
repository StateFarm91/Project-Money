# Independent security review (delta): `claude/w4-ADOPT` `752950e4..194c6029`

- **Subject:** `git diff 752950e4..194c6029`. Two commits, 6 files, +296/−17.
  - Product code: `ops/retention.py`, `publish/manual_adoption.py`, `runtime/etsy_ops.py`.
  - Tests: the two ADOPT suites.
  - Docs: ADOPT.md.
- **Prior review:** `INDEPENDENT_SECREVIEW_ADOPT_752950e.md` on `claude/w4-SECREVIEW-ADOPT-752950e`. It reported R-1 and N-1 to N-5.
- **Reviewer:** an independent reviewer. I judged the code, not ADOPT.md. Date: 2026-10-31 (UTC). No product code was changed.
- **Method:**
  - I read the full diff.
  - I applied 17 single-point mutants, one at a time, in a scratch worktree at `194c6029`, and re-ran the relevant suites against each.
  - All runs were one at a time, using `PYTHONPATH=src:tests nice -n 19 python tests/<f>`. The environment needed `pip install -r requirements.lock` first.

## Verdict: **SHIP**

- Every prior finding with a security or operational impact (R-1, N-1, N-2, N-3, N-4) is fixed at the root, and a test fails when its fix is mutated.
- Nothing uncompared can reach "proven".
- Drift on a listing with no certified payload stays halting after a baseline.
- The diff adds no Etsy write, and it relaxes no gate. The only gate change makes N-1 stricter.
- The changed precondition in `test_after_acceptance_policy_fields_still_drift` is legitimate (see below).
- What remains is three Info items, all fail-closed redundancy or untested hygiene. None blocks shipping.

## Test runs (`194c6029`)

| Suite | Result |
|---|---|
| `test_w4_adopt_manual_listing` | OK, exit 0 |
| `test_w4_secreview_adopt_adversarial` | OK, `failed: 0` |
| `test_w4_fmbatch1_retention_guard` | OK, exit 0. It failed at `752950e4` (R-1). |
| `test_rc1_own_verify` | OK, exit 0 |
| `test_etsy_readback_observe` | 37 passed, 0 failed |

## Mutation results

"Killed" means at least one suite failed. The default suites are the two ADOPT suites. R-1 used the retention guard.

| Fix | Mutant | Result |
|---|---|---|
| R-1 | rename the `listing.adopted_manual` entry in `KNOWN_READ_ACTIONS` | killed (`test_w4_fmbatch1_retention_guard`) |
| N-1 | drop the `properties: no certified payload …; UNVERIFIED` line in `_field_drift` | killed (both suites, including `test_a1_…`) |
| N-2 | `proof_problems` ignores the baseline's notes (`notes = []`) | killed (branch suite) |
| N-2 | no fallback to the adoption's notes for an older baseline | killed (branch suite) |
| N-2 | preview does not carry `unverified` into `not_covered_by_baseline` | killed (both suites, including `test_a2_…`) |
| N-2 | `accept_baseline` stores `not_verifiable: []` | **survives**, see I-1 |
| N-3 | preview passes `read["remote"]` without the properties read | killed (branch suite) |
| N-3 | no "getListingProperties was not read" line in the preview | **survives**, see I-2 |
| N-4 | drop the UNVERIFIED clause | killed |
| N-4 | drop the `differences` clause | killed |
| N-4 | drop the `baseline.not_covered` clause | killed |
| N-4 | drop the open-incident clause | killed |
| N-4 | drop only the `etsy.listing_drift` signature | killed |
| N-5 | drop the claim backfill on `repeat` | **survives**, see I-3 |
| F-1 (prior) | drop `_policy_field_drift` on the no-payload path | killed (`test_after_acceptance_policy_fields_still_drift`, `test_materials_left_empty_…`) |
| precondition | always emit a policy-field drift line on the no-payload path | killed (`test_after_acceptance_policy_fields_still_drift`) |

N-4 is closed. With the other conditions satisfied, each proof clause now fails a test on its own.

## The changed precondition: legitimate

- **Old precondition:** after acceptance, `lid not in field_drift`.
- **Why it had to change:** after the N-1 fix, a listing with no certified payload always carries the `properties … UNVERIFIED` line. The old precondition is therefore false for the correct reason, the same way the earlier `materials=[]` change was.
- **New precondition:** no line starting with a policy field (`who_made`, `when_made`, `is_supply`, `type`, `quantity`, `materials`).
- **The new test discriminates in both directions:**
  - It fails if policy drift is not computed (mutant F-1 above).
  - It fails if policy drift is reported spuriously before the change (mutant "precondition" above).
- **What it does not check:** that the accepted copy edit is absent. That is pinned separately by `test_hand_edits_accepted_as_baseline_…`, which asserts that no `description:`/`title:`/`tags:` line is present and that the halting incident stays open with the UNVERIFIED properties line.
- **Effect on scope:** the test's intent is unchanged. It verifies that policy fields are still compared after a baseline, and its scope is narrower and more targeted than before.

## Answers to the brief

1. **Each finding is fixed at the root, with a discriminating test.** See the mutation table. The exceptions, I-1 to I-3, are redundancies or Info hygiene, not unguarded paths.
2. **Nothing uncompared reaches "proven".**
   - Every route by which an uncompared item is recorded reaches `proof_problems`:
     - the adoption's `not_verifiable`;
     - the preview's fresh `not_verifiable`;
     - an unread or unreadable properties line;
     - the no-payload line in `not_covered_by_baseline` (`manual_adoption.py:821`).
   - Each route feeds both `not_covered` and the baseline's `not_verifiable`, so either one alone keeps the proof red.
   - The only exempt note is the pre-existing `digital file hash: NOT READABLE`, which was accepted in earlier reviews.
   - `accept_baseline` recomputes the preview on the server (`manual_adoption.py:842`). It does not trust a client-supplied `shown`.
   - The `[:20]` truncation keeps at least one item, so the proof still fails closed.
3. **No-payload drift stays halting.**
   - `_field_drift` emits a properties UNVERIFIED line.
   - `accept_baseline` keeps `etsy.listing_drift:<id>` open, because that line is not a baseline field.
   - No census can resolve the incident until a certified payload exists. `test_a1_…` pins this: the incident stays open and halting, and the proof stays non-empty.
4. **No fail-open path, no Etsy writes, no gate relaxed.**
   - The diff adds no Etsy call. Every suite asserts `writes() == []`. The only `.delete(` in the diff removes a test-database row.
   - Retention now runs, and the new action is protected as `lifetime_total`, which is correct for a reader that collects every adoption.

## Findings

### I-1: INFO. The baseline's stored `not_verifiable` is redundant with `not_covered`

**What:** the preview already appends `unverified` to `not_covered_by_baseline`, and `proof_problems` reads `not_covered`. Storing `not_verifiable: []` therefore changes no outcome.

**Assessment:** this is defence in depth, and it fails closed. Its second purpose, the older-baseline fallback, *is* pinned.

**Reproduce:** in `accept_baseline`, replace `"not_verifiable": shown["not_verifiable"][:20]` with `"not_verifiable": []`. Both ADOPT suites stay green.

**Optional fix:** add one test whose baseline has `not_covered: []` while the recorded `not_verifiable` is non-empty. The existing case `baseline.not_verifiable` does this by direct injection, but no test reaches it end to end.

### I-2: INFO. The preview's own "properties not read" line is redundant with `compare()`

**What:** when the certified taxonomy is known with properties, `compare()` already emits `properties: getListingProperties was not read` (`manual_adoption.py:341`), and the preview carries it forward.

**When the preview's own line matters:** only when `want_props` is `None`. In that case `not_covered_by_baseline` still reports properties against the payload, so the result fails closed.

**Reproduce:** replace the `else: unverified.append("properties: getListingProperties was not read")` branch with `pass`. The suites stay green, because `test_preview_compares_properties_…` still finds the line, which now comes from `compare()`.

### I-3: INFO. The N-5 claim backfill on `repeat` is untested

**Reproduce:** change `if claim is None:` in the `repeat` branch to `if False:`. The suites stay green.

**Assessment:** this is harmless. `af042099` was never shipped, so no pre-claim adoptions exist to backfill. A test that inserts an adoption without a claim and then repeats the adoption would pin it.

### Note (not a defect)

The launch-day consequence stated in ADOPT.md is accurate:
- Until a certified payload exists, every adopted listing keeps one halting `etsy.listing_drift` line, even after the owner accepts a copy baseline.
- This is the intended fail-closed behaviour.
- BUILD_STATE should keep it visible as a known halting item, not as a defect.

## Appendix: mutation driver

`git worktree add /tmp/mw 194c6029`, then run the script from outside the worktree. Each mutant is an exact, single-occurrence string replacement. The script restores the file after each run.

```python
import subprocess, sys, pathlib
R = pathlib.Path("/tmp/mw/brambleloop")
MA="src/brambleloop/publish/manual_adoption.py"; EO="src/brambleloop/runtime/etsy_ops.py"; RT="src/brambleloop/ops/retention.py"
M = {
 "R1 drop retention entry": (RT, '    "listing.adopted_manual": ("lifetime_total",', '    "listing.adopted_manual_X": ("lifetime_total",', ["test_w4_fmbatch1_retention_guard"]),
 "N1 drop UNVERIFIED properties line": (EO, '''                    + [f"properties: no certified payload to compare against "
                       f"({str(e)[:120]}); UNVERIFIED"])''', ''')''', None),
 "N2a proof: baseline notes ignored": (MA, '''        notes = (base["not_verifiable"] if "not_verifiable" in base
                 else adopted.get("not_verifiable") or [])''', '''        notes = []''', None),
 "N2b proof: no fallback for old baseline": (MA, '''        notes = (base["not_verifiable"] if "not_verifiable" in base
                 else adopted.get("not_verifiable") or [])''', '''        notes = base.get("not_verifiable") or []''', None),
 "N2c preview: unverified not carried into not_covered": (MA, '''    not_covered += [n for n in unverified if n not in not_covered]''', '''    pass''', None),
 "N2d accept: not_verifiable not stored": (MA, '''                "not_verifiable": shown["not_verifiable"][:20]}''', '''                "not_verifiable": []}''', None),
 "N3a preview uses read without properties": (MA, '''            remote["properties"] = canonical_properties(read["properties"])''', '''            pass''', None),
 "N3b unread properties not noted": (MA, '''        unverified.append("properties: getListingProperties was not read")''', '''        pass''', None),
 "N4 drop UNVERIFIED clause": (MA, '''        out.append("manual adoption UNVERIFIED (not read back)")''', '''        pass''', None),
 "N4 drop differences clause": (MA, '''        uncovered = [f"{d.get('field')}" for d in adopted.get("differences") or []]''', '''        uncovered = []''', None),
 "N4 drop baseline.not_covered clause": (MA, '''        uncovered = list(base.get("not_covered") or [])''', '''        uncovered = []''', None),
 "N4 drop incident clause": (MA, '''                out.append(f"open incident {sig}")''', '''                pass''', None),
 "N4 drop drift-incident sig only": (MA, '''        for sig in (f"{REVIEW_PREFIX}{slug}@{version}", f"etsy.listing_drift:{lid}"):''', '''        for sig in (f"{REVIEW_PREFIX}{slug}@{version}",):''', None),
 "N5 drop claim backfill": (MA, '''if claim is None:   # N-5: backfill an adoption recorded before claims existed
                    s.add(ManualListingClaim(etsy_listing_id=lid, slug=slug, version=version))''', '''if False:
                    pass''', None),
}
M["F1 no-payload path drops policy drift"]=(EO, "return (copy + _policy_field_drift(db, known, remote)", "return (copy + []", None)
M["precondition: policy drift always reported"]=(EO, "return (copy + _policy_field_drift(db, known, remote)", "return (copy + ['who_made: x'] + _policy_field_drift(db, known, remote)", None)
DEF=["test_w4_adopt_manual_listing","test_w4_secreview_adopt_adversarial"]
only = sys.argv[1:]
for name,(f,old,new,suites) in M.items():
    if only and not any(o in name for o in only): continue
    p=R/f; src=p.read_text(); assert src.count(old)==1,(name,src.count(old)); p.write_text(src.replace(old,new))
    res=[]
    try:
        for s in suites or DEF:
            r=subprocess.run(["nice","-n","19","python",f"tests/{s}.py"],cwd=R,env={"PYTHONPATH":"src:tests","PATH":"/usr/bin:/bin:/usr/local/bin"},capture_output=True,text=True,timeout=900)
            fails=[l.split()[1] for l in r.stdout.splitlines() if l.startswith("FAIL")]
            res.append(f"{s}: exit {r.returncode} {fails[:4]}")
    finally: p.write_text(src)
    print(("KILLED  " if any("exit 0" not in x for x in res) else "SURVIVED") , name, "|", " ; ".join(res), flush=True)
```
