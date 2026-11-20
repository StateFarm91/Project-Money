"""The company authority model (wave-3 cluster K11: F-497 F-658 F-669 F-700 F-702 F-703
F-708 F-721 F-743).

* `classes`      -- every action classified OBSERVE..CREDENTIALS; build vs operate planes.
* `policy`       -- the owner's AuthorityPolicy rows, the earned-autonomy ladder and the
                    dispatch check `agents.registry.Registry.authorize` calls for every job.
* `dag`          -- the durable company work DAG: dependencies, priority, ownership,
                    authority state (AWAITING_APPROVAL blocks only dependants) and completion
                    evidence, recomputed by every COO orchestrator tick.
* `constitution` -- the Brambleloop Constitution (F-700) as one check.

Everything here fails closed: an unreadable policy, an unclassifiable consequential action or
an unverifiable owner refuses.
"""
