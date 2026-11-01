# Independent re-review: OPUS2 fixes for reviews E and F (OPUS2EF2)

Reviewer: an independent Claude Code session. Date: 2026-11-01 (UTC). This review is read-only:
nothing on `opus2/*` or `claude/repository-setup-nc9x6o` was changed. Every probe below ran in
a scratch worktree and was reverted.

| # | Subject | Commit | Verdict |
|---|---|---|---|
| 1 | `opus2/p0-revenue-workforce`: review E, E1–E4 | `0e941757` | **CHANGES REQUIRED** (EF2-1) |
| 2 | `opus2/p0-listing-package`: review F part A, A-1 to A-8 | `b42f4245` | **CHANGES REQUIRED** (EF2-4) |
| 3 | `opus2/p1-owner-queue-races`: review F part B, B-1 to B-3 | `007f5d1c` | **CHANGES REQUIRED** (EF2-6) |

None of the three fixes adds an outbound action, a publish, an upload, a message or any spend.
The findings concern the integrity of gates and of the owner queue.

---

## Subject 1: `0e941757` (E1–E4)

### Per finding

| Finding | Fixed at the root? | Discriminating test? (mutation result) |
|---|---|---|
| E1 route: only a titled tote drafts | Yes. `_TOTE_WORDS` no longer contains `bag`, and a `bag` category with no tote word is refused through `NEEDS["bag"]`. | **No.** Putting `bag` back into `_TOTE_WORDS` (M1) leaves both suites green. So does dropping the bag-category refusal (M10). The cause: every refused title in the test also carries a `_SHAPED_WORDS` word ("drawstring", "holder", ...), so the tests never reach the route itself. With M1, "Lunch Bag", "Grocery Bag", "Project Bag" and "Bag" draft as a tote again (EF2-2). |
| E1 multiplicity: straps back a count | **No, only patched.** The review asked that `title_promise` count finished objects and exclude strap parts. It still sums `Component.make`. Instead, `plan` refuses some words by regex (`_MULTIPLE_WORDS`). | Removing the multiplicity refusal (M2) fails the test. But words missing from the list still pass, backed by the straps (EF2-1). |
| E1 size word | Partly. Small, mini and medium are honoured. | Killed (M7). "Tiny Tote" still drafts large (EF2-3). |
| E2 size gate fails closed | **Yes.** Every row of the review's table is now a claim again, and "3 baskets of yarn" and "2x to 4x" are still excluded. | Killed: M5 (case-insensitivity), M6 (`_VESSEL`), M9 (the "2x" skip). |
| E3 cosy never below girth | **Yes.** `ceil` is used, and a yarn weight with more than 15% ease is refused. The test checks every yarn weight. | Killed: M3 (`ceil`→`round`), M8 (ease cap). |
| E4 character, texture or second-object cosy | Mostly. | Killed (M4). "Egg Cosy & Basket", "Striped Egg Cosy" and "Egg Cosy Pom Pom" still route to `COSY` (EF2-3). |

### Findings

**EF2-1 MEDIUM: the root cause of E1 is still there. A strap still backs "bundle" and
"collection", and a second object in a tote title is dropped.**
Repro: `PYTHONPATH=src:tests`, using the review E setup and category `bag`. For every title
below, `F.plan(...)["family"] == "tote"` and `E.name_truth(F.tote(c), None) == []`:

| Title | `launch0.title_promise` |
|---|---|
| "Tote Bag Bundle" | `plural_markers=('bundle',)`, makes 3, **backed=True** ("the CIR makes 3") |
| "Tote Bag Collection" | `('collection',)`, makes 3, **backed=True** |
| "Double Tote", "Tote Bag Family", "Mother & Daughter Tote" | no marker seen; one bag drafted |
| "Tote and Coaster", "Market Tote with Pocket", "Tote with Zipper", "Lined Tote", "Reversible Tote" | one plain unlined tote; the second object or feature is absent |

So the class from review E (and OPUS2C N3.1) still passes product truth: a title promises more
than the CIR contains. The fix is a denylist placed in front of a counter that is still wrong.

*Fix:*
- Make `title_promise` count finished objects, so that components joined into another piece by
  `cir.assembly` (the straps) are not counted. This is what review E asked for. The regex can
  stay as an earlier refusal.
- Apply the cosy's `_COSY_NOT_PLAIN` idea to the tote: refuse `and`, `with`, `&`, `+` and named
  features (pocket, zip or zipper, lined or lining, reversible, double, family, bundle,
  collection).
- Add the titles above as "refused" cases.

**EF2-2 LOW-MEDIUM (test gap): the E1 route narrowing is not pinned.** This is the M1 and M10
result above. Add plain non-tote bags to the refused list: "Lunch Bag", "Grocery Bag",
"Project Bag" and "Bag" (category `bag`). Today they are refused only because of
`NEEDS["bag"]`, and no test exercises that path.

**EF2-3 LOW: residual size and cosy words.**
- "Tiny Tote" drafts at size large. Either map "tiny" and "petite" to small, or refuse any size
  word that is not in the table.
- "Egg Cosy & Basket" routes to `COSY`. `_COSY_NOT_PLAIN` lists `and` and `with` but not `&` or
  `+`, so the basket is dropped.
- "Striped Egg Cosy" routes to a plain one-colour cup, and so does "Egg Cosy Pom Pom" (the pom
  pom is a second piece).

**EF2-3b LOW: material phrases are now treated as contents.** The contents exclusion is
`of (yarn|wool|cotton|...)`, so "Two bowls of wool rope" and "2 baskets of cotton" (meaning the
material they are made from) are no longer claims. The impact is narrow. Prefer to exclude
contents only after a container-for-contents verb or noun ("bags of yarn" as stash), or to keep
the claim when the next word is a material noun ("rope", "cord", "t-shirt yarn").

### Tests (subject 1)
`test_opus2_draft_constructions` 0 failed · `test_opus2_size_claims` 0 failed ·
`test_opus2_rim_negative` 0 failed · `test_opus2_chain_deadends` 0 failed · `test_vacuity` OK ·
`test_shadow`: see the Test runs section.

Mutations: M2, M3, M4, M5, M6, M7, M8 and M9 were killed. **M1 and M10 survived.**

---

## Subject 2: `b42f4245` (A-1 to A-8)

### Per finding

| Finding | Status |
|---|---|
| A-1 HIGH: PDF bound to the release | **Fixed at the root.** `_files` takes its hashes from `pipeline._certified_pdf_hashes(db, slug, version, release)` and returns None when the release is empty. The descriptive metadata comes only from an `assets.build` job whose own release equals this one. An empty release is also listed as a blocker. |
| A-2 re-queue after completion | Fixed, but over-suppresses (EF2-4). |
| A-3 stale open request | Fixed. On a fingerprint change, the open request is superseded and a new one cites the new release and fingerprint (tested). |
| A-4 copy versus `Listing.release_hash` | Fixed as the review specified ("when set and differs"). The single-row claim rests on a unique constraint on `listings(product_slug, version)`. A listing whose `release_hash` is empty still passes this check. The search certificate still covers it, as before (INFO). |
| A-5 alt text | Fixed in §8. The estimate notes in §7 wait for PDF1, as the review allowed. |
| A-6 / A-7 class and documentation | Fixed. The job is now class `BUILD`, like `chain.rebuild`, and the docstrings state the internal writes. Moving from OBSERVE to BUILD tightens the class; it does not relax it. |
| A-8 isolation | Fixed. `record()` runs under `_try` for each release. The owner-queue lock is now the first statement of `record()`. |
| Never publishes, uploads, messages or spends | **Holds.** Sockets are refused in the test, `publishes: False` is kept, and no Etsy write, model call or upload call was added. Every asset stays bound to the certified release: the PDFs through the canonical reader, the frames through `certified_frames(release=)`, and the copy through the A-4 blocker plus the search certificate. |

### Findings

**EF2-4 MEDIUM: a package that goes READY → BLOCKED → READY with the same content never asks
the owner again.**
The fingerprint covers `state` and `blockers`, so the READY fingerprint X comes back
identically once a transient blocker clears. The job itself closed X's request as
`SUPERSEDED`. `already = any(r.requirement_key == current for r in rows)` then counts that
closed row as "the owner closed it", and no request is raised. The package sits READY with no
open review. The owner was never asked about it again, and never completed the first request.
*Repro* (on this branch's test fixture):
1. `record(ready fp=a…)` gives `review_requested=True`.
2. `record(blocked fp=b…)` gives `review_withdrawn=True`.
3. `record(ready fp=a…)` gives **`review_requested=False`**, with no open row.

Nothing is published as a result, so this fails safe for publication. But it silently drops an
owner review. That is the A-2 class turned around: the owner is now asked too little instead of
too often.
*Fix:* suppress a new request only when a closed row for `current` was closed by the owner
(`state` is SATISFIED or WITHDRAWN). Treat a row the job itself SUPERSEDED as absent. Add the
three-step sequence above as a test.

**EF2-5 LOW: requests under the legacy key are orphaned.** Open rows keyed
`listing_package:<slug>@<version>`, the unfingerprinted key from `f779fac2`, never match
`like("listing_package:<slug>@<version>:%")`. Such a row stays open forever beside the new
fingerprinted request. In the probe it stayed `done=False` while the fingerprinted request was
open. This matters only if `f779fac2` ever ran against a durable DB.
*Fix:* also match the exact legacy key, and supersede it.

### Tests (subject 2)
See the Test runs section.

---

## Subject 3: `007f5d1c` (B-1 to B-3, documented B-4 to B-6)

### Per finding

| Finding | Status | Mutation |
|---|---|---|
| B-1: loser expunged with id None | Fixed. The newcomer is merged onto the open row and given its id, including when the keeper is inserted in the same flush. But the merge introduces EF2-6 and EF2-7. | Killed (S3M4 restate off, S3M5 id hand-over off) |
| B-2: re-key onto an open key | Fixed. The re-key is reverted. | Killed (S3M2) |
| B-3: reopen beside an open row | Fixed. The reopen is reverted, but this damages the lifecycle (EF2-8). | Killed (S3M3) |
| B-4: Core `insert` / `update` | Documented only. Confirmed still open: a Core `update(OwnerAction).values(done=False)` reopens a second row (probe: 2 open K3 rows). The same applies to `insert()`, `bulk_*` and raw SQL. | — |
| B-5: partial unique index | **Not built**, proposed to the integrator. | — |
| B-6: Postgres lock order | Documented. There is no Postgres test (unchanged from review F). | — |

**Does every OwnerAction writer now have a real constraint? No.** The guard covers ORM
inserts, re-keys and reopens on SQLite. That includes all of today's writers, as far as the
review F inventory goes. But it is still the **only** constraint. Review F's condition ("sound
as a backstop; must not be the only constraint") is **not met**. B-4 and B-6 are acceptable as
documented follow-ups. **B-5 is acceptable as a follow-up only if it is an integration blocker
before production or Postgres**, not an open-ended proposal. The duplicate-closing migration it
needs is small and mechanical: keep the newest open row per key and close the others as
`SUPERSEDED`. It can be written as an explicit, owner-free script, so the refusal in
`core.migrate` does not have to stop it.

### Findings

**EF2-6 MEDIUM: the merge copies `max_cost_cad` without `max_cost_basis`, so a stated ceiling
can become a "free" CA$0.00.**
`_RESTATED` copies action, reason, `max_cost_cad`, minutes, consequence and blocks. It does not
copy `max_cost_basis`, `why_software_cannot` or `expires_at`. If a newcomer with basis
`UNKNOWN` (placeholder 0.0) merges onto an open row with basis `stated` and CA$50, the row
becomes **CA$0.00 with basis stated**, and `max_cost_known == 0.0`. W3-WIRE4 says exactly that
"no spend path may treat [the placeholder] as free".
*Repro:*
1. Commit an open `SPEND` row with 50.0 and basis stated.
2. In a new session, add `OwnerAction(requirement_key="SPEND", max_cost_cad=0.0,
   max_cost_basis="UNKNOWN")` and flush.
3. Result: `[(1, False, 0.0, 'stated', 0.0)]`.

This is reachable only when two writes for one key race or collide, but the merge path exists
precisely for that case.
*Fix:* restate `max_cost_cad` and `max_cost_basis` together, plus `why_software_cannot` and
`expires_at`. Better, never lower a stated ceiling silently on merge: keep the higher stated
figure, or keep UNKNOWN if either side is UNKNOWN. Add a test.

**EF2-7 LOW-MEDIUM: changes a caller makes after the flush to a merged object are silently
lost.** The newcomer is expunged and carries only the keeper's id. A caller that then sets
`row.done = True`, `row.why_software_cannot = ...` or any other field changes a transient
object, and nothing is written. Probe: after the merge, the caller set `done=True` and
`why_software_cannot="KYC"`; the stored row stayed `done=False`, `why_software_cannot=""`. A
caller that re-adds the object (for example through a relationship cascade) would hit a
primary-key `IntegrityError`.
*Fix:* return the keeper to callers through a helper such as `owner_queue.ensure(key, ...)`
that returns the persistent row, and move writers to it. Alternatively, document that the
object is detached after a merge, and assert in tests that no current writer mutates the row
after its flush.

**EF2-8 LOW: reverting a reopen destroys the row's lifecycle state.** A reopen goes through the
`done` validator (state → open), and the revert sets `done=True` again, which stamps
`closed_unclassified`. Probe: a `satisfied` row that is reopened and then reverted ends as
`closed_unclassified`, so the owner's real outcome is lost from the history.
*Fix:* when reverting, restore `state`, `state_at` and `state_reason` from their attribute
history (or expire the object), not only `done`.

### Tests (subject 3)
`test_opus2_owner_queue_races` 0 failed · `test_w4_owner_queue_race` OK ·
`test_w3_k7_owner_queue` 10 passed, 0 failed · `test_vacuity` OK.
Mutations S3M2 to S3M5 were killed. S3M1 was not applied (pattern mismatch); S3M5 covers the
same line.

---

## Test runs

Each run used `cd brambleloop && PYTHONPATH=src:tests nice -n 19 python tests/<f>`, one suite
at a time, after `pip install -r requirements.txt`: the container lacked SQLAlchemy.

| Branch | Suite | Result |
|---|---|---|
| p0-revenue-workforce | test_opus2_draft_constructions | 0 failed |
| p0-revenue-workforce | test_opus2_size_claims | 0 failed |
| p0-revenue-workforce | test_opus2_rim_negative | 0 failed |
| p0-revenue-workforce | test_opus2_chain_deadends | 0 failed |
| p0-revenue-workforce | test_vacuity | OK |
| p0-revenue-workforce | test_shadow | PENDING |
| p0-listing-package | test_opus2_listing_package | PENDING |
| p0-listing-package | test_vacuity | PENDING |
| p1-owner-queue-races | test_opus2_owner_queue_races | 0 failed |
| p1-owner-queue-races | test_w4_owner_queue_race | OK |
| p1-owner-queue-races | test_w3_k7_owner_queue | 10 passed |
| p1-owner-queue-races | test_vacuity | OK |

## Integrator actions

1. Subject 1: fix EF2-1 (count finished objects in `title_promise`, and refuse tote second
   objects and features) and add the EF2-2 tests. EF2-3 can follow.
2. Subject 2: fix EF2-4 so that only an owner-closed row suppresses a new request, and add the
   three-step test. EF2-5 is a one-line follow-up.
3. Subject 3: fix EF2-6 (cost basis on merge) before integration. Make B-5, the partial unique
   index with its duplicate-closing script, an integration blocker before production or
   Postgres. EF2-7 and EF2-8 can follow.
