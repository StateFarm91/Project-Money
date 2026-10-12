"""Public interface: `brambleloop.laura.identity` (wave 3 lane D).

Re-exports the canonical identity API from `laura.core.identity` so consumers (Command Center
lane F, store copy lanes) import one stable path:

    from brambleloop.laura import identity
    identity.load(db)            # verified current record (dict)
    identity.current(db)         # {"version", "sha256", "record", ...}
    identity.genesis()           # frozen version 1; identity.record() = genesis + amendments
    identity.public_profile()    # what any surface may say about her (no private content)
    identity.voice_lint(text)    # public/business-register check
    identity.summary(db)         # Command Center provider contract
"""
from .core.identity import (AUTHORISED_IDENTITY_AMENDMENTS, AUTHORITY, CHARTER,  # noqa: F401
                            CONSTITUTION, CURRENT_SHA256, FOUNDER_RULING_TEXT, GENESIS_SHA256,
                            IDENTITY_KEY, OWNER_CONTROLLED_FIELDS, PUBLIC_VOICE,
                            RECORDED_AMENDMENTS, IdentityRefused, IdentityTampered, amend,
                            current, decision_recorded, ensure, genesis, load, public_profile,
                            record, sha256_of, summary, voice_lint)

# The current visual identity (laura-r2-a42aeac7 since the D-FB-14 amendment), not genesis's.
VISUAL_IDENTITY_ID = record()["visual_identity"]["identity_id"]
