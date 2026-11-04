# A6 ledger transaction composition: review only

`GrantLedger.refusal_in_session` reads one family snapshot using a caller-owned
SQLAlchemy session. The check refuses missing grants, invalid family chains,
revocations, and inconsistent revocation identifiers. It does not change the
existing `refusal` API and no production handler calls it.

Python 3.11, file-backed SQLite: `PYTHONPATH=src python -m pytest -q
tests/test_codex_sealed_chain_session.py` passed 2/2. A separate reviewer reran
the tests after finding an inconsistent-revocation case, which now refuses.

**Not an authority or evidence fence. Do not integrate A6 on this basis.**
The caller must authenticate the signed grant content, establish its independent
trusted current anchor, and keep all relevant evidence stable through the action.
Family selection uses mutable `audit_log.action`; hiding or deleting the latest
family row is not detected by the existing chain alone. It is not protected by a
DB-enforced append-only policy. No identified external monotonic anchor or
protected family registry exists in this branch. Snapshot isolation, locking,
transaction retry, and incident handling remain the caller's responsibility.

An owner step-up protects the Command Center route, but legacy Learning approval
rows are unsigned. No existing approval is automatically made authentic by this
helper; a reviewed authority model and explicit owner reapproval/migration are
required. The web-only Ed25519 pattern in `ops/storefront_authority.py` is a
possible component, subject to its process-separation and tail-truncation limits.
No credential, approval, deployment, or production configuration was changed.
