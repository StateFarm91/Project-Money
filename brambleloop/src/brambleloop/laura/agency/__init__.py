"""Laura's agency in the Owner Command Center (W3 lane F): "Talk to Laura".

* `talk.converse(db, question)` -- a business question answered as Laura from durable,
  source-linked evidence (UNKNOWN when evidence is missing), persisted as a turn.
* `talk.overview(db)` / `talk.history(db)` -- the Laura view's header and conversation.
* `followon.create(db, turn_id, proposal_key, ...)` -- authorised follow-on work: GREEN
  internal missions through the COO orchestrator; protected work becomes an owner action
  (step-up), never a job.
* `identity_view.identity()` / `portrait()` -- read-only view of Laura's canonical identity
  (lane D `laura.identity` when merged, else the owner-ruled constants) and her internal,
  labelled canonical portrait.

HTTP: `/api/cc/laura/*` in `app/command_center/api.py` (owner session + CSRF + nonce, step-up
for protected follow-ons). Business register only; no private-register code lives here.
"""
