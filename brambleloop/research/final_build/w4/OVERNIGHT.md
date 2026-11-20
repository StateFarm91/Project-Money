# W4-OVERNIGHT: F-895 overnight-autonomy grading, ready before the deploy

Branch `claude/w4-OVERNIGHT` from `origin/claude/w4-INTEG2` 85ec5d0. Row: F-895 (launch-critical,
`release_not_deployed`). Nothing is deployed and nothing is written to production.

## What it is
`src/brambleloop/ops/overnight_grade.py` grades one unattended night. It reuses `ops.slo`'s own
pieces: the department map, `runtime.pipeline.did_no_work`, `CADENCES`, the self-observing exclusions
and `INTERACTIVE_ACTORS`.

**Proof mode** is `grade_db(db, start, end, commit=)` and reads durable rows. It has these criteria:
- the window ended and lasted at least 6 h;
- no interactive actor appears in the audit log;
- a cadence job was created in every hour;
- the named build ran the night (checked only when a commit is named);
- each expected department has at least one *useful* finished job, listed per department;
- at least 3 departments did useful work;
- no P0 or P1 incident was opened.

The verdict is FAIL if any criterion fails, INCOMPLETE if any is UNKNOWN, and PASS otherwise.

**Pre-check mode** is `grade_public(fetch, base, ...)`. It uses public GETs only: `/api/status`,
`/api/audit`, `/api/swarm/runtime`. It counts completions per department. Public rows carry no outputs,
so usefulness is UNKNOWN and the verdict is never better than INCOMPLETE.

## Run it straight after the next deploy
Choose the night in UTC, for example 02:00Z to 10:00Z on the morning after the deploy.

Public pre-check (anyone, no credentials):

    cd brambleloop && PYTHONPATH=src python -m brambleloop.ops.overnight_grade \
      --public https://brambleloop-os-production.up.railway.app \
      --start 2026-10-13T02:00:00Z --end 2026-10-13T10:00:00Z --commit <deployed sha> --markdown

Proof (run where the production database is reachable, for example the Railway shell; it only reads):

    PYTHONPATH=src python -m brambleloop.ops.overnight_grade --db "$DATABASE_URL" \
      --start 2026-10-13T02:00:00Z --end 2026-10-13T10:00:00Z --commit <deployed sha> --markdown

The command exits 0 only on PASS. Paste the markdown table into the board evidence for F-895.

## Acceptance evidence
`tests/test_w4_overnight_grade.py` covers:
- an unattended useful night passes, with every department named and its example job;
- a department that ran but did nothing fails by name;
- an attended night fails;
- a scheduler gap fails, and so does a P1 incident;
- an empty night is not PASS, a short window fails, and a future window is refused;
- the named build is checked;
- the public pre-check counts completions, stays INCOMPLETE and calls only `/api/` GETs.

Results are in the commit message.

## Board row
F-895 moves from "no grading tool" to "grading tool ready". It stays blocked on the deploy plus one
unattended night. Only a PASS from `grade_db` closes it.
