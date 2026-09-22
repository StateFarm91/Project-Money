"""Turning an approved reference pack into the frozen canonical identity (#200).

The owner approved the revised pack on 2026-09-22. This is the one path from "measured and
presented" to "canonical", and it is deliberately narrow, because everything downstream
treats the frozen pack as the definition of a person: `drift_check` compares against it and
`gate_frames` blocks customer-facing frames that disagree with it.

Three rules, and the first is the one that made this module necessary rather than a call.

**A pack with an unpinned required dimension cannot be frozen, approval or no approval.**
The newest pack on file when the approval arrived -- v16 -- had `bust: unmeasurable`. Freezing
it would have written an identity whose chest has no stated value, and then every future
comparison against that field would have had nothing to compare to. The owner's own
instruction in the same message is that unmeasurable never becomes pass, and a frozen floor
with a hole in it is that failure made permanent: not a wrong verdict once, but a dimension
that can never fail again. So the freeze reaches back for the newest pack that is actually
freezable and says which one it took and which newer ones it skipped.

**Every field is sourced, never invented.** Thirteen of the fifteen come from what a
vision model actually read off the rendered frames -- one per drift dimension. `complexion` comes from the owner's own written
direction, and `representative_angles` from the frames the pack really rendered. Nothing here
writes a plausible sentence into a field the pack could not fill.

**The superseded packs stay.** The pre-revision body pack and the five rejected tournament
finalists remain in the audit log as evidence and are not eligible for selection: nothing in
this module can promote them, and `select_canonical` refuses a second canonical outright.
"""
from __future__ import annotations

from . import brief, identity

# Fields no drift dimension reports, and where each honestly comes from instead.
#
# `complexion` is the owner's written direction rather than a reading, because it is a
# stated target and the observer describes skin in whatever words it likes.
# `representative_angles` is the set of reference frames the pack actually rendered -- the
# angles the identity is defined at, which is a fact about the pack rather than about her.
UNREADABLE_BY_OBSERVATION: tuple[str, ...] = ("complexion", "representative_angles")


class FreezeRefused(ValueError):
    """A freeze that would write an identity with a hole in it, or one nobody approved."""


def fields_from(package: dict) -> dict:
    """The fifteen pack fields, each from what the pack actually established.

    Thirteen come from the drift dimensions the observer read; the two in
    `UNREADABLE_BY_OBSERVATION` come from the brief and from the frames themselves.
    """
    observed = dict(package.get("reference_observation") or {})
    fields: dict[str, str] = {}
    for dimension, field in identity.DIMENSION_FIELD.items():
        value = str(observed.get(dimension) or "").strip()
        if value and value.lower() != identity.UNMEASURABLE:
            fields[field] = value
    fields.setdefault("complexion", brief.PHYSICAL_DIRECTION["complexion"])
    frames = [f.get("frame") for f in package.get("reference_frames") or []]
    fields.setdefault("representative_angles",
                      ", ".join(str(f) for f in frames if f) or "")
    return fields


def missing(package: dict) -> list[str]:
    """Which of the fifteen this pack cannot fill. Empty means freezable."""
    fields = fields_from(package)
    return [f for f in identity.IDENTITY_FIELDS if not str(fields.get(f) or "").strip()]


def freezable(package: dict) -> dict:
    """Whether this pack may be frozen, and why not when it may not."""
    if not package.get("built"):
        return {"freezable": False, "why": "the pack did not finish building"}
    absent = missing(package)
    if absent:
        return {"freezable": False, "missing": absent,
                "why": (f"{absent} could not be read off this pack's frames. A frozen "
                        f"identity with an unstated dimension is a dimension that can "
                        f"never drift again, which is the owner's unmeasurable-is-never-"
                        f"pass rule made permanent rather than broken once")}
    required = [d for d in identity.REQUIRED_MEASURABLE["morphology"]
                if d in (package.get("unpinned_dimensions") or [])]
    if required:
        return {"freezable": False, "missing": required,
                "why": (f"{required} are the owner's named hard floors and this pack "
                        f"could not state them")}
    return {"freezable": True, "why": ""}


def candidates_on_file(db, *, limit: int = 20) -> list[dict]:
    """Every pack build on file, newest first, with whether each could be frozen."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog
    from . import reference_pack

    out: list[dict] = []
    with db.session() as s:
        for row in s.scalars(select(AuditLog)
                             .where(AuditLog.action == reference_pack.PACK_ACTION)
                             .order_by(desc(AuditLog.id)).limit(limit)):
            detail = row.detail or {}
            verdict = freezable(detail)
            out.append({"at": str(row.at), "pack_version": detail.get("pack_version"),
                        "candidate_fingerprint": detail.get("candidate_fingerprint"),
                        "built": bool(detail.get("built")),
                        "freezable": verdict["freezable"], "why_not": verdict["why"],
                        "missing": verdict.get("missing", []),
                        "_package": detail})
    return out


def newest_freezable(db) -> dict | None:
    """The newest pack that can actually be frozen, with what was skipped to reach it."""
    rows = candidates_on_file(db)
    skipped: list[dict] = []
    for row in rows:
        if row["freezable"]:
            return {"package": row["_package"], "pack_version": row["pack_version"],
                    "at": row["at"], "skipped_newer": skipped}
        skipped.append({"pack_version": row["pack_version"],
                        "why_not": row["why_not"], "missing": row["missing"]})
    return None


def freeze(db, *, owner_approved: bool, key: str = "brambleloop-canonical",
           package: dict | None = None) -> dict:
    """Promote the newest freezable pack to canonical. The one path, and it refuses.

    `owner_approved` is passed through to `select_canonical`, which is the function that
    actually refuses without it -- this does not re-implement that rule, because two
    places holding one rule is how they come to disagree.
    """
    from . import model_registry

    if not owner_approved:
        raise FreezeRefused(
            "freezing is the owner's decision and nothing here may make it. A candidate "
            "that becomes canonical by being the only one left is an identity nobody chose")

    existing = model_registry.canonical_pack(db)
    if existing is not None:
        return {"frozen": False, "already_canonical": True,
                "version": existing.version,
                "approved_at": existing.approved_by_owner_at,
                "why": ("a canonical identity already exists. Replacing her is a redesign "
                        "and a separate owner decision, not a side effect of running this "
                        "again (#200)")}

    chosen = ({"package": package, "pack_version": (package or {}).get("pack_version"),
               "at": "supplied by the caller", "skipped_newer": []}
              if package is not None else newest_freezable(db))
    if chosen is None:
        raise FreezeRefused(
            "no pack on file can be frozen. Every build either did not finish or could "
            "not state a required dimension, and a pack with a hole in it would freeze a "
            "floor that can never fail")
    verdict = freezable(chosen["package"])
    if not verdict["freezable"]:
        raise FreezeRefused(verdict["why"])

    fields = fields_from(chosen["package"])
    # `select_canonical` takes the first of these as the pack's `reference_image`, and the
    # gate hands that straight to a vision call -- which needs a URL or a file that is
    # actually on this disk. A render's `/tmp` path is neither after the next restart, and
    # an `/api/...` path is not a URL a provider can fetch. The approved portrait is a file
    # committed to the repository, so it exists in every container by construction: the one
    # reference here that cannot evaporate.
    refs = [brief.approved_portrait()]
    refs += [sha for sha in ((f.get("image") or {}).get("sha256")
                             for f in chosen["package"].get("reference_frames") or [])
             if sha]
    note = (f"frozen from {chosen['pack_version']} on the owner's approval of "
            f"2026-09-22, including the revised torso/full-length morphology and "
            f"bust/chest proportion. Superseded packs and the rejected tournament "
            f"finalists remain evidence and are not eligible for selection")

    model_registry.record_candidate(db, key, fields=fields,
                                    image_refs=[r for r in refs if r], note=note)
    pack = model_registry.select_canonical(db, key, owner_approved=True)
    return {"frozen": True, "key": key, "version": pack.version,
            "approved_at": pack.approved_by_owner_at,
            "pack_version": chosen["pack_version"],
            "built_at": chosen["at"],
            "candidate_fingerprint": chosen["package"].get("candidate_fingerprint"),
            "fields": dict(pack.fields),
            "skipped_newer": chosen["skipped_newer"],
            "why_those_were_skipped": (
                "a newer build that could not state a required dimension is not a newer "
                "identity, it is an unusable one. Naming them keeps the choice auditable "
                "rather than looking like the newest pack was taken"),
            "superseded_stay_evidence": (
                "the pre-revision body pack and the five rejected tournament finalists "
                "remain in the audit log and cannot be promoted: nothing selects them, "
                "and `select_canonical` refuses a second canonical outright")}


# ---------------------------------------------------------------------------
# What the owner asked to be proved after persistence (2026-09-22)


def _observation(**overrides) -> dict:
    """A synthetic reading of a frame: every dimension matching unless told otherwise."""
    out = {d: identity.MATCH for d in identity.DRIFT_DIMENSIONS}
    out.update(overrides)
    return out


def enforcement_proof(db) -> dict:
    """Drive the persisted canonical pack through the real gate, and report what held.

    Seven properties, named by the owner on approving the identity. Every one is run
    against the pack **read back out of the database**, not against one held in memory:
    the question is whether the identity that survived persistence is the one being
    enforced, and an in-memory check cannot tell those apart.

    The observations are synthetic on purpose and that is the strength of it -- these are
    the cases a live render almost never produces on demand. A body that drifted under a
    matching face, a chest nobody could see, a customer-facing frame with no verdict at
    all: waiting for a generator to make each of those would mean never checking them.
    The pack, the drift logic and the release gate are the real production ones.
    """
    from . import model_registry

    pack = model_registry.canonical_pack(db)
    if pack is None:
        return {"proved": False,
                "why": "no canonical pack is persisted, so there is nothing to enforce"}

    checks: list[dict] = []

    def check(name: str, holds: bool, evidence, why: str) -> None:
        checks.append({"check": name, "holds": bool(holds), "evidence": evidence,
                       "why_it_matters": why})

    # 1. The pack that comes back is the revised one, and it is complete.
    #
    # Presence rather than a count: the persisted pack carries the fifteen identity fields
    # *plus* `reference_image`, which `select_canonical` adds so the pack can be compared
    # against and conditioned on. Asserting an exact number would fail on a field the
    # design requires, which is a test measuring its own arithmetic.
    blank = [f for f in identity.IDENTITY_FIELDS if not str(pack.fields.get(f) or "").strip()]
    reference = str(pack.fields.get("reference_image") or "")
    check("the_revised_pack_is_what_loads",
          not blank and bool(reference) and bool(pack.approved_by_owner_at),
          {"identity_fields_present": len(identity.IDENTITY_FIELDS) - len(blank),
           "of": len(identity.IDENTITY_FIELDS), "blank": blank,
           "bust_proportions": str(pack.fields.get("bust_proportions") or "")[:120],
           "torso_length": str(pack.fields.get("torso_length") or "")[:80],
           "reference_image_present": bool(reference),
           "approved_at": pack.approved_by_owner_at},
          "a pack read back with a blank field is a dimension that can never drift "
          "again, and one with no reference image is a description of a woman nobody "
          "can produce or check against")

    def group(verdict: dict, name: str) -> str:
        return str((verdict.get(name) or {}).get("verdict") or "")

    # 2. Facial identity is enforced.
    face_drift = identity.drift_check(_observation(face=identity.DRIFT), pack)
    check("facial_identity_is_enforced",
          group(face_drift, "face") == "fail" and face_drift["blocks_release"],
          {"face": group(face_drift, "face"),
           "morphology": group(face_drift, "morphology"),
           "overall": face_drift["verdict"], "blocks": face_drift["blocks_release"]},
          "a different face on the right body is a different woman")

    # 3. Morphology is enforced separately from the face.
    body_drift = identity.drift_check(_observation(waist=identity.DRIFT), pack)
    check("morphology_is_enforced_separately",
          group(body_drift, "morphology") == "fail"
          and group(body_drift, "face") == "pass" and body_drift["blocks_release"],
          {"face": group(body_drift, "face"),
           "morphology": group(body_drift, "morphology"),
           "overall": body_drift["verdict"]},
          "two independent floors, reported independently or they average")

    # 4. Bust and torso are hard.
    hard = {}
    for dimension in identity.REQUIRED_MEASURABLE["morphology"]:
        verdict = identity.drift_check(
            _observation(**{dimension: identity.UNMEASURABLE}), pack)
        hard[dimension] = {"morphology": group(verdict, "morphology"),
                           "blocks": verdict["blocks_release"]}
    check("bust_and_torso_are_hard_dimensions",
          all(v["morphology"] != "pass" and v["blocks"] for v in hard.values()), hard,
          "the owner named chest/bust and torso as hard floors; a set that cannot see "
          "them has not checked the body")

    # 5. Unmeasurable is never a pass.
    blind = identity.drift_check(
        {d: identity.UNMEASURABLE for d in identity.DRIFT_DIMENSIONS}, pack)
    check("unmeasurable_never_becomes_pass",
          group(blind, "face") != "pass" and group(blind, "morphology") != "pass"
          and blind["verdict"] != "pass" and blind["blocks_release"],
          {"face": group(blind, "face"), "morphology": group(blind, "morphology"),
           "overall": blind["verdict"], "blocks": blind["blocks_release"]},
          "a frame nobody could read is the case a blended score waves through")

    # 6. A matching face cannot carry a drifted body.
    compensate = identity.drift_check(
        _observation(bust=identity.DRIFT, torso=identity.DRIFT), pack)
    check("a_face_match_cannot_compensate_for_body_drift",
          group(compensate, "face") == "pass"
          and group(compensate, "morphology") == "fail"
          and compensate["verdict"] != "pass" and compensate["blocks_release"],
          {"face": group(compensate, "face"),
           "morphology": group(compensate, "morphology"),
           "overall": compensate["verdict"], "drifted": compensate["morphology"]["drifted"]},
          "the exact failure the owner named: a familiar face stops anybody looking "
          "further down the frame")

    # 7. A model-bearing customer-facing frame cannot bypass the gate.
    #
    # Two frames, because the gate has to bite on one and stay out of the way of the other.
    # A product-only render has no identity to drift and must not be held up by a check
    # that does not apply to it -- `not_applicable` is that answer, and it is not a pass.
    modelled = model_registry.gate_frames(
        db, [{"role": "listing-hero", "has_model": True, "image_ref": "hero.png"}],
        observer=lambda _db, _ref, _cand=None: {"error": "the judge did not answer"})
    product_only = model_registry.gate_frames(
        db, [{"role": "blanket-flat", "has_model": False, "image_ref": "flat.png"}])
    check("model_bearing_assets_cannot_bypass_the_gate",
          modelled.get("verdict") == "fail" and bool(modelled.get("blocking"))
          and product_only.get("verdict") == "not_applicable",
          {"model_bearing": modelled.get("verdict"),
           "blocking": modelled.get("blocking", [])[:2],
           "checked": modelled.get("checked"),
           "product_only": product_only.get("verdict")},
          "an unjudged model frame must block, and a product-only frame must not be "
          "held up by a check that does not apply to it")

    failed = [c["check"] for c in checks if not c["holds"]]
    return {
        "proved": not failed,
        "canonical_version": pack.version,
        "approved_at": pack.approved_by_owner_at,
        "checks": checks,
        "failed": failed,
        "note": ("Run against the pack read back out of the database, because the "
                 "question is whether the identity that survived persistence is the one "
                 "being enforced. The observations are synthetic and that is the point: "
                 "a drifted body under a matching face is not something a generator "
                 "produces on request, and waiting for one would mean never checking it."),
    }
