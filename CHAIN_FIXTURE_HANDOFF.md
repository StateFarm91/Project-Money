# Chain fixture migration checkpoint
Base 7fd49e8; implementation 8f07d25; branch codex/final-chain-fixtures-01.

Owned only test_cert_parity_copy.py and test_cert_rebuild_chain.py. No production/gate/status edits.

The parity suite used current Launch-0 build_hexagon_coaster() (default version 1.1.0) but addressed chain jobs/audits as 1.0.0. Its prior source-bound result at 624618d was 12 passing / 8 failing (root receipt 20260928T154407608215Z). The change defines CHAIN_CIR from the actual builder and derives SLUG/CIR_VERSION, then uses that version for chain job inputs, audit keys, generated-hero negative fixture, image provenance assertion, physical-photo negative control and reproduction command prefix. Independent fake frame/review/model-shot-plan/rival fixtures retain their original versions. Assertions and H no-redraw expectations remain intact.

The rebuild chain used legacy Nordic Forest (16 SC gauge). It now uses current Launch-0 builder.for_slug('cloudline-baby-blanket'), preserving the blanket premise. Tests address lifecycle/provenance, not Nordic stitch/colorwork arithmetic. The independent shaped fixture and synthetic image judge describing pine/cream/gold remain untouched. Such judge premises are not generated proof; failures remain failures.

Validation pending: root schedules parity run; rebuild awaits root PDF/chart repair to avoid repeating known renderer failure. git diff --check passed. No suite PASS claimed for this checkpoint.

## Source-bound parity result
20 passing / 0 failing on clean 7e1919921c40260ad1d6902303887a5f6a766bf0. Receipt 20260928T154953519722Z-test_cert_parity_copy; source fingerprint unchanged before/after; 168.5 seconds. runtime-build2 dependencies, bundled Python and Poppler DejaVuSans font; dependency lock not verified, release_eligible=false. Existing generated-product-photo refusal and model-shot-plan-only assertions passed unchanged. Thus all eight prior parity failures were resolved by correct chain version addressing without gate/threshold/assertion weakening. Rebuild still awaits integrated PDF fix and its own run.
