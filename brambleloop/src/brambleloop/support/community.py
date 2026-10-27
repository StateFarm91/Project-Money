"""Community feedback loop (F-820) -- W4-C14.

"Community/project-photo/support signals feed the learning ledger. Common successes/failures
can improve tutorials, patterns and FAQs while respecting privacy and content rights."

A signal is `{kind, ref, reporter, product_slug, outcome, text, consent, photo_ref}`:

* `kind` -- `project_photo`, `community_post`, `support` or `review`;
* `outcome` -- `success` or `failure` (anything else is not counted);
* `consent` -- `{"learning": bool, "reuse": bool}` as the person gave it.

Privacy and content rights, enforced here rather than promised:

* a private signal (`project_photo`, `support`) without learning consent is not used at all --
  it is counted as declined and nothing of it is kept;
* no text is kept from any signal: it is classified into the failure modes of `project_tips`
  and dropped; the reporter is kept only as a salted digest, to count distinct people;
* a photo reference is kept only with reuse consent. Without it the photo still counts as
  evidence of a success or failure, but no reference to it survives, so nothing downstream can
  show or reuse it.

What feeds the ledger: an aggregate (product, mode, outcome) with `MIN_CONTRIBUTORS` distinct
people becomes one lesson on the cross-department bus (`improve.bus.publish`, origin
`customer_experience`), subject `sizing` for a sizing mode and `instruction_clarity` otherwise --
which routes it to Learn, Quality, Pattern Engineering and Customer Experience. The lesson's
evidence ref is the aggregate's key, so re-reading the same community never publishes twice.
Its statement carries counts only.
"""
from __future__ import annotations

import hashlib

from . import project_tips as P

KINDS = ("project_photo", "community_post", "support", "review")
PRIVATE_KINDS = frozenset({"project_photo", "support"})
OUTCOMES = ("success", "failure")
MIN_CONTRIBUTORS = 3
_SALT = "brambleloop.community.v1"


def _who(reporter) -> str:
    return hashlib.sha256(f"{_SALT}:{reporter}".encode()).hexdigest()[:16]


def admit(signal: dict) -> dict | None:
    """The privacy-safe record of one signal, or None when it may not be used."""
    if signal.get("kind") not in KINDS or signal.get("outcome") not in OUTCOMES:
        return None
    consent = dict(signal.get("consent") or {})
    if signal["kind"] in PRIVATE_KINDS and not consent.get("learning"):
        return None
    modes = P.classify(signal.get("text", "")) or ["general"]
    return {"kind": signal["kind"], "product_slug": signal.get("product_slug"),
            "outcome": signal["outcome"], "modes": modes,
            "who": _who(signal.get("reporter") or signal.get("ref")),
            "photo_ref": signal.get("photo_ref") if consent.get("reuse") else None}


def intake(db, signals) -> dict:
    admitted, declined, ignored = [], 0, 0
    for sig in signals or ():
        rec = admit(sig)
        if rec is not None:
            admitted.append(rec)
        elif sig.get("kind") in PRIVATE_KINDS and sig.get("outcome") in OUTCOMES:
            declined += 1
        else:
            ignored += 1
    agg: dict[tuple, dict] = {}
    for rec in admitted:
        for mode in rec["modes"]:
            a = agg.setdefault((rec["product_slug"] or "*", mode, rec["outcome"]),
                               {"who": set(), "photos": [], "kinds": {}})
            a["who"].add(rec["who"])
            a["kinds"][rec["kind"]] = a["kinds"].get(rec["kind"], 0) + 1
            if rec["photo_ref"]:
                a["photos"].append(rec["photo_ref"])
    from ..improve import bus

    published, below = [], []
    for (slug, mode, outcome), a in sorted(agg.items()):
        n = len(a["who"])
        row = {"product_slug": slug, "mode": mode, "outcome": outcome, "contributors": n,
               "by_kind": dict(sorted(a["kinds"].items())),
               "reusable_photos": sorted(a["photos"])}
        if n < MIN_CONTRIBUTORS or mode == "general":
            below.append({**row, "why": ("not one failure mode" if mode == "general" else
                                         f"{n} of {MIN_CONTRIBUTORS} distinct contributors")})
            continue
        subject = "sizing" if mode == "sizing" else "instruction_clarity"
        verb = "succeed with" if outcome == "success" else "struggle with"
        statement = (f"{n} community members {verb} {mode.replace('_', ' ')} on "
                     f"{'the catalogue' if slug == '*' else slug}; the tutorial, FAQ and "
                     f"pattern notes for it should "
                     f"{'keep what works' if outcome == 'success' else 'be revisited'}.")
        lesson_id = bus.publish(db, origin_cell="customer_experience", subject=subject,
                                statement=statement,
                                evidence_ref=f"community:{slug}:{mode}:{outcome}",
                                confidence="observed")
        published.append({**row, "lesson_id": lesson_id, "subject": subject})
    return {"admitted": len(admitted), "declined_no_consent": declined, "ignored": ignored,
            "published": published, "below_threshold": below,
            "privacy": "no text kept; reporters as salted digests; photo refs only with reuse "
                       "consent"}
