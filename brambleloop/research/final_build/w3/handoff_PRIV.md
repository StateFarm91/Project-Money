# Handoff — lane PRIV: owner-only private context, security infrastructure only

Branch `claude/w3-PRIV`, based on `claude/visual-investigation` (as instructed by the integrator).
Requirement source: `spec/07_Laura_Owner_Ruling_2026-10-06.md` (isolation and access-control
parts: owner correction items, Ruling 2). Everything is tested with neutral sentinels
(`PRIV-SENTINEL-000n`, `PRIV-LABEL-n`). The repo contains no personal, romantic or intimate content.

## GATED (open, not implemented)
**The conversational persona/register for the private context is NOT implemented. It stays an
explicitly GATED requirement.** This lane does not generate, prompt, template or style any
private conversation. It only stores, protects and returns owner-supplied text and genuine
interaction turns. Wiring a model to produce `laura` turns needs its own owner-approved lane.
That lane must follow the provider's usage policies (spec/07 integrator note a), and it must
record each reply through `store.record_turn(..., role="laura", reply_to=<owner turn>,
model_ref=...)`, the only way a reply can enter history.

## Requirements and status
| # | Requirement | Status | Where / proof |
|---|---|---|---|
| 1 | Separate store, encrypted at rest, key from `BRAMBLELOOP_PRIVATE_MEMORY_KEY`, refuse without key | COMPLETE | `laura/private/{models,crypto,store}.py`. Tables `laura_private_entries/_grants/_access` sit on their **own** metadata, not `core.db.Base` and not `company_memory`. Encryption is AES-256-GCM from `cryptography` 50.0.1, which is already in the venv, with a random 96-bit nonce per record. Record metadata is bound as AAD. Sub-keys are HKDF-SHA256 derived (enc / blind-index / principal-tag / key-id). Fact keys, roles, model refs and sources are all inside the ciphertext. A key that is missing, not base64, under 32 bytes or one repeated byte gives `KeyUnavailable`. There is no plaintext fallback. |
| 2 | Access only for a verified, unexpired, unrevoked owner session explicitly flagged private | COMPLETE (infra), needs F wiring | `access.py`: `open_context(db, sid, flag=PRIVATE_FLAG)` needs a live session plus a fresh step-up. Each call re-verifies the exact type, the HMAC tag, the grant (session match, key, revoked, TTL 30 min ≤ session expiry) and the owner session. All other principals are refused, including a verified business `Principal.owner`. |
| 3 | Provenance: owner_supplied or genuine interaction only | COMPLETE | `store.py`. `generated=True` and any other provenance are refused. An interaction fact must quote a cited existing turn word for word. A `laura` turn must answer an owner turn from the same live grant, once, and name its model. No parameter accepts a date or an author. |
| 4 | No influence on protected decisions | COMPLETE (API + import proof); call sites need wiring | `firewall.py` is stdlib only: `reject_private`, `@guard`, fail-closed depth. Static AST and runtime subprocess tests show that finance/, gates/, quality/, cir/, security/auth/approvals/emergency, authority APIs, funding, credentials, provider accounts and ads_readiness never import or load the private API. |
| 5 | No ordinary logging | COMPLETE | The store writes only its own tables. Refusals go to `laura_private_access` (op/outcome/class name only). Tests check no sentinel in Python logging at DEBUG (SQLAlchemy included), stdout/stderr, exceptions, any `Base` table or the continuity export. Row counts of audit_log, company_timeline, company_memory, cc_notifications and cc_security_events stay unchanged. `PrivateValue` renders `[private]` in str/repr/format. `json.dumps` and pickle refuse it. |
| 6 | Continuity across restart / model swap | COMPLETE | Tested with a new engine and a new session/grant on the same file, with turns from two different `model_ref`s. Without the key after restart nothing decrypts. `sealed_export`/`restore_sealed` produce an owner-held, ciphertext-only backup. Restore authenticates every row, is idempotent, and refuses on a wrong key. |
| 7 | Adversarial leak tests | COMPLETE | `test_w3_priv_leak.py`: store preview (4 renders + summary), all CC tabs incl. account and notifications, every `providers.PROVIDERS` entry, 9 Ask Company questions incl. probing ones, support drafts, seo summary/next_work, ads summary/proposals, autonomy timeline, business memory, continuity export. The SQL watch shows zero `laura_private` statements, and it has a positive control. |

## Files
New: `src/brambleloop/laura/private/{__init__,values,firewall,errors,crypto,models,access,store,_testkit}.py`;
tests `tests/test_w3_priv_{store,access,provenance,firewall,continuity,leak}.py` (these reuse
`tests/w3_laura_memory_harness.py` read-only). No shared files edited.

## Tests (each run: `cd brambleloop && PYTHONPATH=src /home/user/Project-Money/brambleloop/.venv/bin/python tests/test_w3_priv_<x>.py`)
store 8 OK · access 7 OK · provenance 7 OK · firewall 7 OK · continuity 3 OK · leak 7 OK = **39 OK, 0 FAIL**.
Also re-ran `test_vacuity.py` and `test_secret_scan.py` (0 FAIL) and `test_w3_laura_memory_isolation.py` (0 FAIL).

## Contract for lane F (WIRING REQUESTS — lane F owns app/command_center/**)
Full text is in the `access.py` docstring. Summary:
1. Add a new module **`brambleloop.app.command_center.private_context`**. It is the only
   non-private module allowed to import `laura.private.{access,store}` or call `.reveal()`
   (`access.ALLOWED_IMPORTERS`; static test enforced).
2. Add `POST /cc/api/private/open` (owner auth + CSRF). It requires a fresh step-up and calls
   `access.open_context(db, session.public_id, flag=access.PRIVATE_FLAG)`. Keep `grant_id`
   server-side and rebuild with `access.resume(db, sid, grant_id)` on each request. Map
   `PrivateAccessRefused` to 403 and `KeyUnavailable` to 503, with generic text.
3. Private routes (`GET /cc/api/private/facts|conversation`, `POST .../remember|turn|forget|close`):
   `Cache-Control: no-store`. Reveal values only in that response body. Never send them to
   notifications, the timeline, audit detail, Ask Company or provider summaries.
4. On logout and in `auth.revoke_session`, call `access.revoke_session_contexts(db, public_id)`.
5. Security events for refusals: kind `private_context`, reason = exception class name only.
6. A status badge may use `store.configured()` (bool, non-content).
7. Protected-path call sites (WIRING REQUEST to finance/E, Product Truth, security/F, spend/SPEND,
   legal owners): call `firewall.reject_private(input, context="<finance|spend|...>")` at
   entry points that take external or agent-supplied input. The import is stdlib only and safe.

## Owner action (deploy-time only, not needed for tests)
Set `BRAMBLELOOP_PRIVATE_MEMORY_KEY` (32 random bytes, base64) as a Railway secret, and keep
an offline copy. **Losing the key loses the private store by design.** Cost CA$0, about 5 minutes. Until it is set,
the private context refuses everything and nothing else is affected.

## Open defects / limits / not verified
- The firewall works by tags. Plaintext obtained through an explicit `.reveal()` carries no tag. That risk
  is contained because only the allowlisted module may call `.reveal()`, and that is statically
  checked. Protected modules do not call the firewall yet; see wiring item 7.
- In-process Python can always open the DB directly. Encryption plus the key-bound tag mean
  forged principals and raw rows are useless without the key. No HSM/KMS is used.
- There is no key rotation API yet; rotation means sealed export, then re-key, then re-entry. This is an open item.
- Postgres is not exercised. The tests run on SQLite only, though the types are portable.
- The step-up freshness rule relies on lane F's `stepup_until` semantics. The HTTP routes do not exist yet.
