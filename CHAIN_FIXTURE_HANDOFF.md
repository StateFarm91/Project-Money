# Chain fixture migration checkpoint
Base 7fd49e8; implementation 8f07d25; branch codex/final-chain-fixtures-01.

Owned only test_cert_parity_copy.py and test_cert_rebuild_chain.py. No production/gate/status edits.

The parity suite used current Launch-0 build_hexagon_coaster() (default version 1.1.0) but addressed chain jobs/audits as 1.0.0. Its prior source-bound result at 624618d was 12 passing / 8 failing (root receipt 20260928T154407608215Z). The change defines CHAIN_CIR from the actual builder and derives SLUG/CIR_VERSION, then uses that version for chain job inputs, audit keys, generated-hero negative fixture, image provenance assertion, physical-photo negative control and reproduction command prefix. Independent fake frame/review/model-shot-plan/rival fixtures retain their original versions. Assertions and H no-redraw expectations remain intact.

The rebuild chain used legacy Nordic Forest (16 SC gauge). It now uses current Launch-0 builder.for_slug('cloudline-baby-blanket'), preserving the blanket premise. Tests address lifecycle/provenance, not Nordic stitch/colorwork arithmetic. The independent shaped fixture and synthetic image judge describing pine/cream/gold remain untouched. Such judge premises are not generated proof; failures remain failures.

Validation pending: root schedules parity run; rebuild awaits root PDF/chart repair to avoid repeating known renderer failure. git diff --check passed. No suite PASS claimed for this checkpoint.
