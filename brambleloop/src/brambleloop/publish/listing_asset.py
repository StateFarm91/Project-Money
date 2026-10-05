"""One decision about which picture a product needs, in one place.

A blanket is photographed flat and a cardigan is photographed on somebody, and until
2026-09-22 only the first of those existed -- so every worn form refused and the refusal
was the end of the road. Now both paths exist, and the thing that must not happen is two
callers each deciding for themselves which one to use: the seasonal cycle, the daily
photography job and the release chain would drift into three different answers to "does
this product need the model", and the one that got it wrong would be shipping a cardigan
photographed flat or a blanket draped over a stranger.

So the form decides, once, here. `owned_photography.needs_no_model` is the predicate and
this is the only place that branches on it.

`last` reads both records for the same reason. A caller asking "is there an asset for this
product yet" that only knew about one of the two paths would answer no for every garment
ever photographed, which is how a cycle re-renders something it already has.
"""
from __future__ import annotations


def needs_the_model(cir) -> bool:
    """Whether this product's listing frame has to carry her."""
    from . import owned_photography

    return not owned_photography.needs_no_model(cir)


def _in_launch_scope(slug: str) -> bool:
    """Disclosed renders are verified against the Launch-0 registry (D-FB-7); a product
    outside it has no authoritative CIR to verify against, so it is not offered one."""
    from ..products.launch0 import launch_scope_slugs

    return slug in launch_scope_slugs()


def make(db, cir, twin, *, record: bool = True, **kw) -> dict:
    """Render the listing asset this product actually needs, by its form, and file it.

    Filing is the half that was missing and it is not incidental. A caller that renders
    and then asks "is there an asset for this product" reads the audit log, so a render
    nobody filed is a render nobody can find: the seasonal cycle would have rendered a
    blanket, looked for it, failed to see it and reported its assets link unreachable --
    with the money already spent. The hats arena hid that, because a garment refused
    before it ever got as far as rendering.

    `record=False` is for a caller that files its own row. The two job handlers call the
    underlying `make` functions directly and audit afterwards, so they never come through
    here and cannot double-write.
    """
    from . import model_photography, owned_photography

    if needs_the_model(cir):
        # The sequence rather than a single frame: the body floor and the fabric floor
        # are questions about two different photographs, and one frame cannot answer both.
        action, out = (model_photography.ACTION,
                       model_photography.sequence(db, cir, twin, **kw))
    else:
        # The product-first path takes no identity observer and no realism judge: there is
        # no identity in the frame to compare, and passing one would be a check on nobody.
        for identity_only in ("observer", "realism_judger"):
            kw.pop(identity_only, None)
        action, out = owned_photography.ACTION, owned_photography.make(db, cir, twin, **kw)
        if not out.get("made") and _in_launch_scope(cir.slug):
            # D-FB-7: no qualified photograph and generative redraw is refused (F-852), so
            # the product's listing imagery is the disclosed deterministic render -- drawn
            # from this CIR, verified against it from the pixels, disclosed in the image,
            # its alt text and the copy. A product the renderer cannot draw truthfully is
            # refused there and stays without imagery rather than getting a guess.
            from . import disclosed_listing

            rendered = disclosed_listing.build(cir, db=db)
            if rendered.get("made"):
                action, out = disclosed_listing.ACTION, rendered

    if record and out.get("made"):
        from ..core.models import AuditLog

        with db.session() as s:
            s.add(AuditLog(actor="publishing", action=action, detail=out))
    return out


def last(db, *, slug: str = "") -> dict | None:
    """The most recent listing asset on file from either path, newest first."""
    from . import disclosed_listing, model_photography, owned_photography

    found = [a for a in (model_photography.last_asset(db, slug=slug),
                         owned_photography.last_asset(db, slug=slug)) if a]
    # A photograph that clears every floor wins; otherwise the disclosed render set, which is
    # the listing imagery D-FB-7 permits when it verifies, ahead of an unusable photo record.
    if any(usable(a) for a in found):
        return next(a for a in found if usable(a))
    disclosed = disclosed_listing.last_asset(db, slug=slug)
    if disclosed is not None:
        return disclosed
    if not found:
        return None
    # Both records carry the audit row's own ordering only within their own action, so
    # prefer the one whose product actually needs it rather than guessing at recency.
    return found[0]


def usable(record: dict | None) -> bool:
    """Whether a record from either path clears every floor its path applies."""
    if not record or not record.get("made"):
        return False
    from ..visual.product_authority import structural_floor
    frames = record.get("frames") or [record]
    return bool(record.get("usable_as_listing_asset")) and all(
        structural_floor(frame)["status"] == "PASS" for frame in frames)


def frames_for(db, *, slug: str) -> list[dict]:
    """Every frame this product's listing would export, flat, for the parity gate.

    A model-bearing listing is a sequence and a product-first one is a single hero, so a
    caller that assumed either shape would be wrong about half the catalogue. #75 judges
    the set, so the set is what this returns -- and an empty list is an answer: parity on
    no frames is `unjudged`, which blocks, rather than passing by having nothing to fail.
    """
    record = last(db, slug=slug)
    if not record or not record.get("made"):
        return []
    frames = record.get("frames")
    return list(frames) if frames else [record]
