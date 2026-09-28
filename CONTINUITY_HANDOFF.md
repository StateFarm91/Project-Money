# Continuity cleanup handoff
Base436568f; branch codex/final-continuity-01. Defect Windows WinError32 on temporary restored SQLite database, leaving ops.continuity failed despite completed proof or masking an injected restore/export failure.

Reproduction before repair: new real-file tests0/3, all WinError32 during work-dir cleanup. Scratch session contexts close transactions but return connections to SQLAlchemy pool; retained pooled handle blocks unlink on Windows.
Repair: core.continuity.prove_restore owns scratch Database and now disposes that engine in finally across success, restore exception returned as failed proof, and roundtrip export exception. Caller-owned source engine remains untouched. No restore/hash thresholds modified.
Runtime: scheduled ops.continuity -> runtime.release.handle_continuity -> core.continuity.prove_restore -> scratch export/restore/hash proof -> retained archive and audit -> workspace cleanup. Existing tests cover retained archive/restore; new tests cover scratch-handle lifetime and original error preservation.
Validation: new tests/test_continuity_cleanup.py3/3 PASS after fix, existing tests/test_continuity.py15/15 PASS unchanged. Tests use real SQLite files, assert disposed pool empty and immediate unlink, then query source. No global Windows skip or weakened assertion. No heavy/full suite run.
Environment: Windows bundledPython, existing runtime-build2 injected on sys.path. No new dependencies/network calls, no deploy or production mutation.
Files: core/continuity.py; newtest; CODEX_CONTINUITY_SCOPE.md; thishandoff. H and network harness untouched. Ready for coordinator review/integration and centrally scheduled clean cert_wiring rerun.
