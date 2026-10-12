"""Brambleloop's own operating loop (v1.1 lane A: F-880..F-896, F-918, F-920, F-927, F-929/930).

The hosted runtime -- not a development session, not the owner's PC -- observes every
department, generates the next highest-value safe work for any that is idle, executes it
through the ordinary worker, measures the outcome and persists what it learned.

  charters      the eleven departments: mission, authority, KPIs with anti-gaming guards
  generators    evidence-driven candidates (handoff > overdue cadence > self-review)
  orchestrator  the Executive Orchestrator tick and the idle-queue wake
  kpis          department KPIs, VOID on a tripped guardrail, UNKNOWN never 0
  memory        keyed company memory + company timeline (idempotent writes)
  handlers      autonomy.orchestrate / autonomy.department_review / autonomy.morning_handoff
  status        summary(db) / timeline(db, limit) for the Owner Command Center
  map           the autonomy map, generated from the code that is actually wired
"""
