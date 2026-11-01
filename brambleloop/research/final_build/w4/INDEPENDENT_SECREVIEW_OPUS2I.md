# Independent security and correctness review OPUS2I: deltas on the OPUS2G and OPUS2H findings, 2026-11-01

Reviewer: an independent Claude Code session (branch `claude/w5-SECREVIEW-OPUS2I`). This review
is read-only on every branch under review; this report is the only file written. Every probe
and mutation ran in scratch worktrees under `/tmp/rv/` and was reverted with `git checkout`, and
`git status` was clean afterwards. Nothing was deployed, published, messaged or spent; Railway
and production were not touched. A throwaway local PostgreSQL 16 cluster (`/tmp/pgdata`, port
55432) was used only for the PR #6 and PR #7 Postgres paths.

`git fetch origin` first. Every head matched the brief:

| # | PR | Branch | Head | Diffed against |
|---|---|---|---|---|
| 1 | #6 | opus2/p1-owner-queue-races | 23935b58 | cc8f2b4f (OPUS2G) |
| 2 | #7 | opus2/p1-culture-sweep-timeout | 4c777a0b | ec97a79e (OPUS2G) |
| 3 | #8 | opus2/p0-family-membership | fa529381 | 0f862a1b (OPUS2G) |
| 4 | #5 | opus2/p0-listing-package | be96a598 | e93b16ed (OPUS2G; already in `claude/w5-INTEG1` d3688000) |
| 5 | #3 | opus2/p0-revenue-workforce | 558e7ca9 | 13d67502 (OPUS2H; already in `claude/w5-INTEG1`) |
| 6 | — | opus2/p0-cir-colourwork | f57219d0 | 5b0f8e0e (OPUS2H HOLD); digests also checked against d230e8fd |

## Verdicts

| # | Subject | Verdict | Highest open finding |
|---|---|---|---|
| 1 | PR #6 owner-queue races (D-1, D-2, D-4; D-3 documented) | **ACCEPT** | INFO |
| 2 | PR #7 culture sweep timeout (C-2, C-3; C-1 stated) | **ACCEPT** | LOW (C-4: a pre-send bug is swallowed and billed as unknown spend) |
| 3 | PR #8 family membership (F-1, F-2, F-3) | **ACCEPT** | LOW (F-5: `bundle_ready` still derived for culture families) |
| 4 | PR #5 listing package (L5-1) | **ACCEPT** | INFO |
| 5 | PR #3 revenue workforce (H1-1, H1-2, H1-3) | **CHANGES_REQUIRED** | MED (I-1: the H1-3 fix lets plural titles "Sets", "Pairs", "Bundles" pass as backed single objects) |
| 6 | Colourwork (H2-1 to H2-6) | **KEEP HOLD** | HIGH (I-2: the listing-side colourwork gate still backs mosaic, intarsia and fair isle with one contrast stitch) |

None of the six weakens the paid-call anti-double-spend protocol (F-307/F-339), and none queues
a paid job. No Launch-0 `design_digest`, release hash, CIR JSON, written pattern, yardage,
colour plan or `fabric_truth` verdict moves (item 6).

---

## 1. PR #6: opus2/p1-owner-queue-races 23935b58 — ACCEPT

### D-1 (dedupe loses the owner's deferral, lowers a ceiling): fixed at the root

`owner_queue_dedupe.close_duplicates` now:
- loads each duplicate group through the ORM;
- picks the keeper as the newest PARKED row, falling back to the newest row;
- merges every other row's ceiling onto the keeper with the guard's own `_merge_cost`;
- closes the others through `owner_queue.transition(SUPERSEDED)`, which writes one
  `owner_action.lifecycle` audit row each.

Repro (`/tmp/rvtools/probe6.py`: the OPUS2G P2 shape plus a three-row group M = open 5.0,
parked 1.0, open UNKNOWN). The index was dropped and the rows were inserted with Core.

| Engine | Commit | K kept | C kept | M kept | Audit rows |
|---|---|---|---|---|---|
| SQLite | cc8f2b4f | #2 open, stated 0.0 (deferral lost, UNKNOWN→0) | #4 stated **0.0** | #7 open | 0 |
| SQLite | 23935b58 | #1 **parked**, UNKNOWN | #4 stated **50.0** | #6 **parked**, UNKNOWN | 4 |
| PG 16 | cc8f2b4f | same as SQLite base | same | same | 0 |
| PG 16 | 23935b58 | same as SQLite fix | same | same | 4 |

`conflicts()` is 0 afterwards on both engines.

### D-2 (the acceptance ruling lands on a detached copy): fixed at the root

`_record_acceptance_ruling` now calls `owner_queue.ensure(...)` and then `transition(SATISFIED)`.

Repro (`probe6.py`, real `approvals._record_acceptance_ruling`, an open row already under
`executor.ACCEPTANCE_RULING_KEY`):

| Commit | Returned id | Stored row |
|---|---|---|
| cc8f2b4f | 1 | `open, done=False` (the ruling was lost, but the response reported success) |
| 23935b58 | 1 | `satisfied, done=True` |
| 23935b58, existing row PARKED | 1 | `satisfied, done=True` (the base left it `parked`) |

Same on PostgreSQL 16.

### D-4: fixed

The test adds the 50 → 10 → assert 50 step. The OPUS2G survivor M6a ("take the newcomer's
ceiling") is now killed by ef26 itself (M6o below).

### D-3: documented only, as stated

The guard docstring now states the close-plus-reopen-in-one-flush restriction (fail-closed:
the index refuses it and the transaction rolls back). It is latent because `store_readiness`
reopens only when no row is open. Acceptable as documented.

### No new fail-open

- The keeper only moves to a PARKED row the owner set.
- Cost is merged with the same never-lower rule, and UNKNOWN is sticky.
- Closing goes through the audited lifecycle API.
- No gate is relaxed and no test is weakened. The diff only adds assertions.

### Findings

- **D-6 INFO: the keeper is not restated.** When a PARKED row is kept, the newer OPEN row's
  action text, reason and `expires_at` are dropped with it. The owner sees the text they
  deferred, which is defensible. A parked keeper whose own expiry has passed will be EXPIRED by
  `sweep`, after which no open row exists until the producer re-raises it.
- **D-7 INFO: "the newest of several parked rows" is not pinned.** M6p (`parked[0]` instead of
  `parked[-1]`) is killed only incidentally, by the b5 migrate test.
- **D-5 (OPUS2G INFO) is still open.** A deferred index is still not surfaced in `/api/verify`.

### Mutations (worktree `/tmp/rv/q`, each reverted; clean afterwards)

| ID | Mutation | Result |
|---|---|---|
| M6k | keeper = newest row, PARKED ignored | **killed**: d1 test |
| M6l | `_merge_cost` across the group removed | **killed**: d1 test |
| M6m | `transition` replaced by unaudited `close` | **killed**: d1 test (audit count) |
| M6n | ruling written to a fresh `OwnerAction` again (the base shape) | **killed**: d2 test |
| M6o | guard merge takes the newcomer's ceiling (OPUS2G M6a) | **killed**: ef26 (now) and ef27 |
| M6p | oldest PARKED row kept | **killed**: b5 migrate test only (D-7) |
| M6q | PARKED detection compares `"PARKED"` (never matches) | **killed**: d1 test |

---

## 2. PR #7: opus2/p1-culture-sweep-timeout 4c777a0b — ACCEPT

### C-2 (other UNCERTAIN failures escape, and their spend is never recorded): fixed

`classify` now catches `Exception` after the Permanent/Transient clause. Once `sent` is true it
does three things:
- releases the reservation with `actual_cad=estimate`;
- writes one ledger row at the estimate (`billing: unknown_counted_at_estimate`, never zero);
- returns "nothing filed / unresolved".

The guard (`paid_calls.guarded`, `_classify_failure`) is untouched, so the paid-call record
stays UNCERTAIN and the P1 incident still opens.

End-to-end repro (`/tmp/rvtools/e2e7.py`): the real `culture.sweep` job runs through the real
`Worker` and `paid_calls.guarded`. Only `AnthropicProvider._send` and the feeds are faked.

| Failure | Commit | Attempts | Cost rows | Reservation | Paid-call outcome | P1 incident |
|---|---|---|---|---|---|---|
| timeout | ec97a79e | 1 → done | 1 at CA$0.013425 | released at estimate | UNCERTAIN | 1 |
| bad JSON (`ValueError`) | ec97a79e | 1 failed, 2 done | **none** | first **left open** | UNCERTAIN | 1 |
| `ConnectionResetError` | ec97a79e | 1 failed, 2 done | **none** | first **left open** | UNCERTAIN | 1 |
| `IncompleteRead` | ec97a79e | 1 failed, 2 done | **none** | first **left open** | UNCERTAIN | 1 |
| each of the four | **4c777a0b**, SQLite | **1 → done** | **1 at CA$0.013425** | **released at estimate** | UNCERTAIN | 1 |
| each of the four | **4c777a0b**, PG 16 | 1 → done | 1 at CA$0.013425 | released at estimate | UNCERTAIN | 1 |
| HTTP 500 (`TransientError`, DECLINED) | 4c777a0b | 1 → done | none (correct: the provider refused before doing work) | released, no actual | DECLINED | 0 |

In every case the call was sent exactly once.

**UNKNOWN spend is never recorded as zero.** M7g (amount 0.0) is killed. The only path with no
cost row is DECLINED, which `_classify_failure` reserves for a provider refusal, the same split
`ModelGateway._billing` uses.

**F-307/F-339 still hold.** `gateway/paid_calls.py` and `gateway/anthropic.py` are unchanged
from the base:
- the call is not re-sent (M7k is killed);
- a later attempt would still get `PaidCallUnresolved`, which is a `PermanentError` and goes to
  the first branch, so it is not counted twice;
- `PaidCallReplayedFailure` and `EffectRefused` are both `PermanentError`, so neither is billed;
- `test_w3_spend_paid_calls` and `test_w4_close5_vision_timeout` pass.

### C-3 (tests bypass the guard): fixed

The new worker-level test fakes `_send` and runs the four failure classes through the real
guard. M7e (timeout classified DECLINED) is now killed by the PR's own suite.

### C-1: stated, not claimed fixed

Commit 4c777a0b says plainly that the PR "does not claim to clear the production dead letter"
and that `jobs.last_error` for job 41979 is still needed. No repository record claims the fix:
- the COORDINATION claim `OPUS2-CULTURE-SWEEP-TIMEOUT` is unchanged since ec97a79e. Its scope
  is "catches the classifier TimeoutError"; it does not mention the dead letter;
- BUILD_STATE still says production is NOT fully healthy while
  `no_unexpected_dead_letters_in_24h` is red.

INFO: two things are stale and should be refreshed when the integrator records the merge:
- the COORDINATION `unowned` entry still states the disproved cause ("the UNCERTAIN paid-call
  intent then refuses every retry");
- the claim's evidence still reads "3/3", and the scope still names only TimeoutError.

### Findings

**C-4 LOW (new): "sent" is set before anything is sent, so a pre-send bug is swallowed and
billed.**
- `sent = True` is assigned before `prompt(topics)` is evaluated, and before the provider's own
  pre-send steps run (`json.dumps`, the guard's write-ahead DB writes).
- Any non-Permanent/Transient exception there is therefore treated as UNCERTAIN.

Repro (`/tmp/rvtools/presend7.py`): `prompt` raises `RuntimeError` on its second call (the
first is the budget estimate), and `_send` is never reached.

| Commit | Result | Sent | Cost rows | Reservation |
|---|---|---|---|---|
| ec97a79e | `RuntimeError` raised (job fails, visible) | 0 | none | left to expire |
| 4c777a0b | **returned** `{"filed": {}, "unresolved": True, "reason": "classifier call outcome unknown (RuntimeError)…"}` | 0 | **1 at CA$0.013422, `unknown_counted_at_estimate`** | released at estimate |

Spend is over-counted (never under), so this is not a spend fail-open. But a deterministic bug
in the prompt builder, or a DB error during the guard's write-ahead, now completes the job
nightly with a phantom charge, no paid-call record and no P1 incident, instead of
dead-lettering visibly. The code comment says "A failure before anything was sent (the budget
check, a bug) is not billed and is re-raised", which is true for the budget check only.
- M7i (the `if not sent: raise` branch deleted) **survives**.
- M7j (`sent = True` from the start) **survives** the PR's suite and `test_culture`,
  `test_w3_spend_paid_calls` and `test_w3_spend_hygiene`.

*Fix:* build `user = prompt(topics)` before `sent = True`. Better, decide by the guard's record:
bill at the estimate only when `paid_calls` wrote an UNCERTAIN outcome for this call (or, outside
a job, only for the exception types `_classify_failure` calls UNCERTAIN), and re-raise
otherwise. Add a test in which a pre-send failure re-raises and writes no cost row.

### Mutations (worktree `/tmp/rv/c`, each reverted; clean afterwards)

| ID | Mutation | Result |
|---|---|---|
| M7f | catch narrowed back to `TimeoutError` | **killed**: c2/c3 worker test (ValueError) |
| M7g | unknown spend recorded as 0.0 | **killed**: 2 tests |
| M7h | reservation not released | **killed** |
| M7e | `_classify_failure`: timeout → DECLINED (OPUS2G survivor) | **killed** by the PR's suite now |
| M7k | call re-sent inside the uncertain branch | **killed** (sent == 2) |
| M7i | `if not sent: … raise` removed | **survives** (C-4) |
| M7j | `sent = True` before the budget check | **survives** (C-4), also in test_culture, test_w3_spend_paid_calls, test_w3_spend_hygiene |

---

## 3. PR #8: opus2/p0-family-membership fa529381 — ACCEPT

### F-1 (`amplify` KeyError for a culture family at the order floor): fixed at the root

`amplify` now checks `family.startswith(CULTURE_FAMILY_PREFIX)` after the parked and held
checks and before `investigate`/`adjacency`/`enqueue`. It:
- records `how`;
- saves the state;
- appends `decision: needs_member_route`;
- `continue`s, so later families still run.

The `radar.score` branch is unreachable for culture families, so no concept slug is queued.

Repro (`/tmp/rvtools/probe8.py`, the OPUS2G shape: two certified `sig-aurora` products, one
unmade concept, 6 orders):

| Commit | amplify | queued |
|---|---|---|
| 0f862a1b | **KeyError 'seed'** (family_engine.py:285) | — |
| fa529381 | `{'decisions': [{'family': 'culture:sig-aurora', 'job_id': None, 'decision': 'needs_member_route'}]}` | `[]` |

### F-2 (call sites untested): fixed

Both call sites are now tested. The OPUS2G survivors M8e and M8f are killed.

### F-3 (buyer-facing "related" follows a news signal): fixed for the buyer-facing edge

`cross_sell.graph` sets `related = []` for a `culture:` family and moves the members to
`planned.culture_family_members` (`internal: True`). Probe: `related: []`,
`planned.culture: ['aurora-stocking']` (base: `related: ['aurora-stocking']`).

### Findings

**F-5 LOW: culture families are still derived as sets in the internal readings.**
- `family_report` still gives `bundle_ready: True` for `culture:sig-aurora` (`distinct >= 2`),
  so `portfolio_has_bundle_ready_family` is True. The `creative.family_engine` audit row
  records `bundle_ready: True`.
- `children.architecture` groups the advisory Baby & Kids navigation `by_family` under
  `culture:…`, and the PR's new test pins that.

Neither is buyer-facing today. `bundle_ready` is read only by `engineering_ops` (audit/report)
and `children.develop` (`sibling_sets`). The navigation is an ADVISORY storefront-director row
that needs an owner grant. But it contradicts F-3's own rule: a culture family is "not a checked
shared visual identity".

*Fix:* `bundle_ready = distinct >= 2 and not culture` (or a separate
`culture_bundle_ready: UNMEASURED`), and keep culture families out of `navigation.by_family`
until the visual-identity check exists.

**F-6 INFO.** A culture family at the floor re-records `needs_member_route` every run. It is
not parked, which is harmless (CA$0, no queue).

### Mutations (worktree `/tmp/rv/f`, each reverted; clean afterwards)

| ID | Mutation | Result |
|---|---|---|
| M8h | culture branch disabled | **killed** (KeyError) |
| M8n | culture branch records no decision | **killed** |
| M8j | `related = same_family` for culture families | **killed** |
| M8m | `culture_family_members` emptied | **killed** |
| M8e | `cross_sell` does not pass `db` (OPUS2G survivor) | **killed** |
| M8f | `children` does not pass `db` (OPUS2G survivor) | **killed** |

---

## 4. PR #5: opus2/p0-listing-package be96a598 — ACCEPT

be96a598 is a linear child of e93b16ed. The delta is three files: `listing_package.py` (6
lines), the test (20 lines) and the handoff. The branch merges into `claude/w5-INTEG1`
(d3688000) with no conflict (`git merge-tree`), and INTEG1 has not changed `listing_package.py`
since e93b16ed.

### L5-1 (an owner's deferral is overridden by a transient block): fixed at the root

`record` skips a PARKED row while the package is not READY. A READY package with the same
fingerprint finds the parked row `not done`, so `already` is true and nothing is re-raised.
Changed content still supersedes it.

Repro (`/tmp/rvtools/probe5.py`, real certified blanket release; the owner parks through
`owner_queue.transition(PARKED)`, the path `owner_action.defer` uses):

| Step | e93b16ed rows | be96a598 rows |
|---|---|---|
| R | #1 open | #1 open |
| owner parks | #1 parked | #1 parked |
| B | #1 **superseded** | #1 parked |
| R | #1 superseded, #2 **open** (re-asked) | #1 parked (not re-asked) |
| B, B, R | #2 superseded, #3 open | #1 parked |
| R′ (new content) | #3 superseded, #4 open | #1 superseded, #2 open |
| B, R′ | #4 superseded, #5 open | #2 superseded, #3 open (EF2-4 re-ask still works) |

### Findings

**L5-4 INFO.** While a package is BLOCKED, a parked request stays parked, and its reason still
reads "Every publication gate passes". If the owner un-parks it during the block, they are asked
to review a blocked package. Nothing treats a SATISFIED review as publication authority
(`listing_package:` keys have no other reader), so this cannot publish. The next READY with
changed content supersedes it, and the same content does not.

### Mutations (worktree `/tmp/rv/l`, each reverted; clean afterwards)

| ID | Mutation | Result |
|---|---|---|
| M5f | the PARKED skip removed | **killed**: l51 test |
| M5g | PARKED rows skipped even when READY with new content | **killed**: l51 test |
| M5h | every open row treated as parked | see the test table |

---

## 5. PR #3: opus2/p0-revenue-workforce 558e7ca9 — CHANGES_REQUIRED

The branch merges into `claude/w5-INTEG1` with no conflict. INTEG1's only later change to
`size_claims.py` is the INTEG5FIX `_PATTERN_REF_BEFORE` exemption, which does not overlap.

### H1-1 (stash vs material): fixed for EF2's own repro, with a narrow relaxation

The new lookahead treats `of [wool|cotton|acrylic|fibre|fiber] (yarn|stuffing|scraps|stash|
skein(s)|ball(s))` as contents, and `of <fibre>` alone stays a claim.
- "2 baskets of cotton", "Two baskets of wool" and "2 baskets of jute" now **FAIL** (claims).
- "3 bags of yarn" and "2 bags of scraps" PASS.

Grid comparison (`/tmp/rvtools/szgrid.py`, 699 phrases: `{2, Two, 3} × {baskets, bags, bowls}
× of × {∅, wool, cotton, acrylic, fibre, t-shirt, jute} × {∅, yarn, rope, cord, stuffing,
scraps, stash, skeins, balls, twine, blend}`, 13d67502 against 558e7ca9):
- **Tightened (PASS → FAIL):** `of cotton`, `of wool`, `of fibre` and their `… blend` forms
  (the intended fix).
- **Relaxed (FAIL → PASS):**
  - `of stash`, `of skeins` and `of balls` (contents, which is correct);
  - `of acrylic yarn|stuffing|scraps|…` (consistent with `of cotton yarn`, which already passed);
  - `2 baskets of yarn cord` (the old material lookahead is gone, so "yarn cord" is read as
    contents).
- "2 baskets made of cotton yarn", "3 nesting baskets of cotton yarn" and "a set of 3 baskets of
  cotton yarn" still FAIL.

**I-3 LOW.** `<n> baskets of cotton yarn` / `of acrylic yarn` is still read as contents
whatever noun precedes it. H1-1 suggested keying the exemption on a stash/container context
("bags of yarn", "a basket full of"). "2 baskets of yarn cord" newly passes. Both are narrow,
and neither reaches any current product.

### H1-2 (conflicting size words): fixed

`plan()` collects every `_TOTE_SIZE_WORDS` key that matches as a whole word and refuses when
there is more than one. "Tiny Large Tote", "Small Big Tote" and "Medium Large Tote" are refused
("more than one size"). "Tiny Small Tote" (one key) still drafts small.

### H1-3 (`PLURAL_MARKERS` substring): fixed for "Sunset", but the fix opens a hole

**I-1 MED (new; Product Truth relaxed): whole-word matching drops every inflected plural
marker.**

`title_promise` now matches `\bset\b`, `\bpair\b`, `\bbundle\b`, and so on, so "Sets", "Pairs",
"Bundles", "Collections", "Duos", "Trios" and "Bundled" no longer read as multiplicity. Each
title below was applied to the drafted one-piece tote (`makes=1`; `/tmp/rvtools/tp3.py`):

| Title | 13d67502 `title_promise.backed` / `name_truth` | 558e7ca9 |
|---|---|---|
| Sunset Market Tote, Closet Tote, Asset Tote | False / flags (H1-3) | True / [] (fixed) |
| Market Tote Set, Market Tote Set-of-2 | False / flags | False / flags |
| **Market Tote Sets** | False / flags | **True / []** |
| **Tote Pairs, Tote Bundles, Tote Collections, Tote Duos, Tote Trios** | False / flags | **True / []** |
| **Bundled Totes** | False / flags | **True / []** |
| Tote Libraries, Totes | True / [] | True / [] (pre-existing gap) |

`plan()` already used `\b{m}\b` (fallback_constructions.py:487), so it never caught these
either. `title_promise` and `name_truth` were the backstop for any path that retitles after
drafting (H1-4), and that backstop is now gone for plural forms.

Catalogue check (`/tmp/rvtools/tpu.py`, 26 buildable universe slugs and 11 Launch-0 builders):
no `backed` verdict changed and no product is unbacked. "Hexagon Coaster Set", "Raised
Diamond Lattice Placemat Pair", "Textured Stripe Ornament Set (6)" and "Heart Applique Motif
Library (12)" still read their markers. So this is latent, but it is a relaxed Product Truth
gate.

*Fix:* match the marker and its inflections as whole words, for example
`rf"\b{w}(?:s|es|d)?\b"` plus `librar(?:y|ies)`, or a stem table. Pin "Market Tote Sets",
"Tote Pairs", "Bundled Totes" and "Tote Libraries" as unbacked next to "Sunset/Closet" as
backed.

### Mutations (worktree `/tmp/rv/r`, each reverted; clean afterwards)

| ID | Mutation | Result |
|---|---|---|
| M3a | refuse only at more than two size keys | **killed** |
| M3b | `PLURAL_MARKERS` substring match again | **killed** ("Sunset") |
| M3c2 | H1-1 lookahead reverted to the 13d67502 one | **killed** ("2 baskets of cotton") |
| M3d | `rope` added to the contents nouns | **killed** ("Two bowls of wool rope") |
| M3e | contents noun made optional | **killed** |
| (M3c) | a near-equivalent mutant (an alternation that cannot match) | survived; discarded and replaced by M3c2 |

No mutation covers I-1: the plural forms are untested, which is a missing test rather than a
surviving mutant.

---

## 6. Colourwork: opus2/p0-cir-colourwork f57219d0 — KEEP HOLD

### Per OPUS2H finding

| Finding | Status at f57219d0 | Evidence |
|---|---|---|
| **H2-1 HIGH** (one contrast stitch backs every technique) | **Fixed in `launch0.fabric_truth` only.** Not fixed in the listing gate (I-2). | `technique_backed` refuses mosaic, overlay and graphghan (reach-down) and intarsia (bobbins) outright. tapestry, fair isle and colourwork need ≥ 3 two-colour rows, ≥ 20 % of rows, and ≥ 10 % minority colour in each such row. `backed = all(...)`. The token repro ("Overlay Mosaic", "Fair Isle", "Intarsia", "Graphghan", "Tapestry", "Colourwork" Basket on one contrast stitch) is refused. "Tapestry Mosaic Basket" on a real band is refused. |
| **H2-2 MED** (carried strand, rows "2-4", yardage) | **Mostly fixed.** I-4 is new; the test for the yardage half is vacuous (I-5). | The repro (rows 2 and 4, plain row 3) now gives `cut=1, ends=6` and "Colourwork rows 2 and 4 … cut it at the end of its last row and rejoin it …". `_row_list` gives exact rows. Carried yarn is charged at `CARRY_FACTOR = 1.0` (stated). Repro yardage: rust 0.4 → 0.5 m. |
| **H2-3 MED** (colour on a non-stitch op) | **Fixed for skips.** Coloured chains are still silent (I-6). | `COLOUR_ON_NON_STITCH` ERROR when `produces == 0` (only `sk`). `ch` produces 1, so `ch 1 with rust` compiles with no finding. H2-3 asked for "a WARNING at least". |
| **H2-4 MED-LOW** (empty colour table) | **Fixed.** | `colors={}`, op colour "teal" → `UNKNOWN_COLOR` ERROR. |
| **H2-5 LOW** (digest test pins nothing) | **Fixed.** | `BASE_DIGESTS` holds 11 full sha256 values. I re-computed them on d230e8fd: they match exactly. |
| **H2-6 LOW** (unwritable colour keys) | **Fixed.** | `COLOUR_KEY_UNWRITABLE` ERROR for "Dusty Rose", using the reverse compiler's grammar. |

### No Launch-0 digest or content hash moves: confirmed

`/tmp/rvtools/dg.py` computed eight values for each of 37 CIRs (11 `launch0.BUILDERS` and 26
buildable `inventory.universe()` slugs) on **d230e8fd, 5b0f8e0e and f57219d0**:
- the sha256 of `to_json`;
- `physical.design_digest`;
- `pattern_refs.release_hash_of`;
- the sha256 of `writer.write_pattern`;
- `yarn_metres_by_color`;
- `fabric_truth.backed`;
- the sha256 of the colour-plan instructions;
- the compile ERROR codes.

**All 37 × 8 values are identical across the three commits.** No product gains a compile error,
and `test_physfix` passes 46/46. No builder or fallback emits `Op.color` yet (`grep 'Op(.*color='`
finds only `Row(color=…)`).

### Findings

**I-2 HIGH (H2-1 not fixed in the second gate): the listing colourwork gate still backs every
technique with one contrast stitch.**

`gates/first_customer.colourwork_findings(cir, twin, title=, tags=)` is unchanged from the base.
It returns no finding as soon as any twin row holds two colours (`if per_row >= 2: return []`).
It is the listing-side check for the publish path:
- `runtime/release.py:1265` (listing assembly);
- `publish/eligibility.py:658` (`listing:` findings);
- `gates/first_customer.py:500` (`check_listing_claims`);
- `seo/strategy.py:539`.

It reads the listing title and tags, which `fabric_truth` (CIR title and notes only) never
sees. Before this branch, `per_row >= 2` was impossible, so every listing claim was refused by
construction. With `Op.color` it is satisfied by one stitch.

Repro (`/tmp/rvtools/fc.py`, the H2-1 token CIR: one `sc 1 with rust` in a 12-stitch round,
everything else plain):

```
fabric_truth (CIR title "Overlay Mosaic Basket")                         backed = False   (fixed)
colourwork_findings(title="Overlay Mosaic Intarsia Basket",
                    tags=("mosaic", "fair isle", "intarsia"))            []               <- passes
the same call on an all-plain CIR                                        2 LISTING_COLOURWORK_UNSUPPORTED findings
```

So a listing can claim mosaic, intarsia and fair isle in its title and tags on a token-stitch
product, which is exactly the H2-1 relaxation, moved one gate over. It becomes reachable the
moment a builder or the radar fallback emits `Op.color`, which is the purpose of the branch.

*Fix:* route `colourwork_findings` through `launch0.technique_backed(claim,
colourwork_motif(twin.color_grid()))` for each claim it finds, so both gates share one rule. Add
the repro above as a test.

**I-4 MED-LOW (new): a tapestry cut is counted as a row-colour change cut, so the row-change
sentence and the certificate message misstate the fabric.**

The tapestry branch increments `plan.cut` and sets `first_cut_row`, which `carry_is_possible`,
`_row_instruction` and `certificate.colour_carry_findings` read as row-change cuts.

Repro (`/tmp/rvtools/cw.py`, flat turned rows):
- rows 1-2 natural, rows 3-4 sage, row 5 natural (two-row stripes, so every row change can be
  carried);
- rows 6 and 8 tapestry rust, with plain row 7 between them.

The plan is `changes=2, carried=1, cut=1`. The PDF sentence reads "Colour changes: **1 of the 2
start at the edge opposite the resting colour, so it cannot be carried**: cut it at the end of
its row …", followed by the tapestry sentence that tells the maker (correctly) to cut the rust
at row 8. The stripe change that sentence calls uncarriable is in fact carriable, and the cut
is printed twice.

With the designer note "carry the resting colour up the side", the certificate raises
`COLOUR_CARRY_IMPOSSIBLE` with "1 of 2 colour changes … start at the opposite edge (first at
row 8)". This fails closed, but row 8 is not a colour change.

*Fix:* count tapestry cuts separately (`plan.tapestry_cuts`, `first_tapestry_cut_row`). Keep
`changes/cut/carry_is_possible` for row changes, and add both to `ends`. Pin the mixed case.

**I-5 LOW (test quality): four of the new rules are not pinned.**
- **C12 and C13:** `COLOURWORK_MIN_MINORITY_SHARE = 0` and `COLOURWORK_MIN_ROW_SHARE = 0` each
  **survive**. Only `COLOURWORK_MIN_ROWS` is pinned (C11 killed), because the token fixture fails
  the row count first. The comment says the thresholds are "pinned by tests".
- **C14:** `backed = any(...)` instead of `all(...)` **survives**. No test combines a backed and
  an unbacked claim ("Tapestry Mosaic Basket" on a real band: `all` → False, `any` → True). That
  combination is the H2-1 class itself.
- **C19:** the carried-strand yardage removed **survives**. The H2-2 test's threshold
  `worked_only = 12*10/18/100 = 0.067 m` sits below rust's worked yardage even with no carry
  (0.4 m; 0.5 m with the carry), so the assertion cannot fail.

*Fix:* fixtures at each threshold boundary, a mixed-claim title, and an exact yardage
expectation (0.5 m against 0.4 m without the carry).

**I-6 LOW (H2-3 residual): a coloured chain is accepted with no finding.** H2-3 asked for a
decision, and at least a WARNING. `ch 1 with rust` inside a row compiles silently, is written
"ch 1 with rust", and is charged to rust. Make it an explicit decision: a WARNING, or allow it
with a pinned test.

**I-7 LOW: the motif rule accepts scattered dots.** Three non-contiguous rows of 15, each with
two separate contrast stitches out of 12 (16.7 %), back "Fair Isle Panel", "Tapestry Panel" and
"Colourwork Panel" (two-colour row share exactly 0.20). H2-1 also asked for a minimum contrast
run. The thresholds are stated as a design rule, so this is a judgement call. A minimum
contiguous contrast run (for example ≥ 2 stitches) and contiguity of the motif rows would make
"fair isle" mean a band.

**I-8 INFO.**
- `products/moment_candidates.py:17` and `pipeline_board.py:270` still say
  `per_stitch_colour_expressible()` is False. It is True on this branch.
- The yardage carry does not charge strands carried up the side across plain rows (rows 2 and
  5 with two plain rows between: "Do not cut", no carry stated). This is conventional and minor.

### Recommendation: **KEEP HOLD**

H2-1 is fixed at the root in `fabric_truth`. It is still open in the listing gate (I-2, HIGH):
the claim a buyer actually reads (listing title and tags) is still backed by one contrast stitch
for mosaic, intarsia and fair isle. Lift the hold when:
1. I-2 is fixed by sharing `technique_backed` between both gates, with the repro as a test;
2. I-4 separates tapestry cuts from row-change cuts, with the mixed test;
3. I-5 pins the two share thresholds, the `all` combination and the exact carry yardage.

I-6, I-7 and I-8 can be handled in the same pass or as follow-ups. Nothing on this branch moves a
Launch-0 release today, so the hold costs nothing in production.

### Mutations (worktree `/tmp/rv/w`, each reverted; clean afterwards)

| ID | Mutation | Result |
|---|---|---|
| C10b | mosaic/overlay/graphghan judged by the motif rule | **killed** |
| C10c | graphghan alone moved to the motif rule | **killed** |
| C15b | intarsia judged by the motif rule | **killed** |
| C11 | `COLOURWORK_MIN_ROWS = 1` | **killed** |
| C12 | `COLOURWORK_MIN_MINORITY_SHARE = 0.0` | **survives** (I-5) |
| C13 | `COLOURWORK_MIN_ROW_SHARE = 0.0` | **survives** (I-5) |
| C14 | `all(...)` → `any(...)` | **survives** (I-5) |
| C16 | the tapestry cut not counted | **killed** |
| C18 | `_row_list` reverted to the "first-last" span | **killed** ("2-4") |
| C19 | carried-strand yardage removed | **survives** (I-5) |
| C20 | `COLOUR_ON_NON_STITCH` removed | **killed** |
| C21 | `UNKNOWN_COLOR` back to `if cir.colors and …` | **killed** |
| C22 | `COLOUR_KEY_UNWRITABLE` removed | **killed** |
| C23 | an "unrecognised claim" returns True | survives; equivalent (every `COLOURWORK_CLAIMS` entry is in a named list) |
| (C10, C15) | the first forms only skipped the branch and fell through to "unrecognised → False", so they were equivalent mutants | discarded and replaced by C10b/C15b |

---

## Test table

Each suite was run one at a time from `brambleloop/` on each branch's worktree, as
`PYTHONPATH=src:tests python tests/<f>.py`, after `pip install -r requirements.txt`.
`run_tests.sh` was not run. "OK" counts the `OK`/`PASS` lines.

| Item | Suite | Result |
|---|---|---|
| #6 | test_opus2_owner_queue_races | 14 OK, 0 failed, exit 0 |
| #6 | test_vacuity | 8 OK, exit 0 |
| #6 | test_w4_fmbatch1_retention_guard | 5 OK, exit 0 |
| #6 | test_w3_k7_owner_queue | 10 passed, exit 0 |
| #6 | test_w4_owner_queue_race | 3 OK, exit 0 |
| #6 | test_w4_auditfix_migrate | 2 OK, exit 0 |
| #6 | test_w4_owner_actions | 6 passed, exit 0 |
| #6 | test_executor | 44 OK, exit 0 |
| #6 | test_w4_b2gates | 12/12, exit 0 |
| #6 | test_w4_owner_incidents | 6 passed, exit 0 |
| #7 | test_opus2_culture_sweep_timeout | 4 OK, exit 0 |
| #7 | test_vacuity | 8 OK, exit 0 |
| #7 | test_w4_fmbatch1_retention_guard | 5 OK, exit 0 |
| #7 | test_culture | 26 OK, exit 0 |
| #7 | test_culture_feed | 24 OK, exit 0 |
| #7 | test_w3_spend_paid_calls | 8 OK + PASS, exit 0 |
| #7 | test_w4_close5_vision_timeout | 4 OK + PASS, exit 0 |
| #7 | test_w3_spend_hygiene | 6 OK + PASS, exit 0 |
| #8 | test_opus2_family_membership | 5 OK, exit 0 |
| #8 | test_vacuity | 8 OK, exit 0 |
| #8 | test_w4_fmbatch1_retention_guard | 5 OK, exit 0 |
| #8 | test_w4_c3 | 4 OK, exit 0 |
| #8 | test_w4_children | 6 OK, exit 0 |
| #8 | test_w4_intelrec_amplify | 11 OK, exit 0 |
| #8 | test_collections | 12 OK, exit 0 |
| #8 | test_w4_intelrec_c06 | 3 OK, exit 0 |
| #8 | test_w4_departments | 19 OK, exit 0 |
| #5 | test_opus2_listing_package | see the addendum below |
| #5 | test_vacuity | see the addendum below |
| #5 | test_w4_fmbatch1_retention_guard | see the addendum below |
| #3 | test_opus2_draft_constructions | 19 OK, exit 0 |
| #3 | test_opus2_size_claims | 13 OK, exit 0 |
| #3 | test_fallback_draft_provenance | Ran 5 tests, OK |
| #3 | test_vacuity | 8 OK, exit 0 |
| #3 | test_launch0 | 52 OK, exit 0 |
| #3 | test_w4_pipe_name_truth | 26 OK, exit 0 |
| #3 | test_w4_pipe2_candidates | 86 OK, exit 0 |
| #3 | test_launch0_listing_truth | 14 OK, exit 0 (209 s) |
| CW | test_opus2_cir_colourwork | 10 OK, exit 0 |
| CW | test_compiler | 9 OK, exit 0 |
| CW | test_twin | 8 OK, exit 0 |
| CW | test_reverse | 18 OK, exit 0 |
| CW | test_vacuity | 8 OK, exit 0 |
| CW | test_pattern_truth | 11 OK, exit 0 |
| CW | test_leadtime | 21 OK, exit 0 |
| CW | test_physfix | 46/46 passed, exit 0 (81 s) |

## Probe scripts

The scratch scripts live in `/tmp/rvtools`. They are not committed, and each is described above:
- `probe6.py`: D-1/D-2 on SQLite and PG (`PG=1`);
- `e2e7.py`: the worker-level `culture.sweep`, with modes timeout, badjson, reset, incomplete
  and http500, and an optional `pg`;
- `presend7.py`: C-4;
- `probe8.py`: F-1/F-3/F-5;
- `probe5.py`: the L5-1 sequence;
- `tp3.py`, `tpu.py`, `szgrid.py`: I-1, the catalogue check and the H1-1 grid;
- `cw.py`, `fc.py`, `dg.py`: colourwork plan and gate probes, I-2, and the 37 × 8 digest
  comparison;
- `mut.py`: apply one mutation, run the suites, revert;
- `run.sh`: run one suite at a time.
