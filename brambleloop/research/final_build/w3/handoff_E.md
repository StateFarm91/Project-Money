# W3 lane E handoff — Laura durable BUSINESS memory

Branch `claude/w3-E` (base `claude/v11-CANON` @ f0c2d12). Scope: business memory only. **The
owner-private / spouse memory tier is NOT built in this lane (explicitly out of scope).** The
API has no private tier; any tier name other than the five below raises `TierRefused`, so no
private data can enter or leave through it.

## Requirements and status
| Requirement (spec/07 item 5, D-FB-13, owner directive §8) | Status |
|---|---|
| Tiers: canonical, brand, operational, experience/lessons, relationship/context | COMPLETE |
| `write(tier,key,value,source,actor)` / `read(tier,query,principal)` with per-principal checks | COMPLETE |
| Canonical identity owner-controlled, read-only to agents | COMPLETE (owner needs live CC session + `supersede=True` to revise) |
| Every entry source-linked and auditable | COMPLETE (immutable revision rows; `history()`; canonical changes + refusals on `company_timeline`) |
| Generated summaries never overwrite canonical facts | COMPLETE (refused in canonical; refused over any recorded fact; `context()` shadows lower-tier collisions with canonical keys) |
| Provenance required, no invented history | COMPLETE (every source must resolve to a real row / decision / doc / owner statement) |
| Survives restart and model swap | COMPLETE (pure DB state; proven with a fresh interpreter under swapped model env) |
| Public/customer surfaces never read non-public tiers | COMPLETE for store preview, Ask Company (no owner principal), support drafts |
| Reuse existing infrastructure | COMPLETE: `company_memory` (kinds `laura.mem`, `laura.mem.rev`), `company_timeline`, `lessons` + `learn_policy_lessons` projected read-only into experience. No new table. |

## API contract (for lanes D and F) — `brambleloop.laura.memory`
```
Principal.owner(session_public_id)  # re-verified every call against cc_owner_sessions (exists, not revoked/expired)
Principal.laura(); Principal.department(charter_key)  # autonomy.charters keys only
Principal.public(surface); Principal.customer(ref); principal_for_surface(name)  # never owner/laura; unknown -> public
write(db, tier, key, value, source, actor, *, generated=False, supersede=False, subject="") -> entry
read(db, tier, query=None, principal=None, *, include_projections=True, limit=200) -> [entry]
    query: None | "exact" | "prefix*" | "~substring" | {key,prefix,department,text}
history(db, tier, key, principal) -> [entry per revision, oldest first]
context(db, principal, query=None, tiers=None) -> {tiers:{tier:[entry]}, canonical:{key:entry}, shadowed:[...], sources:[...]}
ensure_canonical_seed(db) -> [keys written]   # 6 facts transcribed from D-FB-11/12/13; never overwrites
entry = {tier,key,value,subject,sources,actor,principal_kind,department,category,generated,
         revision,authority: canonical|fact|summary|projection, ref:"laura_memory:<tier>:<key>",created_at,updated_at}
Errors (all ValueError): TierRefused, PermissionRefused, ProvenanceRefused, CanonicalOverwriteRefused, SummaryOverwriteRefused
```
Permission matrix: owner reads/writes all (canonical owner-only); laura reads all, writes brand,
operational, experience, relationship (`department/…`, `context/…` keys only); department reads
canonical/brand/operational/experience + relationship `policy/`, `preference/`, own
`department/<key>/`; writes operational/experience, never another principal's entry;
public/customer: nothing. `policy/` and `preference/` (owner-approved) are owner-write only.
Sources: `<table>:<pk>` (any mapped table present; company_memory/timeline by key or id),
`laura_memory:<tier>:<key>`, `decision:<ID>`, `doc:<path under brambleloop/>`,
`owner_statement:<ref>` (owner only; stored as `owner_statement:<session>:<ref>`).
Use for D: canonical identity facts live at `canonical/identity/*` (visual id
`laura-v15-a42aeac7`); write Laura's executive decisions to `operational` citing the job/mission
row. Use for F: Talk-to-Laura answers call `context(db, Principal.owner(session.public_id))`;
cite `entry["ref"]`/`sources` as evidence.

## Files
New: `src/brambleloop/laura/__init__.py` (one-line docstring — **lane D may also create it; keep
either**), `src/brambleloop/laura/memory/{__init__,errors,principals,tiers,provenance,store}.py`,
`tests/w3_laura_memory_harness.py`, `tests/test_w3_laura_memory_{permissions,canonical,provenance,isolation,persistence}.py`.
No shared file modified.

## Tests
`SUITES="tests/test_w3_laura_memory_*.py" PY=<venv python> bash run_tests.sh` → TOTAL PASSING: 28;
suites failing: 0 (permissions 9, canonical 6, provenance 6, isolation 5, persistence 2).
`tests/test_vacuity.py` and `tests/test_secret_scan.py`: 0 FAIL.

## Runtime proof
Isolation suite seeds a unique canary in every tier, then runs `preview.summary` + `render_preview`
(standard/brand_face × mobile/desktop), `ask.ask` for 8 questions, and 5 support drafts while
watching the API, every SQL statement (no `laura:`/`laura.mem` touched) and every output (no
canary). A self-test proves the watch detects a real read. Persistence spawns a fresh Python
process with swapped provider/model env vars and reads back identical entries and revisions.

## Wiring requests
None required (tables already registered by `core.db.create_all` via autonomy.models).
Lane F: HTTP routes must construct `Principal.owner(...)` only from the verified owner session.

## Open defects / not verified
- In-process code can still query `company_memory` directly; this API is the boundary, not a DB
  ACL. Postgres not exercised (SQLite only). Owner-private tier: not built (out of scope).
- `ensure_canonical_seed` writes under actor `owner_ruling:<D-FB-x>` without a live owner session
  (fixed transcription of recorded rulings, absent-only); the integrator may prefer gating it.
