# test_cert_wiring timing on listings candidate d69a3ec (W-INTEG5, 2026-10-21)

Method: INTEG4's `time_handlers.py`, unchanged except that it prints the top 80 job types instead of
25. Every run was solo on a quiet machine (load below 1, no other suite running). No repository code
and no limit were changed.

| run | tree | result |
|---|---|---|
| quiet_…T1539Z_cand_d69a3ec | candidate d69a3ec | 12/16; "did not drain: 272 jobs in 1200s"; handler total 1533 s over 265 jobs |
| quiet_…T1606Z_prod_b931d17 | **b931d17**, the production before 15800536 (git archive) | **11/16; "did not drain: 268 jobs in 1258s"**; handler total 1429 s |
| measure_uncapped_…_cand_d69a3ec | candidate, measured with a **scratch copy** of the test (`measure_copy_of_test_cert_wiring.py`): `max_seconds` set to 7200 and the drain time printed | **full drain: 293 jobs in 1220.2 s**; 15/16. The one failure is the copy's own path artefact (ROOT points at scratch), not a drain problem |
| INTEG4 baseline (2026-10-21T0005Z) | b997efd / b931d17 | 16/16 in 844 s / 825 s |

**Findings**

1. **The cause is not LISTREADY's code. The same production code (b931d17) now fails the same drain
   on this machine.** It passed 16/16 in 825 s at 00:05Z today.
2. **The handlers themselves are slower.** Handlers whose code is identical in all trees take about
   1.5-1.8x longer than in the morning baseline. For example, assets.build: 238.7 s for b997efd at
   00:05Z, against 415.8 s for b931d17 and 385.1 s for d69a3ec now; listing.seo 110 s against 182 s
   and 175 s; store.publish 86 s against 135 s and 137 s. That is consistent with a slower host after
   the container restarts, not with added work.
3. **`visual.rnd.cycle` now runs twice in the drain in both trees** (2 jobs, 418-485 s), where the
   baseline ran it once (184 s). It is the same in production and the candidate, and plausibly depends
   on the clock or the date, because the drain fast-forwards deferred jobs. It is worth checking for
   hermeticity, but it is not added by this release.
4. **The candidate adds almost nothing to production today.**
   - `visual.image_production`: 23 jobs, 28 s. It came from INTEG4/b997efd and was already accepted.
   - `ops.maturity_disagreements`: +41 s.
   - **The coordinator's guess is refuted.** LISTREADY's `seed_launch0`, `retry_halted`, launch-review
     and storefront jobs, and the draft/compile/certify chain, do not appear as distinct heavy job
     types. `cir.draft` is 12 jobs in 0.2 s; `gate.*` and `chain.rebuild` are under 3 s.
5. **Legitimacy.** Every timed job is a registered handler that the test deliberately drains; no
   handler waits on a provider, a timeout or a retry sleep. The only questionable item is the second
   `visual.rnd.cycle` (finding 3).

**The smallest justified limit, if raising it is the owner's ruling:**
- Measured full drain: 1220 s.
- Margin: +25%, for `visual.rnd.cycle`'s observed run-to-run spread (178-298 s per cycle) and for
  JOBS=3 contention in the full suite (about +3% in INTEG4's data).
- Result: **about 1525 s**.

The alternative is to keep 1200 s and remove the clock-dependent second `visual.rnd.cycle` from the
hermetic drain. That needs a root cause first.
