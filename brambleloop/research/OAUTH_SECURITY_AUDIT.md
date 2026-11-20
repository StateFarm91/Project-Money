# Etsy / OAuth security audit, and the two historical reliability failures closed

Lane E (Reliability / Coordinator), 2026-09-25. `BRAMBLELOOP_PHASE=shadow`. **CA$0 spent, no
model call, no image generation, nothing published, deployed or activated. No credential was
sought, printed or used** — every secret in this document and in the tests is a literal
invented by the test, shaped like the real thing so the shape-matching half of the redactor is
exercised honestly.

Tests added or extended, all green:

| file | checks | owner |
|---|---|---|
| `tests/test_oauth_security_audit.py` (new) | 84 | this lane |
| `tests/test_board.py` | 21 → 32 | this lane |
| `tests/test_board_restart.py` | 65 → 82 | this lane |

Run: `PYTHONPATH=src python tests/test_oauth_security_audit.py` (and the two board files).
`tests/test_etsy_oauth_callback.py` (41), `test_spend_governance.py`, `test_continuity.py`
were re-run unchanged and stayed green.

Two leaks are **proven**, both in files this lane does not own. Exact diffs are in
[§7](#7-exact-diffs-for-lane-a). Nothing was edited outside `ops/**` and this lane's tests.

---

## 1. Part one: the two historical failures, and what the registry does not close

### What was verified

`ops/board.py` and `ops/registry.py` were read against the two failures and both are
reproduced as tests that fail against the old behaviour:

* **The ~100-minute self-match.** `alive()` excludes the caller's whole process lineage and
  takes an injectable process table, so the exact shape — the *only* process carrying the
  marker is the observer — is exercised rather than argued. A job with no sentinel whose only
  match is its own watcher reads `STALLED`, which is the third answer the old code could not
  give. Closed.
* **The 47-minute unread suite.** `COMPLETE_UNREPORTED` is that failure named as a state,
  carrying its age and quoting the job's own headline. Closed **for a log the job wrote in
  place** — see the residual below.
* **The 2026-09-25 restart.** `registry.survey()` takes no job list, recomputes every verdict
  from the job's own evidence, and persists no verdict. `INTERRUPTED` and `EVIDENCE_LOST` are
  computed from two facts each rather than from an absence. Closed.

### What it did **not** close: three findings, all fixed in this lane's own files

#### 1a. A completed lane's evidence could exist and go unread, and nobody had to forget anything

`board.read` called `read_text` bare and `registry.survey` had no guard around a row. A single
lane whose log path existed and refused its bytes — a directory where a file should be, a
permission the container lost — **raised out of the survey**, and the survey is the one call
that answers for every lane. One broken log therefore buried the finished suites sitting on
disk and handed the operator a traceback in place of a board: the morning of 2026-09-25 again,
reconstruct-the-night-by-hand, this time caused by the tool built to abolish it.

Reproduced before the fix:

```
SURVEY RAISED: IsADirectoryError [Errno 21] Is a directory: '/tmp/.../bad.log'
-> the completed lane A evidence is on disk and unread
```

Fixed in `ops/board.py` (new state `EVIDENCE_UNREADABLE`, in `needs_attention`, never in
`refillable`) and in `ops/registry.py` (`_row_or_refusal`, new state `UNREADABLE_RECORD` for
a record that cannot be turned into a verdict at all — a pattern that no longer compiles, a
git call that throws). Both are reported *as themselves* in the row where they belong; neither
is ever `COMPLETE` and neither is `MISSING`, because "wrote nothing" and "refuses to be read"
are different facts.

Proven against the injected defect: restoring the bare `read_text` makes `test_board.py` die
with the original `IsADirectoryError` and `test_board_restart.py` drop two checks.

#### 1b. The *age* of a completion was the filesystem's opinion, not the job's

`COMPLETE_UNREPORTED` fired on `now - log.stat().st_mtime`. An mtime is not evidence the job
wrote. Copy the log, restore it from an archive, move one into place or merely touch it, and a
suite that finished 47 minutes ago reads `COMPLETE`, silently leaves `needs_attention`, and
goes unread **for exactly the reason the state was invented**. The one rule — completion comes
from the job's own terminal evidence — was satisfied for the verdict and quietly broken for
the number that makes the verdict actionable.

`Job.finished` is now an optional pattern whose first group is a stop time the job itself
wrote (epoch seconds or ISO 8601). When present it wins; otherwise the mtime is used, and
every finished row carries `age_source` (`"job"` / `"mtime"` / `"unavailable"`), so a
watcher-side age is **disclosed rather than forbidden**. The convention is persisted by the
registry alongside `terminal` and `result`, for the same reason those are: a restarted process
that fell back to "no stamp" would silently go back to reading the age off the filesystem.
An unparseable stamp falls back and says so; it never becomes the epoch.

Proven against an injected defect (ignore the stamp): two checks fail in `test_board.py`,
three in `test_board_restart.py`.

#### 1c. Nothing pushed. The coordinator still had to remember to *look*

This is the one the brief named, and it was still open. The registry closes "the coordinator
has to remember **what** ran". It does not close "the coordinator has to remember **to
look**" — and that second one *is* the 47-minute failure: no self-match, no lost list, nothing
wrong with the evidence. The suite had finished, `TOTAL PASSING: 3469` was in the file, and
nobody re-read it. A survey nobody runs is a log nobody re-reads with more machinery behind it.
`ops/HEARTBEAT_PROMPT.md` did not mention the registry at all.

So the survey stops being something to remember and becomes a **side effect of the one step a
session cannot skip**. `ops/lock.py acquire` — step 3 of every heartbeat, and of every stale-
lease takeover, which is the case where it matters most — now prints every lane whose own
evidence says it finished and which nobody has acknowledged, plus every lane whose evidence
cannot be established:

```
acquired

1 lane(s) need attention before new work is started:
  [complete_unreported] demo (D, 120 min)  EXIT 0
  read each one's evidence, then `python3 ops/registry.py ack <name>`.
```

Three properties, each deliberate: it **prints and decides nothing** (acknowledging stays an
act the caller makes, because a watcher that clears its own alerts is back to reading
completion from watcher state); it **never changes the script's exit code** (a board that
cannot be built must not be able to stop a session working); it **never raises** (an absent,
empty or corrupt registry prints one honest line). `ops/HEARTBEAT_PROMPT.md` step 3 now also
says to enrol a long background job before starting it.

### Residuals, stated rather than fixed

* **`registry.survey` is still pull, not push, outside the heartbeat.** The lease is the only
  mandatory choke point that exists; a lane that finishes mid-session is surfaced at the *next*
  acquire, not at the moment it finishes. Closing that needs a supervisor, which `registry.py`
  deliberately is not. What would settle whether it is worth building: whether a lane has ever
  finished and gone unread *within* one session rather than across a restart.
* **A job with no stamp still gets a filesystem age.** `age_source` makes it visible; it does
  not make it right. Every long-running job in this repo should start ending with
  `echo "FINISHED AT $(date -u +%s)"` beside its `echo "EXIT $?"`.

---

## 2. The rule this audit was run against

> No authorization code, access token, refresh token, shared secret, PKCE verifier, encryption
> key or operator token may reach a log, report, artifact, audit row or exception body.

Every path below is named with a verdict. **PROVEN LEAK** means a test in
`tests/test_oauth_security_audit.py` reproduces it.

---

## 3. LEAK 1 — the refresh path has no redactor at all *(high)*

**Where.** `integrations/etsy_oauth.py::_token_request`:

```python
detail = body.get("error_description") or body.get("error") or body
...
raise EtsyAuthNeedsOwner(f"Etsy refused the {what} with {status}: {detail}. ...")
```

`detail` is Etsy's own text, and when Etsy names neither `error` nor `error_description` it is
**the entire response body**, rendered by `str(dict)`.

**Why that is a credential.** On the refresh grant the form we POST carries the refresh token.
`tests/fake_etsy.py` already has `echo_token_in_error`, with a comment saying a real API has
been observed echoing a bearer token back inside an error body — which is precisely the case
redaction-by-field-name misses. Reproduced:

```
EtsyAuthNeedsOwner | token present in message: True
  Etsy refused the refresh grant with 400: refresh token 111111.rYQ6bF3k9sZ2wQ8t... was
  already used. A refresh token lasts 90 days and is single-use per refresh, ...
```

**Where it lands.** Not argued — run end to end through the real `JobQueue`, the real
`Worker` and a real database, on `store.publish`, which is the job type that actually builds a
`TokenProvider` and fetches a token when it assembles its request headers:

* `runtime/worker.py` line 185: `detail={"error": str(e)}` → an **`AuditLog` row**.
* `runtime/worker.py` line 184: `queue.fail(job.id, f"{type(e).__name__}: {e}\n{traceback…}")`
  → **`Job.last_error`**, durable, with a traceback beside it.

Both asserted present in the test. And both tables are in `continuity.NON_REDERIVABLE` and
**not** in `EXCLUDED_TABLES`, so the leak is carried by `/api/continuity/export` (served as a
download), by the off-provider archive, and by `core/backup.py`'s `pg_dump` — **in the clear**,
which is more exposure than `oauth_credentials` itself has, since that table is ciphertext.

**The asymmetry is the finding.** The callback path *does* redact: `etsy_authorise.finish`
builds a `Redactor`, seeds it with the shared secret, the authorization code and the PKCE
verifier, and puts `str(exc)` through it. Exercised in the same test run against the same
echoing server: the code, the verifier and an echoed access token are all replaced by
fingerprints. `TokenProvider._refresh_now` has no redactor, no caller that adds one, and no
test that would have noticed.

**The fix is cheap and is measured, not asserted.** `Redactor()` with *nothing registered*
already removes an Etsy-shaped token by shape wherever it appears, including inside a sentence:

```
THE FIX HOLDS: an unseeded Redactor already removes it by shape alone   OK
```

Diff in §7.1. It closes the refresh path, the probe path and every future caller in one place —
the message, rather than each of the places the message ends up.

**Reachability today.** The refresh only happens when a real Etsy call is made, and
`store.publish` is gated by SHADOW. It is **not** reachable today. It becomes reachable the
moment Lane C's one controlled round trip runs, or at the first container replacement after
LIMITED PRODUCTION, whichever is first. The credential is live now (`rotations: 0`), so this
should be closed before that round trip, not after it.

---

## 4. LEAK 2 — the access-log filter can be walked around *(low, but it is a bypass of the stated invariant)*

**Verified first that the filter holds** for the shape uvicorn actually writes — the known and
recorded leak, where the request line *is* the credential. It does:

```
127.0.0.1:0 - "GET /api/etsy/oauth/callback?code=***ab718407&state=***f39dac6c HTTP/1.1" 200
```

Path, method and status survive; an ordinary request line comes out byte-identical; both
`record.args` (lazy formatting, which is what uvicorn uses) and `record.msg` (eager) are
covered; a filter that throws replaces the line wholesale rather than printing it.

**Installation order, which was the residual doubt, holds and holds better than claimed.**
uvicorn's `Config.__init__` configures logging before `load()` imports the app, and
`access_log.install()` runs at import of `app.main`. Checked further: a *later*
`logging.config.dictConfig(uvicorn.config.LOGGING_CONFIG)` removes and replaces the
**handlers** but leaves the **logger's** filters in place — and the logger-level filter
rewrites the record before any handler sees it, so handler replacement is survivable. Asserted.

**The bypass.** `access_log._PARAM` matches a literal parameter name, and its name character
class is `[A-Za-z0-9_.\-]` — no `%`. Starlette reads the query with
`urllib.parse.parse_qsl`, which percent-decodes the **name** as well as the value. So there is
a spelling of `code` the application honours and the scrubber does not see:

```
scrubbed : GET /api/etsy/oauth/callback?%63ode=SECRETCODE...&state=***f39dac6c HTTP/1.1
app sees : {'code': 'SECRETCODE...', 'state': '...'}
leaked   : True
```

**Severity, honestly.** Etsy will never send this: the browser sends what Etsy's `Location`
header contains. Someone who crafts this request is writing *their own* value into our log, not
extracting ours. So it is not an exfiltration route for the live credential. It is still a
bypass of the invariant the filter exists to enforce, it also defeats `state` scrubbing, and it
costs two characters to close. Diff in §7.2, with a test proving both halves are needed
(widening the charset alone does nothing; decoding alone never runs).

**What remains outside our reach, unchanged and correctly recorded:** a reverse proxy's own
access log. The bound stands — an Etsy authorization code is single-use, short-lived and
useless without the PKCE verifier, which never leaves the sealed database.

---

## 5. Findings that are not leaks

### 5a. Rotation fork: a losing compare-and-set poisons the *next* write *(high — this is the process-replacement finding)*

`integrations/etsy.py::_persisting_on_refresh` guards the first collision with compare-and-set.
Its docstring says the loser "stop[s] claiming to own the stored value — the next write from
this process **adopts** whatever is there rather than fighting over it." The code does the
opposite. `state["expected"] = None` makes the next write **unconditional**, and an
unconditional write replaces whatever is there. Reproduced against the real store:

```
after A            : ***3bedd2a0        (container A won the CAS)
after B conflict   : ***3bedd2a0        (correct: the loser did not overwrite)
after B 2nd refresh: ***a45dfa8f   <-- B silently replaced A's live credential
rotations          : 2                  (nothing in the numbers shows the fork)
```

Two containers overlapping is not hypothetical here: this platform replaces the container
several times an hour, a deploy roll leaves the old one draining, and `Credentials.from_env`
forces a refresh at start-up (`expires_at = 0.0`). Once both sides have lost a claim once,
both write unconditionally and the stored credential is last-writer-wins between two divergent
chains. If Etsy implements refresh-token **reuse detection** — RFC 6819 and OAuth 2.1 both
recommend revoking the whole chain on replay — the losing container's later refresh is a replay
that could revoke the winner's live credential. That is a self-inflicted logout whose only
repair is the owner in a browser.

Repair, §7.3: after a conflict, **re-read the store and adopt**, and keep naming an
expectation. `save_refresh_token` already refuses a write that names a stale token (asserted),
so the whole fix is to stop dropping the name.

### 5b. Refresh failure declares an owner action that may be false *(medium)*

`_token_request` maps 400/401/403 on a refresh to `EtsyAuthNeedsOwner`: *"this needs the owner
to open the authorize URL in a browser and approve the app again. No code path avoids this."*
That is true when the stored credential is dead. It is **false** when only *this process's
in-memory* token is stale — which is exactly the state 5a produces, and the state any container
that lost a race is in. The system would raise an OWNER ACTION REQUIRED while a live,
openable credential sat in `oauth_credentials`.

Etsy does not document what happens when a refresh token is reused or expires (recorded as
UNKNOWN in `ETSY_OAUTH_CALLBACK.md`), so this path must be defensive rather than confident.
Repair, §7.4: before declaring the owner action, re-read the sealed credential; if its
fingerprint differs from the token just tried, adopt it and retry **once**. Never retry with
the same token — that is the replay that risks chain revocation.

### 5c. `key_fingerprint` renders bare on the callback page *(cosmetic, but inconsistent)*

`finish` puts `sealed.key_health(env)` into `Completed.detail` untouched on the `not_stored`
branches, so the page and the audit row show `key_fingerprint: dc4c5d17` — a digest, not the
key, so not a leak. But `configuration()` deliberately strips that exact field and
`credential_health` re-adds it as `***…`. Two of three call sites mark it; one does not, on the
page whose footer promises *"every token on this page is an eight-character SHA-256
fingerprint"*. Diff in §7.5.

### 5d. `opsauth.check` raises `TypeError` on a non-ASCII credential *(low)*

`hmac.compare_digest` on `str` requires ASCII. A presented token containing a smart quote or a
non-breaking space — which is what a copy-paste out of a document produces — raises `TypeError`,
which the three OAuth routes do not catch, so it becomes a 500 with a traceback in
`uvicorn.error` instead of a 401. No secret escapes (a Python traceback carries no locals), but
an operator gets an unexplained 500 and an attacker learns their guess contained a non-ASCII
byte. Diff in §7.6.

### 5e. The OAuth `state` is not registered in `finish`'s redactor

`finish` seeds the redactor with the shared secret, the code and the verifier — not the state.
An Etsy `error_description` echoing the state back would render it on the page and into the
audit row. Low: by that point the state is consumed and single-use, and its fingerprint is
already published deliberately. Recorded, not diffed.

---

## 6. Everything else audited, with the verdict

| path | verdict | evidence |
|---|---|---|
| `core/sealed.py` — seal / unseal | **no leak** | ciphertext contains neither plaintext nor key; context-bound (a verifier's context cannot open a refresh token); `SealBroken` is the same sentence for a wrong key and a wrong context, so it is not an oracle, and it carries no plaintext, key or ciphertext; `from None` suppresses the chained cause |
| `core/sealed.py` — `key_health` | **no leak** | never returns the key; the fingerprint is a digest, not a prefix |
| `core/oauth_store.py` — `Consumed.redacted()` | **no leak** | asserted for all six verdicts: no verifier in any of them |
| `core/oauth_store.py` — `credential_health`, `save_refresh_token` | **no leak** | fingerprints only; `CredentialConflict` names both sides by fingerprint and neither by value |
| `core/oauth_store.py` — state storage | **no leak** | only SHA-256 + fingerprint stored; the state is never readable back out of the database |
| `integrations/etsy_oauth.py` — reprs | **no leak** | `TokenSet`, `OAuthApp`, `Credentials` all fingerprint-only, which is what keeps a token out of a traceback |
| `integrations/http.py` — `Redactor` | **holds, deliberately narrow** | by field name *and* by value; `token_type` and `listing_id` are not eaten, which is why it is a redactor nobody switches off. `TOKEN_SHAPED` is Etsy-shaped only — **and a PKCE verifier is not token-shaped**, so only explicit registration protects it. `finish` does register it; asserted |
| `app/main.py` — callback route | **no leak** | `Completed.detail` is fingerprints by construction; page escapes every value (`error_description` arrives on a URL); `no-store`, `no-referrer`, CSP `default-src 'none'`, `form-action 'none'` |
| `app/main.py` — audit detail construction | cosmetic | the `{k:v for … if k != "tokens"}` / re-add dance is a no-op; `tokens` is already `TokenSet.redacted()`. Harmless, and misleading to a reader who assumes it removes something |
| `app/main.py` — `/health` | **no leak** | `db: f"{type(e).__name__}: {e}"` on an unauthenticated endpoint. Checked against a real failure with a password in the URL: psycopg2 does not echo it. Worth knowing that `continuity.redact` exists if that ever changes |
| `ops/retention.py` | **correct** | `oauth_credentials` in `NEVER_PRUNED_TABLES`, never imported, never deleted; `apply` prunes handshakes only, through `oauth_store.prune_handshakes` |
| handshake retention | **correct, with a pinned residual** | a live handshake is never deleted at any age (asserted at 29 and 31 days); a spent one is kept 30 days and a replay inside the window is answered `state_replayed`; **beyond the window it reads `state_unknown`** — still refused, for a vaguer reason. Pinned as a test so the trade-off stays deliberate |
| process replacement | **correct** | a handshake opened by one process is closed by another and cannot be closed twice; a credential sealed by one process opens in the next and **does not open without the key**, which is what makes the database half not a credential; `openable` distinguishes stored from stored-and-we-still-hold-the-key |
| spend on the new paths | **CA$0, measured** | no `CostEntry` written by either path; no OAuth module imports the gateway or calls a provider method; `test_model_spend_paths.scan_tree()` re-run — the unguarded set is still exactly `KNOWN_UNGUARDED`, no new entries; `finish` is named `finish` so that scanner needs no exclusion here |
| `core/backup.py` | **recorded, unchanged** | `pg_dump` carries `oauth_credentials` as ciphertext, so that backup's security is the sealing key's. Note that the two leaks above are *not* ciphertext in that dump |

---

## 7. Exact diffs for Lane A

Proposed, not applied. Line context is from the files as of this commit.

### 7.1 `src/brambleloop/integrations/etsy_oauth.py` — redact Etsy's words before they become an exception

```diff
@@ def _token_request(transport: Transport, app: OAuthApp, form: dict[str, str], *,
     body = getattr(last, "body", {}) or {}
     status = getattr(last, "status", 0)
     if status >= 400:
-        detail = body.get("error_description") or body.get("error") or body
+        # Etsy's own words, and an error body has been observed echoing back the credential
+        # that was sent to it (`tests/fake_etsy.py::echo_token_in_error`). On the callback
+        # this message is caught by `etsy_authorise.finish` and redacted there; on the
+        # REFRESH grant nothing catches it, and `runtime.worker` writes `str(e)` into an
+        # AuditLog row and into Job.last_error -- both of which are in the continuity export
+        # and in pg_dump, in the clear. So the redaction happens where the message is built,
+        # once, rather than at each of the places a message ends up.
+        from .http import SECRET_KEYS, Redactor
+
+        # Seeded from the SENSITIVE form fields only. `form.values()` would also register
+        # `grant_type` ("refresh_token") and `client_id`, and a redactor that replaces the
+        # literal word `refresh_token` in its own error message is one somebody switches off
+        # -- the same argument `SECRET_KEYS` already makes about `token_type`.
+        _redactor = Redactor(v for k, v in form.items() if k.lower() in SECRET_KEYS)
+        detail = body.get("error_description") or body.get("error") or body
+        detail = _redactor.string(str(detail))[:400]
         if status in (400, 401, 403):
```

The seeding registers exactly the secrets this request is holding — the refresh token, or the
code and the verifier — and `Redactor.string` additionally catches any Etsy-shaped token by
shape with nothing registered at all. Both halves are asserted in
`test_oauth_security_audit.py`, and the seeded-vs-unseeded difference was measured:

```
message : refresh token 111111.rYQ6bF3k9sZ2wQ8t... already used
tight   : refresh token ***a67460a2 already used
naive   : {'submitted': {'***6c8a7d4a': '***a67460a2'}, 'grant_type': '***6c8a7d4a'}   <- do not
```

The import is local to match the file's existing style and to keep `http` out of module load.

Worth doing at the same time, in `runtime/worker.py`, as defence in depth — the worker is the
generic sink and should not depend on every raiser remembering:

```diff
@@ class Worker
         except Exception as e:  # noqa: BLE001 - a worker must survive any handler
+            from ..integrations.http import Redactor
+
+            _scrub = Redactor().string
             _note_funding(self.db, str(e))
-            self.queue.fail(job.id, f"{type(e).__name__}: {e}\n{traceback.format_exc()[:2000]}")
+            self.queue.fail(job.id, _scrub(
+                f"{type(e).__name__}: {e}\n{traceback.format_exc()[:2000]}"))
             self.agents.audit(job.agent, "job.failed", job_id=job.id, phase=self.phase,
-                              detail={"error": str(e)})
+                              detail={"error": _scrub(str(e))})
```

(`runtime/worker.py` is not in this lane's list either; flagged for whoever owns it.)

### 7.2 `src/brambleloop/app/access_log.py` — close the encoded-name bypass

```diff
-_PARAM = re.compile(r"([?&])([A-Za-z0-9_.\-]{1,64})=([^&\s\"']*)")
+# `%` is in the NAME class on purpose. Starlette reads the query with `parse_qsl`, which
+# percent-decodes the parameter name as well as the value, so `%63ode=` is `code=` to the
+# application. A scrubber that matches only the literal spelling is walked around by the
+# encoded one, and the application still honours it.
+_PARAM = re.compile(r"([?&])([A-Za-z0-9_.%\-]{1,64})=([^&\s\"']*)")
@@ def scrub_query(text: str) -> str:
     def one(match: re.Match) -> str:
         sep, name, value = match.group(1), match.group(2), match.group(3)
-        if name.strip().lower() not in SCRUBBED_QUERY_KEYS or not value:
+        # The NAME is decoded before it is looked up; the VALUE is not. The value is
+        # fingerprinted, and fingerprinting the bytes that were actually on the wire is the
+        # honest thing to do.
+        if urllib.parse.unquote(name).strip().lower() not in SCRUBBED_QUERY_KEYS or not value:
             return match.group(0)
         return f"{sep}{name}=***{fingerprint(value)}"
```

plus `import urllib.parse` at the top. Both halves are needed and each is separately asserted:
widening the charset without decoding scrubs nothing, and decoding without widening never runs.
The ordinary request line comes out byte-identical either way.

### 7.3 `src/brambleloop/integrations/etsy.py` — a lost claim must not become an unconditional write

```diff
         except oauth_store.CredentialConflict:
-            state["expected"] = None
+            # ADOPT, which is what the docstring above says and what the code did not do.
+            # Setting the expectation to None makes the NEXT write unconditional, and an
+            # unconditional write replaces the winner's live credential with this process's
+            # divergent chain -- silently, with the rotation count still climbing. Re-read the
+            # row instead and keep naming what is there, so a later write from this process
+            # is refused rather than allowed to win by being last.
+            stored = oauth_store.load_refresh_token(db, env=env)
+            state["expected"] = sealed.fingerprint(stored) if stored else None
             log.warning(
                 "etsy refresh token was rotated by another worker first; this process kept "
                 "its access token and did not overwrite the stored credential")
```

### 7.4 `src/brambleloop/integrations/etsy_oauth.py` — do not declare an owner action on a stale in-memory token

Etsy does not document refresh-token reuse, so this is defensive by construction: re-read the
store once before concluding the credential is dead, and **never** retry with the same token.

```diff
@@ class TokenProvider
     def _refresh_now(self) -> None:
         assert self.tokens is not None
-        fresh = refresh(self.transport, self.app, self.tokens.refresh_token)
+        try:
+            fresh = refresh(self.transport, self.app, self.tokens.refresh_token)
+        except EtsyAuthNeedsOwner:
+            # "The owner must authorise again in a browser" is true when the STORED
+            # credential is dead and false when only this process's copy is stale -- which is
+            # what a lost rotation race leaves behind. Ask the store once. A different token
+            # there is a different fact, and it is worth one attempt. The same token there is
+            # the genuine article and is NOT retried: re-presenting a spent refresh token is
+            # a replay, and a provider with reuse detection answers a replay by revoking the
+            # whole chain.
+            adopted = self.adopt() if self.adopt is not None else None
+            if not adopted or adopted == self.tokens.refresh_token:
+                raise
+            fresh = refresh(self.transport, self.app, adopted)
         rotated = fresh.refresh_token != self.tokens.refresh_token
```

with `adopt: Callable[[], str | None] | None = None` added to the dataclass beside
`on_refresh`, and `Credentials.from_env` passing
`adopt=lambda: oauth_store.load_refresh_token(db, env=e)` in the same block where it already
builds `on_refresh`. Keeping it a callback preserves the module's rule that where a secret is
persisted is a deployment decision and not this file's.

### 7.5 `src/brambleloop/integrations/etsy_authorise.py` — mark the key fingerprint like every other one

Two sites, both `"sealing_key": sealed.key_health(env)`:

```diff
-        return _outcome("not_stored", detail={**base, "sealing_key": sealed.key_health(env)})
+        return _outcome("not_stored", detail={**base, "sealing_key": _key_facts(env)})
```

```diff
         return _outcome("not_stored", detail={
             **base, "error_class": type(exc).__name__,
-            "sealing_key": sealed.key_health(env)})
+            "sealing_key": _key_facts(env)})
```

with, beside `_outcome`:

```python
def _key_facts(env: dict[str, str] | None) -> dict:
    """`key_health` with the fingerprint marked, the way every other report marks one.

    The page's footer promises that every token on it is an eight-character fingerprint, so an
    unmarked one reads like a value. `configuration()` strips this field and
    `credential_health` marks it; this is the third site and it did neither.
    """
    key = sealed.key_health(env)
    return {**{k: v for k, v in key.items() if k != "key_fingerprint"},
            "fingerprint": f"***{key['key_fingerprint']}"}
```

### 7.6 `src/brambleloop/core/opsauth.py` — a non-ASCII credential is a refusal, not a 500

```diff
     supplied = (presented or "").strip()
     if supplied.lower().startswith("bearer "):
         supplied = supplied[7:].strip()
-    if not supplied or not hmac.compare_digest(supplied, expected):
+    # Compared as bytes. `compare_digest` on `str` refuses anything non-ASCII with a
+    # TypeError, which no route catches, so a credential pasted with a smart quote or a
+    # non-breaking space became a 500 with a traceback instead of a 401. Still constant-time.
+    if not supplied or not hmac.compare_digest(supplied.encode("utf-8"),
+                                               expected.encode("utf-8")):
         raise OpsAuthRefused("operator credential rejected")
```

---

## 8. UNKNOWN, and what would settle each

| unknown | what would settle it |
|---|---|
| Whether Etsy revokes the whole refresh chain when a spent refresh token is replayed | Not documented. One deliberate experiment after the credential is safe to spend: authorise, refresh once, then present the *old* refresh token, then check whether the *new* one still works. Costs one re-authorisation if the answer is yes. Until then §7.4 assumes it does, which is the safe assumption |
| Whether Etsy's error bodies actually echo the submitted token | Not observable without a real failing refresh. §7.1 does not depend on the answer: it costs one line and removes the question |
| Whether any intermediary in front of this deployment logs the request line | Unreachable from here. Bounded by the code being single-use, short-lived and useless without the verifier |
| Whether `rotations` ever reaches 1 with the credential still openable | The rotation fix is still unproven in production (`rotations: 0`). §7.3 and §7.4 change what happens at the *first* rotation, so they should land before it, not after |
| The authorization code's lifetime and single-use property | Etsy does not state them; that is RFC 6749. Already recorded as UNKNOWN in `ETSY_OAUTH_CALLBACK.md` and not re-litigated here |

---

## 9. One thing recorded but not proposed

`core/sealed.py` derives the AES key with a single `sha256(domain + passphrase)`. That is fine
for 32+ characters of CSPRNG output, which is what the owner generated. It is not a slow KDF,
so a *low-entropy* passphrase of the same length would be brute-forceable offline from a
database dump. Changing it means a new `SEAL_VERSION` and a re-seal of the one live credential
row — a deliberate migration, not a patch — and the current key is not low-entropy. Recorded
here so the next person who reads `MIN_KEY_LENGTH = 32` and thinks "passphrase" knows the
constraint is entropy and not length.

---

## 10. Status

* Committed on this lane's branch. **Not pushed, not merged.**
* CA$0. No model call, no image generation, no network request to Etsy or anywhere else.
* No credential sought, printed or used. Every secret in the tests is an invented literal.
* No check weakened. Two new states were added to `ops/board.py` and `ops/registry.py`, both
  in `needs_attention` and neither in `refillable`.
* No file outside `ops/**` and this lane's own tests and research notes was edited. The six
  diffs above are for Lane A and `runtime/worker.py`'s owner to apply or refuse.
