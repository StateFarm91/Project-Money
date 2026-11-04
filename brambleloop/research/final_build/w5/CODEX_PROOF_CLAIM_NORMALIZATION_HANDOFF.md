# Product Truth proof-claim normalization

Based on the isolated safety preview at `6cb70e3`. The existing proof ladder maps `test crocheted` to physical tester evidence, but the first-customer listing gate previously let `test-crocheted` through without that evidence. The existing `tested` substring already caught `maker-tested`.

The existing claim phrases and listing copy are now folded consistently and punctuation is treated as spacing before comparison. This changes no proof thresholds or authority. It can conservatively match negated or otherwise contextual phrases, as the existing substring rule already did. It is a finite phrase matcher, not a semantic classifier; other paraphrases, evidence authenticity, A6/A9 authority and concurrent-writer fencing remain open.

Synthetic tests exercise the first-customer listing gate with and without the physical-evidence flag and the actual `gate.certify` Worker, confirming the unproved stored copy is blocked and audited. The flag is only a test fixture, not physical proof. No purchase, publication, deployment, or real tester sample was created.
