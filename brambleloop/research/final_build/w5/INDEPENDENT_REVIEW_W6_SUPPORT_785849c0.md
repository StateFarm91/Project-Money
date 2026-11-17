# Independent delta review: W6 support-defect incident, 785849c0

Reviewed 2026-11-07 (UTC). Scope: `git diff 05961fd0 785849c0`, plus all of `support/defects.py`, `/api/owner/decision` (app/main.py:1436-1485), `REMEDIATION["support.defect"]` (ops/incident_lifecycle.py:190-194) and `handle_support_triage` (runtime/release.py:~2600-2622).

- Worktree: `/home/user/bl-runs/wt-rev-support3` (detached at 785849c0). Nothing was committed or pushed, and every mutant was reverted (`git status` is clean).
- Scripts (run from `brambleloop/` with `/home/user/bl-runs/venv-integ4/bin/python`):
  - `/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/rev3/repro.py` (R1-R5)
  - `/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/rev3/route_probe.py` (HTTP)
  - `/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/rev3/mut.py` (16 mutants; output in `mut.out`)

## Verdict: DO NOT SHIP 785849c0

N-1 through N-4 are fixed for the cases they describe, and the owner route is authenticated and fail-closed. But supersession is unconditional:
- Any other certified version ends the incident, including a confirmed one. That holds even when the new version has an identical CIR, so the defect certainly persists.
- No incident, hold, card or signal carries over to the new version.

That is the exact property this delta was asked to protect ("should not hide that the defect may persist"). Two more problems:
- `confirmed` is not a sticky state. The card re-opens on every triage, and a later generic resolution releases the hold.
- Null-version cases are re-attributed to whatever version is current, which re-creates N-2 for unversioned cases on the corrected release.

## Claimed fixes

| Finding | Fixed? | Evidence |
|---|---|---|
| N-1: the hold never clears | **Yes.** There is a route, a REMEDIATION row and an owner card. `not_a_defect` resolves and releases. | Test `owner_decides...`; M7, M9, M13, M16 KILLED. `needs_owner_path` no longer lists it. |
| N-2: cross-version buyers | **Yes for versioned cases.** `by_version` counts distinct refs per version (defects.py:92-106). **No for null-version cases** (see F-3). | M12 KILLED; M10 (drop the null→current mapping) SURVIVES. |
| N-3: unstored version | **Yes.** It is filtered by `withholding._release` (defects.py:97-100). | M11 KILLED. |
| N-4: hold timestamp churn | **Yes.** The problem string is now constant (defects.py:163-164). | Test asserts `reasons` is unchanged after a new mention. |

## Findings

### F-1 (HIGH): supersession silently ends even a `confirmed` defect, with no carry-over to the new version.
- **Location.** defects.py:310-338, the condition at :325 (`cur != d["version"]`), called every triage from release.py `handle_support_triage`.
- **What it does.** Any certified version that differs from the incident's version resolves the incident as "superseded", closes the card and sets `keep_hold`.
  - It never checks that the new version is newer (it uses `!=`).
  - It never checks that the row changed, or that the defect was fixed.
  - It ignores `owner_decision == "confirmed"`. The module docstring (defects.py:46-48) says confirmed "records that a corrected version is required", but any certification counts as the correction.
- **On the new version.** There is no incident, no hold, no card and no note. Buyer counting restarts at zero on that version.
- **Repro R4.** Open the incident, decide `confirmed`, then certify 9.0.0 with the **same CIR**. The output is:
  `[('...:1.2.1:row3', True, 'superseded by certified ...@9.0.0; 1.2.1 stays withheld')]`, `9.0.0 withheld: False`, `open cards: []`.
- **Repro R2: an old-version incident never reaches the owner.** Four buyers cite row 3 on the stored but uncertified 0.9.0. The incident is opened, its card raised and superseded **in the same triage**. The output is `resolved: True ... cards: [(1, True, 'superseded')]`. The new test `test_buyers_are_counted_per_version...` enshrines this without noticing it.
- **Fix.**
  - Supersede only when the new version is newer and its CIR differs on the cited row.
  - Never supersede a `confirmed` incident automatically. Carry a `may_persist` incident or card onto the new version, naming the old signature, instead of resolving silently.
  - Do not open-and-supersede in one sweep. If a non-current version reaches the threshold, ask whether the current version shares the row.

### F-2 (MED): `confirmed` is not sticky.
- **Location.** defects.py:296-305 and 157-158.
- **The card re-opens.** `confirmed` closes the card as SATISFIED but leaves the incident open. The next triage's `escalate` calls `_owner_card` → `owner_queue.ensure`, which finds no open row and inserts a new card asking the same "Decide..." question. That happens every time the owner decides `confirmed`.
- **A later resolution releases the hold.** `confirmed` does not set `keep_hold`. Any later generic resolution of the incident (`incident_lifecycle.resolve_signatures`, `GateKeeper.resolve`, hygiene) makes `release_resolved` clear the hold on a release the owner confirmed is defective.
- **Repro R1.** Cards go `[(1, True, 'satisfied')]` → after the next triage `[(1, True, 'satisfied'), (2, False, 'open')]`.
- **Repro R5.** Decide `confirmed`, call `resolve_signatures(...)`, then triage. The output is `withheld: False`.
- **Flip.** `confirmed` → `not_a_defect` is accepted, and the test asserts it. Allowing a reversal is defensible, but it should be explicit: record the prior decision instead of overwriting `owner_decision`, and require a why that addresses it. Right now the confirmed record is lost (defects.py:293-295 overwrites it).
- **Fix.**
  - Have `_owner_card` skip when `owner_decision.decision == "confirmed"`. Or keep one open "ship a corrected version" card with a different action.
  - Set `keep_hold` on `confirmed`.
  - Keep a decision history.

### F-3 (MED): null-version cases follow whatever version is current, so the corrected release is held on old buyers.
- **Location.** defects.py:94 (`v = v or current`).
- **Effect.** Three buyers with no recorded version hold 1.2.1. The fix 9.0.0 is certified, and the 1.2.1 incident is superseded. On the next triage the same three cases are counted against 9.0.0, which opens a new incident and holds the corrected version. That is N-2 again for unversioned cases.
- **Repro R3.** `held 9.0.0 = True [('...:1.2.1:row3', True), ('...:9.0.0:row3', False)]`.
- **Untested.** M10 (drop the mapping) SURVIVES.
- **Fix.** Attribute an unversioned case to the version that was current when the case was created (`SupportCase.at` against `PatternVersion` certification order). Or count unversioned cases only toward an incident that already exists.

### F-4 (LOW): guards with no test (surviving mutants).
- M3: drop the `startswith(SIGNATURE)` family check (defects.py:290). The route probe shows the guard works today (`health:x` id → 400), but nothing pins it.
- M4: drop the already-resolved refusal (defects.py:288-292 region).
- M8: no card close on supersede (defects.py:331-335). An orphan open card for a resolved incident would go unnoticed.
- M14 / M15: the route's `support_defect` branch, and mapping `DecisionRefused` to 400 (main.py:1474-1482). There is no HTTP test of `kind=support_defect` anywhere; `test_cert_owner_decision` covers only `improvement`.

### F-5 (LOW): validation of the `why` field and body shape.
- **Location.** defects.py:286; main.py:1464.
- **What is checked.** `why` is only checked for at least 10 non-space characters. It is unbounded: a 200,000-character why was stored verbatim in `Incident.detail.owner_decision.why`, and also, for `not_a_defect`, in `detail.resolution` (route_probe: `why huge 200`, `stored why len 200000`).
- **Body shape.** A JSON array body raises `AttributeError` and returns 500 (pre-existing, applies to all kinds).
- **Leak check.** I found no path to Learning. `improve/mine.py:_read` reads only **unresolved** incidents and uses `summary`, the family and `detail.cir`/`pattern_version`. The why text is owner-written, and no support case text is copied into incident detail. Still, store the why bounded (for example 500 characters) and keep it out of `resolution`, which other readers display.

### F-6 (LOW): non-idempotent retry, and a lexical tie-break.
- **Retry.** Re-posting the same `not_a_defect` after a lost response returns 400 "already resolved" (R1 retry) instead of returning the recorded decision.
- **Tie-break.** Ties among non-current versions break by version string order (defects.py:101), so "10.0.0" sorts before "9.0.0". The current version still wins when it reaches the threshold.

### Checked and OK
- **Auth.** No token → 401, bad token → 401, server token unset → 503 (fail-closed). `test_route_auth_default_deny` asserts 401.
- **Incident type.** A non-support incident id or a missing id returns 400. The decision whitelist and why length are enforced (M1 and M2 KILLED).
- **Old version's hold.** `keep_hold` is honoured by `release_resolved` (M5 KILLED). `record_owner_decision` cannot reach a superseded incident (it is refused as resolved), so there is no bypass through the route. The remaining bypass is F-2 (`confirmed` without `keep_hold`).
- **Owner card contents.** It carries the exact call, `max_cost_cad=0.0`, `minutes=10` and a consequence. It is deduplicated by `ensure` while open. It is closed on `not_a_defect`, `confirmed` and supersede, but not when another resolver closes the incident.

## Mutants (all three suites, one at a time, venv-integ4)

| Id | Mutation | Result |
|---|---|---|
| M1 | no decision whitelist | KILLED |
| M2 | no why length check | KILLED |
| M3 | no signature-family check | **SURVIVED** |
| M4 | no already-resolved check | **SURVIVED** |
| M5 | `release_resolved` ignores `keep_hold` | KILLED |
| M6 | supersede disabled | KILLED |
| M7 | card not closed on decision | KILLED |
| M8 | card not closed on supersede | **SURVIVED** |
| M9 | no owner card | KILLED |
| M10 | null version dropped | **SURVIVED** |
| M11 | unstored versions allowed | KILLED |
| M12 | no preference for the current version | KILLED |
| M13 | no release inside the decision | KILLED |
| M14 | route drops the `support_defect` kind | **SURVIVED** |
| M15 | route returns 500 on `DecisionRefused` | **SURVIVED** |
| M16 | `confirmed` resolves too | KILLED |

## Suites (baseline, unmutated)

| Suite | Result |
|---|---|
| `tests/test_w6_support_defect_incident.py` | 0 failures |
| `tests/test_cert_owner_decision.py` | PASS, 0 failing |
| `tests/test_route_auth_default_deny.py` | 8/8 passed |
