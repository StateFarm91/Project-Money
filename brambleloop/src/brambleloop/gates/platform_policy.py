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
                    summary: str = "", checked_on: str = "") -> dict:
    """Record one reading of one policy, and say whether it changed materially.

    "Material" is decided by comparing digests against the previous snapshot of the same
    source rather than by judgement, because a judgement about whether a policy change
    matters is exactly the judgement somebody makes quickly at the end of a week.
    """
    from sqlalchemy import select

    from ..core.models import PolicySnapshot

    if source not in POLICY_SOURCES:
        raise PolicyRefused(f"{source!r} is not a watched policy: {sorted(POLICY_SOURCES)}")

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
            summary=summary, material_change=changed, affects=list(affects))
        s.add(row)
        s.flush()
        snapshot_id = row.id

    return {"id": snapshot_id, "source": source, "digest": new_digest,
            "material_change": changed, "affects": list(affects),
            "first_reading": previous is None}


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

    blocked_workflows = sorted({w for src in never + [e["source"] for e in stale]
                                for w in POLICY_SOURCES[src][1]})
    return {
        "current": current,
        "stale": stale,
        "never_checked": never,
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
        "certified_against_current_policy": f["all_fresh"],
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

    def to_dict(self) -> dict:
        return {"ref": self.ref, "role": self.role, "generated": self.generated,
                "deterministic_render": self.deterministic_render, "labelled": self.labelled}


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
    for asset in assets:
        if asset.role not in ASSET_ROLES:
            raise PolicyRefused(f"{asset.role!r} is not an asset role: {sorted(ASSET_ROLES)}")
        requirement, why = ASSET_ROLES[asset.role]
        if asset.deterministic_render:
            any_deterministic = True
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

    if not assets:
        problems.append(
            "no listing assets were classified. A release with no image claims has not "
            "passed this gate; it has skipped it")

    return Classification(product_class=product_class,
                          disclosures=sorted(set(disclosures)), problems=problems)


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
