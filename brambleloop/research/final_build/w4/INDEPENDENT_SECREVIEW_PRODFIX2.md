# Independent review: W4-PRODFIX2 (`improve/evolution.py` `stop_list`)

| Scope | Verdict | Blocking findings |
|---|---|---|
| `git diff 24ada531..67920948` (one commit, `6792094`, branch `claude/w4-INTEG7`) | **SHIP** | None |

Reviewed 2026-10-26 (UTC) by an independent reviewer that did not write the change. This was a
review only: no code was changed, no PR was opened, and nothing touched production, secrets or
deploys.

## What the change does

`stop_list` grouped `SerpSnapshot` rows by query as `(tuple(rank_list), total_count)` and
checked `len(set(recent)) == 1` over the last `QUERY_UNCHANGED_CAPTURES` (4). `rank_list`
entries are dicts, so the tuple could not be hashed and `set()` raised
`TypeError: unhashable type: 'dict'` as soon as any query had 4 captures. The fix builds the
key from `json.dumps(rank_list or [], sort_keys=True, default=str)` plus `total_count`. The
diff touches nothing else in production code; it adds one test file.

## Findings

### 1. Correctness and STOP semantics: correct, and the rule is unchanged

- The rule still says: a query is STOPped when it has at least 4 captures and the last 4 are
  identical in both ranked list and total count. The window (`seen[-4:]`), the threshold, the
  `id` ordering, the `total_count` component and the Stop text are all unchanged.
- `rank_list` order is kept, since `sort_keys` sorts dict keys and not list elements. A
  reordered ranking still counts as a change, which is what `tuple(...)` meant.
- `None` and `[]` both serialise to `"[]"`. The old `tuple(snap.rank_list or [])` already
  treated them the same, so that is unchanged.
- The old code never produced a query STOP on dict entries; it crashed instead. The fix gives
  the behaviour the original code intended. It does not make the rule broader.

### 2. Can canonical JSON compare wrongly?

The values come from a SQLAlchemy `JSON` column (`core/models.py:2119`). A row read in a new
session is always `json.loads` output: str keys, and values that are str, int, float, bool,
None, list or dict. The only writer is `intel/serp.py:215`, which builds entries with string
keys. I checked each case with a probe script:

| Case | Result | Can it happen here? |
|---|---|---|
| Key order differs (`{"b":1,"a":2}` vs `{"a":2,"b":1}`) | Equal (correct) | Yes, and it is handled |
| `1` vs `1.0` vs `true` | Unequal (`1`, `1.0`, `true`) | No. A JSON round trip keeps the int/float/bool type, so the same capture always serialises the same way. Python `==` would call them equal; here they differ, which is the stricter and safer choice. |
| Floats | `repr` round-trips exactly (`0.1+0.2` survives) | Stable |
| Key `None` vs key absent | Unequal (correct, they are different data) | Possible. They differ, which is the safe direction. |
| NaN | Serialised `NaN == NaN` as strings | Only if a NaN reached the column. Python tuple equality would give the same result through the identity shortcut. Harmless. |
| `datetime` / `Decimal` | `default=str` stringifies them; no raise | No. Values read back from a JSON column cannot be these types. |
| `Decimal("1")` vs the string `"1"` | Collide (equal) | No, for the same reason. In theory this could compare equal when the data differs, but it cannot be reached. |
| Mixed int/str dict keys | `sort_keys` raises `TypeError` | No. JSON object keys are always str after a round trip. |

Conclusion: no reachable input makes two logically identical captures compare unequal, or two
different captures compare equal. No reachable input makes `json.dumps` raise. `default=str`
is a harmless guard.

### 3. Spurious STOP cards, outward or paid actions, other changes

- A query STOP needs 4 byte-identical captures. `rank_list` carries volatile fields such as
  `favourites`, `thumbnail_url`, `image_count`, `has_video` and `created_ts`, and
  `total_count` must match too. This means a STOP is conservative: it fires only when nothing
  observable moved. It is not spurious.
- The only effect of a query STOP is a line in one batched `OwnerAction` row
  (`route_owner_card`, key `improve.stop_list:weekly`, `max_cost_cad=0.0`). It is an internal
  DB row. It sends no message, disables no capture schedule and spends nothing. The card asks
  the owner to decide.
- One behavioural note, not a defect: `improve.weekly` now runs to completion where it used to
  dead-letter. That means the rest of the handler runs again in production: stale experiments
  are marked stopped, the STOP card is routed, then `director.route_retirements` and
  `director.execute_approved` run. All of this already ran for any database with fewer than 4
  captures per query, so the fix restores code that was already reviewed; it adds no new
  action. When the fix is deployed, the first cycle may open a STOP card that lists several
  queries at once. That is the intended output, not noise.
- The dead-lettered job 26949 stays dead-lettered. The diff does not re-drive it. The next
  scheduled `improve.weekly` will run normally.

### 4. Do the new tests discriminate? Yes

I put `24ada531`'s `evolution.py` back in place and kept the new tests:

```
FAIL test_identical_captures_with_dict_entries_become_a_query_stop TypeError unhashable type: 'dict'
FAIL test_the_weekly_cycle_completes_with_serp_captures_on_file AssertionError TypeError: unhashable type: 'dict'
```

With the fix restored (`git checkout`), both pass. The first test also includes a negative
case: `crochet hat` has the same `total_count` but a different `listing_id` each time. So a
mutation that compared only `total_count`, or one that STOPped every query with 4 captures,
would also fail. One gap that is not blocking: no test covers a reordered `rank_list` or
dict-key order. The code handles both correctly, as shown in section 2.

### 5. Was any test weakened? No

The diff's only test change is the new file
`brambleloop/tests/test_w4_prodfix2_weekly_serp.py` (58 lines added, no lines removed). No
existing test file was touched.

## Test runs

The venv was built from `brambleloop/requirements.lock` plus `requirements-test.lock` on
Python 3.13.17. pytest is in neither lock file, so each suite ran through its own `__main__`
runner at `nice -n 19`:

| Suite | Result |
|---|---|
| `tests/test_w4_prodfix2_weekly_serp.py` | 2/2 ok, exit 0 |
| `tests/test_weekly.py` | 27/27 OK, exit 0 |
| `test_w4_prodfix2_weekly_serp` with the fix reverted | 2/2 FAIL (see section 4) |
