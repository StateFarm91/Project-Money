# Review request — eng/product-run-perf

**Branch:** `eng/product-run-perf`, cut from `claude/batch19c-etsy` (2026-11-21). Not merged,
not deployed, no PR. Test-only change: no file under `src/` changed, so production behaviour
is unchanged.

**Brief:** `tests/test_product_run.py` (36 tests) never finished inside a release window.
Profile it, fix the cause without weakening any test, run the whole suite, and report.

**Note:** the brief cites DECISION_LOG entry `D-MAIN-19B-PRODUCT-RUN-INCOMPLETE`. No entry
with that name, or containing `PRODUCT-RUN`, exists in `brambleloop/DECISION_LOG.md` on this
branch. This work went ahead from the brief alone.

## Result

**36 passed, 0 failed. The whole file ran in 1544 s (25.7 min) on a 4-CPU host**, with other
processes using the CPU at the same time. Run record: `/tmp/claude-0/prof/suite2.log`, which is
transcribed below because the container is ephemeral.

## Profile (step 1)

I ran cProfile over the first three tests in file order. Those three share one cached
unattended cycle (`_run_once`), so the cycle is the whole cost:

| test | time under cProfile |
|---|---|
| test_the_whole_chain_runs_unattended_with_no_unexpected_failures | 1336.4 s (builds the cycle) |
| test_the_flagship_uses_the_engineered_design_not_the_template | 0.2 s |
| test_the_flagship_is_a_plausible_physical_object | 0.0 s |

The same cycle took 957 s without the profiler. That baseline was measured with the original
code and per-handler timers.

Hot spots, by cumulative time out of 1333 s:

- **`publish.pdf.build_pattern_pdf`: 788 s (59%), 68 calls.**
  - 40 of those calls come from `gates.first_customer._documents`. That function re-renders
    both customer documents every time `release_gates.for_publish` runs, and `for_publish`
    runs twice per product per cycle (`listing.package` and `store.publish`). Those calls
    repeat identical inputs.
  - The other 28 come from `assets.build`.
- **`visual.disclosed_render.render`: 319 s (24%), 335 calls, only 43 of them unique (87%
  repeats).**
  - 272 calls come from `pdf._disclosed_views`. The US and UK documents draw the same frames,
    and each PDF rebuild draws them again.
  - The rest come from `listing_set` and the gallery supplements.
- **Listing-set pixel checks:** `mobile.title_safe_ink` (128 s, 530 calls), `contents_frame.draw`
  (which rasterises PDF pages through pdfium) and `gallery_frames.draw`. All three are re-run
  on the same frames by every `for_publish`, `listing.package` and `launch.plan` pass.
- **Repeated full cycles across tests.** `test_a_pipeline_upgrade_reaches_products_that_already_shipped`
  and `test_a_stale_listing_is_rebuilt_not_only_a_missing_one` each re-ran the whole
  `plan.cycle` from an empty database, with the same seed and the same `as_of` as `_run_once`,
  before attacking it. On the original code the upgrade test alone took **1609 s**.
- **Not a cause: real sleeps and lease waits.** `Worker.run_once` never sleeps (only `Worker.run`
  does, and the tests don't call it). The `Condition.wait` samples are the `_LeaseRenewal`
  daemon thread waiting idle, not the main thread. No test waits on a lease timeout.

## Fix (step 2)

There are two changes, both test-side.

**1. `tests/render_memo.py` (new): a content-addressed memo, installed only by
`test_product_run.py`.**

It wraps five functions that are deterministic by contract. Each wrapper replaces the module
attribute, which every caller looks up at call time. The key is a sha256 over every input
the function reads:

| function | key |
|---|---|
| `disclosed_render.render` | the CIR's full canonical dict (not just the fingerprint), view, layout, `RENDERER_VERSION` |
| `pdf.build_pattern_pdf` | the full CIR dict; every kwarg pickled, the twin included (with its calibration and tolerance); the printed date (`released_on`, or `date.today()` under the pinned clock); the benchmark-lesson effects snapshot the PDF standard reads |
| `mobile.title_safe_ink` | image mode, size and pixel bytes; `px` |
| `contents_frame.draw`, `gallery_frames.draw` | the facts dict, the PDF bytes, and whether a layout record was requested |

Rules the memo follows:

- **First call runs the real code.** The first call with any input runs the production code
  unchanged. So does any input that cannot be pickled.
- **Refusals are never cached.** An exception is recomputed on every call.
- **Hits are deep copies,** so no caller can see another caller's mutations.
- **Side effects are replayed.**
  - `build_pattern_pdf` buffers benchmark-lesson notes for the worker to flush to the
    learning store. The memo records those notes on the miss and replays them on every hit,
    so the database gets the same notes it would have got.
  - The `layout` out-parameter of the two `draw` functions is recorded and replayed into the
    caller's list.
- **The determinism test bypasses it.**
  `test_the_same_certified_pattern_renders_the_same_file_every_time` runs inside
  `render_memo.bypassed()`. Its three renders per CIR are real; otherwise the memo would make
  the test true by construction. The memo is only sound because these renders are
  byte-deterministic, which is the claim that test and `test_disclosed_render.py` prove.
- **Scope.** `run_tests.sh` runs each test file as its own process, so the memo exists only in
  this file's process. No other suite, and no mutation suite that patches renderer internals,
  ever sees it.

**2. The full cycle is built once and shared as an immutable fixture.**

- Right after `_run_once` drains, before any test reads or writes it, it takes a byte copy of
  its warehouse (`pristine.sqlite`, made with SQLite's own backup API because the file is in
  WAL mode).
- The upgrade test and the stale-listing test each start from a private copy (`_cycle_copy`)
  instead of re-running `plan.cycle` from empty.
- If `_run_once`'s drain had stopped at its 900-step cap rather than on an empty queue, the
  copy is drained on up to the test's original 2500-step budget. So a test never starts from
  a less finished cycle than it used to build itself.
- Everything after the setup is unchanged in both tests: the key stripping, the
  `chain.rebuild`, the 3000-step drain and every assertion.

**No assertion, threshold, fixture CIR, drain budget or production file changed.** The diff
to `test_product_run.py` is limited to:
- installing the memo;
- the snapshot (`_sqlite_copy` / `_cycle_copy`);
- swapping the two duplicate cycles for `_cycle_copy`;
- the `bypassed()` block;
- removing the imports those swaps left unused.

## Whole suite (step 3)

Run 2 (both memo tiers plus the shared cycle) is the final code. Run 1 (render and PDF memo
plus the shared cycle, without the pixel-check tier) is shown for comparison. Both ran
alongside other CPU-heavy processes. Run 1 shared the host with two other runs, including the
baseline; run 2 overlapped run 1.

| test | run 1 | run 2 (final) |
|---|---|---|
| test_a_chain_bump_is_what_unblocks_a_refused_rebuild | 0.0 s | 0.0 s |
| test_a_childrens_listing_carries_its_statements_through_the_real_chain (builds the shared cycle) | 657.5 s | 510.6 s |
| test_a_pipeline_upgrade_reaches_products_that_already_shipped | 363.0 s | 196.2 s |
| test_a_rebuild_that_has_already_been_refused_says_so_instead_of_looking_untried | 252.2 s | 114.5 s |
| test_a_recertified_release_rebuilds_its_listing | 234.4 s | 126.9 s |
| test_a_redesigned_product_re_enters_the_chain | 232.0 s | 117.7 s |
| test_a_stale_listing_is_rebuilt_even_when_its_release_is_unchanged | 235.7 s | 114.2 s |
| test_a_stale_listing_is_rebuilt_not_only_a_missing_one | 354.0 s | 191.0 s |
| test_the_rebuild_explains_its_decision | 230.4 s | 118.4 s |
| test_the_same_certified_pattern_renders_the_same_file_every_time (memo bypassed) | 48.5 s | 47.1 s |
| test_attack_a_chart_from_a_different_size_cannot_pass_as_this_one | 3.6 s | 3.8 s |
| the other 25 tests | ≤ 0.3 s each | ≤ 0.1 s each |
| **TOTAL (including 3.4 s import)** | **2615.2 s, 36 passed / 0 failed** | **1544.3 s, 36 passed / 0 failed** |

Memo counters for run 2:

| function | hits | misses |
|---|---|---|
| render | 851 | 222 |
| pdf | 278 | 197 |
| title_safe_ink | 2737 | 205 |
| gallery.draw | 768 | 60 |
| contents.draw | 1278 | 26 |

Tests are listed in the order the file's `__main__` runner uses (sorted by name). The order
matters for one reason: whichever test first calls `_run_once` pays for the cycle.

**Baseline (original code), as far as it was measured:**
- the cycle: 957 s;
- `test_a_pipeline_upgrade_reaches_products_that_already_shipped`: 1609 s.

The stale-listing test has the same shape as the upgrade test, so it would cost about the
same. Not measured on the original code: the five single-product rebuild tests and the whole
file end to end. I did not wait a further hour for those, so there is no measured "before"
total to set against 1544 s.

## Failures (step 4)

None. Both full runs: 36 passed, 0 failed.

## Open / for the reviewer

- **What dominates now.** The single run of the cycle and the six single-product
  certify-then-rebuild tests, which take about 115 s each. Each of those builds a fresh
  warehouse and a different design, so the memo has less to reuse there. Per-test hit counts
  were not recorded, so this is inferred, not measured.
  - A next step could share one certified-placemat snapshot between the tests that certify
    the identical CIR. Those are `..._even_when_its_release_is_unchanged` and
    `..._already_been_refused...`; `redesigned` and `recertified` certify the same stale
    design.
  - Not done here, to stay inside the 04:00Z window.
- **Risk to check: pytest in one process.** If pytest ever collects several files in a single
  process, the memo installed by this file would stay active for later files. `run_tests.sh`
  does not do this, and pytest is not a dependency.
- **Wall-clock dependence.** The snapshot is taken under the pinned, ticking clock. A test
  that starts from it runs its rebuild some minutes later on that clock than its own fresh
  cycle would have. No assertion in either test reads elapsed time.
