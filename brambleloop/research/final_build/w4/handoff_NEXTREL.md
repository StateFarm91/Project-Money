# W4-NEXTREL handoff: next-release integration branch

Branch `claude/w4-NEXTREL` (worktree `.claude/worktrees/W4-NEXTREL`), based on c131f07
(`c131f072b3eb4a9f31fa290c69fd33e8434cf267`). Date 2026-10-11 UTC.

This is an integration branch, not a frozen candidate. No full suite has been run on it, and it
has no release record. Nothing was deployed, and nothing was written to Railway or Etsy.

## Merged lanes

| lane | how | commits | notes |
|---|---|---|---|
| `claude/w4-AUDITFIX` e0fe1da | `--no-ff` merge, clean | merge 3200469 | Re-audit fixes D-1 (non-finite model ceiling), L-1 (TOTP), L-2 (login throttle lock) and L-3 (migrate index creation). Based on 7421ef6. |
| `claude/w4-FMEND` own commits | cherry-pick `-x` of 578dc4c, fc7cf04 and 8cef206, all clean | fae59a1, e3177ae, 3a633be | Brings in the F-878 operator GET `/api/launch/packet`, `scripts/emit_runtime_packets.py`, the shadow-rehearsal owner-phase-transition fix, and the c131f07 evidence. FMEND's merge of w4-PACKETREL was **deliberately left out**: none of the FMEND code needs PACKETREL's `src/` changes. NEXTREL's `launch/packet.py` is therefore c131f07's version. |
| `claude/w4-CCGAP` 15a2380 (head) | two `--no-ff` merges (c7fdd2d, then the head), both clean | ebff6f1, 9355982 | Includes **the PDFium crash lock**, which is release-critical: the web process aborted or segfaulted under concurrent CC reads. Also includes the honest CC cards, the phone overflow fixes, per-card timestamps and the CC gap report. |

**Not merged:**

- `claude/w4-RELFIX`, which is pending an owner decision.
- PACKETREL's `src/` changes.
- CCGAP's later work and LAUNCHREADY, which come next.

## Code delta compared with c131f07

`src/` changes:

- `app/command_center/` (from AUDITFIX and CCGAP): `api.py`, `auth.py`, `tabs.py`, `company.py`,
  `ask.py`, `emergency.py`, plus static JS and CSS.
- `app/main.py` and `app/security.py` (FMEND route).
- `core/migrate.py`, `gateway/anthropic.py` and `runtime/growth_ops.py` (AUDITFIX).
- `visual/contents_frame.py` (CCGAP, the PDFium lock).

Outside `src/`: `scripts/shadow_rehearsal.py` and `scripts/emit_runtime_packets.py`.

## Focused test results

Each test ran as its own process, one at a time, with a private TMPDIR.

**Round 1** (after AUDITFIX + FMEND):

| test | result |
|---|---|
| test_w4_auditfix_cc_auth | 9/9 |
| test_w4_auditfix_ceiling | 6 OK, 0 failing |
| test_w4_auditfix_migrate | 2 OK, 0 failing |
| test_w4_fmend_packet_route | 4/4 |
| test_w4_fmend_packets | 3/3 |
| test_w4_fmend_rehearsal_phase | 5/5 |
| test_shadow_rehearsal (fast mode) | 5/5 |
| test_route_auth_default_deny | 7/7 |
| test_web_security | 11/11 |
| test_v11_cc_auth | 16/16 |
| test_gateway | exit 0 (30 OK) |
| test_platform | exit 0 (22 OK) |
| **test_cert_claude_independence** | **3/4: FAIL**, see below |
| test_compiler, test_reverse, test_twin | exit 0 |

**Round 2** (after the CCGAP c7fdd2d merge):

| test | result |
|---|---|
| test_w4_ccgap_pdfium | pass, exit 0 |
| test_w4_ccgap_views | pass, exit 0 |
| test_w4_visual2 | 8/8 |
| test_w4_cc_company | 23/23 |
| test_w4_ccfin | 9/9 |
| test_v11_reliability_slo | exit 0 (26 OK) |
| test_w4_ccpacket | 5/5 |
| test_w4_auditfix_cc_auth | 9/9 |
| test_v11_cc_auth | 16/16 |
| test_w4_fmend_packet_route | 4/4 |
| test_route_auth_default_deny | 7/7 |
| test_web_security | 11/11 |
| core three | exit 0 |

**Round 3** (after the CCGAP head 15a2380):

| test | result |
|---|---|
| test_w4_ccgap_views | 10/10 |
| test_w4_ccgap_pdfium | 2/2 |
| test_v11_pwa_static | 81 passed, 0 failed |
| test_v11_cc_views | 13/13 |
| test_v11_cc_auth | 16/16 |
| test_w4_auditfix_cc_auth | 9/9 |
| test_w4_cc_company | 23/23 |
| test_route_auth_default_deny | 7/7 |

## Failing test: inherited from c131f07, not caused by these merges

`test_cert_claude_independence::test_the_deployed_image_and_start_command_carry_no_session_state`
fails with:

```
AssertionError: ('.../brambleloop/release/suite_runs/20261010T062725Z-14513.log', '.claude')
```

The committed suite log for 3967f40 contains `.claude/worktrees/...` checkout paths. That file
is in c131f07's tree unchanged (blob 878b1c46), so **the same test fails on c131f07**. The full
suite running on c131f07 should therefore show this failure too.

The fix is `claude/w4-RELFIX` 4285683: the release record strips checkout paths. That branch is
pending an owner decision, so it was not merged and the test was not edited. A new release
record produced with the RELFIX behaviour would clear it.

## Remaining before NEXTREL can be a candidate

1. Merge the CCGAP follow-ups and LAUNCHREADY (coordinator).
2. Get the owner decision on RELFIX, then merge it or otherwise resolve the release-log path
   leak.
3. Run `REQUIRE_CLEAN=1 ./run_tests.sh` on the final head, then write the release record and
   freeze.
4. Re-run `scripts/shadow_rehearsal.py`, `scripts/launch_packet.py`, the packet emitter and
   `final_proof` on the frozen SHA.
