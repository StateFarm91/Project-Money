"""Owner-supplied listing frames: the same gates as generated ones (ENG-OWNER-GALLERY).

The owner makes listing frames outside the factory (FLUX 3 on the BFL dashboard, with the
locked Laura model `visual.canonical.IDENTITY_ID`) and supplies them as files.
`ingest(db, slug, version, files, actor="owner")` takes a set of them. It certifies a gallery
only when every frame passes every gate a generated frame must pass, plus the checks below.
Nothing here is a lighter path.

**What intake does, in order:**

1. It stores the exact bytes in the artefact store, keyed by their sha256. The bytes are
   never modified: no label, no watermark, no re-encode.
2. It records the internal provenance: an append-only `images.owner_frame_received` audit
   row with the sha256, the owner-reported generator and model, the Laura identity id and
   the actor. The candidate row has provenance kind `ai_generated_owner_submitted` and the
   gallery asset claims `is_photograph: False, supplied_by: owner`. These records are
   internal: no buyer surface reads them.
3. It assigns each file a campaign role (`shot_plans.FLUX_SLOTS`: hero, colour_context,
   lifestyle, angle, detail, size). A file marked `alternate` is judged but not placed.
4. It judges each frame:
   - `candidate_gates.evaluate` on the generated-gallery route: binding, provenance,
     quality, role, product truth against the release's CIR anchor, motif fidelity,
     identity, body proportions, outfit, anatomy, realism and disclosure. These are the
     same judges with the same rules.
   - `gallery_persist.frame_matrix`: the same per-frame gate matrix, including
     `cir_references` (the frame must have been conditioned on the release's CIR reference
     renders, in order) and the generated-gallery exception (`eligibility.gallery_exception`).
   - three checks on top of those:
     - `product_scale`: `visual.scale` against the twin's finished size;
     - `stripe_layout`: the vessel wall's colour bands against the CIR, measured in code on
       a column the judge points at;
     - `alt_text`: the buyer-facing alt text, through `buyer_text_problems`.
5. It runs the set checks: every slot filled exactly once, and `campaign_consistency` (one
   version, release, CIR and outfit; the frames agree on the item).
6. With no blocker at all, it writes the frames as gallery-route `ListingAsset` rows, records
   the selection and has `release_gates.listing_set` certify the set. The listing set runs its
   own four gates, the seven-frame standard, the CONTENTS frame, mobile QA and the dimension
   audit. With any blocker nothing is written, and each blocker names the file, the gate and
   the reason.

**Buyer-facing text (D-OWNER-NO-RENDER-LABELS, owner direct order 2026-11-21).** The order
reads: "NO FLUX PHOTOS WILL SAY RENDERING. Everything is supposed to look real. Do not add
labels." Therefore:
- no label or watermark is drawn on the pixels;
- an owner frame's alt text describes the scene and the certified product. It never says
  "render"/"rendering", never claims to be a photograph, and never claims a made sample
  (`buyer_text_problems`);
- listing copy that claims a made sample, a test or "I made this" is refused
  (`check_listing_copy`, which also runs `gates.estimate_claims`' physical-claim words).

Provenance stays recorded internally, as the order requires.

**What the judges point at and what code measures.** As in `visual.scale`, the vision judge
only points: it returns boxes. Code does the measuring. Locally, and in tests, the judge is a
stub, and every reading it makes is labelled.
"""
from __future__ import annotations

import hashlib
import io
import re
from pathlib import Path

from ..publish import eligibility as el
from . import candidate_gates as CG

PROVENANCE_KIND = "ai_generated_owner_submitted"      # = publish.owner_images.PROVENANCE_KIND
SUPPLIED_BY = "owner"
METHOD = "owner_submitted"
RECEIVED_ACTION = "images.owner_frame_received"
VERDICT_ACTION = "images.owner_frame_verdict"
CERTIFY_ACTION = "images.owner_gallery_certify"
RUN_SUFFIX = "#owner"          # owner frames are recorded under their own run, never mixed
                               # into a generated run's candidate selection
DEFAULT_GENERATOR = "FLUX 3 (BFL dashboard, owner-reported)"
DEFAULT_PROVIDER = "bfl-dashboard"
PROMPT_VERSION = "owner-supplied"
MAX_BYTES = 25_000_000
ALTERNATE = "alternate"
OWNER_AGENT = "ENG-OWNER-GALLERY"

PASS, FAIL, UNMEASURED, NA = "PASS", "FAIL", "UNMEASURED", "NOT_APPLICABLE"


class OwnerFrameRefused(ValueError):
    """The intake itself is refused (no certified release, unreadable file, bad roles)."""


class CopyRefused(ValueError):
    """Buyer-facing copy that says what is not true."""


def slots() -> tuple[tuple[str, str], ...]:
    """(job, role) for every generated slot of the seven-frame campaign, in order."""
    from .shot_plans import FLUX_SLOTS

    return tuple((j, r) for j, r in FLUX_SLOTS if j != el.CONTENTS)


# ---- buyer-facing text -----------------------------------------------------------------------

# Owner direct order 2026-11-21: no FLUX frame "says rendering".
_RENDER_WORDS = re.compile(r"\brender(?:s|ed|ing|ings)?\b", re.IGNORECASE)
# Claims that a made sample exists or that the seller made or tested the item.
_MADE_SAMPLE = re.compile(
    r"\b(?:i|we)\s+(?:have\s+|had\s+|just\s+)?(?:made|crocheted|stitched|hooked|worked|"
    r"tested)\s+(?:this|these|it|one|mine|ours|the\s+(?:sample|basket|piece|item))\b"
    r"|\bhand\s*made\s+by\s+(?:me|us)\b|\bmade\s+by\s+(?:me|us)\b"
    r"|\b(?:my|our)\s+(?:own\s+)?(?:sample|test\s+piece|finished\s+(?:piece|basket|item))\b"
    r"|\b(?:made|worked|test(?:er)?|finished|physical|real)\s+sample\b"
    r"|\bsample\s+(?:i|we)\s+made\b"
    r"|\b(?:pattern|design)\s+(?:is\s+|was\s+|has\s+been\s+)?tested\b",
    re.IGNORECASE)
# On an image's alt text: the image must not call itself a photograph of the thing.
_PHOTO_CLAIM = re.compile(r"\bphoto(?:graph)?s?\b|\bpictured\b|\bsnapshot\b", re.IGNORECASE)


def buyer_text_problems(text: str, *, surface: str = "copy") -> list[str]:
    """Every reason `text` may not be shown to a buyer. `surface`: "alt" or "copy".

    Both surfaces refuse: render/rendering wording (owner order), a made-sample or
    "I made this" claim, and `gates.estimate_claims`' physical-measurement words ("tested",
    "measures", "as pictured", ...) after its honest negations are removed. Alt text also
    may not call the image a photograph, and must fit Etsy's alt-text limit."""
    from ..gates import estimate_claims as EC

    text = str(text or "")
    honest = EC._clean(text)          # "not yet tested on a physical sample" is the truth
    out: list[str] = []
    if _RENDER_WORDS.search(text):
        out.append("says render/rendering (owner order D-OWNER-NO-RENDER-LABELS)")
    m = _MADE_SAMPLE.search(honest)
    if m:
        out.append(f"claims a made sample or that the seller made/tested it ({m.group(0)!r})")
    phys = EC._PHYSICAL.search(honest)
    if phys:
        out.append(f"implies a physical measurement or test of a made piece "
                   f"({phys.group(0)!r}; gates.estimate_claims)")
    if surface == "alt":
        from ..publish.disclosed_listing import ALT_TEXT_MAX

        p = _PHOTO_CLAIM.search(text)
        if p:
            out.append(f"calls the image a photograph ({p.group(0)!r}); no made sample exists")
        if not text.strip():
            out.append("alt text is empty")
        if len(text) > ALT_TEXT_MAX:
            out.append(f"alt text is {len(text)} characters; Etsy allows {ALT_TEXT_MAX}")
    return out


def check_listing_copy(text: str) -> dict:
    """Refuse listing copy that claims a made sample, a test or "I made this"."""
    problems = buyer_text_problems(text, surface="copy")
    if problems:
        raise CopyRefused("; ".join(problems))
    return {"ok": True, "checked": len(str(text or ""))}


_COUNT_WORD = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
_SHAPE_WORD = {3: "Triangular", 4: "Square", 5: "Pentagonal", 6: "Hexagonal", 8: "Octagonal"}


def product_phrase(cir) -> str:
    """What the certified product is, in buyer words, from the CIR (never from the image)."""
    from . import vessel as V

    models = [m for m in V.vessel_models(cir) if m.modelled] if V.is_vessel(cir) else []
    if models:
        m = models[0]
        shape = _SHAPE_WORD.get(int(m.sides or 0), "Round" if not m.sides else "")
        main = m.wall_bands[0] if m.wall_bands else ""
        stripes = {}
        for c in m.wall_bands:
            if c != main:
                stripes[c] = stripes.get(c, 0) + 1
        tail = " and ".join(f"{_COUNT_WORD.get(n, n)} {c} stripe{'s' if n > 1 else ''}"
                            for c, n in stripes.items())
        noun = "basket"
        return " ".join(x for x in (shape, "crochet", noun) if x) + (
            f" in {main}" if main else "") + (f" with {tail}" if tail else "")
    title = re.sub(r"\b(?:crochet|pattern)\b", "", str(cir.title or ""), flags=re.I)
    return "Crochet " + " ".join(title.split()).lower()


def alt_text(cir, scene: str) -> str:
    """The buyer-facing alt text: the certified product, then the scene. No label."""
    scene = " ".join(str(scene or "").split()).rstrip(".")
    return (f"{product_phrase(cir)}, {scene}." if scene else f"{product_phrase(cir)}.")


# ---- the measurements the judge points for -----------------------------------------------------

def wall_prompt() -> str:
    return ("Find the handmade crochet vessel in this image. Choose one wall face that faces "
            "the camera most squarely. Give a narrow vertical strip on that face, from the "
            "bottom edge of the wall up to the top edge of the rim, as a box in fractions of "
            "the image width and height. Do not describe colours or count anything. Answer as "
            'JSON: {"wall_box": [x0, y0, x1, y1]} or {"wall_box": null} if no wall is visible.')


def bands_in_column(data: bytes, box, palette: dict[str, str], *, min_frac: float = 0.03):
    """The colour runs, bottom to top, of the per-row mean colour inside `box`.

    The strip is first white-balanced: its brightest quarter of rows is taken to be the
    palette colour nearest them, and per-channel gains map it there, so warm or dim light
    does not move a colour. Each row is then labelled with the nearest palette colour in
    CIELAB. Lightness separates a dark stripe from shaded main yarn, which chromaticity alone
    does not when the light desaturates the stripe. A run shorter than `min_frac` of the
    strip's height (or 2 px) is merged into its neighbour."""
    import numpy as np
    from PIL import Image

    from . import fidelity as FID

    img = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = img.size
    x0, y0, x1, y1 = (float(t) for t in box)
    px = (int(x0 * w), int(y0 * h), max(int(x1 * w), int(x0 * w) + 1),
          max(int(y1 * h), int(y0 * h) + 1))
    arr = np.asarray(img.crop(px), dtype=float)
    rows = arr.mean(axis=1)[::-1]                                  # bottom to top
    names = list(palette)
    pal_rgb = np.array([FID._hex_rgb(palette[n]) for n in names], dtype=float)
    pal_lab = FID._lab(pal_rgb)
    lum = rows.mean(axis=1)
    bright = rows[lum >= np.quantile(lum, 0.75)].mean(axis=0)
    ref = int(np.argmin(FID._de(FID._lab(bright[None, :]), pal_lab)))
    gains = pal_rgb[ref] / np.maximum(bright, 1.0)
    balanced = np.clip(rows * gains, 0, 255)
    d = FID._de(FID._lab(balanced)[:, None, :], pal_lab[None, :, :])
    labels = [names[i] for i in d.argmin(axis=1)]
    runs: list[list] = []
    for lab in labels:
        if runs and runs[-1][0] == lab:
            runs[-1][1] += 1
        else:
            runs.append([lab, 1])
    floor = max(2, int(min_frac * len(labels)))
    merged = True
    while merged and len(runs) > 1:
        merged = False
        for i, (lab, n) in enumerate(runs):
            if n < floor:
                j = i - 1 if i > 0 else i + 1
                runs[j][1] += n
                del runs[i]
                k = 0
                while k < len(runs) - 1:                         # re-join equal neighbours
                    if runs[k][0] == runs[k + 1][0]:
                        runs[k][1] += runs.pop(k + 1)[1]
                    else:
                        k += 1
                merged = True
                break
    return [(lab, n) for lab, n in runs], len(labels)


def stripe_layout(judge, data: bytes, cir) -> dict:
    """The vessel wall's colour bands against the CIR (stripe count and placement).

    The judge points at one wall strip; code reads the bands bottom to top and compares them
    with `vessel.vessel_models(cir)`: the band sequence must be the CIR's, and each band's
    share of the wall must be within `vessel.SHARE_REL_MAX` of the CIR's row share. Shares
    are read on one face, so perspective scales them alike. Not a vessel: NOT_APPLICABLE
    (product truth reads it). No pointer, no box: UNMEASURED."""
    from . import vessel as V
    from . import vision_judges as VJ

    name = "stripe_layout"
    if not V.is_vessel(cir):
        return VJ._c(name, NA, "not a vessel; the wall layout is product truth's reading")
    models = [m for m in V.vessel_models(cir) if m.modelled]
    if not models:
        return VJ._c(name, CG.UNKNOWN, "the CIR's wall cannot be modelled")
    m = models[0]
    got = VJ.ask(judge, "wall_column", wall_prompt(), [data], max_tokens=200)
    if not got["answered"]:
        return VJ._c(name, CG.UNKNOWN, f"not pointed: {got['why']}", needs="vision judge")
    box = (got["reading"] or {}).get("wall_box")
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return VJ._c(name, CG.UNKNOWN, "no wall strip was pointed at", judge=got["judge"])
    try:
        x0, y0, x1, y1 = (float(t) for t in box)
        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
            raise ValueError("box outside the frame")
        runs, height = bands_in_column(data, box, m.palette)
    except Exception as exc:  # noqa: BLE001 - unmeasurable is UNKNOWN, never PASS
        return VJ._c(name, CG.UNKNOWN, f"wall strip unreadable ({type(exc).__name__}: {exc})"
                     [:300], judge=got["judge"])
    if height / max(m.wall_total_rows, 1) < V.MIN_PX_PER_ROW:
        return VJ._c(name, CG.UNKNOWN, f"{height} px for {m.wall_total_rows} wall rows",
                     judge=got["judge"])
    seen = [lab for lab, _n in runs]
    want = list(m.wall_bands)
    main = want[0] if want else ""
    stripes_seen = sum(1 for c in seen if c != main)
    stripes_want = sum(1 for c in want if c != main)
    measured = {"bands": seen, "px": [n for _l, n in runs], "expected": want,
                "expected_rows": list(m.wall_rows), "strip_px": height,
                "stripes_seen": stripes_seen, "stripes_expected": stripes_want,
                "judge": got["judge"], "box": [round(float(t), 4) for t in box]}
    if seen != want:
        return VJ._c(name, FAIL, f"wall bands {seen} bottom to top ({stripes_seen} stripe(s)); "
                                 f"the CIR's wall is {want} ({stripes_want} stripe(s))",
                     code="WRONG_COLOUR_LAYOUT", **measured)
    shares = [n / height for _l, n in runs]
    expect = [r / m.wall_total_rows for r in m.wall_rows]
    rel = [abs(s - e) / e for s, e in zip(shares, expect)]
    worst = max(rel)
    measured.update(shares=[round(s, 3) for s in shares],
                    expected_shares=[round(e, 3) for e in expect], worst_rel=round(worst, 3))
    if worst > V.SHARE_REL_MAX:
        i = rel.index(worst)
        return VJ._c(name, FAIL, f"band {i + 1} ({seen[i]}) is {shares[i]:.0%} of the wall; "
                                 f"the CIR's is {expect[i]:.0%} ({m.wall_rows[i]} of "
                                 f"{m.wall_total_rows} rounds); worst off by {worst:.0%}",
                     code="WRONG_COLOUR_LAYOUT", **measured)
    return VJ._c(name, PASS, f"wall bands {seen} with shares within "
                             f"{V.SHARE_REL_MAX:.0%} of the CIR's rounds", **measured)


# The roles whose job is to show size, and any frame with a person in it, must be measured
# for scale; a plain, prop-free product shot (`setting: plain`) has nothing a buyer reads size
# from, so an anchor-less reading there is NOT_APPLICABLE. Any measured FAIL is a FAIL.
SCALE_REQUIRED_ROLES = frozenset({"size", "lifestyle"})


def product_scale(judge, data: bytes, cir, *, role: str, laura: bool) -> dict:
    from . import scale as SC
    from . import vision_judges as VJ

    out = SC.verify(judge, data, cir)
    if out.get("status") != CG.UNKNOWN:
        return out
    setting = str(out.get("setting") or "").lower()
    if (role not in SCALE_REQUIRED_ROLES and not laura and setting == "plain"
            and "no known-size anchor" in str(out.get("why") or "")):
        return VJ._c(SC.CHECK, NA, "plain product shot with no scene objects: nothing in "
                                   "the frame states a size", judge=out.get("judge"))
    return out


# ---- intake ------------------------------------------------------------------------------------

def _bytes_of(spec: dict) -> bytes:
    if spec.get("data") is not None:
        data = bytes(spec["data"])
    elif spec.get("path"):
        data = Path(spec["path"]).read_bytes()
    else:
        raise OwnerFrameRefused(f"{spec.get('name') or '?'}: no bytes and no path")
    if not data:
        raise OwnerFrameRefused(f"{spec.get('name') or '?'}: empty file")
    if len(data) > MAX_BYTES:
        raise OwnerFrameRefused(f"{spec.get('name') or '?'}: over {MAX_BYTES // 1_000_000} MB")
    return data


def owner_run_key(slug: str, version: str, release: str) -> str:
    from . import image_production as IP

    return IP.run_key(slug, version, release) + RUN_SUFFIX


def _flux_run_key(slug: str, version: str, release: str) -> str:
    from . import image_production as IP
    from .shot_plans import FLUX_ROUTE

    return IP.run_key(slug, version, release, route=FLUX_ROUTE)


def _prepared_cir_references(db, flux_key: str):
    """The ordered sha256 of the CIR reference renders the release's generated-gallery run
    prepared, or None when no such run has prepared them."""
    from . import image_production as IP

    try:
        prepared = ((IP._stage_data(db, flux_key).get("prepare_references") or {})
                    .get("outputs") or {}).get("references")
    except Exception:  # noqa: BLE001 - not on file is unmeasured
        return None
    if not isinstance(prepared, list):
        return None
    from ..creative.pdf_page_refs import is_page_ref

    return [r["sha256"] for r in prepared if r.get("kind") == "pattern_derived"
            and not is_page_ref(r)]


def _validate(files: list[dict]) -> list[dict]:
    roles = {r for _j, r in slots()}
    placed: dict[str, str] = {}
    out = []
    for i, spec in enumerate(files):
        name = str(spec.get("name") or f"file-{i + 1}")
        role = str(spec.get("role") or "")
        if role not in roles:
            raise OwnerFrameRefused(f"{name}: role {role!r} is not a campaign slot "
                                    f"{sorted(roles)}")
        alternate = bool(spec.get(ALTERNATE))
        if not alternate:
            if role in placed:
                raise OwnerFrameRefused(f"{name}: slot {role!r} is already filled by "
                                        f"{placed[role]}; mark one of them alternate")
            placed[role] = name
        out.append({**spec, "name": name, "role": role, ALTERNATE: alternate})
    return out


def ingest(db, slug: str, version: str, files: list[dict], *, actor: str = "owner",
           judges=None, pointer=None, store_root=None, generator: str = DEFAULT_GENERATOR,
           provider: str = DEFAULT_PROVIDER, issue: bool = True) -> dict:
    """Take a set of owner frames for `slug@version`, judge each on the same gates as a
    generated frame, and certify the gallery only when nothing blocks.

    `files`: [{name, path|data, role, laura_present, scene, outfit_id?, references?,
    alternate?}]. `scene` is the buyer-facing scene description the alt text is built from.
    `references` lists what the owner conditioned the frame on ([{sha256, kind}]); Laura's
    canonical face is added for a frame with Laura in it.
    `judges`: the candidate-gate judges (`candidate_gates.RealJudges` by default).
    `pointer`: the vision transport that points for scale and the wall strip (the production
    one when None, so nothing is read unless it is funded)."""
    from sqlalchemy import select

    from ..core.models import AuditLog
    from ..publish import release_gates as RG
    from . import canonical
    from . import gallery_persist as GP
    from . import image_production as IP
    from . import outfits
    from .image_records import ImageCandidate, ensure_tables
    from .shot_plans import flux_family

    actor = str(actor or "owner")[:64]
    specs = _validate(list(files or []))
    if not specs:
        raise OwnerFrameRefused("no files")
    cir, release = RG._release(db, slug, version)
    if cir is None or not release:
        raise OwnerFrameRefused(f"{slug}@{version} has no certified release; owner frames are "
                                f"judged against a certified CIR only")
    judges = judges or CG.RealJudges(db)
    if pointer is None:
        pointer = judges._vision_judge() if hasattr(judges, "_vision_judge") else None
    ensure_tables(db)
    listing = outfits.listing_of(slug)
    flux_key = _flux_run_key(slug, version, release)
    own_key = owner_run_key(slug, version, release)
    cir_refs = _prepared_cir_references(db, flux_key)
    jobs = {r: j for j, r in slots()}
    frames: list[dict] = []
    for spec in specs:
        data = _bytes_of(spec)
        sha = IP.store_bytes(db, data, key=f"owner-frame/{slug}@{version}",
                             why="owner-supplied AI frame (never a photograph)")
        laura = bool(spec.get("laura_present"))
        model = f"{generator}; Laura model {canonical.IDENTITY_ID}" if laura else generator
        refs = [dict(r) for r in spec.get("references") or []]
        if laura and not any(r.get("sha256") == canonical.FACE_SHA256 for r in refs):
            refs.insert(0, {"sha256": canonical.FACE_SHA256, "kind": "laura_canonical"})
        received = {"name": spec["name"], "sha256": sha, "bytes": len(data),
                    "generator": generator, "provider": provider, "model": model,
                    "laura_identity": canonical.IDENTITY_ID if laura else None,
                    "laura_present": laura, "role": spec["role"],
                    "alternate": spec[ALTERNATE], "references": refs, "actor": actor,
                    "is_photograph": False, "supplied_by": SUPPLIED_BY}
        with db.session() as s:
            row = AuditLog(actor=actor, action=RECEIVED_ACTION, artifact=f"{slug}@{version}",
                           detail=received)
            s.add(row)
            s.flush()
            audit_id = row.id
        receipt = hashlib.sha256(f"{RECEIVED_ACTION}:{audit_id}:{sha}".encode()).hexdigest()
        cand = {"data": data, "sha256": sha, "slug": slug, "version": version,
                "release": release, "role": spec["role"], "prompt": "",
                "provider": provider, "model": model, "references": refs,
                "laura_present": laura,
                "outfit_id": (str(spec.get("outfit_id") or "").strip().lower() or None),
                "listing": listing, "provenance_kind": PROVENANCE_KIND,
                "route": el.GALLERY_ROUTE, "prompt_version": PROMPT_VERSION,
                # the release's CIR anchor lives on its generated-gallery run
                "run_key": flux_key,
                # the receipt binds this candidate to its intake audit row and its bytes
                "identity_evidence": {"request": {"request_sha256": receipt}},
                "cost_basis": "owner-made; not reported"}
        verdict = CG.evaluate(db, cand, judges=judges)
        checks = dict(verdict["checks"])
        checks["product_scale"] = product_scale(pointer, data, cir, role=spec["role"],
                                                laura=laura)
        checks["stripe_layout"] = stripe_layout(pointer, data, cir)
        alt = alt_text(cir, spec.get("scene") or "")
        alt_problems = buyer_text_problems(alt, surface="alt")
        checks["alt_text"] = CG._c(FAIL if alt_problems else PASS,
                                   "; ".join(alt_problems) or "describes the scene; no label, "
                                   "no render wording, no made-sample claim", text=alt)
        job = jobs[spec["role"]]
        publication = CG.publication_verdict({**cand, "_db": db}, checks, job, laura)
        full = {**verdict, "checks": checks, "technical_status": CG.technical_of(checks),
                "publication": publication, "publishable": publication["publishable"],
                "unknown": CG.unknown_of(checks)}
        rec = IP.record_candidate(db, {**cand, "supplied_by": SUPPLIED_BY}, full,
                                  method=METHOD, run=own_key, stage="owner_intake",
                                  submitted_by=actor)
        m = GP.frame_matrix(db, GP._row_of(db, rec["candidate_id"]), job=job,
                            laura_expected=False, cir_references=cir_refs)
        for gate in ("product_scale", "stripe_layout", "alt_text"):
            st, why = GP._status(checks, (gate,))
            m["gates"][gate] = {"status": st, "owner": OWNER_AGENT, "why": why}
        m["ok"] = all(g["status"] in (PASS, NA) for g in m["gates"].values())
        frame = {"name": spec["name"], "sha256": sha, "candidate_id": rec["candidate_id"],
                 "role": spec["role"], "job": job, "alternate": spec[ALTERNATE],
                 "laura_present": laura, "alt_text": alt, "audit_id": audit_id,
                 "gates": m["gates"], "ok": m["ok"],
                 "blockers": [{"gate": g, "status": v["status"], "why": v["why"],
                               "owner": v["owner"]}
                              for g, v in m["gates"].items() if v["status"] not in (PASS, NA)]}
        with db.session() as s:
            s.add(AuditLog(actor=actor, action=VERDICT_ACTION, artifact=f"{slug}@{version}",
                           detail={k: frame[k] for k in ("name", "sha256", "candidate_id",
                                                         "role", "job", "alternate", "ok",
                                                         "blockers")}))
        frames.append(frame)

    placed = [f for f in frames if not f["alternate"]]
    order = {r: i for i, (_j, r) in enumerate(slots(), start=1)}
    blockers: list[dict] = []
    for f in placed:
        blockers += [{"file": f["name"], "role": f["role"], **b} for b in f["blockers"]]
    missing = sorted(set(order) - {f["role"] for f in placed}, key=order.get)
    if missing:
        blockers.append({"file": None, "role": "gallery", "gate": "slots", "status": FAIL,
                         "why": f"campaign slots with no frame: {missing}",
                         "owner": OWNER_AGENT})
    with db.session() as s:
        rows = [r for r in s.scalars(select(ImageCandidate).where(
            ImageCandidate.id.in_([f["candidate_id"] for f in placed])))]
        set_rows = [{"candidate_id": r.id, "listing": r.listing, "version": r.version,
                     "release": r.release,
                     "cir_fingerprint": (r.binding or {}).get("cir_fingerprint"),
                     "laura_present": r.laura_present, "outfit_id": r.outfit_id or None,
                     "item_reading": IP._item_reading(r.checks)} for r in rows]
    consistency = CG.campaign_consistency(set_rows)
    st = CG.gate_status(consistency)
    if st != PASS:
        blockers.append({"file": None, "role": "gallery", "gate": "campaign_consistency",
                         "status": FAIL if st == FAIL else UNMEASURED,
                         "why": str(consistency.get("why"))[:400], "owner": OWNER_AGENT})
    record = {"slug": slug, "version": version, "release": release, "actor": actor,
              "files": [{k: f[k] for k in ("name", "sha256", "role", "alternate", "ok")}
                        for f in frames],
              "blockers": [{k: b.get(k) for k in ("file", "role", "gate", "status", "why")}
                           for b in blockers]}
    out = {"slug": slug, "version": version, "release": release, "frames": frames,
           "blockers": blockers, "consistency": consistency, "certified": False}
    if blockers:
        with db.session() as s:
            s.add(AuditLog(actor=actor, action=CERTIFY_ACTION, artifact=f"{slug}@{version}",
                           detail={**record, "certified": False}))
        out["why"] = f"{len(blockers)} blocker(s); nothing written, nothing certified"
        return out

    written = GP.write_frames(db, slug, version,
                              [{"position": GP.STORED_BASE + order[f["role"]],
                                "role": f["role"], "job": f["job"],
                                "candidate_id": f["candidate_id"], "sha256": f["sha256"]}
                               for f in placed],
                              run_key=own_key, actor=actor, route=el.GALLERY_ROUTE,
                              extra_claims={"supplied_by": SUPPLIED_BY})
    if written["refused"]:
        with db.session() as s:
            s.add(AuditLog(actor=actor, action=CERTIFY_ACTION, artifact=f"{slug}@{version}",
                           detail={**record, "certified": False,
                                   "refused": written["refused"]}))
        return {**out, "why": "a gallery position already holds other bytes",
                "written": written}
    selection = {"route": el.GALLERY_ROUTE, "run_key": own_key, "supplied_by": SUPPLIED_BY,
                 "family": flux_family(_category(slug)),
                 "frames": [{"position": order[f["role"]], "role": f["role"], "job": f["job"],
                             "stored_position": GP.STORED_BASE + order[f["role"]],
                             "sha256": f["sha256"], "candidate_id": f["candidate_id"],
                             "supplied_by": SUPPLIED_BY, "alt_text": f["alt_text"]}
                            for f in sorted(placed, key=lambda x: order[x["role"]])],
                 "contents": {"position": len(order) + 1}}
    with db.session() as s:
        s.add(AuditLog(actor=actor, action=GP.SELECTED_ACTION, artifact=f"{slug}@{version}",
                       detail=selection))
    ls = RG.listing_set(db, slug=slug, version=version, store_root=store_root, issue=issue,
                        store_renders=True)
    certified = bool((ls.get("certificate") or {}).get("valid")) and not ls.get(
        "blocks_release")
    with db.session() as s:
        if not certified:
            s.add(AuditLog(actor=actor, action=GP.SELECTED_ACTION,
                           artifact=f"{slug}@{version}",
                           detail={**selection, "withdrawn": True, "why": ls.get("reasons")}))
        s.add(AuditLog(actor=actor, action=CERTIFY_ACTION, artifact=f"{slug}@{version}",
                       detail={**record, "certified": certified,
                               "listing_set_reasons": ls.get("reasons"),
                               "certificate_record": (ls.get("certificate") or {}).get(
                                   "record_id")}))
    return {**out, "certified": certified, "listing_set": ls, "written": written,
            "selection": selection,
            "why": ("every frame and set check passed; certificate issued" if certified
                    else f"listing set refused: {ls.get('reasons')}")}


def _category(slug: str) -> str:
    try:
        from .shot_plans import _listing_shape
        from . import outfits

        return _listing_shape(outfits.listing_of(slug))[0]
    except Exception:  # noqa: BLE001 - an unknown category plans as lived-with
        return ""
