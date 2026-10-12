# handoff W4-FMLEDGER (Final Master launch-critical ledger on the RC line)

- Branch `claude/w4-FMLEDGER`, starting from `claude/w4-SHADOWFIX` 56d7b38. SHADOWFIX 3d755dd is
  merged in as 2f36fe0. Latest pushed SHA: `git log -1 origin/claude/w4-FMLEDGER`.
- Status: COMPLETE. Launch-critical OPEN went from 15 to 9. Ledger: `FM_LEDGER_2026-10-10.md`.
- Rows: F-514, F-098, F-310 and F-659 are COMPLETE. F-030 and F-254 are GATED on owner
  `visual_paid_generation`. F-839, F-848 and F-878 were refreshed and stay OPEN as END-STAGE rows.
- Code: `runtime/release.py` now adopts F-659 checkpoints in `handle_model_photography` and
  `handle_seasonal_cycle_proof`. Test: `tests/test_w4_fml_checkpoint_adoption.py`.
- WIRING REQUEST (CC lane), F-878: serve `launch.packet.build(db, sha=build.commit())` on an
  operator-gated GET listed in `security.OPERATOR_GET_ROUTES`.
- Next: the integrator freezes the RC (F-845). The other 8 END-STAGE rows close on that SHA, as
  listed in the ledger table.
- Re-run: `python3 research/final_build/w4/close_fml.py --plan|--apply && python3 research/final_build/aggregate.py`
