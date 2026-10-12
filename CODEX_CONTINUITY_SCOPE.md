# Continuity cleanup scope
Base436568f. Branch codex/final-continuity-01. Defect: scratch SQLite engine in core.continuity.prove_restore retains pooled connections past caller work_dir cleanup, causing WinError32 and masking restore failures.
Own only core/continuity.py, new tests/test_continuity_cleanup.py, this scope/handoff. Root owns Windows event-loop network harness repair. No H changes.
Acceptance: scratch engine disposed on successful proof, returned restore-failure proof, and raised round-trip export failure; scratch file/directory deletable immediately; caller-owned source remains usable. Existing continuity suite must retain all hash/credential/retention assertions.
Runtime entry ops.continuity->handle_continuity->prove_restore->export/restore/hash proof->retain/audit->workspace cleanup. No threshold/status change; no network/production action.
