# W4-RESEARCH: research tasks, unknown detection, claim classes, reproducibility, expiry

Branch `claude/w4-RESEARCH` from `origin/claude/w4-INTEG2` 85ec5d0. Rows: F-403, F-409, F-424, F-431, F-433.

## Changes
- New `src/brambleloop/intel/research.py`, with the `research_tasks` table. Each task records:
  - its question, the trigger that raised it, a dedupe key, `decision_ref` and domain;
  - `query_terms` and the **internal evidence searched first** (matching lessons and observations);
  - its sources, each with a retrieval class (fetched / search_summary / repository / rendered_image /
    internal) and the date read;
  - its findings, each labelled `fact | source_claim | inference | hypothesis | unresolved`;
  - a stop condition and a spend bound (default CA$0: the module spends nothing);
  - its outcome, `answered_at` and `expires_on`.
- Rules enforced in code:
  - a `fact` needs a fetched, repository, rendered-image or internal source; a search summary supports
    only a `source_claim`;
  - a `source_claim` or `inference` must name what it rests on;
  - a task closes only with a fact or an explicit `unresolved` finding;
  - a task without a decision is refused;
  - an unknown freshness domain is refused (no default expiry).
- **F-433:** `expires_on` comes from the learning domain's `fresh_for_days` (marketplace policy 21 d,
  techniques 365 d, ...) or from the improvement world speeds (market 72 h → 3 d). Mathematical findings
  never expire on a date. `expire_due()` marks a task EXPIRED and re-opens its question once.
- **F-403:** `detect_unknowns()` turns learning domains nobody has observed, and children's-safety
  constraints whose primary page was not fetched (`childrens.unfetched_sources()`), into research
  questions. It is idempotent per trigger. It is wired into the hourly `learn.scan` handler, together
  with `expire_due`, and failures there are reported beside the scan, never fatal.
- **F-409 / F-424:** `learning.record` takes `claim_class` (default `source_claim`), `query_terms` and
  `decision_ref`, stored in `detail`. `observations()` returns them, and rows written before this change
  read `unresolved`, not a class nobody assigned.
- `research_tasks` is registered in `create_all` and `continuity.NON_REDERIVABLE`.

## Scope note (F-431)
The board text asks for a `research.run` job type. Adding a job type touches six registries: the agent
allowlist, charters, the authority classes, the swarm bands, the pipeline work keys and the autonomy map.
For now the research step runs inside the existing GREEN `learn.scan` cadence, which is hourly and spends
nothing. A dedicated `research.run` job type with an external-fetch step is the remaining half of F-431.
F-431 is therefore **advanced, not closed**.

## Acceptance evidence (testslot)
`tests/test_w4_research.py` (10 tests):
- unknowns open questions once;
- an observed domain is no longer an unknown;
- internal evidence is searched first;
- claim classes are enforced;
- claims and guesses cannot close a task;
- expiry follows the domain, mathematical findings never expire, and expired questions re-open;
- a task needs a decision and spends nothing by default;
- observations carry their class, terms and decision;
- `learn.scan` routes unknowns;
- the table is non-rederivable.

Regression suites green: test_learn_launch, test_w3_k10_learn, test_w4_learn_presale, test_v11_wiring,
test_childrens.

## Board rows advanced
F-403, F-409, F-424 and F-433 move to implemented and tested on this branch. F-431 is partial: the core
is built and wired through `learn.scan`; the dedicated job type and the fetch step remain.
