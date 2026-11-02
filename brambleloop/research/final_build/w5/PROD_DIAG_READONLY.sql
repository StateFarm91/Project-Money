-- Brambleloop production diagnostic: STRICTLY READ-ONLY. 2026-11-02, release 0967c3ee.
-- Paste the whole file into Railway -> Postgres -> Data/Query (or psql) and run it once.
-- The transaction is opened READ ONLY, so Postgres itself refuses any write, and it ends in
-- ROLLBACK. It returns job types, counts, timestamps and error-class text only: no customer
-- data, no tokens, no secrets. Copy the result tables back to the integrator.
--
-- It answers:
--   Q1. what dead-lettered after the deploy (no_unexpected_dead_letters_in_24h);
--   Q2. which job held the worker 03:40-03:56Z (worker_is_alive false at 03:45-03:48Z);
--   Q3. publishing_halt_clear;
--   Q4. stale_artefacts_rebuilding;
--   Q5. no_repeated_paid_call_in_24h;
--   Q6. weekly_jobs_completing.

BEGIN TRANSACTION READ ONLY;

-- Q1 dead letters, last 24 h
SELECT id, job_type, agent, attempts, max_attempts, created_at, started_at, finished_at,
       left(last_error, 400) AS last_error
FROM jobs
WHERE upper(status) = 'DEAD' AND coalesce(finished_at, created_at) > now() - interval '24 hours'
ORDER BY coalesce(finished_at, created_at) DESC;

-- Q2 jobs that ran across the worker stall (2026-11-02 03:28-03:58Z), longest first
SELECT id, job_type, upper(status) AS status, attempts, started_at, finished_at,
       round(extract(epoch FROM (coalesce(finished_at, now()) - started_at))::numeric, 1) AS seconds,
       left(last_error, 200) AS last_error
FROM jobs
WHERE started_at < timestamptz '2026-11-02 03:58:00+00'
  AND coalesce(finished_at, now()) > timestamptz '2026-11-02 03:28:00+00'
ORDER BY seconds DESC NULLS LAST
LIMIT 25;

-- Q3 publishing halt: newest truth sweep and its systemic reading; open systemic / halting incidents
SELECT at, left(detail::text, 600) AS truth_sweep_detail
FROM audit_log WHERE action = 'ops.truth.sweep' ORDER BY id DESC LIMIT 1;
SELECT id, at, severity, signature, product_slug, left(summary, 200) AS summary
FROM incidents
WHERE resolved = false AND (halts_publication = true OR signature = 'systemic-halt:publication')
ORDER BY at DESC LIMIT 30;

-- Q4 stale artefacts: newest sentinel; open stale-artefact incidents; chain.rebuild outcomes, 7 days
SELECT at, left(detail::text, 600) AS sentinel_detail
FROM audit_log WHERE action = 'ops.sentinel' ORDER BY id DESC LIMIT 1;
SELECT count(*) AS open_stale_incidents, min(at) AS oldest
FROM incidents WHERE resolved = false AND signature LIKE 'stale-artefact:%';
SELECT upper(status) AS status, count(*), min(created_at) AS oldest, max(finished_at) AS newest_finished
FROM jobs WHERE job_type = 'chain.rebuild' AND created_at > now() - interval '7 days'
GROUP BY 1 ORDER BY 1;
SELECT action, count(*), max(at) AS newest
FROM audit_log
WHERE action IN ('chain.rebuild_completed', 'chain.rebuild_unbound', 'ops.rebuild_propagated')
  AND at > now() - interval '7 days'
GROUP BY 1;

-- Q5 paid calls: intents in 7 days; billed requests repeated in 24 h (effect + fingerprint)
SELECT count(*) AS intents_7d,
       count(*) FILTER (WHERE at > now() - interval '24 hours') AS intents_24h
FROM paid_call_records WHERE at > now() - interval '7 days';
SELECT effect, left(fingerprint, 12) AS fingerprint, count(*) AS billed_calls,
       string_agg(DISTINCT job_type, ',') AS job_types, min(at) AS first_at, max(at) AS last_at
FROM paid_call_records
WHERE at > now() - interval '24 hours'
  AND (outcome IN ('OK', 'FAILED_BILLED', 'UNCERTAIN') OR orphan_billed)
GROUP BY effect, fingerprint HAVING count(*) > 1
ORDER BY billed_calls DESC LIMIT 20;

-- Q6 weekly job
SELECT id, upper(status) AS status, attempts, created_at, finished_at, left(last_error, 200) AS last_error
FROM jobs WHERE job_type = 'improve.weekly' ORDER BY id DESC LIMIT 5;

ROLLBACK;
