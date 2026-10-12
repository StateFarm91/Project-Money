# W4-CCALL: Command Center completion, consolidated (CCREL + CCGAP2 + CCFM1 + CCFM2 + CCGROW)

Branch `claude/w4-CCALL` from `origin/claude/w4-INTEG2` @ 85ec5d0. The five worker branches are merged in with merge commits:

- **CCREL and CCGAP2** merged cleanly.
- **CCFM1** conflicted in `cc_mock/check.mjs` and `css/app.css`. Both conflicts were additions at the same anchor; the fix keeps both sides, and `node --check` passes.
- **CCFM2 and CCGROW** merged cleanly.

Nothing here deploys or writes to production or Etsy. Phase stays shadow, and UNKNOWN is never shown as 0.

| Part | Rows / items | Detail |
|---|---|---|
| CCFM1 | F-619, F-621, F-651, F-652, F-670 (F-620 blocked on F-614/F-610) | `CCFM1.md` |
| CCFM2 | F-661, F-668, F-729 (F-653 evidence; F-660 is runtime, not CC) | `CCFM2.md` |
| CCREL | Queue item 2: Approvals release card, Etsy Connect end to end in the mock, Laura CEO briefing view | `CCREL.md` |
| CCGAP2 | Queue item 3: CC_GAP FU-7 (reasons derived from the card's items), FU-5 (Laura "Needs you" equals the Approvals count) | `CCGAP2.md` |
| CCGROW | F-504, F-126 (experiment part); other growth/brand rows triaged as gated or not this domain | `CCGROW.md` |

Not taken, with reasons:

- **F-453.** The deploy and production window belong to the integrator.
- **F-622.** Needs real buyers.
- **F-873.** Needs an owner ruling.
- **F-680 and F-748.** These are visual evidence panels in the image domain. `/cc/image-review` already exists.

## Test results on CCALL

All runs go through `/home/user/bl-runs/testslot.sh`. Results are filled in below as they finish.
