# W4-CLOSE5

Branch `claude/w4-CLOSE5`, based on `origin/claude/w4-INTEG3` at 364ade0. Production is b931d17
(SHADOW). This branch makes no deploys, no production writes and no spend.

## 1. Security review of 324927f, R1 (LOW): FIXED, dev-proven

**Finding:** an unauthenticated refusal flood on `/api/etsy/webhook` could take the shared
AnyIO threadpool tokens (40 per process, shared with about 187 sync routes) and the DB pool
(5 + 10 overflow).

**Fix:**
- `integrations/etsy_webhooks.py`: `WebhookGate` / `GATE` gives the webhook its own
  `anyio.CapacityLimiter` with `WEBHOOK_SLOTS = 4`, so it never uses the default limiter.
  Admission is non-blocking (`threading.BoundedSemaphore.acquire(blocking=False)`). When the
  gate is saturated, the route returns `None` at once and runs no thread and no DB work.
  `busy()` returns a static 503 with `Retry-After: 5`. Etsy retries a 5xx, so a real delivery
  that is shed is not lost. `summary()["gate"]` exposes in-process counters
  (`slots`, `in_flight`, `admitted`, `shed_busy`) without a DB read.
- `app/main.py` `api_etsy_webhook`: `refuse` and `receive` run through `gate.run(...)`. A
  slot is taken only after the capped async body read, so a slow client cannot hold one.

**Tests:**
- `tests/test_w4_close5_r1.py`, 4 tests:
  - a private limiter is used (the default limiter's borrowed tokens do not change);
  - the 4th call is shed in under 50 ms, and its work never runs;
  - a slot is released when the work raises;
  - `slots < QueuePool pool_size (5)`;
  - the route answers 503 + Retry-After with `refuse`/`receive` never called and the refusal
    counters unchanged, then recovers (401 counted, 202 accepted).
- `tests/test_w4_integ3_secfixes.py::test_m1_...threadpool` is now **strengthened**: it
  requires `gate.run` and forbids `run_in_threadpool` in the route.

Production evidence is still needed, so this is dev-proven and awaiting deploy.

## 2. Spend: weekly `creative.grid_tournament`, input tokens cut, dev-proven

**Measured run:** about CA$13, 84 judge calls, 2.89M input tokens. That is about 34,400
tokens a call, or about 4,300 an image at 8 images a call. Full-size images dominate:
`IMAGE_TOKENS_ESTIMATE`'s measured mean is about 5,000 per `il_fullxfull` image.

**Unchanged:**
- models (`provider_for("gallery_observation")`);
- the 3 judges and their personas;
- `MAX_IMAGES_PER_CALL` (8);
- the median rule, `GRID_THRESHOLD` and the F-278 / #218 readers;
- the spend ceiling and the per-call reservation (`IMAGE_TOKENS_ESTIMATE` per image is still
  reserved, so the budget check stays conservative).

**Downscale** (`creative/blinded.py`, `judge_view`). The judges are asked to score
*thumbnails on a simulated Etsy search page*; the browsing judge looks "on a phone ... for
about a second". On a search results card, Etsy serves `il_340x270` (1x) and `il_570xN`
(2x srcset). 570 px wide is therefore the largest picture a real search page shows, and the
smallest that loses nothing the simulated page would show. The same rule applies on both
sides, so the comparison stays fair:
- benchmark: `il_fullxfull.<id>` becomes `il_570xN.<id>`, the same Etsy image resized by Etsy
  itself. It is still a URL and nothing is downloaded. Checked by a read-only GET
  (2026-10-20): the variant exists, 1200x1400 becomes 570x665;
- ours: resized locally to 570 px wide, aspect kept, never enlarged, same format and
  basename. The copy is in a content-addressed cache bounded to 256 entries.

**Reuse** (`grid_fingerprint`, `cached_panel`, `store_panel`):
- The fingerprint hashes:
  - the content address of every cell on the page (URL, or sha256 of the bytes sent);
  - pod, provider, model, judge personas, prompt template, fields, max_tokens and the batch
    limit;
  - the view width and version.
- A complete panel is stored as an `AuditLog` row `creative.grid_panel`. A panel is complete
  only when every judge answered every cell on every field, nothing was stopped and nothing
  failed.
- An identical grid is reused within `PANEL_REUSE_DAYS` (56), with cell-by-cell mapping
  through content addresses. A reused panel costs 0 and makes no call. It is revalidated
  before use, so a tampered or partial stored row is refused.
- The panel is not reused when:
  - any picture or the benchmark set changes (scores are relative to the page);
  - the model changes;
  - two cells share one picture.
- Registered in `ops/retention.KNOWN_READ_ACTIONS` as `windowed`.

**Estimated saving** (`tests/test_w4_close5_grid_spend.py::test_estimated_saving_on_the_measured_production_run`,
using the provider's (w x h)/750 rule):

| | per image | per call (8 images) | run (84 calls) | CA$ |
|---|---|---|---|---|
| before (measured) | ~4,300 | ~34,400 | 2.89M | ~13.0 |
| after, square 570x570 | 434 | ~3,700 | ~0.31M | ~1.4 |
| after, worst 2:3 portrait 570x855 | 650 | ~5,450 | ~0.46M | ~2.1 |

That is **at least 84% fewer input tokens, about CA$11 or more saved a run**, before reuse.
Reuse then makes every week whose page is unchanged (same benchmark set, same heroes)
cost **CA$0** for that pod. The reuse rate is not measured yet, so no number is claimed for it.

**Tests:**
- `tests/test_w4_close5_grid_spend.py` (10): Etsy variant rewrite; resize, aspect, name,
  format and no-enlarge; judges receive only 570-wide images; the saving estimate; identical
  grid reused with no call and 0 spend; changed hero, changed benchmark set or changed model
  re-judged; incomplete panel never stored or reused; stale or tampered panel refused;
  duplicate pictures not reused; retention registration.
- Existing suites unchanged and green: `test_blinded` (46), `test_w4_herotourney` (4),
  `test_w4_b2vision` (7), `test_cert_preengineering` (19), `test_cert_intel_wave2` (15).

This is dev-proven and awaiting deploy. The production saving is read from the first weekly
run after deploy: `spend_report` rows with purpose `search_grid_tournament`.
