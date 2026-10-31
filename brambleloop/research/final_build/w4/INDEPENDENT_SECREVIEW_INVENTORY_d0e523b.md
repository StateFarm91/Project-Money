# Independent security & integrity review — W5-INVENTORY @ d0e523b

- **Subject:** `git diff b0133916..d0e523bb` (branch `claude/w5-INVENTORY`, 11 files, +2,175/−1)
- **Reviewer:** independent session; reviewed the code itself, with `INVENTORY.md` as background only
- **Date:** 2026-10-31 (UTC)
- **Verdict: DO NOT SHIP** until H1 is fixed. M1–M4 should be fixed in the same pass because each fix is small.

The view never writes, enqueues or sends anything, and auth holds. All four findings below are
about what the view **claims**: in each case the inventory can show **"Ready for publication"**
(or "Owner approval pending") while `store.publish` would refuse. The Directive forbids
claiming a state until it is verified, so these block shipping even though the view is display-only.

## Suites run (one at a time, `PYTHONPATH=src:tests nice -n 19 python tests/<f>`)

| Suite | Result |
|---|---|
| `test_w5_inventory` | 10/10 PASS |
| `test_route_auth_default_deny` | 8/8 OK |
| `test_w4_fmbatch1_retention_guard` | all OK |
| `test_w4_fmbatch1_route_audit` | all OK |

(The container lacked deps; installed from `requirements-test.lock`.)

## Q1 — Read-only: **PASS (verified by instrumentation)**

I attached a SQLAlchemy `before_cursor_execute` spy for INSERT/UPDATE/DELETE/DDL. I also wrapped
`httpx.Client.send`, `urllib.request.urlopen` and every `enqueue` in `brambleloop.queue.durable`,
on top of the test's socket block. I then ran `derive()` in both `recorded` and `live` mode,
`production_summary()`, `production.build()` and an authenticated `GET /api/cc/production`:

- **Direct calls:** 0 writes, 0 network, 0 enqueues.
- **HTTP GET:** the only write was `UPDATE cc_owner_sessions SET last_seen_at` (the auth layer
  touching the session), which is expected.

The shipped test compares row *counts*, so it cannot detect an UPDATE. The spy closes that gap
(see the adversarial note in Q5).

## Q2 — Authorisation & leakage: **PASS**

**Who can reach `/api/cc/production`:**

| Request | Result |
|---|---|
| Anonymous | 401 |
| Operator bearer token | 401 |
| Trailing slash | 401 |
| `http://` scheme | 401 |
| `/api/CC/…` | 404 |

`test_route_auth_default_deny::test_every_get_is_gated_unless_on_the_public_allow_list` passes,
and the route is not in `PUBLIC_ROUTES`. POST returns 403/404/405.

**`production_summary`:** returns counts only. The key set is exactly the 12 documented keys. A
seeded secret slug, title, cost, `jane@example.com` and `sk-live` do not appear in it. The CC
view blob also does not contain the seeded `last_error` email or token.

**`production.js`:** no XSS. It builds everything with `h()`, which uses `textContent` and
`createTextNode` (`dom.js:29,54`). `href`/`src` values are scheme-filtered, and the view contains
no innerHTML or HTML-string path.

## Q3 — Truthfulness: **FAIL**

### H1 (HIGH) — a *settled* draft intent is ignored, so the view shows Ready while `store.publish` refuses

- **The gap:** `UNSETTLED_INTENTS = ("CREATING", "RECONCILE_REQUIRED")`. But
  `store.publish` → `_publish_and_read_back` calls `draft_intent.refuse_if_existing`
  (`publish/draft_intent.py:115`), which refuses on **any** existing intent.
- **Where it bites:** `checkpoint` moves an intent to `CREATED` and the listing to
  `incomplete_on_etsy` (`draft_intent.py:82-84`). That state is not in
  `PUBLISHED_LISTING_STATES` and not in `UNSETTLED_INTENTS`, so it falls through to the gates.
- **Effect:** a product whose remote Etsy draft already exists but is incomplete is shown as
  **Ready for publication**, and counted in both the private-draft and public tiers.
- **Reproduction:**
  1. Run `up_to(DB,"x-created","gates")`.
  2. Add `DraftIntent(state="CREATED", slug="x-created", version="1.0.0", …)`.
  3. Set `Listing.state="incomplete_on_etsy"`.
  4. Run `derive()` with the owner gates open.
  5. Result: `('ready_for_publication', True, True, 'every required gate passes')`.
  6. With the owner gates closed (the real state today), the same row reads "Owner approval
     pending", which claims every product gate passes.
- **Fix:** treat any intent row as blocking, mirroring `refuse_if_existing`. Optionally show
  `incomplete_on_etsy` as its own reason.

### M1 (MEDIUM) — three safety readers fail open when they crash

`derive_row` swallows reader exceptions in three places, and each one fails open:

| Reader | What the crash is treated as |
|---|---|
| `load_records` → `DraftIntent` | `intents = {}` |
| `active_veto` | `{"vetoed": False}` |
| `withholding.reasons` | `blocks_build: False` |

The real `store.publish` gate (`for_publish` → `standards_gate` veto check and
`withholding.reconcile`, plus `refuse_if_existing`) does **not** swallow these errors. In
recorded mode, the stored verdict only reflects state as of when it was written. Results:

| Reproduction | Result |
|---|---|
| Replace `draft_intent.DraftIntent` with an object that makes the select fail; product `g-intent` (`RECONCILE_REQUIRED`) | `ready_for_publication` |
| Make `active_veto` raise; product `x-veto` has an active `OwnerVeto` | `ready_for_publication` (normal path: `rejected`) |
| Make `withholding.reasons` raise; product `s-ready` | `ready_for_publication` |

A whole-row crash, by contrast, fails closed (`revision_required`, `public_ready=0`), and so does
a whole-view crash (`status: UNKNOWN`, `sections: {}`). The brief asked whether a missing or
crashing reader fails closed: for these three readers, it does not.

**Fix:** on exception, add a closed-gate reason or hold so the row cannot reach Ready or
Owner-pending.

### M2 (MEDIUM) — a recorded verdict has no age limit and no `as_of` check

`_recorded_product_gates` counts a verdict as stale only when a non-`store.*` job finished after
it. Two problems follow:

- **No time limit.** `for_publish` depends on today's date (`window_decision(today=…)`, #297
  seasonal windows), and owner, veto, withholding and standards state can change without any job.
  A PASS from months ago stays PASS.
- **Replayed dates are accepted.** `store.publish` records the verdict computed with the job's
  `as_of`. `_revalidate_publish_effect` explicitly rejects that date ("Historical replay dates
  cannot stand in for current execution evidence"), but the inventory accepts it.

**Reproductions:**
1. Seed a chain 200 days old with a verdict 199 days old → `ready_for_publication`.
2. Seed a `store.publish` job with `as_of: "2025-01-01"` and its recorded PASS → `ready_for_publication`.

**Fix:** reject verdicts from jobs with `as_of`, and apply a TTL of at least the publish
cadence. After the TTL the verdict is UNKNOWN, which keeps the product at Listing package completed.

### M3 (MEDIUM) — a passed sample followed by a failed sample still reads as "passed"

`physical_status` returns `passed` if **any** test passed (`if passed:` is checked before the
latest completed test). So an old pass followed by a newer failure shows **passed**, and the
product becomes **Ready** with the public tier ready. If the order is reversed it reads `failed`
and the product goes to `revision_required`. The same evidence therefore gives opposite answers
depending on order.

A `passed=True` row with `completed_at=None` also counts as passed.

- **Reproduction:** on `x-phys` (`physical_test_required=True`), add `PhysicalTest(passed=True,
  completed_at=now-2d)` and then `PhysicalTest(passed=False, completed_at=now)`. Result:
  `('ready_for_publication', 'passed', True)`.
- **Context:** no other gate enforces the sample on this path. `publication_authority._certification`
  reports `physical_proof` from `cert.physical_test_passed` for information only, so the inventory's
  public tier is the only place this is applied.
- **Fix:** decide on the latest completed test, and require `completed_at`.

### M4 (MEDIUM, defence in depth) — a `store.release_gates` row is not bound to a job

The parity row is now bound to its `store.publish` job (the chain finding), but the
release-gates row is matched only by `artifact == slug` and `detail.version`.

- **Reproduction:** add `store.release_gates` with `{"version":"1.0.0","blocks_release":false}`
  and `job_id=None`, alongside a bound parity row → `ready_for_publication`.
- **Severity:** today only `runtime/pipeline.py:1639` writes this action, so impact is limited.
- **Fix:** bind it the same way as parity, and require the gates and parity rows to come from
  the **same** `store.publish` job.

### Checks that passed

| Check | Result |
|---|---|
| "Published" | Only from a real `Listing` row in `published / active / published_manually`. No other path sets it (3j: only `s-published`). |
| Physical sample as an attribute | Pending never blocks internal stages (`internal.complete=True`, `private_draft.ready=True`), always blocks public, and is never Ready or Owner-pending whether the owner gates are open or closed. |
| Phase / `publication_authority` | Shadow phase with no grant gives Owner-pending. A crashing owner reader is closed. `live` mode in shadow gives `listing_package_completed`. |
| Stale verdict (relative to jobs), unbound parity, missing parity, blocking gates or parity | All refuse Ready (shipped tests, confirmed by mutation). |

## Q4 — Retention: **PASS (low notes)**

- **`pricing.refused` → `latest`.** It is used only as a hold annotation and never sets a state,
  and no other reader existed before this branch. Under retention rule 2 only the globally newest
  row per action survives, so an older product's "pricing refused" hold can disappear silently.
  That is cosmetic, not a safety issue. **(INFO)**
- **`quality.reverified` is `windowed` (existing decision).** It now drives `revision_required`.
  If a product's daily re-verification stops running, a pruned failing row lets the product
  advance. `for_publish` does not read this action either, so the real gate gives no backstop.
  **(LOW)** Consider having `quality_ops` record a withholding on failure, or protecting failing rows.

## Q5 — Do the tests discriminate? **Mostly. Three mutants survive.**

I applied 12 mutants to `production_inventory.py` one at a time and ran `test_w5_inventory`:

| Mutant | Result |
|---|---|
| M1 drop unsettled-intent check | KILLED |
| M2 drop staleness check | KILLED |
| M3 accept unbound parity | KILLED |
| M4 drop physical-pending return | KILLED |
| M5 drop gate-FAIL return | KILLED |
| M6 owner reader crash → open | KILLED |
| M7 parity `blocks_release is True` (missing key → open) | **SURVIVED** |
| M8 drop `published_manually` | KILLED |
| M9 `live` gate mode always PASS | **SURVIVED** (no caller uses `live` in production; untested path) |
| M10 failed sample not revision | KILLED |
| M11 public tier ignores physical | KILLED |
| M12 row-crash fallback = READY | **SURVIVED** |

Tests to add:

- one for each of H1 and M1–M4 (the probes below);
- a parity row whose detail has no `blocks_release` key;
- a `live`-mode case with a blocking `for_publish`;
- a `derive_row` crash, asserting `public_ready == 0`;
- replace the row-count read-only check with the statement spy.

## Reproduction harness (not committed; run from `brambleloop/`)

Mutation runner: copy each `(old, new)` pair from the Q5 table into `production_inventory.py`,
run the suite, then restore. Probe harness `adv_inventory.py`, which imports
`tests/test_w5_inventory` for its seeded DB:

```python
import test_w5_inventory as T
from brambleloop.products import production_inventory as pi
from brambleloop.publish.draft_intent import DraftIntent
from brambleloop.core.models import Listing, PhysicalTest
from datetime import timedelta
def st(slug):
    with T._Patch():
        it = T.item(pi.derive(T.DB), slug)
    return it["state"], it["tiers"]["private_draft"]["ready"], it["tiers"]["public"]["ready"]
# H1
T.up_to(T.DB, "x-created", "gates")
with T.DB.session() as s:
    s.add(DraftIntent(key="c"*64, slug="x-created", version="1.0.0", release="r",
                      content_digest="d"*64, token="t"*32, state="CREATED"))
    s.query(Listing).filter_by(product_slug="x-created").one().state = "incomplete_on_etsy"
assert st("x-created")[0] != pi.READY, "H1"            # FAILS on d0e523b
# M3
T.up_to(T.DB, "x-phys", "gates", physical=True)
with T.DB.session() as s:
    s.add(PhysicalTest(product_slug="x-phys", version="1.0.0", tester_ref="a", passed=True,
                       completed_at=T.NOW - timedelta(days=2)))
    s.add(PhysicalTest(product_slug="x-phys", version="1.0.0", tester_ref="b", passed=False,
                       completed_at=T.NOW))
assert st("x-phys")[0] != pi.READY, "M3"               # FAILS on d0e523b
# M1 (veto): monkeypatch brambleloop.intel.mission_runtime.active_veto to raise, then
# st("<vetoed slug at 'gates'>") -> ready_for_publication on d0e523b.
# Write spy: sqlalchemy.event.listen(T.DB.engine, "before_cursor_execute", spy) and match
# ^(INSERT|UPDATE|DELETE|REPLACE|CREATE|DROP|ALTER) around derive/build/GET.
```

## Not covered

- `ops/flow_health.py` stall and loop thresholds were exercised only through the instrumentation
  run (no writes, no network). I did not review their correctness.
- I did not re-derive the full 15-state ordering beyond the gate-adjacent states.
