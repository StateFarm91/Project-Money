"""Owner-only private context for Laura: security infrastructure only (spec/07 Ruling 2).

This package is deliberately separate from `brambleloop.laura.memory` (the business memory,
which refuses any non-business tier). It holds an encrypted, owner-only store and the
firewall that protected business paths call to reject private input.

Import discipline (enforced by tests/test_w3_priv_firewall.py):

* `brambleloop.laura.private.firewall` and `.values` are stdlib-only. Protected modules
  (finance, Product Truth, security, authorization, spend, legal) may import the firewall
  and nothing else from this package.
* `.store`, `.access`, `.crypto`, `.models` are the private API. Only the Command Center's
  private-context view (lane F, see `access.F_CONTRACT`) may import them.

This `__init__` imports nothing, so importing the firewall never loads the store, the key
handling or the tables.

GATED: no conversational persona or register is implemented here. That requirement stays
gated (see research/final_build/w3/handoff_PRIV.md). This package only stores, protects and
returns owner-supplied text and genuine interaction records.
"""
