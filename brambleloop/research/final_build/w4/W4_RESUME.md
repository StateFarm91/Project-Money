# Wave 4 resume manifest (durable; update on every integration)

Integrator branch: claude/visual-investigation (worktree .claude/worktrees/visual-investigation). Brief: research/final_build/w4/WAVE4_BRIEF.md.
Board (dashboard feed): research/final_build/w4/COMPLETION_BOARD.json. Owner directive: stop the certification loop; finish Build 2 +
existing Final Master + Command Center + Store/SEO/product/autonomy; do NOT start the "Actually Final" extension.

## Lanes (branch claude/w4-<LANE>, worktree .claude/worktrees/W4-<LANE>, handoff research/final_build/w4/handoff_<LANE>.md)
B2, FM, AUTO, CC, PIPE, CREATIVE, MJS, STORE, SEO, VISUAL, LEARN, OWNER — launched 2026-10-06T23:56Z from fee1cfe.
Validation lane: full suite on 94f99ad (log /home/user/bl-runs/full_94f99ad.log) — bounded; no further serial full-suite cycles
until a release candidate is intended.

## Integration loop
On each lane report: review diff → focused + affected tests (TMPDIR private) → merge --no-ff → push → refill the slot from
B2_OPEN_CLUSTERS.json / FM_OPEN_CLUSTERS.json / lane next-steps. Update COMPLETION_BOARD.json + this file.

## Resume after a session reset
1. git -C /home/user/Project-Money fetch origin; for each lane branch compare origin vs local; read its handoff_<LANE>.md.
2. Relaunch any lane whose handoff is not COMPLETE with: "resume from handoff_<LANE>.md on your branch; obey WAVE4_BRIEF.md".
3. Stopping condition: Build 2 executable OPEN = 0; existing Final Master executable OPEN = 0; Command Center ready for safe
   hosted deployment (owner-controlled); autonomy proven to generate useful work without prompts; real multi-product pipeline;
   store/search/SEO materially advanced; remaining non-PROVEN rows genuinely owner/data/external gated.
