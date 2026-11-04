# Traffic trust proof: isolated review candidate

Bare passed flags, owner-made samples and duplicate/unlinked sale ledger rows
could previously count toward the legitimate-proof rung. This candidate
conservatively counts one recorded reference per eligible tester or buyer.
It withholds incomplete/owner-made physical tests and requires a full-make PASS,
recorded independent agreement, matching source snapshot and content hash. It
withholds unbacked, ambiguous, voided or inconsistent sales and requires a
countable order linked to matching measured receipt-ledger facts.
`growth_ops.proof_sweep` now skips ineligible evidence instead of treating it as
proof or failing the whole sweep. These checks do not send messages or authorize
or activate paid traffic.

The PHYSFIX-owned `quality/physical.py` recorder now stores a SHA-256 of the
agreement source in new test records. Legacy records lacking that snapshot are
withheld; no old record is automatically reauthorized. A hash of guessable source
text is **not** confidentiality, authentication, or proof of a real person.
Changing this Main-owned shared file requires PHYSFIX owner and integration
review. The stricter predicate may hold legitimate legacy evidence until an
authorized evidence workflow establishes the missing binding.

Python 3.11 focused SQLite tests passed 16/16, including the real trust gate,
the existing tester-agreement and physical-record functions with synthetic
fixtures, duplicate/unbound rows, consent-source changes, and the PHYSFIX
agreement regression. Independent review reran trust/proof tests 15/15. A
broader physical/risk run was interrupted after 27 passes and is **not** a
suite pass. All tests were local and no physical evidence was fabricated in
production.

**Do not integrate or treat this as an authority fence.** Recorded identities,
agreements and receipts are not independently authenticated here. Reads and
proof-audit issuance span transactions; concurrent mutation or revocation can
race the check, and concurrent sweeps can duplicate proof audits. The current
agreement reader does not itself establish a revocation model. No PostgreSQL
or complete downstream regression was performed. Revalidating each proof in a
large sweep also needs performance review. Existing spending/owner gates remain
in force and no paid provider was called or activated.
