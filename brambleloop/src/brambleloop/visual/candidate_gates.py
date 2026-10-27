"""One set of gates for every generated listing-image candidate (W-OWNERIMG).

Owner redirect, 2026-10-19: autonomous image production is the primary path, and an owner
upload is only a fallback. **No gate or criterion may differ by generation method.** Both
paths therefore call `evaluate`, and `evaluate` never reads `method`. It only records it.

Each check is PASS, FAIL, UNKNOWN or NOT_APPLICABLE, and UNKNOWN is never PASS. Every check
reuses existing machinery:

| check | reused from |
|---|---|
| binding | the certified `PatternVersion` (`release_gates._release`) and the certified PDF hashes `assets.build` recorded (`pipeline._certified_pdf_hashes`) |
| provenance | `gates.asset_truth` competitor-source markers (#305); the kind is always `ai_generated_*`, never a photograph |
| quality | Etsy facts on record (`w3/ETSY_REQUIREMENTS.md`): ≥2000 px each side, no transparency, no webp |
| role | `publish.eligibility` Candidate / `may_serve` and the `ASSET_CONCEPT_AS_HERO` rule |
| product_truth | `visual.fidelity` (the generated-image verifier, W-FIDELITY) against the certified CIR; a `visual.product_authority.structural_floor` FAIL stays FAIL; for LIFESTYLE also `visual.compose.lifestyle_evidence` |
| identity | `visual.identity_gate.assess` (Laura only) |
| anatomy, realism | the vision judge (`image_vision`); UNKNOWN when unfunded or unread |
| disclosure | `eligibility.honesty_label` (CONCEPT_LABEL) |
| outfit | `visual.outfits` (D-W4-LAURA-OUTFIT; Laura only) |

**Publication** is a separate layer. Its parts:

* `eligibility.may_export` with the four gates mapped from the checks. Its F-852 rule refuses
  generated product imagery in every role.
* The Etsy listing-image policy reading, which is UNKNOWN (VISGATE V1).
* For Laura, `visual.canonical.asset_status` must be `publication_approved`.

An owner's visual approval is not an input to this module.
"""
from __future__ import annotations

import hashlib
import io

from ..gates.asset_truth import AssetClass
from ..publish import eligibility as el
from . import outfits
from .shot_plans import JOB_OF_ROLE

PASS, FAIL, UNKNOWN, NA = "PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"
GATES_VERSION = "candidate-gates/1"
MEDIUM = AssetClass.AI_LIFESTYLE_CONCEPT
MIN_PX = 2000
ALLOWED_FORMATS = ("PNG", "JPEG")
# Reference kinds a candidate may declare (owner form, generator receipt).
REFERENCE_KINDS = ("laura_canonical", "pattern_derived", "physical_product_photo",
                   "prior_candidate", "other")
ETSY_POLICY_UNKNOWN = (
    "Etsy Listing Image Requirements could not be read (HTTP 403, DataDome) and the help "
    "articles conflict on 'use your own photographs' for designed items (VISGATE §3, V1). "
    "Whether a generated image may appear on a digital-pattern listing is UNKNOWN")
CHECKS = ("binding", "provenance", "quality", "role", "product_truth", "identity",
          "body_proportions", "anatomy", "realism", "disclosure", "outfit",
          "outfit_distinctness", "outfit_consistency")
FAILURE_CATEGORY = {"identity": "identity_drift", "product_truth": "product_fidelity",
                    "anatomy": "anatomy", "quality": "quality", "outfit": "outfit_duplication",
                    "realism": "realism", "role": "role", "binding": "binding",
                    "provenance": "provenance", "disclosure": "disclosure",
                    "body_proportions": "body_proportion_drift",
                    "outfit_consistency": "outfit_consistency",
                    "outfit_distinctness": "wardrobe_repetition"}


def _c(status: str, why: str, **kw) -> dict:
    return {"status": status, "why": why, **kw}


def worst(*statuses: str) -> str:
    s = [x for x in statuses if x != NA]
    return FAIL if FAIL in s else UNKNOWN if (UNKNOWN in s or not s) else PASS


# ---- binding -----------------------------------------------------------------------------

def binding(db, slug: str, version: str, release: str) -> dict:
    """Bind to the certified release and its certified PDF hash. Never a rebuild's hash."""
    from ..publish.release_gates import _release
    from ..runtime.pipeline import _certified_pdf_hashes

    try:
        cir, release_hash = _release(db, slug, version)
    except Exception as exc:  # noqa: BLE001 - unreadable is unknown
        return _c(UNKNOWN, f"certified release unreadable ({type(exc).__name__})")
    if cir is None:
        return _c(FAIL, f"{slug}@{version} has no certified release; nothing to bind to")
    rel = str(release or "").strip().lower()
    if not rel:
        return _c(UNKNOWN, "no release id given", release_hash=release_hash)
    if not (len(rel) >= 12 and str(release_hash).lower().startswith(rel)):
        return _c(FAIL, f"release {rel!r} is not the certified release of {slug}@{version} "
                        f"({str(release_hash)[:12]})", release_hash=release_hash)
    pdfs = _certified_pdf_hashes(db, slug, version, release_hash) or {}
    fp = None
    try:
        # `CIR.fingerprint` is a property; calling it raised and left every binding with
        # cir_fingerprint None, which made campaign_consistency's CIR comparison vacuous.
        fp = cir.fingerprint() if callable(cir.fingerprint) else cir.fingerprint
    except Exception:  # noqa: BLE001
        pass
    if not pdfs:
        return _c(UNKNOWN, "no certified PDF hash is on record for this release",
                  release_hash=release_hash, cir_fingerprint=fp)
    return _c(PASS, "bound to the certified release and its certified PDF",
              release_hash=release_hash, pdf_sha256_by_terminology=pdfs, cir_fingerprint=fp,
              pieces=_pieces(cir))


def _pieces(cir) -> int | None:
    try:
        return int(sum(int(getattr(c, "make", 1) or 1) for c in cir.components))
    except Exception:  # noqa: BLE001
        return None


# ---- quality -----------------------------------------------------------------------------

def quality(data: bytes) -> dict:
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:  # noqa: BLE001 - undecodable bytes are not an image
        return _c(FAIL, f"not a decodable image ({type(exc).__name__})")
    fmt, (w, h) = str(img.format or ""), img.size
    problems = []
    if fmt not in ALLOWED_FORMATS:
        problems.append(f"format {fmt or '?'} (Etsy: PNG/JPEG; no webp)")
    if w < MIN_PX or h < MIN_PX:
        problems.append(f"{w}x{h} px is below the {MIN_PX} px minimum on each side")
    alpha = None
    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        alpha = img.convert("RGBA").getchannel("A").getextrema()[0]
        if alpha < 255:
            problems.append("has transparent pixels (Etsy renders transparency black)")
    out = {"width": w, "height": h, "format": fmt, "mode": img.mode}
    if problems:
        return _c(FAIL, "; ".join(problems), **out)
    return _c(PASS, f"{w}x{h} {fmt}, opaque", **out)


# ---- role --------------------------------------------------------------------------------

def role(role_key: str) -> dict:
    job = JOB_OF_ROLE.get(role_key)
    if job is None:
        return _c(FAIL, f"role {role_key!r} has no gallery job; a frame with no job is filler")
    pos = 1 if job == el.HERO_JOB else 2
    try:
        cand = el.Candidate(asset_id=f"candidate-{role_key}", medium=MEDIUM,
                            purpose=el.CONVERSION_CREATIVE, job=job, position=pos)
    except el.EligibilityRefused as exc:
        return _c(FAIL, str(exc)[:300], job=job)
    served = el.may_serve(cand)
    if not served["may_serve"]:
        return _c(FAIL, served["why"][:300], job=job)
    if job == el.HERO_JOB:
        return _c(FAIL, "ASSET_CONCEPT_AS_HERO: a generated image may not be the hero; the hero "
                        "has to be the thing the pattern actually makes", job=job)
    if el.PHYSICAL_PROOF in el.JOB_PURPOSES[job] and el.CONVERSION_CREATIVE not in \
            el.JOB_PURPOSES[job]:
        return _c(FAIL, f"{job} needs a photograph of a real sample", job=job)
    return _c(PASS, served["why"], job=job)


# ---- provenance / disclosure -------------------------------------------------------------

def provenance(cand: dict) -> dict:
    from ..gates.asset_truth import _APPROPRIATED

    text = " ".join(str(cand.get(k) or "") for k in ("prompt", "provider", "model")).lower()
    for marker in _APPROPRIATED:
        if marker in text:
            return _c(FAIL, f"provenance says the source was {marker!r} (#305)")
    kinds = {str(r.get("kind") or "other") for r in cand.get("references") or []}
    bad = sorted(kinds - set(REFERENCE_KINDS))
    if bad:
        return _c(FAIL, f"unknown reference kinds {bad}")
    if not cand.get("provider") or not cand.get("model"):
        return _c(UNKNOWN, "provider and model must be recorded")
    return _c(PASS, f"AI-generated ({cand['provider']}/{cand['model']}), never a photograph",
              kind=cand.get("provenance_kind"))


def disclosure(job: str | None) -> dict:
    if not job:
        return _c(UNKNOWN, "no job, so no label can be chosen")
    label = el.honesty_label(MEDIUM, job)
    if label.get("required") and label.get("label"):
        return _c(PASS, "honesty label assigned to the image's alt text and caption",
                  label=label["label"])
    return _c(FAIL, "a generated image must carry a disclosure and none is defined")


# ---- judges (product truth, identity, anatomy, realism) ----------------------------------

class RealJudges:
    """The production judges: existing deterministic gates, no invented readings.

    `vision` is the vision judge the fidelity verifier asks about craft texture and anchor
    consistency (`visual.fidelity.GatewayVisionJudge`, gated on `image_vision`). Unfunded,
    it answers nothing, and those checks stay UNKNOWN."""

    def __init__(self, db, *, vision=None, second_vision=None, references=None):
        self.db = db
        self.vision = vision
        # W-VISNEXT: a second, independent judge transport (another model). Identity and body
        # proportions need two distinct readings to pass; with one, they can only refuse.
        self.second_vision = second_vision
        self.references = references
        self._adapters = None

    def _vision_judge(self):
        if self.vision is None:
            from .fidelity import GatewayVisionJudge

            self.vision = GatewayVisionJudge(self.db)
        return self.vision

    def adapters(self):
        """The blind vision-judge adapters (`visual.vision_judges`) on this judge transport."""
        if self._adapters is None:
            from .vision_judges import Adapters

            self._adapters = Adapters(self.db, self._vision_judge(), second=self.second_vision,
                                      references=self.references)
        return self._adapters

    def product_truth(self, cand: dict, bind: dict) -> dict:
        """Product Truth for a generated image (W-FIDELITY, OWNERIMG E3).

        `structural_floor` reads UNKNOWN for every generated frame: it has no qualified
        producer for one. `visual.fidelity` is the independent verifier for generated images,
        measured against the certified CIR, so its verdict replaces that UNKNOWN. A floor
        FAIL (wrong stitch scale, a mismatch) stays FAIL whatever the verifier says, and for
        LIFESTYLE `lifestyle_evidence` still applies on top. Publication is untouched: F-852
        refuses generated product imagery in `publication_verdict` whatever this reads."""
        from .product_authority import structural_floor

        floor = structural_floor({"kind": "generated", "generated": True,
                                  "provider": cand.get("provider") or "generated",
                                  "slug": cand.get("slug"), "version": cand.get("version"),
                                  "image": {"sha256": cand.get("sha256")}})
        from .vision_judges import blind_consistency

        fid = fidelity_reading(self.db, cand, bind, judge=self._vision_judge(),
                               consistency=blind_consistency,
                               locate=self.adapters().product_region)
        out = {"structural_floor": floor, "fidelity": fid}
        status = FAIL if floor.get("status") == FAIL else fid["status"]
        if JOB_OF_ROLE.get(cand.get("role")) == el.LIFESTYLE:
            le = lifestyle_reading(cand, bind)
            out["lifestyle_evidence"] = le
            status = worst(status, le["status"])
        why = (f"fidelity {fid['status']}"
               + (f" ({', '.join(fid.get('failed') or [])} failed)" if fid.get("failed") else "")
               + (f" ({', '.join(fid.get('unknown') or [])} unknown)" if fid.get("unknown")
                  else "")
               + f"; structural floor {floor.get('status')}: {floor.get('why') or ''}"
               + ("; lifestyle_evidence " + out["lifestyle_evidence"]["status"]
                  if "lifestyle_evidence" in out else ""))
        return _c(status, why[:400], codes=list(fid.get("codes") or []), **out)

    # W-VISNEXT (OWNERIMG E2): every vision check is a blind, structured question through
    # the same `image_vision`-gated, budget-reserved transport, compared in code
    # (`visual.vision_judges`). Gate closed or unfunded: nothing is called, UNKNOWN.

    def identity(self, cand: dict) -> dict:
        return _plain(self.adapters().identity(cand))

    def anatomy(self, cand: dict) -> dict:
        return _plain(self.adapters().anatomy(cand))

    def body_proportions(self, cand: dict) -> dict:
        # D-W4-LAURA-FLUX3: bust and body proportions against the canonical torso and
        # full-length references.
        return _plain(self.adapters().body_proportions(cand))

    def outfit_consistency(self, cand: dict, outfit: dict | None) -> dict:
        return _plain(self.adapters().outfit_consistency(cand, outfit))

    def realism(self, cand: dict) -> dict:
        return _plain(self.adapters().realism(cand))


def _plain(check: dict) -> dict:
    """An adapter check as a gate reading (status, why, plus what it measured)."""
    return {k: v for k, v in check.items() if k != "check"}


def fidelity_reading(db, cand: dict, bind: dict, *, judge=None, consistency=None,
                     locate=None) -> dict:
    """`visual.fidelity` on a generated candidate, against its certified CIR.

    The product-only anchor is verified as an unfolded flat lay. Any other role is a
    lifestyle image: it needs the release's anchor PASS (read from the learning rows), the
    candidate's declared `product_region` and a vision consistency reading."""
    from . import fidelity as FID
    from .image_production import ANCHOR_ROLE

    def unknown(why: str) -> dict:
        return {"status": UNKNOWN, "checker": FID.CHECKER, "why": why, "checks": [],
                "failed": [], "unknown": ["fidelity"], "codes": [FID.FC.UNVERIFIABLE_COUNT]}

    data = cand.get("data") or b""
    if not data:
        return unknown("no image bytes to verify")
    try:
        if bind.get("experiment"):
            # W4-WRAPTEST: an EXPERIMENT verifies against its own uncertified content (bound
            # by `experiment.binding`); the verdict is never publication evidence.
            from . import experiment as XP

            reg = XP.registration(db, cand.get("slug", ""), cand.get("version", ""),
                                  bind.get("release_hash"))
            cir, release_hash = (XP.cir_of(reg), reg["release"]) if reg else (None, None)
        else:
            from ..publish.release_gates import _release

            cir, release_hash = _release(db, cand.get("slug", ""), cand.get("version", ""))
    except Exception as exc:  # noqa: BLE001 - unreadable is unknown
        return unknown(f"certified CIR unreadable ({type(exc).__name__})")
    if cir is None:
        return unknown("no certified CIR to verify against")
    if cand.get("role") == ANCHOR_ROLE:
        return FID.verify_anchor(data, cir, judge=judge)
    release = str(bind.get("release_hash") or release_hash or "")
    anchor, anchor_data = _anchor_of(db, cand, release)
    region, located = cand.get("product_region"), None
    if not region and locate is not None and (anchor or {}).get("status") == PASS:
        # Only asked once the release's anchor has passed: without it the image cannot pass
        # whatever its colours, so the call would be spend without a decision.
        # W-VISNEXT: the lifestyle product-region detector (interior fabric patches located
        # blind by the vision judge; the palette inside them is measured in code).
        located = locate(cand)
        region = located.get("patches") or None
    out = FID.verify_lifestyle(data, cir, release_hash=release, anchor=anchor,
                               anchor_data=anchor_data, product_region=region, judge=judge,
                               consistency=consistency)
    if located is not None:
        out = {**out, "product_region": {"source": "vision_judges.locate_product",
                                         "patches": located.get("patches") or [],
                                         "why": located.get("why") or ""}}
    return out


def _anchor_of(db, cand: dict, release: str):
    """The release's best product-only anchor and its bytes, or (None, None)."""
    from .image_production import ANCHOR_ROLE, _best, run_key

    if not release:
        return None, None
    listing = cand.get("listing") or outfits.listing_of(cand.get("slug", ""))
    try:
        best = _best(db, listing=listing, role=ANCHOR_ROLE,
                     run=run_key(cand.get("slug", ""), cand.get("version", ""), release)) or \
            _best(db, listing=listing, role=ANCHOR_ROLE)
    except Exception:  # noqa: BLE001 - no learning table yet: no anchor
        return None, None
    if not best or not best.get("sha256") or not str(best.get("release") or "").startswith(
            release[:12]):
        return None, None
    data = None
    try:
        from ..core.artifacts import ArtifactStore

        data = ArtifactStore().get(best["sha256"], db=db)
    except Exception:  # noqa: BLE001 - bytes unavailable: consistency stays unread
        data = None
    return ({"status": best.get("technical_status"), "release_hash": best.get("release"),
             "sha256": best["sha256"]}, data)


def lifestyle_reading(cand: dict, bind: dict) -> dict:
    """`compose.lifestyle_evidence` on what is known about a generated image."""
    from .compose import lifestyle_evidence

    kinds = {r.get("kind") for r in cand.get("references") or []}
    rclass = ("physical_product_photo" if "physical_product_photo" in kinds else
              "chart" if "pattern_derived" in kinds else None)
    ev = {"product": {"slug": cand.get("slug"), "version": cand.get("version"),
                      "pdf_version": cand.get("version"), "pieces": bind.get("pieces"),
                      "cir_fingerprint": bind.get("cir_fingerprint")},
          "reference": {"class": rclass, "product_version": cand.get("version")}}
    return lifestyle_evidence(ev)


# ---- the one evaluation ------------------------------------------------------------------

def evaluate(db, cand: dict, *, judges=None, record_outfit_use: bool = True) -> dict:
    """Every check, the technical verdict and the publication verdict for one candidate.

    `cand`: sha256, data (bytes), slug, version, release, role, provider, model, prompt,
    references [{sha256, kind}], laura_present, outfit_id, listing, provenance_kind. Nothing
    here reads `method`.
    """
    judges = judges or RealJudges(db)
    data = cand.get("data") or b""
    sha = hashlib.sha256(data).hexdigest() if data else ""
    if cand.get("sha256") and cand["sha256"] != sha:
        raise ValueError("candidate sha256 does not match its bytes")
    cand = {**cand, "sha256": sha}
    job = JOB_OF_ROLE.get(cand.get("role"))
    checks: dict[str, dict] = {}
    bind = None
    if cand.get("experiment"):
        # W4-WRAPTEST: an EXPERIMENT candidate binds to its uncertified content (scratch
        # database only); without an open experiment it falls through and fails as usual.
        from .experiment import binding as experiment_binding

        bind = experiment_binding(db, cand.get("slug", ""), cand.get("version", ""),
                                  cand.get("release", ""))
    bind = bind or binding(db, cand.get("slug", ""), cand.get("version", ""),
                           cand.get("release", ""))
    checks["binding"] = bind
    checks["provenance"] = provenance(cand)
    checks["quality"] = quality(data)
    checks["role"] = role(cand.get("role", ""))
    pt = judges.product_truth(cand, bind)
    from .repair_routes import UNVERIFIABLE_COUNT

    if UNVERIFIABLE_COUNT in (pt.get("codes") or []) and pt.get("status") == PASS:
        # A count the image cannot show is never passed (owner wrap experiment, 2026-10-19).
        pt = {**pt, "status": UNKNOWN, "why": f"{UNVERIFIABLE_COUNT}: " + str(pt.get("why"))}
    checks["product_truth"] = pt
    laura = bool(cand.get("laura_present"))
    checks["identity"] = judges.identity(cand) if laura else _c(NA, "Laura does not appear")
    checks["body_proportions"] = (_judge(judges, "body_proportions", cand) if laura else
                                  _c(NA, "Laura does not appear"))
    checks["anatomy"] = (judges.anatomy(cand) if laura or job == el.LIFESTYLE
                         else _c(NA, "no person or hands in a product-only frame"))
    checks["realism"] = judges.realism(cand)
    checks["disclosure"] = disclosure(job)
    listing = cand.get("listing") or outfits.listing_of(cand.get("slug", ""))
    if laura:
        checks["outfit"] = outfits.check_use(
            db, cand.get("outfit_id"), listing=listing,
            product=f"{cand.get('slug')}@{cand.get('version')}", image_sha256=sha,
            record=record_outfit_use and checks["identity"]["status"] != FAIL)
        checks["outfit_distinctness"] = outfits.distinctness(db, cand.get("outfit_id"),
                                                             listing)
        reserved = outfits.get(db, cand["outfit_id"]) if cand.get("outfit_id") else None
        checks["outfit_consistency"] = (
            _judge(judges, "outfit_consistency", cand, reserved)
            if checks["outfit"]["status"] == PASS else
            _c(UNKNOWN, "no reserved outfit to compare the image against"))
    else:
        checks["outfit"] = _c(NA, "Laura does not appear")
        checks["outfit_consistency"] = _c(NA, "Laura does not appear")
        checks["outfit_distinctness"] = _c(NA, "Laura does not appear")
    technical = worst(*(c["status"] for c in checks.values()))
    publication = publication_verdict({**cand, "_db": db}, checks, job, laura)
    if bind.get("experiment"):
        from .experiment import publication_blockers

        publication = {**publication, "publishable": False, "may_export": False,
                       "blockers": publication_blockers(bind) + list(publication["blockers"])}
    failures = sorted({FAILURE_CATEGORY[k] for k, c in checks.items() if c["status"] == FAIL})
    # The shared Product Truth failure codes (W-FLUXAPI's constant; repair_routes) are kept
    # as reported so learning and the repair router read the same words.
    # Every check that reports codes (Product Truth, outfit uniqueness and distinctness,
    # outfit consistency) contributes them, so a wardrobe failure is learnt like a fabric one.
    for c in checks.values():
        if c.get("status") in (FAIL, UNKNOWN):
            failures += [str(x) for x in c.get("codes") or [] if str(x) not in failures]
    out = {"gates_version": GATES_VERSION, "sha256": sha, "listing": listing, "job": job,
           "checks": checks, "technical_status": technical,
           "publication": publication, "publishable": publication["publishable"],
           "failure_categories": failures,
           "unknown": sorted(k for k, c in checks.items() if c["status"] == UNKNOWN)}
    if laura:
        out["laura_gates"] = laura_gate_order(checks, publication)
    return out


def _judge(judges, name: str, *args) -> dict:
    """A judge reading; a judge that cannot make this reading leaves it UNKNOWN."""
    fn = getattr(judges, name, None)
    if fn is None:
        return _c(UNKNOWN, f"no {name} reading: the judge in use cannot make it")
    return fn(*args)


def _gate(gate: str, status: str, why: str) -> el.GateResult:
    outcome = {PASS: el.PASSED, FAIL: el.FAILED}.get(status, el.NOT_RUN)
    return el.GateResult(gate, outcome, why or status)


ETSY_POLICY_STATUS = UNKNOWN   # VISGATE V1: the binding page has not been read


def _scope_of(cand: dict, job: str | None) -> str:
    if cand.get("scope"):
        return str(cand["scope"])
    if job == el.DETAIL:
        return "detail"
    if cand.get("laura_present") or job == el.LIFESTYLE or cand.get("role") in (
            "lifestyle", "angle"):
        return "lifestyle"
    return "product_only"


def exception_evidence(cand: dict, checks: dict, job: str | None, laura: bool, *,
                       other_publication_blockers: list[str]) -> dict:
    """The D-W4-F852-AMEND evidence for `eligibility.may_export`, read only from the checks
    this module ran and the candidate's recorded provenance. Never the owner's approval."""
    st = {k: (v or {}).get("status", UNKNOWN) for k, v in checks.items()}
    fid = ((checks.get("product_truth") or {}).get("fidelity") or {})
    bind = checks.get("binding") or {}
    ev = cand.get("identity_evidence") or {}
    receipt = (ev.get("request") or {}).get("request_sha256") or ev.get("task_id") or \
        cand.get("receipt")
    label = (checks.get("disclosure") or {}).get("label")
    return {
        "label": label, "scope": _scope_of(cand, job), "laura_present": laura,
        "presented_as": ("ai_generated" if str(cand.get("provenance_kind") or "ai_generated")
                         .startswith("ai_generated") else str(cand.get("provenance_kind"))),
        "fidelity_release": bind.get("release_hash") if fid else None,
        "checks": {
            "structural_fidelity": fid.get("status") or UNKNOWN,
            "photographic": st.get("realism", UNKNOWN),
            "product_truth": st.get("product_truth", UNKNOWN),
            "quality": st.get("quality", UNKNOWN),
            "identity": st.get("identity", UNKNOWN),
            "body_proportions": st.get("body_proportions", UNKNOWN),
            "outfit": worst(st.get("outfit", UNKNOWN), st.get("outfit_distinctness", UNKNOWN),
                            st.get("outfit_consistency", UNKNOWN)),
            "etsy_policy": ETSY_POLICY_STATUS,
            "publication_gates": FAIL if other_publication_blockers else PASS},
        "provenance": {"model": cand.get("model"),
                       "references": [{"sha256": r.get("sha256"), "kind": r.get("kind")}
                                      for r in cand.get("references") or []],
                       "release": bind.get("release_hash"),
                       "prompt_version": cand.get("prompt_version"),
                       "receipt": receipt, "disclosure": label},
        # recorded so a reader can see it was not used
        "owner_visual_approval_is_not_an_input": True}


def publication_verdict(cand: dict, checks: dict, job: str | None, laura: bool) -> dict:
    blockers: list[str] = []
    other: list[str] = []
    if laura:
        from . import canonical

        status = canonical.asset_status(cand.get("sha256", ""))
        if status != canonical.PUBLICATION_APPROVED_STATUS:
            other.append(f"Laura publication gate: these bytes are '{status}', not "
                         f"publication_approved")
    export = None
    if job is not None:
        try:
            c = el.Candidate(asset_id=f"candidate-{cand.get('sha256', '')[:12]}", medium=MEDIUM,
                             purpose=el.CONVERSION_CREATIVE, job=job,
                             position=1 if job == el.HERO_JOB else 2)
            st = {k: v["status"] for k, v in checks.items()}
            results = [
                _gate(el.DATA_TRUTH, worst(st["binding"], st["product_truth"]),
                      checks["product_truth"]["why"]),
                _gate(el.LAYOUT_QA, st["quality"], checks["quality"]["why"]),
                _gate(el.COMMERCIAL_QA, worst(st["role"], st["realism"], st["anatomy"]),
                      checks["role"]["why"]),
                _gate(el.POLICY_PROVENANCE, worst(st["provenance"], st["identity"],
                                                  st["body_proportions"], st["disclosure"],
                                                  st["outfit"], st["outfit_distinctness"],
                                                  st["outfit_consistency"]),
                      checks["provenance"]["why"])]
            export = el.may_export(c, results,
                                   truth_verdict=el.FAILED if st["product_truth"] == FAIL
                                   else None,
                                   generated_evidence=exception_evidence(
                                       cand, checks, job, laura,
                                       other_publication_blockers=other))
            blockers += export["blockers"]
        except el.EligibilityRefused as exc:
            blockers.append(str(exc)[:300])
    else:
        blockers.append("no gallery job")
    if ETSY_POLICY_STATUS != PASS:
        blockers.append(ETSY_POLICY_UNKNOWN)
    blockers += other
    if cand.get("_db") is not None:
        from .experiment import LABEL, is_experiment_image

        if is_experiment_image(cand["_db"], cand.get("sha256")):
            blockers.insert(0, f"{LABEL}: a controlled-experiment image is never published")
    return {"publishable": not blockers, "blockers": blockers,
            "may_export": bool(export and export["may_export"])}


def laura_gate_order(checks: dict, publication: dict) -> list[dict]:
    from . import canonical

    m = {"canonical_identity": checks["identity"],
         "body_proportions": checks["body_proportions"],
         "outfit_consistency": checks["outfit_consistency"],
         "outfit_distinctness": checks["outfit_distinctness"],
         "photorealism": checks["realism"],
         "anatomy": checks["anatomy"], "product_truth_if_product_shown": checks["product_truth"],
         "outfit_uniqueness": checks["outfit"],
         "composition_brand_qa": _c(UNKNOWN, "brand QA has not reviewed this image"),
         "disclosure_policy": _c(worst(checks["disclosure"]["status"], UNKNOWN),
                                 "label assigned; Etsy policy reading UNKNOWN"),
         "publication_gate": _c(PASS if publication["publishable"] else FAIL,
                                "; ".join(publication["blockers"])[:400] or "publishable")}
    return [{"gate": g, **m[g]} for g in canonical.LAURA_LISTING_GATES]


def campaign_consistency(rows: list[dict]) -> dict:
    """One product version, release, CIR (colours, components, construction), listing and,
    for Laura, one outfit across a gallery's images (D-W4-LAURA-FLUX3 §6). A mix is refused."""
    if not rows:
        return _c(UNKNOWN, "no images to compare")
    problems = []
    for field in ("listing", "version", "release", "cir_fingerprint"):
        vals = {r.get(field) for r in rows}
        if len(vals) > 1:
            problems.append(f"{field} differs across the gallery: {sorted(map(str, vals))}")
    looks = {r.get("outfit_id") for r in rows if r.get("laura_present")}
    if len(looks) > 1:
        problems.append(f"Laura wears {len(looks)} outfits in one listing: {sorted(map(str, looks))}")
    # F-226 (W4-C08): two Laura frames that are one photograph are copy-paste sameness, not a
    # real person photographed on different days. Frames whose bytes are not held are skipped.
    from . import naturalism

    same = naturalism.sameness_only(rows)
    for f in same["findings"]:
        problems.append(f"copy-paste sameness between Laura frames {f['frames']}: {f['why']}")
    if problems:
        return _c(FAIL, "; ".join(problems))
    return _c(PASS, f"{len(rows)} image(s): one version, release, CIR and outfit")
