# A6 continuation for independent review

Source: `opus2/a6-codex-contract` at `594d5e384262975d9b321d50414253cd071765c1`;
merged with `codex/p0-learning-reference` at `1ae00eb390b8ba586429aa6a504d121c6b0dcf7f` on this isolated Codex branch. The generated autonomy map was regenerated after the merge. Neither source branch was changed. Main retains integration and deployment authority.

Drafting selects the evaluated, approved finishing rule for the actual CIR construction family using `applicable_to_cir`, freezes it and records the exact pin. A correctable failed draft with no pin can freeze the approved applicable rule during `cir.revise`; an existing pin must verify and is kept exactly as it was. A stale pin stops revision. All ordinary compile, certificate, release, quality and PDF checks continue to apply. No production review or physical evidence is invented.

The inherited legacy lesson-consumer allowed an independently approved lesson to mutate construction or yarn without the evaluated DesignRule contract, including where image and physical stages remain UNKNOWN. Those legacy positive changes are held; safety holds still work. `test_w5_a6_learning_to_design.py` contains assertions expecting legacy-only construction/yarn effects and will require a reviewed replacement acceptance path once a construction rule has qualifying evidence. No construction rule has been approved here. This is a deliberate fail-closed behavior, not a claim that the construction-learning acceptance criterion is complete.

The frozen-knowledge regression keeps audit-referenced jobs and runs the authorized `quality_director` certificate handler, checks the job reached DONE and actually granted, and checks the exact pinned CIR was persisted before the asset handler runs. It compares the rendered writer body against the baseline, covers a family-scoped approved rule and wrong-family refusal, and exercises revision and retired-pin refusal. The test's private benchmark fixtures are synthetic/pinned research fixtures, not physical outcomes or provider calls.

The inherited draft hook does not automatically rewrite existing engineered catalogue versions: certified releases remain immutable and a changed design needs a distinct new release version followed by recertification and downstream gates. The new construction evidence and owner authority are still needed. A6 merged with Learning must be independently reviewed, then tested against the selected integration branch and its A1/A2/A4/A5 changes. The `claude/w6-INTEG1` target is not currently present; do not merge or deploy from this branch.

## Verification

Python 3.11 with a private local benchmark fixture: `test_w5_a6_frozen_knowledge.py` 5/5; `test_codex_knowledge_contract.py` 4/4; `test_codex_learning_http_e2e.py` 1/1; `test_w4_agents.py` 14/14. `test_w5_a6_learning_to_design.py` 4/6: its unchanged positive-effect legacy construction and yarn tests fail because those unevaluated mutation paths are deliberately held. The negative/unapproved, named-construction, conflict and hold tests pass. The two failures remain open for an independently approved construction/material rule and a reviewed acceptance update; they must not be described as a passing suite.

## Visual boundary follow-up

Every `visual.image_production` stage re-checks a stored CIR's frozen knowledge before resolving a generator or scheduling the next stage. Owner gallery publication approval, gallery persistence, and candidate re-verification also refuse when the stored pin no longer verifies. Legacy releases with no pins retain their existing behavior; publication and experiment controls still apply. A real-worker regression retires an approved rule and verifies the queued visual job, gallery approval, gallery persistence and image re-verification all refuse before work. No paid generator is called. Python 3.11 visual regressions: `test_w4_visnext_frames.py` 7/7 and `test_w4_visnext.py` 21/21.
