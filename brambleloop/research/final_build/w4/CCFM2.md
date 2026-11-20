# W4-CCFM2: Command Center completion, batch 2 (F-661, F-668, F-729; F-653 evidence; F-660 not CC)

Branch `claude/w4-CCFM2`, based on `origin/claude/w4-INTEG2` at 85ec5d0. The work is read-only. All figures come from durable tables, and UNKNOWN is never shown as 0.

The rows are, in board order after CCFM1, the Final Master entries marked `post_launch` / `blocked_engineering` with `app/*` modules. The new code is in `app/command_center/executive.py`. It is wired into the Home, Autonomy & Learn and Operations tabs.

## Rows

| Row | Ledger reason at 85ec5d0 | Change | Evidence |
|---|---|---|---|
| **F-661** Executive Command Center | Missing: today/month/90-day objective, profit, conversion, live listings, customer risk. | Added `executive(db)` to Home as "Executive: today, month, 90 days". It shows:<br>• **Revenue for today, the month and 90 days.** Only measured, reconciled, countable sale rows count (the A3-09 predicate, `dashboard_truth._reconciled_measured`). The order source must also be measured; until then each window reads **UNMEASURED**.<br>• **Profit** (all time, from the accountant section).<br>• **Conversion: UNKNOWN.** Etsy shop stats are not read, so there is no visits reading.<br>• **Live listings:** recorded `active` rows with an Etsy id, shown beside the drafted count.<br>• **Customer risk:** open P0/P1 incidents plus escalated support cases awaiting a reply. | `test_w4_ccfm2::test_executive_is_unmeasured_until_the_order_source_is_read`<br>`::test_revenue_windows_sum_only_reconciled_measured_sales_when_measured` (unreconciled and estimated rows are never counted) |
| **F-668** Agents Workspace | No current work, heartbeat, cost, completions or failures per agent. | Added `agents_workspace(db)` to Autonomy & Learn. It has one row per registered agent with:<br>• department, from the charter;<br>• state (active / idle / disabled / UNKNOWN when it never ran);<br>• current job;<br>• completed and failed jobs in 24 h;<br>• spend today against the daily ceiling (`spend_report.per_agent_today`, where a CA$0 ceiling is a permission of 0);<br>• spenders with no agent row. | `::test_agents_workspace_columns_equal_sql` |
| **F-729** Autonomy Health in Command Center | Missing: autonomous operating hours, WATCHING agents, oldest ready work, owner-blocked work counts. | Added `autonomy_health(db)` to Operations. It reports:<br>• hours with completed work in the last 24 h;<br>• the oldest ready job (pending with `run_after <= now`), with the ready count;<br>• open owner decisions;<br>• agent states (active / watching = asleep with a scheduled wake / blocked / unknown).<br>With no job ever recorded, every value is UNKNOWN rather than 0. | `::test_autonomy_health_reads_hours_oldest_ready_owner_blocked_and_states` |
| **F-653** Galaxy Access | No responsive or touch-optimised owner view, no narrow-width render test. | **Evidence only, no code.** The Command Center is phone-first. `cc_mock/check.mjs` renders every tab at 390×844 and asserts no horizontal scroll and tap targets of at least 44 px. W4-CCUX added collapsible long pages, the More breadcrumb and Decide-first. Home is the compact owner view: health, owner decisions and today's numbers. | `tests/test_v11_pwa_browser.py` → `check.mjs` (390 px per tab), `tests/test_w4_ccux.py` |
| F-660 Elastic Capacity | No runtime burst-capacity path. | **Not taken.** This is runtime and infrastructure work (worker processes, finance ceilings), not Command Center work. | — |

All three blocks are also listed in `tabs.home` / `tabs.autonomy` / `tabs.operations`, and the views give them explicit titles (`::test_tabs_carry_the_new_blocks`).

## Test status

- `tests/test_w4_ccfm2.py` runs through `/home/user/bl-runs/testslot.sh`.
- The cc_mock browser check waits until slots N ≥ 3. The blocks render through the generic envelope renderer that the existing per-tab 390 px checks already cover.
