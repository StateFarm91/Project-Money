"""Public interface: `brambleloop.laura.executive` (wave 3 lane D) -- Laura's Founder/CEO layer.

    from brambleloop.laura import executive
    executive.tick(db, queue=None, now=None) -> report dict   # one executive pass
    executive.summary(db)        # Command Center provider contract (status/as_of/basis/items)
    executive.priorities(db, status=None, limit=50)
    executive.history(db, limit=50, kind=None)   # her durable decisions (real actions only)
    executive.observe(db)        # the company state she reads
    executive.results_wake(db, queue)            # results -> Laura event wake
    executive.EXEC_JOB           # "laura.executive_tick" (cadence `laura_executive`)

Constitution (Finance / Product Truth / Security can block her):
    from brambleloop.laura.core import constitution
    constitution.review(db, proposal); constitution.challenge(db, raised_by=..., reason=...)
"""
from .loop import (EXEC_JOB, LAURA_AGENT, Priority, cognition, history,  # noqa: F401
                   observe, prioritise, priorities, results_wake, summary, tick)
