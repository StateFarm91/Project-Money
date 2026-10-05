"""Etsy's rules as a dated snapshot, not as a constant somebody typed once.

Requirements 35 and 39. The failure this module exists to prevent is not breaking a rule; it
is breaking a rule that changed. A platform policy encoded in code is true on the day it is
written and silently becomes a claim about the past, and the moment it matters is a suspension
notice about listings that were compliant when they were created.

Three things follow.

**A policy has a date, and a certificate records which date it was certified against (#39).**
`POLICY_VERSION` alone answers "which version of our own rules"; it cannot answer "which
version of Etsy's". A snapshot carries the source, the day it was read and a digest, so a
later change is detectable as a change rather than as a difference of opinion.

**Never checked is not the same as unchanged.** With no policy fetcher connected the watch
reports that it has never read anything — and that *blocks* enabling a new asset or product
class, which is exactly what #35 asks for. The alternative is a watch that returns "no
material changes" on an empty table, which is the most confident possible way to be wrong.

**An AI-generated image is never assumed to satisfy a listing-image requirement (#35).** Etsy
permits seller-designed digital downloads and seller-prompted AI work, with disclosure where
required. What it does not permit is a listing image that misrepresents what the buyer
receives, and an AI lifestyle render of a finished blanket is a picture of a blanket that does
not exist. That is not a disclosure problem; it is a different problem wearing a disclosure's
clothes, and disclosing it does not fix it.

None of this is legal advice, and the module says so where it matters. It encodes the
company's own conservative reading, records what that reading was based on, and makes the
reading re-checkable.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

# The five policy surfaces #39 names. Each is checked separately because each blocks a
# different workflow, and a single "Etsy policy" blob would block all of them or none.
POLICY_SOURCES: dict[str, tuple[str, tuple[str, ...]]] = {
    "seller_policy": ("https://www.etsy.com/legal/sellers/",
                      ("publishing", "listing", "support")),
    "creativity_standards": ("https://www.etsy.com/legal/handmade/",
                             ("publishing", "creative_assets", "product_creation")),
    "listing_image_rules": ("https://help.etsy.com/hc/en-us/articles/360000343508",
                            ("creative_assets", "publishing")),
    "advertising_rules": ("https://www.etsy.com/legal/advertising/",
                          ("growth", "paid_media")),
    "shilling_and_reviews": ("https://www.etsy.com/legal/prohibited/",
                             ("growth", "support", "portfolio")),
    # Children and Baby Products, effective 2026-06-02. Watched because its scope is wider
    # than the others in a way that reaches us directly: it prohibits the PATTERNS, DESIGNS
    # AND INSTRUCTIONS for making prohibited children's items, not only the items. A shop
    # selling nothing but PDFs can be actioned under it. It therefore gates product_creation
    # as well as publishing -- the point to refuse a crib-bumper pattern is before a CIR is
    # written for it, not at the listing.
    "children_and_baby": ("https://www.etsy.com/legal/prohibited-items/children/",
                          ("publishing", "product_creation")),
}

# Beyond this, a snapshot is a historical document rather than a current policy.
MAX_AGE_DAYS = 30

# How a product is classified under the Creativity Standards. Closed, because the useful
# question is which of these it is, and "other" is how a classification stops classifying.
SELLER_DESIGNED_DIGITAL = "seller_designed_digital_download"
SELLER_MADE_PHYSICAL = "seller_made_physical"
AI_ASSISTED_DESIGN = "ai_assisted_design"

PRODUCT_CLASSES: dict[str, str] = {
    SELLER_DESIGNED_DIGITAL: ("a pattern designed by the seller and delivered as a file; "
                              "what Brambleloop sells"),
    SELLER_MADE_PHYSICAL: "a finished object made by the seller",
    AI_ASSISTED_DESIGN: ("a design where a model contributed to the creative work, which "
                         "requires disclosure"),
}

# What a listing image is doing, and whether a generated image can honestly do it. The
# distinction is not aesthetic: some frames are evidence about the object, and a generated
# image cannot be evidence about an object that does not exist.
PHOTOGRAPH_REQUIRED = "photograph_required"
GENERATED_PERMITTED = "generated_permitted"

ASSET_ROLES: dict[str, tuple[str, str]] = {
    "primary_listing_image": (PHOTOGRAPH_REQUIRED,
                              "the buyer's first and main evidence of what they are buying"),
    "finished_object_photo": (PHOTOGRAPH_REQUIRED,
                              "a claim about how the finished object looks"),
    "detail_photo": (PHOTOGRAPH_REQUIRED, "a claim about stitch, texture or scale"),
    "scale_reference": (PHOTOGRAPH_REQUIRED, "a claim about finished dimensions"),
    "chart_render": (GENERATED_PERMITTED,
                     "a deterministic render of our own chart, which is the artefact itself"),
    "pattern_page_preview": (GENERATED_PERMITTED, "a render of the document being sold"),
    "colourway_illustration": (GENERATED_PERMITTED,
                               "an illustration of available colours, labelled as such"),
    "mood_frame": (GENERATED_PERMITTED,
                   "an atmosphere frame that makes no claim about the object"),
}

# Disclosure lines. Short, plain, and written to be true rather than to be minimal.
DISCLOSURES: dict[str, str] = {
    "ai_assisted_design": ("Parts of this design were developed with AI assistance, directed "
                           "and edited by the designer."),
    "generated_imagery": ("Some listing images are illustrations or renders rather than "
                          "photographs, and are labelled where they appear."),
    "digital_download": ("This is a digital pattern. No physical item is shipped."),
    "deterministic_render": ("Charts and previews are rendered directly from the pattern "
                             "file, so they show exactly what is in the document."),
    # D-FB-7: the product images are disclosed deterministic renders. The wording carries the
    # contract phrase the images themselves carry (visual.render_contract.DISCLOSURE).
    "disclosed_render": ("About the images: each listing image is a digital rendering of the "
                         "pattern's finished design, not a photograph. Every stitch in it is "
                         "drawn from the pattern itself at the stated gauge, with a centimetre "
                         "scale; no sample has been photographed, and your finished piece will "
                         "vary with yarn and tension."),
}


class PolicyRefused(Exception):
    """A release certified against a policy nobody has read, or an image making a false claim."""


# ---------------------------------------------------------------------------
# The freshness watch (#39)


@dataclass(frozen=True)
class Snapshot:
    source: str
    checked_on: str
    version: str
    digest: str
    summary: str = ""

    def to_dict(self) -> dict:
        return {"source": self.source, "checked_on": self.checked_on,
                "version": self.version, "digest": self.digest, "summary": self.summary}


def digest_of(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def record_snapshot(db, source: str, *, text: str, version: str = "",
                    summary: str = "", checked_on: str = "", read_by: str = "",
                    basis: str = "") -> dict:
    """Record one reading of one policy, and say whether it changed materially.

    "Material" is decided by comparing digests against the previous snapshot of the same
    source rather than by judgement, because a judgement about whether a policy change
    matters is exactly the judgement somebody makes quickly at the end of a week.

    Only the digest of `text` is stored, never the text: the snapshot proves which reading a
    certificate rests on without keeping a copy of Etsy's page. `read_by` and `basis` say who
    read it and how, and live in `detail`.
    """
    from sqlalchemy import select

    from ..core.models import PolicySnapshot

    if source not in POLICY_SOURCES:
        raise PolicyRefused(f"{source!r} is not a watched policy: {sorted(POLICY_SOURCES)}")
    if not (text or "").strip():
        raise PolicyRefused("an empty reading is not a reading: the digest of nothing proves "
                            "nothing was read")

    url, affects = POLICY_SOURCES[source]
    new_digest = digest_of(text)
    with db.session() as s:
        previous = s.scalars(select(PolicySnapshot).where(
            PolicySnapshot.source == source).order_by(
                PolicySnapshot.id.desc())).first()
        changed = previous is not None and previous.digest != new_digest
        row = PolicySnapshot(
            source=source, url=url, checked_on=checked_on or date.today().isoformat(),
            version=version or date.today().isoformat(), digest=new_digest,
            summary=summary, material_change=changed, affects=list(affects),
            detail={"read_by": read_by, "basis": basis, "text_length": len(text)})
        s.add(row)
        s.flush()
        snapshot_id = row.id

    return {"id": snapshot_id, "source": source, "digest": new_digest,
            "material_change": changed, "affects": list(affects),
            "first_reading": previous is None}


PAGE_BASIS = "page"

CHANGE_SIGNATURE = "policy_changed:"


def unreviewed_changes(db) -> list[dict]:
    """Sources whose newest reading differs materially from the one before, unreviewed (#39).

    A material change is a digest difference; it stays unreviewed until somebody records
    that the affected workflows were reviewed and tested against it (`review_change`). Until
    then those workflows are blocked, which is the requirement's own sentence.
    """
    from sqlalchemy import select

    from ..core.models import PolicySnapshot

    # CB2-I01: the question is whether the newest *material change* of each source was
    # reviewed, not whether the newest *reading* is a change. A->B followed by a second
    # unchanged reading of B is still the unreviewed A->B change; reading a page twice is
    # not reviewing it.
    with db.session() as s:
        latest_change: dict[str, PolicySnapshot] = {}
        for r in s.scalars(select(PolicySnapshot).where(
                PolicySnapshot.material_change.is_(True)).order_by(PolicySnapshot.id)):
            latest_change[r.source] = r
        return [{"source": src, "snapshot_id": r.id, "checked_on": r.checked_on,
                 "version": r.version, "affects": list(r.affects or POLICY_SOURCES[src][1])}
                for src, r in latest_change.items()
                if not (r.detail or {}).get("reviewed_at")]


def review_change(db, source: str, *, reviewed_by: str, tested: str) -> dict:
    """Record that a material change was reviewed and the affected workflows re-tested.

    Both halves are required: a review with no statement of what was tested is a signature,
    and the requirement says "until reviewed/tested".
    """
    from sqlalchemy import select
    from sqlalchemy.orm.attributes import flag_modified

    from ..core.models import PolicySnapshot

    if not (reviewed_by or "").strip() or not (tested or "").strip():
        raise PolicyRefused("a change review names who reviewed it and what was re-tested")
    with db.session() as s:
        # The newest material change of this source, even when unchanged readings were
        # recorded after it (CB2-I01).
        row = s.scalars(select(PolicySnapshot).where(
            PolicySnapshot.source == source, PolicySnapshot.material_change.is_(True))
            .order_by(PolicySnapshot.id.desc())).first()
        if row is None or (row.detail or {}).get("reviewed_at"):
            raise PolicyRefused(f"{source}: there is no material change to review")
        detail = dict(row.detail or {})
        detail.update(reviewed_at=datetime.now(timezone.utc).isoformat(),
                      reviewed_by=reviewed_by.strip(), tested=tested.strip()[:2000])
        row.detail = detail
        flag_modified(row, "detail")
        return {"source": source, "snapshot_id": row.id, "reviewed": True}


def record_page_reading(db, *, source: str, text: str, version: str = "", summary: str = "",
                        read_by: str, checked_on: str = "",
                        today: date | None = None) -> dict:
    """An operator's reading of an Etsy policy page, recorded and acted on at once.

    Etsy's bot protection refuses automated retrieval of these pages (recorded in
    `gates.policy_knowledge.RETRIEVAL_BLOCK`), and this company does not evade it. A person
    opening the page in their own browser, reading it and pasting what they read is not
    evasion: it is the ordinary way a seller learns the rules, and it is the owner action the
    policy incidents have been asking for. So this records that reading as a `page`-basis
    snapshot, which supersedes the repository's excerpt reading of the same source, and
    closes the open `policy_stale:<source>` incident immediately with the same fields the
    watch uses -- but only when the reading is itself current. A reading older than
    `MAX_AGE_DAYS` is recorded and the incident stays open, because recording an old page
    is not the same as the policy being current.

    The text is digested and never stored or logged.
    """
    from sqlalchemy import select

    from ..core.models import Incident, utcnow

    if not (read_by or "").strip():
        raise PolicyRefused("a page reading must say who read it")
    today = today or date.today()
    checked = checked_on or today.isoformat()
    try:
        age = (today - date.fromisoformat(checked)).days
    except ValueError as e:
        raise PolicyRefused(f"checked_on {checked!r} is not an ISO date") from e
    if age < 0:
        raise PolicyRefused("a reading cannot be dated in the future")
    res = record_snapshot(db, source, text=text, version=version or checked,
                          summary=summary, checked_on=checked, read_by=read_by.strip(),
                          basis=PAGE_BASIS)
    resolved: list[int] = []
    current = age <= MAX_AGE_DAYS
    if current:
        with db.session() as s:
            for inc in s.scalars(select(Incident).where(
                    Incident.resolved == False,  # noqa: E712
                    Incident.signature == f"policy_stale:{source}")):
                detail = dict(inc.detail or {})
                detail["resolution"] = (
                    f"{source} read on {checked} (version {version or checked}) by "
                    f"{read_by.strip()} from the page itself; snapshot {res['id']}")
                detail["resolved_at"] = utcnow().isoformat()
                inc.detail = detail
                inc.resolved = True
                resolved.append(inc.id)
    return {**res, "basis": PAGE_BASIS, "checked_on": checked, "age_days": age,
            "current": current, "incidents_resolved": resolved,
            "note": ("recorded; the incident stays open because the reading is older than "
                     f"{MAX_AGE_DAYS} days" if not current else "recorded and current")}


def freshness(db, *, today: date | None = None) -> dict:
    """Which policies are current, which are stale, and which have never been read."""
    from sqlalchemy import select

    from ..core.models import PolicySnapshot

    today = today or date.today()
    with db.session() as s:
        rows = list(s.scalars(select(PolicySnapshot).order_by(PolicySnapshot.id)))

    latest: dict[str, PolicySnapshot] = {}
    for r in rows:
        latest[r.source] = r

    current, stale, never = [], [], []
    for source in POLICY_SOURCES:
        row = latest.get(source)
        if row is None:
            never.append(source)
            continue
        age = (today - date.fromisoformat(row.checked_on)).days
        entry = {"source": source, "checked_on": row.checked_on, "age_days": age,
                 "version": row.version, "material_change": row.material_change}
        (stale if age > MAX_AGE_DAYS else current).append(entry)

    changed = unreviewed_changes(db)
    blocked_workflows = sorted({w for src in never + [e["source"] for e in stale]
                                + [c["source"] for c in changed]
                                for w in POLICY_SOURCES[src][1]})
    return {
        "current": current,
        "stale": stale,
        "never_checked": never,
        "changed_unreviewed": [c["source"] for c in changed],
        "all_fresh": not stale and not never,
        "blocked_workflows": blocked_workflows,
        "max_age_days": MAX_AGE_DAYS,
        "note": ("Never checked is not the same as unchanged. A watch that reported 'no "
                 "material changes' from an empty table would be the most confident possible "
                 "way to be wrong (#39)."),
    }


def policy_stamp(db, *, today: date | None = None) -> dict:
    """What a release certificate records about the platform rules it was certified against.

    `POLICY_VERSION` answers which version of *our* rules. This answers which version of
    Etsy's, which is the one that changes without telling us.
    """
    f = freshness(db, today=today)
    latest = {e["source"]: e["version"] for e in f["current"] + f["stale"]}
    return {
        "platform": "etsy",
        "sources": latest,
        "unread_sources": f["never_checked"],
        "stale_sources": [e["source"] for e in f["stale"]],
        "changed_unreviewed": f["changed_unreviewed"],
        "certified_against_current_policy": f["all_fresh"] and not f["changed_unreviewed"],
        "note": ("A certificate that does not say which policy it was read against cannot "
                 "be re-examined after the policy changes, which is the only time anybody "
                 "wants to re-examine it."),
    }


def check_new_class(db, *, product_class: str, asset_roles: tuple[str, ...] = (),
                    today: date | None = None) -> dict:
    """#35: the Policy Agent re-reads current policy before a new class is enabled.

    Enabling a new product or asset class against a policy nobody has read this month is the
    specific thing this refuses, because a new class is exactly when the old reading is least
    likely to cover the case.
    """
    if product_class not in PRODUCT_CLASSES:
        raise PolicyRefused(
            f"{product_class!r} is not a classified product class: {sorted(PRODUCT_CLASSES)}")
    unknown = [r for r in asset_roles if r not in ASSET_ROLES]
    if unknown:
        raise PolicyRefused(f"{sorted(unknown)} are not asset roles: {sorted(ASSET_ROLES)}")

    f = freshness(db, today=today)
    if not f["all_fresh"]:
        raise PolicyRefused(
            f"cannot enable {product_class!r}: policy sources {f['never_checked'] + [e['source'] for e in f['stale']]} "
            f"have not been read within {MAX_AGE_DAYS} days. A new class is exactly when the "
            f"old reading is least likely to cover the case (#35)")
    if f["changed_unreviewed"]:
        raise PolicyRefused(
            f"cannot enable {product_class!r}: policy sources {f['changed_unreviewed']} "
            f"changed materially and the change has not been reviewed and tested (#39)")
    return {"product_class": product_class, "enabled": True,
            "asset_roles": list(asset_roles), "policy": policy_stamp(db, today=today)}


# ---------------------------------------------------------------------------
# The creativity and disclosure gate (#35)


@dataclass
class AssetClaim:
    """One listing image, what it is doing, and how it was made."""

    ref: str
    role: str
    generated: bool = False
    deterministic_render: bool = False
    labelled: bool = False
    disclosed_render: bool = False

    def to_dict(self) -> dict:
        return {"ref": self.ref, "role": self.role, "generated": self.generated,
                "deterministic_render": self.deterministic_render, "labelled": self.labelled,
                "disclosed_render": self.disclosed_render}


@dataclass
class Classification:
    product_class: str
    disclosures: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def to_dict(self) -> dict:
        return {"product_class": self.product_class,
                "meaning": PRODUCT_CLASSES[self.product_class],
                "disclosures": list(self.disclosures),
                "problems": list(self.problems),
                "ok": self.ok,
                "note": ("Disclosure and misrepresentation are different problems. Saying an "
                         "image was generated does not make it an acceptable photograph of "
                         "an object that does not exist (#35)."),
                "not_legal_advice": ("This is the company's own conservative reading of the "
                                     "platform's published rules, recorded so it can be "
                                     "re-checked rather than remembered.")}


def classify(*, product_class: str, assets: list[AssetClaim],
             ai_assisted_design: bool = False, digital: bool = True) -> Classification:
    """Classify a release and generate the disclosures it owes.

    The one rule worth stating separately: an image in a role that makes a claim about the
    finished object must be a photograph of the finished object, or a deterministic render of
    the artefact being sold. A generated lifestyle shot is neither, and labelling it does not
    convert it — the label tells the buyer the picture is not real, and they are looking at it
    to find out what they are buying.
    """
    if product_class not in PRODUCT_CLASSES:
        raise PolicyRefused(
            f"{product_class!r} is not a classified product class: {sorted(PRODUCT_CLASSES)}")

    problems: list[str] = []
    disclosures: list[str] = []

    if digital:
        disclosures.append(DISCLOSURES["digital_download"])
    if ai_assisted_design or product_class == AI_ASSISTED_DESIGN:
        disclosures.append(DISCLOSURES["ai_assisted_design"])

    any_generated = False
    any_deterministic = False
    any_disclosed = False
    for asset in assets:
        if asset.role not in ASSET_ROLES:
            raise PolicyRefused(f"{asset.role!r} is not an asset role: {sorted(ASSET_ROLES)}")
        requirement, why = ASSET_ROLES[asset.role]
        if asset.deterministic_render:
            any_deterministic = True
        if asset.disclosed_render:
            any_disclosed = True
            if not asset.labelled:
                problems.append(
                    f"{asset.ref}: a disclosed render in the {asset.role!r} role without its "
                    f"disclosure in the image and alt text; it may not be classified as "
                    f"disclosed until it carries both")
        if not asset.generated:
            continue
        any_generated = True
        if requirement == PHOTOGRAPH_REQUIRED and not asset.deterministic_render:
            problems.append(
                f"{asset.ref}: a generated image in the {asset.role!r} role, which is {why}. "
                f"Never assume an AI-generated lifestyle image satisfies a listing-image "
                f"requirement -- it is a picture of an object that does not exist, and "
                f"labelling it does not change what the buyer is looking at it for")
        elif not asset.labelled:
            problems.append(
                f"{asset.ref}: a generated image in the {asset.role!r} role is permitted and "
                f"must be labelled where it appears")

    if any_generated:
        disclosures.append(DISCLOSURES["generated_imagery"])
    if any_deterministic:
        disclosures.append(DISCLOSURES["deterministic_render"])
    if any_disclosed:
        disclosures.append(DISCLOSURES["disclosed_render"])

    if not assets:
        problems.append(
            "no listing assets were classified. A release with no image claims has not "
            "passed this gate; it has skipped it")

    return Classification(product_class=product_class,
                          disclosures=sorted(set(disclosures)), problems=problems)


# ---------------------------------------------------------------------------
# #35 in the runtime: every release is classified before its listing is written

CLASSIFIED_ACTION = "listing.classified"

# The listing frames `publish.listing_assets` renders, by the role each plays, onto the asset
# roles this gate reasons about. Every one is a deterministic render of the certified pattern.
FRAME_ROLE: dict[str, str] = {
    "hero": "primary_listing_image",
    "whats_included": "pattern_page_preview",
    "size": "scale_reference",
    "materials": "pattern_page_preview",
    "pattern_preview": "pattern_page_preview",
    "chart": "chart_render",
    "collection": "mood_frame",
}

# Model-rendered frames by the job they do. Each makes a claim about the finished object,
# which is the point: a generated image in one of these roles is refused, labelled or not.
GENERATED_ROLE: dict[str, str] = {
    "hero": "finished_object_photo", "fit": "finished_object_photo",
    "lifestyle": "finished_object_photo", "detail": "detail_photo",
    "scale": "scale_reference",
}


# Disclosed renders (D-FB-7) make claims about the finished object -- that is their job -- and
# they make them as deterministic renders of the design being sold, which `classify` permits
# in a photograph-required role. They are never `generated`.
DISCLOSED_ROLE: dict[str, str] = {
    "hero": "primary_listing_image", "scale": "scale_reference", "detail": "detail_photo",
}


def release_assets(frames: list[dict], generated: list[dict] | None = None,
                   disclosed: list[dict] | None = None) -> list[AssetClaim]:
    """The asset claims a release's listing gallery makes, from the records on file.

    `frames` are the deterministic frames `assets.build` stored; `generated` are the
    model-rendered photography frames the parity gate judges. A frame role this gate has no
    mapping for is refused rather than guessed into a permissive role.
    """
    claims: list[AssetClaim] = []
    for frame in frames:
        role = FRAME_ROLE.get(str(frame.get("role") or ""))
        if role is None:
            raise PolicyRefused(
                f"listing frame role {frame.get('role')!r} has no asset-role mapping "
                f"({sorted(FRAME_ROLE)}); an unmapped frame cannot be classified")
        claims.append(AssetClaim(ref=f"frame-{frame.get('position')}", role=role,
                                 generated=False, deterministic_render=True, labelled=True))
    for i, frame in enumerate(generated or [], start=1):
        job = str(frame.get("role") or frame.get("shot") or "hero")
        claims.append(AssetClaim(
            ref=str(frame.get("image_ref") or f"generated-{i}"),
            role=GENERATED_ROLE.get(job, "finished_object_photo"), generated=True,
            deterministic_render=False,
            labelled=bool(frame.get("disclosed_as_illustration", False))))
    # D-FB-7: disclosed deterministic renders of the finished design. Never `generated`; a
    # frame that is not a disclosed render (a photo, a generation) is not accepted here.
    for frame in disclosed or []:
        if frame.get("kind") != "disclosed_render" or frame.get("generated") is not False:
            raise PolicyRefused(f"{frame.get('image_ref')!r} is not a disclosed render")
        role = DISCLOSED_ROLE.get(str(frame.get("role") or ""))
        if role is None:
            raise PolicyRefused(f"disclosed frame role {frame.get('role')!r} has no asset role")
        disclosure = frame.get("disclosure") or {}
        claims.append(AssetClaim(
            ref=str(frame.get("image_ref") or f"disclosed-{frame.get('position')}"), role=role,
            generated=False, deterministic_render=True, disclosed_render=True,
            labelled=bool(disclosure.get("in_image") and disclosure.get("in_alt_text"))))
    return claims


def classify_release(frames: list[dict], generated: list[dict] | None = None, *,
                     ai_assisted_design: bool = True,
                     disclosed: list[dict] | None = None) -> Classification:
    """#35 for one release: Brambleloop sells seller-designed digital patterns whose design
    was developed with AI assistance, so the class is `ai_assisted_design`, digital."""
    return classify(product_class=AI_ASSISTED_DESIGN if ai_assisted_design
                    else SELLER_DESIGNED_DIGITAL,
                    assets=release_assets(frames, generated, disclosed),
                    ai_assisted_design=ai_assisted_design, digital=True)


def disclosure_block(classification: Classification) -> str:
    """The owed disclosures as a description section, verbatim, so the gate can find them."""
    lines = ["DISCLOSURES"] + [f"- {d}" for d in classification.disclosures]
    return "\n".join(lines)


def describe() -> dict:
    return {
        "policy_sources": {k: {"url": v[0], "affects": list(v[1])}
                           for k, v in POLICY_SOURCES.items()},
        "max_age_days": MAX_AGE_DAYS,
        "product_classes": PRODUCT_CLASSES,
        "asset_roles": {k: {"requirement": v[0], "why": v[1]} for k, v in ASSET_ROLES.items()},
        "disclosures": DISCLOSURES,
        "not_legal_advice": ("The company's own conservative reading of published platform "
                             "rules, recorded with its date so it can be re-checked."),
    }
