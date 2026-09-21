"""The durable half of the canonical model, and the gate that actually blocks (#200, #201).

`visual/identity.py` had the whole design: two states with no path between them that does not
go through the owner, a reference pack that pins the fields which drift, and a drift check
that reports `unavailable` rather than passing when it has nothing to compare against.

It had no callers. Not one, anywhere in the codebase.

That is this build's most familiar failure in its most flattering disguise: a table nothing
reads is documentation, and a gate nothing invokes is a good intention with tests. The module
would have gone on being correct and unconsulted while the first model-bearing listing shipped
past it.

So this module is only the two joins that were missing.

**Persistence.** A pack held in memory is gone after the next deploy, and a canonical model
who disappears on a redeploy is not locked to anything. Candidates and the frozen pack live in
`model_identities`, and `select` still refuses to promote one without the owner.

**The release join.** `gate_frames` is called from the listing-image build, and it blocks a
model-bearing frame whose identity cannot be verified. With no canonical pack that is every
model-bearing frame, which is correct: #201 makes drift a release-blocking defect, and the
moment the check is allowed to shrug is the moment it stops being one. Frames that carry no
model are untouched, so a catalogue of product-only renders is unaffected until the day the
first model frame is built -- which is exactly when this has to bite.
"""
from __future__ import annotations

from ..core.resilience import PermanentError, TransientError
from . import identity

# What the observer is asked to read off a rendered face. Deliberately the drift dimensions
# rather than the full pack: the pack is what the owner approved, and this is what a single
# image can be asked about without inventing detail.
OBSERVE_FIELDS: tuple[str, ...] = identity.DRIFT_DIMENSIONS

TASK = "asset_inspection"
OBSERVE_MAX_TOKENS = 300

OBSERVE_SYSTEM = (
    "You are describing one person in a photograph so that the same person can be recognised "
    "in another photograph. Describe only what is visible. Use short, literal phrases."
)


class RegistryRefused(ValueError):
    """A write that would let an identity be chosen by something other than the owner."""


# ---------------------------------------------------------------------------
# Persistence


def _row_to_pack(row) -> identity.ReferencePack:
    return identity.ReferencePack(version=row.version, fields=dict(row.fields or {}),
                                  approved_by_owner_at=row.approved_by_owner_at)


def packs(db) -> list[identity.ReferencePack]:
    from sqlalchemy import select

    from ..core.models import ModelIdentity

    with db.session() as s:
        rows = list(s.scalars(select(ModelIdentity).where(
            ModelIdentity.state == identity.CANONICAL)))
        return [_row_to_pack(r) for r in rows if r.approved_by_owner_at]


def canonical_pack(db) -> identity.ReferencePack | None:
    return identity.canonical(packs(db))


def candidates(db) -> list[identity.Candidate]:
    from sqlalchemy import select

    from ..core.models import ModelIdentity

    with db.session() as s:
        rows = list(s.scalars(select(ModelIdentity).where(
            ModelIdentity.state == identity.CANDIDATE)))
        return [identity.Candidate(key=r.key, fields=dict(r.fields or {}), state=r.state,
                                   note=r.note) for r in rows]


def record_candidate(db, key: str, *, fields: dict, image_refs: list[str] | None = None,
                     note: str = "") -> int:
    """Store one generated face. A candidate, and nothing more."""
    from sqlalchemy import select

    from ..core.models import ModelIdentity

    with db.session() as s:
        row = s.scalar(select(ModelIdentity).where(ModelIdentity.key == key))
        if row is None:
            row = ModelIdentity(key=key)
            s.add(row)
        if row.state == identity.CANONICAL:
            raise RegistryRefused(
                f"{key!r} is the canonical identity. Rewriting her as a candidate is a "
                f"redesign wearing an import's clothes (#200)")
        row.state = identity.CANDIDATE
        row.fields = dict(fields or {})
        row.image_refs = list(image_refs or [])
        row.note = note or row.note
        s.flush()
        return row.id


def select_canonical(db, key: str, *, owner_approved: bool) -> identity.ReferencePack:
    """Freeze one candidate. Refuses without the owner, and refuses a second."""
    from sqlalchemy import select

    from ..core.models import ModelIdentity

    existing = canonical_pack(db)
    with db.session() as s:
        row = s.scalar(select(ModelIdentity).where(ModelIdentity.key == key))
        if row is None:
            raise RegistryRefused(f"no candidate {key!r} has been recorded")
        candidate = identity.Candidate(key=row.key, fields=dict(row.fields or {}),
                                       state=row.state, note=row.note)
        pack = identity.select(candidate, owner_approved=owner_approved, existing=existing)
        row.state = identity.CANONICAL
        row.version = pack.version
        row.approved_by_owner_at = pack.approved_by_owner_at
        return pack


# ---------------------------------------------------------------------------
# Observation


def observe_prompt() -> str:
    return (
        "Reply with a single JSON object and nothing else, one key per item below, each a "
        "short literal phrase. If the photograph contains no person, reply exactly "
        '{"no_person": true}.\n\n'
        + "\n".join(f"- {f}" for f in OBSERVE_FIELDS))


def observe(db, image_ref: str, *, provider=None) -> dict:
    """Read the drift dimensions off one rendered face.

    Routed through the task table like every other model call, and billed. Returns an empty
    dict when nothing could be read -- which `drift_check` treats as maximum drift, because
    an unmeasured dimension is not a matching one.
    """
    import json

    from ..finance import spend_report
    from ..gateway import anthropic as gw

    provider = provider or gw.provider_for(TASK)
    try:
        response = provider.see(OBSERVE_SYSTEM, observe_prompt(), [image_ref],
                                max_tokens=OBSERVE_MAX_TOKENS)
    except (PermanentError, TransientError) as exc:
        return {"error": str(exc)[:200]}

    if db is not None:
        spend_report.record(
            db, agent="quality_director",
            amount_cad=round(
                response.input_tokens * provider.cost_per_1k_input_cad / 1000
                + response.output_tokens * provider.cost_per_1k_output_cad / 1000, 8),
            purpose=TASK, provider="anthropic", model=provider.model,
            department="quality", tokens_in=response.input_tokens,
            tokens_out=response.output_tokens, detail={"price_basis": "assumed"})

    body = (response.text or "").strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        parsed = json.loads(body)
    except ValueError:
        return {"error": f"the observer did not answer with JSON: {body[:120]!r}"}
    if not isinstance(parsed, dict):
        return {"error": "the observer answered with something that is not an object"}
    return parsed


# ---------------------------------------------------------------------------
# The gate (#201)


def gate_frames(db, frames: list[dict], *, observer=None) -> dict:
    """Block model-bearing frames whose identity cannot be verified.

    `frames` are dicts carrying at least `role` and `has_model`, and `image_ref` when there
    is a file to look at. Frames with no model are not examined at all -- a product-only
    render has no identity to drift.
    """
    modelled = [f for f in frames if f.get("has_model")]
    if not modelled:
        return {"checked": 0, "blocking": [], "verdict": "not_applicable",
                "why": ("no frame in this listing carries the model, so there is no identity "
                        "to drift. A product-only render is not waved through; it is not "
                        "asked")}

    pack = canonical_pack(db)
    if pack is None:
        return {
            "checked": len(modelled), "verdict": "unavailable",
            "blocking": [f"{f.get('role', '?')}: no canonical model has been selected"
                         for f in modelled],
            "why": ("#201 makes drift a release-blocking defect, and drift is measured "
                    "against a reference pack. With no pack every model-bearing frame is "
                    "unverifiable, and unverifiable is not a pass -- the moment this check "
                    "is allowed to shrug is the moment it stops being a check"),
        }

    blocking: list[str] = []
    results: list[dict] = []
    for frame in modelled:
        ref = frame.get("image_ref") or ""
        seen = (observer or observe)(db, ref) if ref else {"error": "no image to look at"}
        verdict = identity.drift_check(seen, pack)
        results.append({"role": frame.get("role"), "verdict": verdict["verdict"],
                        "failed": verdict.get("failed", []),
                        "observation_error": seen.get("error", "")})
        if verdict["blocks_release"]:
            blocking.append(f"{frame.get('role', '?')}: {verdict['reason'] or 'unverifiable'}")

    return {"checked": len(modelled), "results": results, "blocking": blocking,
            "verdict": "pass" if not blocking else "fail",
            "pack_version": pack.version}


def state(db) -> dict:
    """What the identity system is, read from rows rather than asserted."""
    pack = canonical_pack(db)
    return {
        **identity.status(packs(db), candidates(db)),
        "persisted": True,
        "gate_is_wired": True,
        "what_blocks_today": (
            "every model-bearing frame, because no canonical model has been selected"
            if pack is None else
            f"a model-bearing frame that drifts from pack version {pack.version}"),
    }
