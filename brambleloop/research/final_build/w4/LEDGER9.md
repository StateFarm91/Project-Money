# W4-LEDGER9: the "918th row", and per-row delivery states

Base: `origin/claude/w4-INTEG8-next` d8f5e852. Generator: `ledger9_states.py` (new, beside
`b0_reconcile.py`). It reads `ENGINEERING_LEDGER.json` and does not change it. Output:
`LEDGER9_STATES.json`. `b0_reconcile.py`, the ledger rows and `src/` are unchanged.

## 1. The 918th row: no such row exists

- `ENGINEERING_LEDGER.json` has **917 Final Master rows**. They match the registry records
  exactly: no extra, missing or duplicate rows. `ledger9_states.py` checks this on every run
  and exits 1 if it fails.
  - The 917 records are the 866 v1.0 records (`master_registry.json`) plus the 51 v1.1
    records F-880..F-930 (`master_registry_v1_1.json`).
  - The IDs therefore run **F-001..F-930, not F-001..F-917**.
  - F-631..F-650 do not exist in the source (MASTER_SPEC_ERRATA E-1).
  - F-514..F-520 each appear twice, as `@v0.15` and `@v0.16` (E-2, D-FB-2). These are 14
    records for 7 IDs.
  - 930 − 20 + 7 = 917. **Additions: 0.**
- Every published total in `LEDGER_STATUS.md` adds up to 917:
  - (a) 871, (b) 0, (c) 3 and (d) 0;
  - (e) **43** = 20 awaiting + 4 owner-gated + 3 by design + 4 proposed + 5 gated + 7 n/a.
- **Origin of 918:** F-114 was counted twice.
  - At 943d64d3 and 6cfc04b5, F-114 was in (e) owner-gated (5 rows, so (e) = 44).
  - Commit 43ec2790 ("add claude/w4-C07 (0d7da718)") moved F-114 to (c) owner-held through
    `OWNER_HELD` in `b0_reconcile.py`. That made (c) 3 and owner-gated 4, so (e) = 43.
  - The figure "(e) 44" comes from the pre-43ec2790 table. Adding it to the current (c) = 3
    counts F-114 in both (c) and (e).
- This was a reader's sum, not a generator error, so the generator is not changed.
- Separate finding: `b0_reconcile.py`'s INTEG8 column reads `origin/claude/w4-INTEG8`
  (abf94bdf). That is 44 commits behind INTEG8-next, though it is an ancestor of it. (b) is
  already 0 against it, so no count changes. `ledger9_states.py` defaults to INTEG8-next.

## 2. States per row

How each state is set:

| state | rule (evidence used) |
|---|---|
| Built | One of these holds: `engineering_complete`; b0_class COMPLETE, COMPLETE_ON_BRANCH, MISSING_INTEGRATION, OWNER_HELD, AWAITING_EVIDENCE or PROPOSED_COMPLETE (B0 says the code exists). BY_DESIGN and F-652 count as partial. |
| Tested | One of these holds: `engineering_complete` (its definition includes tested); A-H status D-G; a cited `test_`; a recorded commit that changes `brambleloop/tests/`. Rows that are built but match none of these are marked unverified. |
| Integrated | Every recorded code commit for the row (`branch_work`, and SHAs named in why or b0_reason) is an ancestor of `--integrated` (default INTEG8-next). |
| Reviewed | Not recorded per row anywhere: the ledger definitions say so, and the Batch 4 review is pending. |
| Deployed | Every recorded commit is an ancestor of `--production`. These include the deployed tree the ledger named for F/G rows (b931d17/b997efd) and every later code commit that names the row. A row with no row-level commit can rely only on B0's "in the combined candidate" (2aeb177f). If nothing is recorded, the value is `not_recorded`; it is never inferred. |
| Production verified | Only when the ledger's own acceptance evidence holds (status G: production readback or acceptance records on a deployed tree) and no code commit for the row is newer than that tree. A row that is deployed but has no such evidence is `pending`, which means deployed, not yet production-verified. |
| Gate | Set only when acceptance is open. For built rows it comes from the B0 class (OWNER_HELD/OWNER_GATED → owner; GENUINELY_GATED → external) or from `board_root` (owner, data/customer and external sets in the script). Unbuilt rows are gated only by a B0 class with a recorded reason (quoted text, owner decision, by design), never by a board root. Unfinished executable work is never gated. |
| Not applicable | b0_class NOT_APPLICABLE. |

To regenerate after a deploy, run this from `brambleloop/`:
`python3 research/final_build/w4/ledger9_states.py --production <sha>`

### Counts at production ee35a493 (deployed 2026-10-27T16:06Z), integrated ref INTEG8-next d8f5e852

| state | Final Master (917 original + 0 additions) | Build 2 (320) |
|---|---|---|
| Built | yes 898, partial 4, no 8, n/a 7 | yes 317, n/a 3 |
| Tested | yes 867, unverified 35, no 8, n/a 7 | yes 317, n/a 3 |
| Integrated (INTEG8-next) | yes 896, partial 4, no 10, n/a 7 | yes 317, n/a 3 |
| Reviewed | not recorded 910, n/a 7 | not recorded 317, n/a 3 |
| Deployed | yes 760, partial 1, no 146, not recorded 3, n/a 7 | yes 315, no 2, n/a 3 |
| Production verified | yes 357, pending 404, no 149, n/a 7 | yes 97, pending 218, no 2, n/a 3 |
| Owner-gated | 139 | 36 |
| Data/customer-gated | 54 | 41 |
| External-gated | 39 | 8 |
| By design (recorded decision) | 3 | 0 |
| Not gated (accepted, or open work that is not gated) | 675 | 232 |
| Not applicable | 7 | 3 |

Furthest state reached (exclusive; sums to the total):

| scope | prod. verified | deployed | integrated | tested | built partial | not built | n/a |
|---|---|---|---|---|---|---|---|
| FM | 357 | 403 | 136 | 2 | 4 | 8 | 7 |
| B2 | 97 | 218 | 2 | 0 | 0 | 0 | 3 |

### Before and after the deploy

| | b2e49455 | ee35a493 |
|---|---|---|
| FM Deployed | yes 447, no 268, not recorded 195 | yes 760, partial 1, no 146, not recorded 3 |
| FM Production verified | yes 357, pending 90, no 463 | yes 357, pending 404, no 149 |
| B2 Deployed | yes 229, no 5, not recorded 83 | yes 315, no 2 |
| B2 Production verified | yes 97, pending 132, no 88 | yes 97, pending 218, no 2 |

Notes on the ee35a493 figures:

- **Rows not deployed.** The FM "no" rows are:
  - the 126 Batch 4 (INTEG8-next) rows;
  - rows not built;
  - F-579/F-607, which are not integrated;
  - nine COMPLETE rows: F-093, F-113, F-251, F-381, F-405, F-457, F-672, F-852 and F-867. Each
    has a later code commit that exists only in INTEG8-next: 5aa78f39, 11b2ecf2, 2b4ecf15,
    31510b44, 9a6af055, fad3afa1, 4676c472, f2b65bb2 and 01b1c8cf.

  The B2 "no" rows are #11 (5d248cff) and #207 (720b2915). In both scopes, where an earlier
  version is deployed, the JSON says so.
- **Verification that predates a later change.** F-251, F-852, F-867 and B2#207 are G, but
  each has a later code commit. They become `pending` once that commit deploys. Their earlier
  verification is not carried forward.

## 3. Rows whose class looks unsupported by its evidence (reported, not changed)

**A. In (a) because INTEG8 contains commits that mention them.** Their ledger status is
A or B, and no recorded commit changes a test (7 rows):

- F-038 (A)
- F-053, F-054, F-055, F-733, F-739, F-859 (B)

**B. AWAITING_EVIDENCE or PROPOSED_COMPLETE ("the code is in place").** Their ledger A-H
status is B (partial), and no newer commit or test is recorded (18 rows):

- F-005, F-007, F-009, F-027, F-031, F-041, F-243, F-247, F-252, F-253, F-278, F-396, F-437,
  F-507, F-515@v0.16, F-594, F-628
- F-446 (PROPOSED_COMPLETE)

**C. OWNER_GATED on work that is not fully built, where the hold is a coordinator call and not
an owner-only action** (2 rows):

- F-438: "provider or fetch-allowlist host (coordinator/owner call)". It looks
  fixture-executable.
- F-652: a coordinator decision; the work is partly built.

**D. Weak but not flagged by the script:**

- F-450 is in (a) on a coordinator ruling ("ruled already met", 4bd020fc). Its test comes
  only through commit 4bd020fc.
- F-113 is in (a) on 6ea10a52, with ledger status A. It passes only because a recorded commit
  changes tests.

Checked and supported:

- **GENUINELY_GATED** F-037, F-155, F-239, F-293 and F-566. Each quotes the requirement text,
  and the code cannot be written.
- **OWNER_GATED** F-483 (the owner's paid CI minutes) and F-789 (needs an owner ruling against
  a non-negotiable).
- **No Build 2 row is flagged.**

The full per-row list is under `scopes.*.class_unsupported` in `LEDGER9_STATES.json`.
