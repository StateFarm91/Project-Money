# Independent security review (delta): `claude/w4-ADOPT` `af042099..752950e4`

- **Subject:** `git diff af042099..752950e4`, 2 commits, 7 files, +637/−57.
- **Prior review:** `INDEPENDENT_SECREVIEW_ADOPT_af04209.md`, which reported F-1 to F-4.
- **Reviewer:** an independent reviewer. I judged the code, not ADOPT.md. Date: 2026-10-31 (UTC). No product code was changed.
- **Method:**
  - I read the full diff.
  - I mutated each fix in a scratch worktree at `752950e4`, then re-ran the two ADOPT suites against each mutant.
  - I ran two adversarial experiments (reproductions below).
  - All runs were one at a time, using `PYTHONPATH=src:tests nice -n 19 python tests/<f>`. The environment needed `pip install -r requirements.lock`.

## Verdict: **DO NOT SHIP**

The four prior findings are fixed at the root, and the tests pin them. Three new problems remain:

1. **R-1 (High, operational).** The required suite `test_w4_fmbatch1_retention_guard` **fails**. The same unclassified audit action makes `ops.retention.apply` raise `RetentionRefused` in production, so the retention job stops running entirely. The bug predates this delta, but the branch still ships it.
2. **N-1 (Medium).** After a baseline is accepted, the halting drift incident for a listing that has no certified payload is resolved by the next census. From then on, listing properties are compared by nothing.
3. **N-2 (Medium, latent fail-open).** `proof_problems` discards every adoption "not verifiable" note once a baseline exists. Today it fails closed only because of an unrelated defect (N-3). Fix N-3 alone and an uncompared listing is proven.

Fix R-1, N-1 and N-2 together with N-3, each with a test, and the branch is shippable.

## Test runs (branch `752950e4`)

| Suite | Result |
|---|---|
| `test_w4_adopt_manual_listing` | OK, exit 0 |
| `test_w4_secreview_adopt_adversarial` | OK, `failed: 0` |
| `test_rc1_own_verify` | OK |
| `test_etsy_readback_observe` | 37 passed, 0 failed |
| `test_route_auth_default_deny` | 8/8 passed |
| `test_w4_fmbatch1_retention_guard` | **FAIL** `test_every_action_the_real_code_reads_is_classified`: `unknown_read_actions() == ['listing.adopted_manual']`. The same value is returned at `af042099`, so the bug predates this delta. |

## Mutation results

Each mutant was applied alone. "Killed" means at least one ADOPT suite failed.

| Fix | Mutant | Result |
|---|---|---|
| F-1 | census compares only the baseline copy fields (pre-fix behaviour) | killed (both suites) |
| F-1 | drop `_policy_field_drift` (no-payload path) | killed (both) |
| F-1 | drop `_certified_field_drift(skip=…)` (full-payload path) | killed (adversarial unit test) |
| F-1 | `accept_baseline` resolves drift unconditionally | killed (branch suite) |
| F-1 | preview reports `not_covered_by_baseline = []` | killed (branch suite) |
| F-2 | VERIFIED ⇒ proven (pre-fix behaviour) | killed (both) |
| F-2 | ignore recorded `differences` | **survives** |
| F-2 | ignore open review/drift incidents | **survives** |
| F-2 | ignore `baseline.not_covered` | **survives** |
| F-2 | ignore `not_verifiable` (no baseline) | killed (branch suite) |
| F-3 | no `ManualListingClaim` row (keep the in-transaction re-check) | killed (race test) |
| F-3 | no in-transaction re-check (keep the claim row) | survives. This is acceptable: the database key alone is sufficient. |
| F-4 | add `'a' != "published"` to `verify_checks.py` | killed (static guard) |

The three surviving F-2 mutants cover for each other. Each clause of the proof is redundant with the incident check, so no test pins any one of them. See N-4.

## Answers to the brief

1. **F-1 to F-4 are fixed at the root, and each has a test that fails without its fix.** The mutation table above shows this. Exception: the individual F-2 clauses (N-4).
2. **Baseline scope.**
   - `BASELINE_FIELDS` is exactly title, description, tags, price and taxonomy_id. `baseline_drift` iterates only those fields.
   - With a certified payload, every other field is compared against it (`skip=BASELINE_FIELDS`).
   - `accept_baseline` resolves `etsy.listing_drift:<id>` only when every recorded line is a baseline field. Otherwise the incident is kept open.
   - **Gap (N-1):** the acceptance itself never resolves non-copy drift. But when no certified payload exists, it makes the next census stop raising the halting incident and stop comparing properties.
3. **`proof_problems` fails closed only incidentally.**
   - Without a baseline, it fails closed on differences, on `not_verifiable` notes (only the file-hash note is exempt), on open incidents and on UNVERIFIED.
   - With a baseline, it ignores `not_verifiable` (N-2).
4. **`manual_listing_claims` uniqueness is enforced by the database.** `etsy_listing_id` is the primary key.
   - The race test is real: a barrier after both Etsy reads, two threads racing the write, and a direct duplicate insert refused with `IntegrityError`.
   - Removing the claim row makes the race test fail (two releases are linked to one id).
5. **No Etsy writes, and the schema is handled.**
   - The only new Etsy call is `get_listing_properties`, a `GET` with `Authority.READ`. Every suite asserts `writes() == []`, and so did both of my experiments.
   - The new table is registered in `core/db.create_all`, and `core/migrate.py` is additive, so existing databases get it.
   - Retention prunes audit rows, not this table, which is correct for a ledger.
   - No gate is relaxed, except N-1.

### The fixture change (`materials=[]` → `["dk cotton"]`): legitimate

- The CIR's materials are `["dk cotton"]`. With `[]`, the listing already genuinely drifts on materials before any change. The fixed census correctly reports that drift, which breaks the test's precondition (`lid not in field_drift` after acceptance) for the right reason.
- With the certified value, the test still checks its intent: who_made, type, quantity and is_supply drift introduced *after* acceptance.
- It still kills the F-1 mutants (both the copy-only and the no-policy mutant).
- **Suggestion:** also assert that `materials=[]` *is* reported, so the case the fix newly catches is pinned.

## Findings

### R-1: HIGH (operational). Retention refuses to run: `listing.adopted_manual` is unclassified

**Where:**
- The action is read by name in `commerce/orders_ingest.py:500` (`AuditLog.action == "listing.adopted_manual"`).
- It is absent from `ops/retention.KNOWN_READ_ACTIONS`.
- `retention.apply` raises `RetentionRefused` whenever `unknown_read_actions()` is non-empty (`retention.py:1056`). The job (`runtime/release.py:7829`) then records `ops.retention_refused` and deletes nothing, on every run.

**Reproduce:**
```
cd brambleloop && PYTHONPATH=src:tests nice -n 19 python tests/test_w4_fmbatch1_retention_guard.py
```
or:
```
python -c "from brambleloop.ops import retention; print(retention.unknown_read_actions())"
```
Both report `['listing.adopted_manual']`.

**Fix:** classify the action. The reader collects the set of adopted artifacts at any time, so pruning would relabel `basis` from `listing.adopted_manual` to `listing_row_created_at`. It should most likely be `lifetime_total` (protected).

### N-1: MEDIUM. A baseline turns the halting "no certified payload" drift into silence, and properties are compared by nothing

**Where:** `runtime/etsy_ops._field_drift`, the baseline branch. When `certified_payload` raises, it returns `copy + _policy_field_drift(...)`. That compares no properties and emits no "uncomparable" line.

**What happens:**
- Before acceptance, the census holds a P1 `etsy.listing_drift:<id>` incident with `halts_publication=True`, recording `no certified payload to compare against …`.
- `accept_baseline` correctly keeps it open.
- The next census finds no copy or policy drift and **resolves it by observation**.
- From then on, a change to the listing's properties on Etsy is reported by nothing. Only the non-halting P2 review item and the live-phase proof stay red.
- The branch test `test_hand_edits_accepted_as_baseline_…` asserts this resolution as intended behaviour. It still relaxes a halting gate as a consequence of acceptance, and leaves a field uncompared.

**Reproduce:** Appendix A.1. It uses the branch fixtures: `T.seed`, `T.adopt` of `remote_listing(lid, description=T.EDITED)`, `T.run_census`, then `baseline_preview` and `accept_baseline`, then set `live[lid]["properties"]=[{"property_id":1,"value_ids":[9]}]` and run `T.run_census`. Output:
```
before: ['no certified payload to compare against: certified listing taxonomy UNKNOWN; …'] True
accept kept: ['etsy.listing_drift:7902', 'listing.adoption_review:…']
census drift after: []
drift incident open after census: False
```

**Fix:** in the no-payload baseline branch, also emit a line such as `properties: no certified payload, UNVERIFIED`, so the halting incident stays open until a certified payload exists and compares clean. Alternatively, compare the properties read at acceptance against the live ones.

### N-2: MEDIUM (latent fail-open). With a baseline, `proof_problems` ignores everything that was never compared

**Where:**
- In `publish/manual_adoption.proof_problems`, `if base: uncovered = list(base.get("not_covered") or [])`. The adoption's `not_verifiable` notes are dropped.
- `not_covered_by_baseline` builds its list from field drift and `differences` only. The fresh `compare(...)["not_verifiable"]` from the preview is discarded too.
- Notes such as `digital files: getAllListingFiles was not read`, `price plan band: …` and `disclosures: …` therefore never reach the baseline or the proof.

**Why it is not visible today:** `not_covered_by_baseline` passes `read["remote"]` without the separately read properties (see N-3). With a full certified payload this always yields `properties: not returned`. That keeps `not_covered` non-empty, so the review item and the proof stay red.

**Reproduce:** Appendix A.2.
- Setup:
  - patch `etsy_ops.certified_payload` to a matching `ListingPayload`, and `MA._certified_taxonomy` to `{"known": True, "taxonomy_id": 2856, "properties": []}`;
  - wrap `MA.read_listing` so files are unread (`files_error="HTTP 503"`);
  - use a live listing with `description=T.EDITED, properties=[]`, which simulates the N-3 fix.
- Then adopt, preview and accept.
- Output:
```
adopt: VERIFIED diff ['description'] nv ['digital files: getAllListingFiles was not read']
proof before baseline: [... 'digital files: getAllListingFiles was not read', 'open incident ...']
not_covered: []   resolved ['listing.adoption_review:…']
proof after baseline: []      unproven: []
```
- So a listing whose files were never read is "read back verified" in live phases.

**Fix:**
- Carry the fresh preview's `not_verifiable` (minus `_STRUCTURAL_NOTES`) into `not_covered`.
- In `proof_problems`, always include the adoption's `not_verifiable`, unless a later fresh read compared those items.
- Add this case as a test.

### N-3: LOW (functional, currently fail-closed). The preview compares properties against a listing read that omits them

**Where:** `not_covered_by_baseline(..., remote=read["remote"])`. The census and `read_back` use `with_properties(...)`, but adoption stores properties separately in `read["properties"]`.

**Effect:**
- Once a certified payload exists, every preview shows `properties: not returned`.
- The review item can never close through a baseline, so a baselined manual listing can never be proven.
- Fixing this without N-2 opens the fail-open described in N-2.

**Fix:** pass `{**read["remote"], "properties": canonical_properties(read["properties"])}` when properties were read. Otherwise emit an explicit "not read" line.

### N-4: LOW (test coverage). The F-2 proof clauses are each unpinned

- Removing the `differences` clause, the `baseline.not_covered` clause or the open-incident clause from `proof_problems` each leaves both suites green. The other clauses cover for the removed one.
- Example of the exposure: an owner manually resolves the P2 review item while a difference remains. The `differences` clause is then the only guard, and no test pins it.
- **Fix:** add one test per clause, each with the other conditions satisfied.

### N-5: INFO

- The `repeat` path of `adopt` never inserts a `ManualListingClaim`. An adoption recorded under `af042099` (pre-claim) therefore stays unclaimed after a repeat adoption. This is harmless because `af042099` was never shipped. A one-line backfill on `repeat` would close it.
- The automated create path (`draft_intent.checkpoint`) writes no claim. Collision is not realistic, because Etsy mints a fresh id, and the in-transaction `taken` check covers the serial case.
- `accept_baseline` decides on the drift lines recorded at the *last* census. Drift outside the copy fields that appeared since then is resolved with it, but the next census re-raises it, because those fields are still compared.
- F-4: the guard's stated limits (runtime-built literals, tuples split across lines) are honest. The mutant was caught.

## Appendix A: reproduction scripts

Run from `brambleloop/` at `752950e4` with `PYTHONPATH=src:tests nice -n 19 python -I -c "import sys; sys.path[:0]=['src','tests']; exec(open('<script>').read())"`.

### A.1 N-1

```python
import _tmp; _tmp.install()
import os
from unittest.mock import patch
import test_w4_adopt_manual_listing as T
from brambleloop.publish import manual_adoption as MA
DB = T.DB
lid = "7902"
live = {lid: T.remote_listing(lid, description=T.EDITED)}
t = T.transport(live)
rel = T.seed(DB); T.adopt(DB, t, lid, rel)
T.run_census(t)
inc = T.open_incident(f"etsy.listing_drift:{lid}")
print("before:", inc and inc.detail.get("drift"), inc and inc.halts_publication)
with patch.dict(os.environ, T.ETSY_ENV), patch.object(MA, "_transport", lambda: t):
    shown = MA.baseline_preview(DB, slug="hexagon-coaster-set", version="1.2.0", etsy_listing_id=lid)
    r = MA.accept_baseline(DB, slug="hexagon-coaster-set", version="1.2.0", etsy_listing_id=lid, expected_digest=shown["digest"], actor="owner:x", reason="e")
print("accept kept:", r["incidents_kept_open"], "resolved:", r["incidents_resolved"])
# properties change on Etsy after acceptance
live[lid]["properties"] = [{"property_id": 1, "value_ids": [9]}]
c = T.run_census(t)
print("census drift after:", c["field_drift"].get(lid) if isinstance(c["field_drift"], dict) else c["field_drift"])
print("drift incident open after census:", T.open_incident(f"etsy.listing_drift:{lid}") is not None)
print("proof:", MA.proof_problems(DB, slug="hexagon-coaster-set", version="1.2.0", etsy_listing_id=lid)[:2])
```

### A.2 N-2

```python
import _tmp; _tmp.install()
import os
from unittest.mock import patch
import test_w4_adopt_manual_listing as T
from brambleloop.publish import manual_adoption as MA
from brambleloop.runtime import etsy_ops
from brambleloop.integrations.etsy import ListingPayload
from brambleloop.app import verify_checks
DB = T.DB
lid = "7901"
payload = ListingPayload(title=T.TITLE, description=T.EDITED, price=4.0, tags=list(T.TAGS),
                         materials=["dk cotton"], taxonomy_id=2856)
known = {"known": True, "taxonomy_id": 2856, "properties": []}
live = {lid: T.remote_listing(lid, description=T.EDITED, properties=[])}
t = T.transport(live)
real = MA.read_listing
def no_files(*a, **k):
    out = real(*a, **k); out.pop("files", None); out["files_error"] = "HTTP 503"; return out
with patch.object(etsy_ops, "certified_payload", lambda db, s, v: payload), \
     patch.object(MA, "_certified_taxonomy", lambda *a, **k: dict(known)), \
     patch.object(MA, "read_listing", no_files):
    rel = T.seed(DB)
    res = T.adopt(DB, t, lid, rel)
    print("adopt:", res["verification"], "diff", [d["field"] for d in res["differences"]], "nv", res["not_verifiable"])
    print("proof before baseline:", MA.proof_problems(DB, slug="hexagon-coaster-set", version="1.2.0", etsy_listing_id=lid))
    with patch.dict(os.environ, T.ETSY_ENV), patch.object(MA, "_transport", lambda: t):
        shown = MA.baseline_preview(DB, slug="hexagon-coaster-set", version="1.2.0", etsy_listing_id=lid)
        print("not_covered:", shown["not_covered_by_baseline"], "acceptable", shown["acceptable"])
        r = MA.accept_baseline(DB, slug="hexagon-coaster-set", version="1.2.0", etsy_listing_id=lid,
                               expected_digest=shown["digest"], actor="owner:x", reason="edit")
        print("resolved", r["incidents_resolved"], "kept", r["incidents_kept_open"])
    c = T.run_census(t); print("census drift:", c["field_drift"])
    p = MA.proof_problems(DB, slug="hexagon-coaster-set", version="1.2.0", etsy_listing_id=lid)
    print("proof after baseline:", p)
    print("unproven:", [u for u in verify_checks._published_rows_proven(DB)["unproven"] if u["etsy_listing_id"] == lid])
print("writes", t.writes())
```
