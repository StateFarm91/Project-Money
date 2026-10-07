# Wave 4 resume manifest (durable; update on every integration)

Integrator branch: claude/visual-investigation (worktree .claude/worktrees/visual-investigation). Brief: research/final_build/w4/WAVE4_BRIEF.md.
Board (dashboard feed): research/final_build/w4/COMPLETION_BOARD.json. Owner directive: stop the certification loop; finish Build 2 +
existing Final Master + Command Center + Store/SEO/product/autonomy; do NOT start the "Actually Final" extension.

## Lanes (branch claude/w4-<LANE>, worktree .claude/worktrees/W4-<LANE>, handoff research/final_build/w4/handoff_<LANE>.md)
B2, FM, AUTO, CC, PIPE, CREATIVE, MJS, STORE, SEO, VISUAL, LEARN, OWNER — launched 2026-10-06T23:56Z from fee1cfe.
Validation lane: stopped by the 2026-10-07 container restart; not restarted (owner: no automatic full-suite restarts during this wave).
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

## 2026-10-07 container restart
All lanes stopped. Uncommitted tracked work of B2/FM/OWNER was committed as WIP checkpoints (a5cdc1b, 9e9cf0d, 1ade34d).
Resumed (8, resource-limited): B2, FM, AUTO, CC, PIPE, CREATIVE, SEO, OWNER. Queued: LEARN, VISUAL, SPEND (K5a+K5b), K9.
Complete: MJS (5092b01), STORE (ba72ca8) — merged on claude/w4-INTEG, focused tests passing so far; ff into visual-investigation next.

## Model policy (owner, 2026-10-07 — FINAL; supersedes every earlier version)
- The ONLY policy: the strongest appropriate model. No Brambleloop work is ever switched to Fable because of usage limits.
- The temporary Fable fallback (recorded here earlier on 2026-10-07, commit afcc83c) was EXPLICITLY REVOKED by the owner
  (DECISION_LOG D-FB-20). Any older commit, handoff or manifest mentioning a Fable fallback is void; never resurrect it.
- If the All Models weekly allowance is exhausted: finish/checkpoint the current atomic work where practical → commit and
  push every worker branch → update every handoff, completion ledger and this manifest → stop work that cannot continue
  on the strongest appropriate model → after the reset resume from those exact checkpoints (no restart, re-audit or redo).


## Checkpoint at 98% weekly usage (2026-10-07)
Main: claude/visual-investigation @ 3219a13 (merged: MJS STORE CREATIVE B2 LEARN OWNER FM GATESI GATESB SEO SPEND SPENDA CC
PIPE2 K9 VISUAL VISUAL2-partial CHAIN RENDER PIPE3; F-416 pin; CC snapshots; decision index D-FB-19/20).
Running lanes, all pushed: AUTO b7fd8f5, PIPE 8e5f825, FM2 77d63d6, VISUAL2 1059763, CAND 766ce09, CREATIVE2 9d5fea3.
Resume after reset (D-FB-20): for each running lane, relaunch "resume from handoff_<LANE>.md on branch claude/w4-<LANE>; merge
origin/claude/visual-investigation first"; merge finished lanes; then the one validation run of the full suite on a frozen
candidate for the owner's Command Center deploy (research/final_build/w4/CC_DEPLOY_PACKAGE.md). Do not redo merged work.
