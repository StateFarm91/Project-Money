# W4-PRODFIX: disposition of the independent review (INDEPENDENT_SECREVIEW_PRODFIX.md)

| Finding | Disposition |
|---|---|
| **F1 (HIGH)** retry reused the stage token | **Fixed.** A sentinel retry carries `retry` (its own daily key). `_targeted_rebuild` folds that key into the stage token, so every stage key moves once per retry and stays stable within the retry. The end-to-end test is on the real chain (`test_w4_prodfix_review`): the first attempt is refused, then the retry gets a new `pricing.position` job and bound `chain.rebuild_completed` evidence. It fails on cbb01777. |
| F2 give-up too broad | **Fixed.** Only a paid answer that does not parse is given up at once. A refusal to record (for example, the provider not visible) keeps its counted retries. Keying the failed count by `method_version()` is not done; it is recorded as a follow-up. |
| F3 prefix match | **Fixed.** The waiver compares against `incident_lifecycle.SYSTEMIC_SIGNATURE` exactly. |
| F4 one integrity family | **Accepted for SHADOW.** Before LIMITED PRODUCTION, review whether checksum, ledger or manifest mismatch families should join `INTEGRITY_FAMILIES`. Only drafts are affected. |
| F5 read-time race | **Fixed.** The evidence and the incident list are read in one session (`_halting_other_than_staleness`). |
| F6 full-table scan | **Fixed.** One bounded query per sentinel run: rows in flight, plus rows that ended or were created inside `RETRY_AFTER`. |
| F7 coverage and probe audit | **Fixed.** The new tests drive `analyse()` and the real chain. `ops.capability_probes` now audits `reused` and `probe_at`. |
| F8 review/snapshot binding | **Fixed.** `review_change(..., snapshot_id=)` refuses if a newer change arrived, checking and writing in one session. The action maps this to "approval preview changed". |
| F9 case-insensitive confirmation | **Fixed.** The confirmation is now matched exactly ("REVIEWED AND TESTED" is refused; there is a test). |
| Environment note (`httpx2`/test lock) | Not addressed here. The HTTP suites were run in `venv-integ4`. A committed test lock is an integrator item. |
