# Independent security & integrity review: OPUS2 listing-package job and owner-queue guard

| Field | Value |
|---|---|
| Reviewer | independent reviewer, branch `claude/w5-SECREVIEW-OPUS2F` (report only, no code changes) |
| Date | 2026-11-01 (UTC) |
| Base | `claude/w4-INTEG8-next` at `276a95a7` (both subjects descend from it, verified) |
| Subject A | `opus2/p0-listing-package` at `f779fac2`: INTEG-LISTING-JOB |
| Subject B | `opus2/p1-owner-queue-races` at `ccb3e8e4`: P1-OWNER-QUEUE-RACES |
| Repro scripts | `research/final_build/w4/secreview_opus2f/{repro_a,repro_b,idem_a}.py`; run from the subject worktree's `brambleloop/` with `PYTHONPATH=src:tests python <script>` (idem_a imports the branch's own test fixture) |

## Verdicts

| Subject | Verdict |
|---|---|
| **A**: automatic listing-package job | **CHANGES REQUIRED** |
| **B**: owner-queue guard | **CHANGES REQUIRED** (sound as a backstop; must not be the only constraint, see B-1 and B-5) |

Neither subject makes an outbound action, spends money or publishes. The blocking findings are
integrity defects: a PDF accepted without a release binding, a review request that re-queues
after the owner completes it, and a guard that silently drops rows that callers then use.

---

## Subject A: `listing.package` (f779fac2)

### Checklist

| # | Question | Result |
|---|---|---|
| 1 | No outbound actions | **PASS.** The job makes no Etsy, network or model call and no upload, message or spend. `publishes: False`. The test closes sockets and passes. It does write internally, through `release_gates.for_publish(read_only=True)`: the first sweep on a fresh chain issued **1 `listing_set_certificates` row** (measured). That is the same write `store.publish` makes, and nothing outbound happens. But the claim "Reads and records only" is not literally true for a job classed `OBSERVE` (A-6). |
| 2 | Exact release | **FAIL for the PDF** (A-1). The frames pass: `certified_frames(release=...)` refuses a certificate issued for another release. The copy passes only indirectly: it rests on the search certificate, and `Listing.release_hash` is never compared (A-4). |
| 3 | Product Truth / disclosures | **PASS after integration, with a presentation gap** (A-5). The package does not check disclosures itself. It relies on `for_publish`, which runs `disclosed_listing_set` → `export_images` → `export_check` on every call. On `claude/w4-PDF1`, `export_check` refuses a frame or copy missing `render_contract.estimate_notes` ("Rim shape estimated"), so after integration a soft-corner package without the note is **BLOCKED**. The owner-facing Markdown, however, does not show the note in §7 Disclosures. |
| 4 | Scheduling | **Idempotent: PASS.** On the real chain fixture, sweep 2 wrote 0 rows and `changed=0`. There is no job storm: one 6-hourly cadence, and `work_done` only on change. **Retention:** one `OperatingReading` per `slug@version`, overwritten in place; one Markdown artifact per distinct fingerprint, bounded by changes. **Owner queue: FAIL** (A-2, A-3). |
| 5 | Authority / overlap | No file overlap. `products/production_inventory.py` does not exist at base and is not touched. `research/final_build/w4/manual_listings/*` is not touched: the job writes to the artifact store under `listing_packages/…`, not to the manual `LISTING_PACKAGE.md` tree. It is a conceptual duplicate of W-LISTING's manual packages; the integrator should name which one is canonical per release (A-7). |

### Findings

**A-1: HIGH. The PDF is not bound to the exact release.** `listing_package._files` accepts any
completed `assets.build` job for `slug@version` whose inputs and outputs carry no `release` key,
because `o.get("release", i.get("release", release))` defaults to the release being packaged. It
also accepts any job at all when `pv.release_hash` is empty (`not release or …`). The canonical
reader `pipeline._certified_pdf_hashes` refuses both cases. The package therefore can list a PDF
hash from another release as the file for this one.
*Repro* (on a scratch DB): add a DONE `assets.build` job with
`inputs={"slug":"s","version":"1.0.0"}` and `outputs={"pdf_sha256_by_terminology":{"US":"OLD…"}}`.
- `LP._files(db,"s","1.0.0","R1…")` returns the `OLD…` hash.
- `pipeline._certified_pdf_hashes(...)` returns `None`.

*Fix:* use `pipeline._certified_pdf_hashes`, or require `(inputs|outputs).release == release`
and a non-empty release.

**A-2: MEDIUM. The review request re-queues after the owner completes it.** `record()` looks only
for an *open* `listing_package:<slug>@<version>` action. Once the owner marks the review done,
the next unchanged sweep (6 h later) finds none and inserts a new one, so the owner is asked
again every six hours for a package they already reviewed.
*Repro:* `record(ready)` → set `done=True` → `record(ready)` again: `review_requested=True`, and
there are 2 rows for the key.
*Fix:* key the request on the package fingerprint, or on the release hash, and suppress it when
a closed row for the same fingerprint exists.

**A-3: MEDIUM. A stale review stays open when a READY package changes.** If the fingerprint
changes while the package is still READY (a new release hash, or new copy or frames for the same
`slug@version`), the open request is kept unchanged, and its `reason` still cites the old
release hash. The owner reviews content that no longer matches the stored package.
*Repro:* `record(ready, release R1)` → `record(ready, release R2, new fingerprint)`:
`changed=True`, `review_requested=False`, and the open action still cites `R1R1R1…`.
*Fix:* on a fingerprint change, supersede the open request (`owner_queue.close(...,
SUPERSEDED)`) and raise one that cites the new fingerprint and release.

**A-4: MEDIUM. The copy is not compared with `Listing.release_hash`.** `Listing` carries
`release_hash`, but neither `_release` nor `certified_payload` checks it against `pv.release_hash`.
The binding rests entirely on the search certificate (F-004 "PASS only while … the copy are
current"). `_release` also reads the newest `Listing` row (`order_by id desc`), while
`certified_payload` reads an unordered first row, so with two rows the identity and the copy
can come from different listings.
*Fix:* add a blocker when `listing.release_hash` is set and differs from the certified release,
and read one `Listing` row in both places.

**A-5: LOW. The estimate note is not surfaced in the owner's package.** §7 "Disclosures" is built
only from frame `honesty_label`s, and §8 does not render `alt_text`. The soft-corner note "Rim
shape estimated" is carried in `gallery[].alt_text` and in the description, so it is present in
the stored JSON, but the Markdown the owner reads lists only the rendering disclosure. A missing
note is still *refused* after integration with `w4-PDF1` (see checklist item 3).
*Fix:* add `render_contract.estimate_notes(slug, view)` per frame to §7 once PDF1 lands, and
render the alt text in §8.

**A-6: LOW. Internal writes under the OBSERVE class.** `for_publish` issues a listing-set
certificate, writes back the hero verdict (`search.judge_hero`) and reconciles withholding. The
job is classed `_O` (OBSERVE) and documented as "reads and records only". This is not outbound,
and the writes are idempotent (sweep 2 wrote nothing), but the documentation and the class
should say so, or the job should be `_B` like `chain.rebuild`.

**A-7: LOW. Duplicate authority with the manual packages.** The manual
`manual_listings/<slug>-<version>/LISTING_PACKAGE.md` files and the automatic artifact cover the
same releases, and nothing reconciles them. The automatic package is keyed by `slug@version`,
not by release hash as the COORDINATION scope says ("idempotent per release hash").

**A-8: LOW. Scaling and isolation.** `sweep` evaluates the full publish gate serially for every
certified, listed release: about 120 s for one release in the test. Exceptions in `record()` are
not isolated per release, so one DB error aborts the whole sweep. The owner action is inserted
without `_serialise_owner_queue`; that is covered only if Subject B lands.

**A-9: INFO. Test coverage.** The READY path is tested only with a hand-built `state=READY`
package. The real chain never reaches READY in SHADOW, so the review request and withdrawal are
never exercised end to end.

---

## Subject B: `ops/owner_queue_guard.py` (ccb3e8e4)

### Checklist

| # | Question | Result |
|---|---|---|
| 1 | Every writer takes the lock in the same transaction as its read | **Partly.** The guard takes the lock at *flush*, not at the read. It then re-reads the open keys under the lock, which is equivalent for **ORM inserts of open, keyed rows**. That covers all 47 insert sites, including the new Subject A writer. Not covered: update paths (re-keying and adoption, B-2; reopen, B-3) and Core `insert()` (B-4; no current site uses it). |
| 2 | Deadlocks | **Possible on Postgres only, through the deadlock detector, not a hang** (B-6). On SQLite the guard adds nothing beyond the write lock the INSERT already needed, so no new SQLite deadlock exists. `in_transaction` under Python 3.13 legacy transaction control is True only after DML, which means RESERVED is held. No code issues a plain `BEGIN`, so the check is sound. Re-entering the lock after `_serialise_owner_queue` is safe: on SQLite the connection is already in a transaction, and on Postgres the advisory xact lock stacks. |
| 3 | Tests | **They discriminate.** The barrier harness plus a no-guard control produces 2 rows without the guard and 1 with it, and a real writer (`record_auth_needs_owner`) is raced. There is **no forced-interleaving test per writer**: only 1 real writer of about 47. A DB-level partial unique index **would be safer** (B-5). |
| 4 | Overlap with f4c3899b (`etsy_ops.seed_owner_queue`) | **No conflict.** `seed_owner_queue` takes `_serialise_owner_queue` first, and the guard sees the open transaction and does not issue a second `BEGIN IMMEDIATE`. The two fixes are redundant for that writer, which is harmless. `test_w4_owner_queue_race` was run three times on B (results below). |

### Findings

**B-1: MEDIUM. The losing writer's row is silently expunged, and callers use it.** The guard
calls `session.expunge(obj)`, so the losing writer's object is transient and `obj.id is None`
after `flush()`. Real writers read the id straight after the insert:
- `laura/agency/voice_selection.py:106` does `int(row.id)`, which raises `TypeError` and fails the job.
- `growth/ads_readiness.py:784` sets `proposal.owner_action_id = act.id` = `None`, unlinking a
  spend proposal from its owner decision for that pass. The next pass relinks it by key.
- `runtime/engineering_ops.py:270` and `app/command_center/approvals.py:474` return or use `None`.

*Repro:* commit an open `K1`, then in a new session `s.add(OwnerAction(requirement_key="K1"))`
and `s.flush()`: `obj.id` is `None`.
*Fix:* do not expunge a caller's object. Either raise a typed `DuplicateOwnerAction` that
writers handle, or merge onto the existing open row so the object maps to its id (for example,
look up and return the existing row through a helper `owner_queue.ensure(key, ...)`).

**B-2: LOW-MEDIUM. Update paths are unguarded: re-keying and adoption.**
`etsy_ops.seed_owner_queue:388` and `release.launch_readiness:4238` re-key keyless open rows,
and `orders_ingest:1295` re-keys legacy auth rows to `AUTH_ACTION_KEY`. An UPDATE that sets
`requirement_key` onto a key that is already open is not checked. `orders_ingest`
(unlocked) racing `record_auth_needs_owner` can yield two open `AUTH_KEY` rows.
*Repro:* an open `K2` plus an open keyless row; set `row.requirement_key = "K2"` → 2 open rows.

**B-3: LOW. Reopen is unguarded.** `etsy_ops._set_owner_action(done=False)` (lines 1120 and
1382) reopens the newest row. Reopening any closed row beside an open one for the same key is
not checked.
*Repro:* a closed `K3` and an open `K3`; set `old.done = False` → 2 open rows.

**B-4: INFO. Core `insert(OwnerAction)` bypasses `before_flush`.** There is no current site, but
the handoff's claim that "every future writer" is covered holds only for ORM `add()`.
*Repro:* `s.execute(insert(OwnerAction).values(requirement_key="K4", …))` beside an open `K4`
→ 2 open rows.

**B-5: RECOMMENDATION. Add a partial unique index as the authoritative constraint.**
`CREATE UNIQUE INDEX uq_owner_actions_open_requirement ON owner_actions(requirement_key)
WHERE done = false AND requirement_key <> ''` is supported by both SQLite and Postgres. It
refuses B-1 through B-4 regardless of the write path; verified on SQLite, where a second open
`K5` raises `IntegrityError`. Before creating it, a migration must close existing open
duplicates (keep the newest, close the others as `SUPERSEDED`). Keep the guard so the common
race does not surface as an `IntegrityError`, but let the index decide.

**B-6: LOW. Postgres lock-order inversion.** The advisory lock is now taken mid-transaction, at
the first flush that inserts an owner action, after a writer may already hold row locks, for
example `ads_readiness` updating its proposal row before `s.flush()`. A writer that took the
advisory lock first (`launch.readiness`) and then touches the same rows can deadlock with it.
Postgres detects this and aborts one transaction with an error, which the job retries; it does
not hang. The lock is also held until commit, so a long transaction that flushed an owner action
early serialises the whole queue. Same-thread nested sessions would hang on Postgres, but they
would equally fail on SQLite (busy timeout), and the SQLite suites pass, so there is no evidence
of such nesting. A live Postgres test is still missing (handoff: INTEGFIX INFO-1).

---

## Test runs

Each suite was run alone with `PYTHONPATH=src:tests nice -n 19 python tests/<f>`, in a worktree
of each subject at its stated head. Python 3.13.18; dependencies from `requirements.txt`.

**PARTIAL: suite results pending at time of this push.**

Ad-hoc measurements:
- **A, real chain fixture:** sweep 1 had `changed=1`, state `blocked` with 5 blockers: search
  profile, FIRST_CUSTOMER gauge, Etsy remote state, SAMPLE_PHOTO and taxonomy. Sweep 2 had
  `changed=0` and wrote **0 rows**.
- **A-1 to A-3 and B-1 to B-5:** reproduced as described above.

## Integrator actions

1. **A:** fix A-1, A-2 and A-3 before merge. A-4 should land with them. A-5 should land with or
   after the PDF1 integration.
2. **B:** fix B-1 (no silent expunge). Add the partial unique index (B-5), with a migration that
   closes duplicates. B-2 and B-3 are then closed by the index.
3. **Both:** merge B before A, or add `_serialise_owner_queue` to `listing_package.record`.
