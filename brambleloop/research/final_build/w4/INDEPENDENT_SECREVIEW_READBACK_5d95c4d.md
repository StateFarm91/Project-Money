# Independent security review — W4-READBACK at 5d95c4d0

- **Subject:** `claude/w4-READBACK` at `5d95c4d0` vs `origin/claude/w4-INTEG8-next` at `b0133916`
  (`git diff b0133916...5d95c4d0`; 11 files, +1946/−14).
- **Reviewer:** independent session (I did not write this code). Reviewed 2026-10-27 (UTC).
- **Scope:** `core/readbackauth.py`, `app/security.py` (`READBACK_ROUTES`, `readback_gate`, gate
  ordering, `PUBLIC_PROJECTIONS`), `app/main.py` (`/api/verify` `evidence_checks`,
  `GET /api/readback/evidence`), `ops/production_evidence.py`, `ops/readback.py --evidence`,
  and the test changes.

## Verdict: **SHIP**

I found no Critical, High or Medium issue. The readback token opens only
`GET /api/readback/evidence`. The operator token is refused on that route. The token is
compared in constant time and is never echoed. The endpoint is closed (503) when the token is
unset, shorter than 32 characters, or equal to the operator token. Anonymous callers see only
`{check, ok}` for each evidence check. The six in-process handler calls each return one scalar
or a list length. In my test they issued SELECT statements only: no enqueue, no paid call, no
socket. The four Low findings below are hardening. None needs to block the merge. L1–L3 are
small, local fixes that should go into the next push on this line of work.

## Tests run (each suite on its own, `PYTHONPATH=src:tests nice -n 19`)

The fresh container had no dependencies. I installed them into a scratch venv from
`requirements.lock` and then `requirements-test.lock` (hash-pinned).

| Suite | Result |
|---|---|
| `tests/test_w4_readback_evidence.py` | 19/19 OK |
| `tests/test_w4_secpatch_public_surface.py` | 10/10 OK (92 s) |
| `tests/test_deploy.py` | 32/32 OK |
| `tests/test_w4_fmbatch1_contracts.py` | 5/5 OK |
| Reviewer adversarial file (appendix A; not committed) | 12/12 OK, 4 of them probes that confirm L1–L4 |

## Answers to the six questions

### 1. Can the readback token open or affect anything other than the evidence route? — **No.**
- `operator_gate` keys on the **matched route template** (`scope["route"].path`), not on the raw
  URL. `readback_route()` is an exact `frozenset` membership test. The readback branch runs
  first and `return`s only after `readbackauth.check` passes. Every other route still goes to
  `opsauth.check`, and the readback value can never satisfy it.
  `presents_operator_credential` is False for the readback token, so the
  projection and scrub middlewares treat a readback caller as anonymous.
- Path tricks I tried with the readback token: `/api/readback/evidence/`,
  `//api/readback/evidence`, `/./`, upper case, `%2F`, `;x`, `../../verify`, `%65vidence`,
  `/api/readback`, and a query string. None reached anything except the evidence route itself
  (including after redirects). The operator routes `/api/continuity`, `/api/etsy`,
  `/api/offsite` and `/api/departments` returned 401 with the readback token.
- Method tricks: POST, PUT, PATCH, DELETE, HEAD and OPTIONS on the evidence route all return
  ≥ 400 before any handler runs. The suite's own sweep runs every method of every other route
  with the readback token and checks two things: the response is 401/403/503, and the database
  fingerprint is unchanged.
- Header tricks: two `Authorization` headers get 400 (`SingleAuthorizationMiddleware`). A
  `?token=` query parameter is ignored (401). `Basic`, a one-character prefix or suffix, a
  case change, an empty bearer, a comma-joined pair, and the operator token all get 401.
  Non-latin-1/UTF-8 bytes in the header get 401, not 500.

### 2. Is the token handled safely? — **Yes.**
- Unset, whitespace-only, shorter than 32, or equal to `BRAMBLELOOP_OPS_TOKEN` after strip:
  `_expected()` returns `""`, and the endpoint answers 503 to everyone. The 503 text names only
  the variable. I checked that a short configured value is not echoed.
- Comparison uses `hmac.compare_digest` on bytes. `_same` refuses an empty value on either
  side, so an empty operator token cannot match an empty presented value.
- No module logs it. The access log records the request line, and the token travels only in a
  header. `ops/readback.py` reads it from the environment only, never from argv. It runs
  `_redact()` over its output as defence in depth, and the suite asserts that a hostile echoing
  server cannot get it printed. One CLI transport issue is listed as L4.

### 3. Does the evidence, or the anonymous `evidence_checks`, leak private data? — **No (one Low nuance, L1).**
- Anonymous `/api/verify`: `PUBLIC_PROJECTIONS` keeps `evidence_checks[*].{check, ok}` only.
  I checked this for no header, the readback token and a garbage bearer. I also checked the
  `api_verify` exception path: the anonymous view gets four `ok:false` entries, and even the
  operator view carries only `error_class`, never exception text.
- `/api/readback/evidence` emits ids, job types, counts, ages, UTC times, product slugs,
  `slug@version` artefacts, detector families (code-built signature prefixes), 12-character
  request-fingerprint prefixes, and Etsy's public taxonomy ids and names. It reads no
  conversation, Laura-store, OwnerAction, customer, order or spend table. `Job.inputs` is read
  only to test for the `laura` key and is never emitted. `PaidCallRecord.payload` (the raw model
  response) is never selected. The suite seeds private strings into each of these and asserts
  none appears.
- Deploy rows: `_project_value` passes a bool, number or null as is, turns a list into
  `{"list_length": n}`, and turns anything else into `null`. I monkeypatched handlers two ways.
  (a) A handler that raised with private text and an email produced
  `{"status":500,"fields":{},"error_class":"ValueError"}`, with no text and no traceback.
  (b) A handler that returned a `JSONResponse` with a private string field and an extra
  private key produced `{"configured": null}`, and a list of private dicts produced
  `{"list_length": 3}`.
- Defence in depth: a readback caller is not an operator, so `OwnerTextScrubMiddleware` and
  `CustomerRefScrubMiddleware` still apply to the evidence response.

### 4. Are the in-process operator handler calls free of side effects? — **Yes, proven at the SQL layer.**
Proof setup:
- A `before_cursor_execute` listener on the live engine records every statement.
- `JobQueue.enqueue` and the paid-call gateway entry points are replaced by tripwires.
- `socket.connect` is a tripwire.
- `GET /api/readback/evidence` is called with all six handlers on the seeded database.

Result: **188 statements, all `SELECT`**. No tripwire fired. The Job, AuditLog, OwnerAction and
Incident counts were unchanged. On a cold engine the first call issued no DDL either. The one
possible write in reach is `etsy_webhooks.ensure_table` (`CREATE TABLE IF NOT EXISTS`, once per
engine). That is schema DDL, not data, and `/api/etsy` already did it before this change.

A static review of the call graph found no write either:
- `agents_view`, `agent_quality`, `latest_allocation`, `work_items`, `orphans`
- the swarm metrics
- `funding_packet.packets`, `offsite.state`, `continuity.retained`
- `etsy_public.capability`, `etsy_webhooks.summary`
- `lifecycle.board`, `halted_releases`, `did_no_work`, `deliberate_refusal`, `crochet_property`

None of these contains an `add`, `commit`, `enqueue`, `audit` or HTTP client call.
`offsite.state` and `etsy_public.capability` report the *last recorded* round trip or probe;
they do not perform one.

### 5. Do the four anonymous checks fail closed? — **Yes, with two Low edge cases (L2, L3).**
The suite and my probes confirm three cases:
- an empty database gives four `false`;
- a database that raises gives four `false` with `readable:false`;
- the weekly check requires `improve.weekly`, so it is false if that cadence is missing.

The checks never change `/api/verify` `ok` or its status code. Anonymous callers cannot write
the rows the checks read: `ops.truth.sweep`, `ops.sentinel` and the `chain.rebuild*` audits,
`paid_call_records`, and DONE/DEAD jobs. I found no anonymous write path to them, so callers
cannot steer the checks.

### 6. Test integrity — **Nothing weakened.**
- `test_deploy`: the old exact assertion `set(public) == {"ok","checks"}` becomes
  `{"ok","checks","evidence_checks"}`. It now also asserts that each public evidence check is
  exactly `{check, ok}`, that there are 4 of them, and that they match the operator view. This
  is stricter.
- `test_w4_secpatch_public_surface`: `PUBLIC_FIELDS` gains the same one projection line. The
  anonymous sweep now expects `{401}` for the readback route when the token is configured and
  `{503}` when it is not. Before, it would have fallen into the generic gated set. This is
  narrower, not wider.
- `test_w4_fmbatch1_contracts`: the route pin moves `7f715ba7… → 750cd12d…`, with a matching
  `ops/CONTRACT_CHANGES.md` row. That is the expected effect of a new route.

## Findings

### L1 — Low — `error_class` can emit one identifier word taken from error text
`production_evidence.error_class` returns the text before the first `:` on an error's first
line whenever it looks like a dotted identifier with a capitalised last part. This value is
used by `dead_letters_24h.by_type[].error_class` and `weekly_jobs[].last_dead_error_class`.

**Reproduction** (appendix A, `error_class_can_carry_one_word_of_error_text`):
`"JaneDoe: refund requested" → "JaneDoe"`, `"Laura: owner said x" → "Laura"`,
`"Customer.JohnSmith: x" → "JohnSmith"`. Emails and phrases containing spaces are correctly
`unclassified`.

**Exposure:** readback-token holders only (never anonymous), one word at most, and only if some
code path writes `f"{name}: …"` errors. I found none, but nothing in the code prevents one.

**Required fix:** emit a name only if it is a known exception class. Either resolve it against
`builtins`, the `sqlalchemy`/`httpx` exception modules and the package's own exception classes,
or require a suffix in (`Error`, `Exception`, `Refused`, `Denied`, `Timeout`, `Exceeded`,
`Unavailable`). Otherwise return `unclassified`. Add a test with the three samples above.

### L2 — Low — `publishing_halt_clear` treats a systemic reading with no `systemic` key as "not systemic"
`truth_sweep_systemic = bool(systemic_reading.get("systemic"))`. A sweep row with
`detail.systemic == {}` yields `False`, so the judge can pass.

**Reproduction:** `systemic_reading_without_key_is_not_judged_systemic` returns `True` on a
fresh DB.

**Mitigations:** the only writer (`incident_lifecycle.systemic_evidence`) always sets the key,
and the judge also requires `systemic_halt_open == 0`.

**Required fix:** use `systemic_reading.get("systemic") is False` for the false case, and
`None` (which fails the judge) when the key is not a bool.

### L3 — Low — a future-dated timestamp counts as fresh forever
`_age_h` can return a negative age. `judge_publishing_halt` (`age <= 2h`) and
`judge_stale_rebuilds` (`age <= 26h`) accept it.

**Reproduction:** `future_dated_sweep_counts_as_fresh_forever`: a sweep dated NOW+365 d gives
`publishing_halt_clear == True`.

**Exposure:** needs clock skew or a bad row; no external writer exists.

**Required fix:** require `0 <= age <= limit`, allowing a few minutes of skew, in both judges.

### L4 — Low (pre-existing pattern, now extended to the new token) — the CLI sends the bearer over any scheme and through cross-host redirects
`ops/readback.py::_fetch` uses `urllib.request.urlopen`. `HTTPRedirectHandler` copies
`Authorization` to the redirect target, including one on another host.

**Reproduction:** `cli_token_redirect_behaviour` shows that `redirect_request` forwards
`Authorization` on a 302 to `evil.invalid`. `--url` and `BRAMBLELOOP_PRODUCTION_URL` also accept
`http://`.

**Exposure:** a misconfigured URL or a compromised upstream redirect could hand the read-only
token to a third party. Its blast radius is the evidence document, but the operator token goes
through the same `_fetch`.

**Required fix:** when a token is attached, use an opener whose redirect handler refuses
redirects. Also refuse a non-`https` URL unless the host is `localhost` or `127.0.0.1`. Add a
test for each.

### I1 — Info — load on anonymous `/api/verify` and on the evidence route
Every anonymous `/api/verify` now also runs four evidence sections, including a 7-day scan of
`paid_call_records` columns. One evidence call is about 188 SELECTs, including the swarm views.
Neither is a leak. If `/api/verify` has no rate limit or short cache, consider caching
`checks(db)` for about 60 s.

### I2 — Info — the check names are an anonymous health oracle
Anonymous callers can see four health booleans: halt, rebuilds, paid-call dedupe and weekly
jobs. This is the documented design (the same posture as `checks`), and it carries no data.
I note it so the decision is explicit.

## Appendix A — reviewer adversarial tests (not committed; this branch carries only the report)
The tests import the suite's own harness (`test_w4_readback_evidence`): temp DB, refused
network and seeded private rows. Run with
`cd brambleloop && PYTHONPATH=src:tests:<dir> python <dir>/test_adv_readback.py`. Results:

```
OK   evidence_endpoint_issues_only_reads_no_enqueue_no_network   (statements: {'SELECT': 188})
OK   first_call_on_cold_engine_ddl_only                           (cold-engine non-SELECT: [])
OK   handler_exception_leaks_class_only
OK   handler_returning_private_body_projects_one_field
OK   path_and_method_tricks_with_readback_token
OK   header_tricks
OK   token_config_rules
OK   error_class_can_carry_one_word_of_error_text                 (probe: L1)
OK   anonymous_verify_projection_and_fail_closed
OK   systemic_reading_without_key_is_not_judged_systemic          (probe: L2, -> True)
OK   future_dated_sweep_counts_as_fresh_forever                   (probe: L3, -> True)
OK   cli_token_redirect_behaviour                                 (probe: L4, forwards: True)
12/12 passed
```

The full source of the adversarial file follows.

```python
"""Independent adversarial tests for W4-READBACK 5d95c4d0 (not committed; report appendix)."""
import json, sys, os, contextlib, traceback
import test_w4_readback_evidence as H  # harness: temp DB, network refused, seeded client
from sqlalchemy import event
from brambleloop.app import main, security
from brambleloop.ops import production_evidence as pe
from brambleloop.core import readbackauth, opsauth

c = H.client()
RB, OP = H.READBACK_TOKEN, H.OPS_TOKEN
results = []


def t(fn):
    try:
        fn(); results.append(("OK  ", fn.__name__, ""))
    except Exception as e:  # noqa
        results.append(("FAIL", fn.__name__, f"{type(e).__name__}: {str(e)[:600]}"))
    return fn


@contextlib.contextmanager
def capture_sql():
    stmts = []
    def before(conn, cursor, statement, params, context, executemany):
        stmts.append(statement.strip().split(None, 1)[0].upper())
    event.listen(main.db.engine, "before_cursor_execute", before)
    try:
        yield stmts
    finally:
        event.remove(main.db.engine, "before_cursor_execute", before)


@contextlib.contextmanager
def tripwires():
    """Any enqueue, paid call or outbound socket during the call is a failure."""
    from brambleloop.queue import durable
    hits = []
    import socket
    saved = []
    def trip(name):
        def f(*a, **k):
            hits.append(name); raise RuntimeError("tripwire " + name)
        return f
    targets = [(durable.JobQueue, "enqueue")]
    try:
        from brambleloop.gateway import paid_calls as pc
        for n in dir(pc):
            if n in ("call", "paid_call", "execute", "run_paid"):
                targets.append((pc, n))
    except Exception:
        pass
    for obj, n in targets:
        saved.append((obj, n, getattr(obj, n))); setattr(obj, n, trip(f"{getattr(obj,'__name__',obj)}.{n}"))
    saved.append((socket.socket, "connect", socket.socket.connect))
    socket.socket.connect = trip("socket.connect")
    try:
        yield hits
    finally:
        for obj, n, v in saved:
            setattr(obj, n, v)


@t
def evidence_endpoint_issues_only_reads_no_enqueue_no_network():
    # Warm once so lazily-created tables (etsy_webhooks.ensure_table) are not counted as the
    # endpoint's own writes; then the real call must issue SELECT/PRAGMA only.
    with H.both_tokens():
        c.get("/api/readback/evidence", headers=H.bearer(RB))
        before = H._db_fingerprint()
        with capture_sql() as stmts, tripwires() as hits:
            r = c.get("/api/readback/evidence", headers=H.bearer(RB))
    assert r.status_code == 200, r.status_code
    kinds = sorted(set(stmts))
    bad = [k for k in kinds if k not in ("SELECT", "PRAGMA", "WITH")]
    assert not bad, f"non-read SQL during evidence: {kinds}"
    assert not hits, hits
    assert H._db_fingerprint() == before
    dr = r.json()["deploy_readback"]
    assert all(v["status"] == 200 for v in dr.values()), dr
    print("  statements:", {k: stmts.count(k) for k in kinds}, file=sys.stderr)


@t
def first_call_on_cold_engine_ddl_only():
    # Cold engine: report what the very first evidence call writes (DDL from ensure_table).
    d = H._fresh_db()
    saved = main.db
    stmts = []
    def before(conn, cursor, statement, *a):
        stmts.append(statement.strip()[:60])
    event.listen(d.engine, "before_cursor_execute", before)
    try:
        main.db = d
        with H.both_tokens():
            r = c.get("/api/readback/evidence", headers=H.bearer(RB))
    finally:
        main.db = saved
        event.remove(d.engine, "before_cursor_execute", before)
    writes = [s for s in stmts if not s.upper().startswith(("SELECT", "PRAGMA", "WITH"))]
    print("  cold-engine non-SELECT:", writes, file=sys.stderr)
    assert all(w.upper().startswith("CREATE") for w in writes), writes


@t
def handler_exception_leaks_class_only():
    secret = "ADV-SECRET-EXC-TEXT-0042"
    orig = main.api_etsy
    def boom():
        raise ValueError(secret + " customer jane@example.com")
    main.api_etsy = boom
    try:
        with H.both_tokens():
            r = c.get("/api/readback/evidence", headers=H.bearer(RB))
    finally:
        main.api_etsy = orig
    assert r.status_code == 200
    assert secret not in r.text and "jane@" not in r.text and "Traceback" not in r.text, r.text[:400]
    assert r.json()["deploy_readback"]["/api/etsy"] == {"status": 500, "fields": {},
                                                        "error_class": "ValueError"}


@t
def handler_returning_private_body_projects_one_field():
    from fastapi.responses import JSONResponse
    orig = main.api_offsite
    main.api_offsite = lambda: JSONResponse({"configured": "ADV-PRIVATE-STR",
                                             "bucket": "s3://ADV-PRIVATE"}, status_code=502)
    orig2 = main.api_funding_packets
    main.api_funding_packets = lambda: {"packets": [{"secret": "ADV-PRIVATE-PKT"}] * 3}
    try:
        with H.both_tokens():
            r = c.get("/api/readback/evidence", headers=H.bearer(RB))
    finally:
        main.api_offsite, main.api_funding_packets = orig, orig2
    assert "ADV-PRIVATE" not in r.text, r.text[:300]
    dr = r.json()["deploy_readback"]
    assert dr["/api/offsite"] == {"status": 502, "fields": {"configured": None}}, dr["/api/offsite"]
    assert dr["/api/funding/packets"]["fields"] == {"packets": {"list_length": 3}}


@t
def path_and_method_tricks_with_readback_token():
    paths = ["/api/readback/evidence/", "//api/readback/evidence", "/api/readback/./evidence",
             "/API/readback/evidence", "/api/readback/evidence%2F", "/api/readback/evidence;x",
             "/api/readback/evidence/../../verify", "/api/readback/%65vidence",
             "/api/readback", "/api/readback/evidence?x=/api/continuity"]
    bad = []
    with H.both_tokens():
        for p in paths:
            r = c.get(p, headers=H.bearer(RB), follow_redirects=False)
            if r.status_code == 200 and "deploy_readback" not in r.text and "evidence_checks" not in r.text:
                bad.append((p, r.status_code, r.text[:80]))
            if r.status_code in (301, 302, 307, 308):
                loc = r.headers.get("location", "")
                r2 = c.get(loc, headers=H.bearer(RB))
                if r2.status_code == 200 and "deploy_readback" not in r2.text:
                    bad.append((p, "->", loc, r2.status_code))
        for m in ("POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
            r = c.request(m, "/api/readback/evidence", headers=H.bearer(RB))
            if r.status_code < 400:
                bad.append((m, r.status_code))
        # The readback token must not unlock any operator route via the evidence path params.
        for p in ("/api/continuity", "/api/etsy", "/api/offsite", "/api/departments"):
            r = c.get(p, headers=H.bearer(RB))
            if r.status_code not in (401, 403):
                bad.append((p, r.status_code))
    assert not bad, bad


@t
def header_tricks():
    with H.both_tokens():
        ok = lambda h: c.get("/api/readback/evidence", headers={"Authorization": h}).status_code
        assert ok(f"Bearer {RB}") == 200
        assert ok(f"bearer   {RB}  ") == 200
        assert ok(RB) == 200  # bare token accepted (documented)
        for h in (f"Bearer {OP}", OP, f"Basic {RB}", f"Bearer {RB}x", f"Bearer {RB[:-1]}",
                  f"Bearer {RB.upper()}", "Bearer ", "", f"Bearer {RB},{RB}"):
            s = ok(h)
            assert s == 401, (h[:12], s)
        # Two Authorization headers
        r = c.get("/api/readback/evidence",
                  headers=[("Authorization", f"Bearer {OP}"), ("Authorization", f"Bearer {RB}")])
        assert r.status_code != 200, r.status_code
        r = c.get("/api/readback/evidence", params={"token": RB})
        assert r.status_code == 401
        # Non-ASCII header bytes: refusal, not 500
        r = c.get("/api/readback/evidence", headers=[(b"authorization", ("Bearer " + "é" * 40).encode("latin-1"))])
        assert r.status_code == 401, r.status_code


@t
def token_config_rules():
    env = {readbackauth.TOKEN_VAR: " " + OP + " ", opsauth.TOKEN_VAR: OP}
    assert not readbackauth.configured(env)
    env = {readbackauth.TOKEN_VAR: "x" * 31}
    assert not readbackauth.configured(env)
    env = {readbackauth.TOKEN_VAR: " " * 40}
    assert not readbackauth.configured(env)
    for env in ({}, {readbackauth.TOKEN_VAR: ""}, {readbackauth.TOKEN_VAR: "x" * 31}):
        try:
            readbackauth.check("", env); raise AssertionError("accepted")
        except readbackauth.ReadbackAuthUnavailable as e:
            assert "x" * 31 not in str(e)
    # unset readback token, empty ops token: empty/blank presented never passes
    for pres in (None, "", "Bearer ", "Bearer  "):
        try:
            readbackauth.check(pres, {readbackauth.TOKEN_VAR: "y" * 40}); raise AssertionError(pres)
        except readbackauth.ReadbackAuthRefused:
            pass
    # Server 503 body does not echo a short configured value
    with H._env(**{readbackauth.TOKEN_VAR: "SHORTSECRET123", opsauth.TOKEN_VAR: OP}):
        r = c.get("/api/readback/evidence", headers=H.bearer("SHORTSECRET123"))
        assert r.status_code == 503 and "SHORTSECRET123" not in r.text, (r.status_code, r.text)
    with H._env(**{readbackauth.TOKEN_VAR: OP, opsauth.TOKEN_VAR: OP}):
        r = c.get("/api/readback/evidence", headers=H.bearer(OP))
        assert r.status_code == 503 and OP not in r.text


@t
def error_class_can_carry_one_word_of_error_text():
    # Documented as LOW: the first `Identifier:` of an error line survives as the "class".
    got = {s: pe.error_class(s) for s in ("JaneDoe: refund requested", "Laura: owner said x",
                                          "Customer.JohnSmith: x", "jane.doe@example.com: x",
                                          "Order 123: x", "ValueError: secret")}
    print("  error_class samples:", got, file=sys.stderr)
    assert got["jane.doe@example.com: x"] == "unclassified"
    assert got["Order 123: x"] == "unclassified"


@t
def anonymous_verify_projection_and_fail_closed():
    with H.both_tokens():
        for h in ({}, H.bearer(RB), {"Authorization": "Bearer garbage"}):
            body = c.get("/api/verify", headers=h).json()
            assert set(body) == {"ok", "checks", "evidence_checks"}, sorted(body)
            for x in body["evidence_checks"]:
                assert set(x) == {"check", "ok"}, x
    # empty DB => all false
    assert not any(x["ok"] for x in pe.checks(H._fresh_db(), now=H.NOW))
    # api_verify exception path: projected to name/ok only and false
    orig = pe.checks
    pe.checks = lambda db: (_ for _ in ()).throw(RuntimeError("ADV-EXC-SECRET"))
    try:
        with H.both_tokens():
            anon = c.get("/api/verify").json()
            full = c.get("/api/verify", headers=H.bearer(OP)).json()
    finally:
        pe.checks = orig
    assert all(x["ok"] is False for x in anon["evidence_checks"]), anon["evidence_checks"]
    assert "ADV-EXC-SECRET" not in json.dumps(full), "exception text in operator view"


@t
def systemic_reading_without_key_is_not_judged_systemic():
    # Fail-open probe: a sweep row whose `systemic` dict lacks the `systemic` key.
    from datetime import timedelta
    d = H._fresh_db()
    H._audit(d, "ops.truth.sweep", {"systemic": {}}, H.NOW - timedelta(minutes=5))
    ok = H._check(d, "publishing_halt_clear")
    print("  publishing_halt_clear with systemic={} ->", ok, file=sys.stderr)
    H._audit(d, "ops.truth.sweep", {"systemic": {"systemic": False}},
             H.NOW + timedelta(days=30))
    ok2 = H._check(d, "publishing_halt_clear", now=H.NOW + timedelta(days=60))
    assert ok2 is False  # a stale sweep is not fresh evidence


@t
def future_dated_sweep_counts_as_fresh_forever():
    from datetime import timedelta
    d = H._fresh_db()
    H._audit(d, "ops.truth.sweep", {"systemic": {"systemic": False}}, H.NOW + timedelta(days=365))
    print("  future-dated sweep ->", H._check(d, "publishing_halt_clear"), file=sys.stderr)


@t
def cli_token_redirect_behaviour():
    # Does ops/readback.py's urllib _fetch forward the bearer across a cross-host redirect?
    import urllib.request
    req = urllib.request.Request("https://a.invalid/x", headers={"Authorization": "Bearer T"})
    h = urllib.request.HTTPRedirectHandler()
    new = h.redirect_request(req, None, 302, "Found", {}, "https://evil.invalid/y")
    fwd = new.get_header("Authorization")
    print("  urllib forwards Authorization on cross-host 302:", fwd is not None, file=sys.stderr)


for r in results:
    print(*r)
print(f"{sum(1 for r in results if r[0]=='OK  ')}/{len(results)} passed")
```
