"""FLUX 3 generation stages (W4-FLUXAPI; D-W4-LAURA-FLUX3; interface for W-OWNERIMG).

The owner's staged workflow, made callable and bound to the 2026-10-19 production standard:

    certified pattern -> product references 4-7 (deterministic, free) ->
    validated canonical Laura references 1/2/3 -> product_only -> lifestyle -> variants

    release_from_cir(cir, release_hash=, out_dir=)                      -> Release
    product_only(release, refs=None, ...)                               -> Candidate
    lifestyle(release, product_candidate, laura_refs, outfit, ...)      -> Candidate
    variant(release, base_candidate, role, edit_instruction, ...)       -> Candidate

Rules enforced here, each with a test (`tests/test_w4_fluxstages.py`):

1. **Every generation featuring Laura transmits all three canonical originals** (face a42aeac7,
   torso afe6191f, full length f32bac68) as provider image inputs, in that order, first. Their
   bytes are validated against the canonical fingerprints before anything is sent. A missing,
   altered, forbidden or substituted reference is refused, never degraded. Supplementary images
   may be added after them and never replace them. Product-only generations carry no Laura.
2. **Product references 4-7** come from the exact certified release (`creative.pattern_refs`),
   bound to its release hash.
3. **The campaign set** (face, torso, body; layout, stitch texture, chart, rules -- the
   ruling's six plus the stitch-texture close-up added after the reading-nook test) is sent as
   seven image inputs where the provider's documented limit allows (FLUX 3 Image: 10). Where it is
   lower, nothing is dropped: the three product references are merged, losslessly, into one
   combined sheet (`combined_reference_sheet`), and the limitation is recorded in the receipt.
   If even that does not fit, the stage is refused. The Laura originals are never merged or
   altered: identity conditions on the originals themselves.
3a. **Stage order:** the product-only image is an unfolded, countable flat lay, and a lifestyle
   image is refused unless that exact flat lay holds a PASS fidelity verdict
   (`fidelity_verdict`). FAIL and UNKNOWN both refuse (`failure_codes.UNVERIFIABLE_COUNT`).
4. **The prompt is built**, not written (`creative.flux_prompt`), from certified data, brand
   rules and W-OWNERIMG's scene, and every section is pinned and hashed.
5. **Spend:** the default renderer is `gateway.images.generate` on `flux-3-image`, which
   reserves the documented price before the request, proves every reference is in the body,
   stores the result bytes at once and fingerprints them. Attempts are bounded (`MAX_ATTEMPTS`)
   and only transient failures retry.

A candidate is only a candidate. Identity, bust and body proportion (UNKNOWN until an
independent judge runs), outfit, Product Truth, anatomy, realism, disclosure and owner approval
are other gates. Nothing here approves or publishes an image.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Protocol, Sequence

from ..core.resilience import TransientError
from . import flux_prompt

MODEL = "flux-3-image"
MAX_ATTEMPTS = 3
DEFAULT_ATTEMPTS = 2
AGENT = "creative_director"
# The listing floor (W-OWNERIMG `candidate_gates.quality`): at least 2000 px on EACH side,
# opaque, PNG or JPEG. FLUX 3's `resolution` is an equal-area tier ("about" 1/2/4/16 MP; exact
# dimensions are not documented), so the cheapest documented request expected to clear 2000 px
# on both sides is 1:1 at the 2k tier (about 2048 x 2048, US$0.100). A 4:5 frame at 2k would
# be about 1832 x 2290 (short side under 2000), so 4:5 needs the 4k tier (US$0.607); 1:1 is the
# default for every stage. The real output size is measured after the render and recorded;
# nothing is ever upscaled.
LISTING_MIN_PX = 2000
PRODUCT_SIZE = "2048x2048"           # 1:1 at the 2k tier
LIFESTYLE_SIZE = "2048x2048"         # 1:1 at the 2k tier
TALL_LIFESTYLE_SIZE = "3664x4580"    # 4:5 at the 4k tier, when a portrait frame is required
MAX_EDIT_CHARS = 400
LAURA_ROLES: tuple[str, ...] = ("laura_face", "laura_torso", "laura_body")
PRODUCT_ROLES: tuple[str, ...] = flux_prompt.PRODUCT_ROLES   # layout, texture, chart, rules
CAMPAIGN_MINIMUM = LAURA_ROLES + PRODUCT_ROLES

VARIANT_ROLES: tuple[str, ...] = ("detail_closeup", "flat_lay", "scale_in_hand",
                                  "styled_scene", "second_angle", "colour_context")
_ROLE_EDITS: dict[str, str] = {
    "detail_closeup": "crop in to a close-up of the stitch texture of the crochet piece",
    "flat_lay": "show the crochet piece laid flat from directly above on the same surface",
    "scale_in_hand": "show the crochet piece held in two hands so its size is clear",
    "styled_scene": "move the scene to a different, natural setting suited to the product",
    "second_angle": "show the same moment from another camera angle",
    "colour_context": "change only the background to a plain warm neutral",
}


from .failure_codes import ALL_CODES as _ALL_CODES  # noqa: E402

# The shared failure codes, under the names W-OWNERIMG's `repair_routes.shared_codes()` reads.
# One constant (`creative.failure_codes`); these are views of it, never a second list.
PRODUCT_TRUTH_FAILURE_CODES: tuple[str, ...] = tuple(sorted(_ALL_CODES))
FAILURE_CODES = PRODUCT_TRUTH_FAILURE_CODES


def expected_px(size: str) -> tuple[int, int]:
    """FLUX 3's output size for a request, estimated from the documented tier area and ratio.

    An estimate: BFL documents the tiers as "about" N megapixels. `_run` measures the real
    bytes afterwards."""
    from ..gateway import images

    tier_mp = {"768sq": 768 * 768 / images.BFL_MP, "1k": 1.0, "1.5k": 2.0, "2k": 4.0,
               "4k": 16.0}[images.bfl3_tier(size)]
    a, b = (int(x) for x in images.bfl3_aspect(size).split(":"))
    area = tier_mp * images.BFL_MP
    w = (area * a / b) ** 0.5
    return int(w), int(w * b / a)


def meets_listing_floor(size: str) -> bool:
    return min(expected_px(size)) >= LISTING_MIN_PX


class StageRefused(ValueError):
    """The stage cannot run honestly with these inputs; nothing was sent or spent."""


# -- data ------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Release:
    """A certified product as the stages need it. Build it with `release_from_cir`."""
    slug: str
    version: str
    release_hash: str
    title: str
    rules: Mapping                         # pattern_refs.technical_rules
    pattern_refs: tuple[str, ...]          # layout, texture, detail, rules (references 4-7)
    pattern_ref_sha256s: tuple[str, ...] = ()
    work_root: str = ""


@dataclass(frozen=True)
class Candidate:
    stage: str
    role: str
    path: str
    sha256: str
    release_hash: str
    receipt: dict = field(default_factory=dict)

    @property
    def features_laura(self) -> bool:
        return bool(self.receipt.get("features_laura"))


class Renderer(Protocol):
    def __call__(self, prompt: str, *, reference_urls: Sequence[str], size: str,
                 work_dir: str, purpose: str, agent: str, db=None,
                 job_id: int | None = None) -> dict: ...


def flux3_renderer(env: Mapping[str, str] | None = None, *,
                   provider_key: str = MODEL) -> "Renderer":
    """The paid renderer: `images.generate` on FLUX 3 Image (reserve, send, store, bill)."""
    from ..gateway import images

    def render(prompt, *, reference_urls, size, work_dir, purpose, agent, db=None,
               job_id=None):
        return images.generate(prompt, reference_urls=list(reference_urls), env=env,
                               size=size, provider_key=provider_key, work_dir=work_dir,
                               db=db, agent=agent, purpose=purpose, job_id=job_id)
    render.reference_limit = images.BY_KEY[provider_key].reference_images  # type: ignore[attr-defined]
    render.provider_key = provider_key  # type: ignore[attr-defined]
    return render


class StubRenderer:
    """The same interface with no network and no spend. Writes a deterministic PNG per call.

    `fail_with` raises the given exceptions in order before succeeding. `reference_limit`
    imitates a provider with a lower documented limit."""

    def __init__(self, fail_with: Sequence[BaseException] = (), *, reference_limit: int = 10):
        self.calls: list[dict] = []
        self._fail = list(fail_with)
        self.reference_limit = reference_limit
        self.provider_key = "stub"

    def __call__(self, prompt, *, reference_urls, size, work_dir, purpose, agent, db=None,
                 job_id=None):
        import io

        from PIL import Image

        refs = list(reference_urls)
        if len(refs) > self.reference_limit:
            raise AssertionError("the stage sent more references than the provider takes")
        self.calls.append({"prompt": prompt, "refs": refs, "size": size, "purpose": purpose,
                           "agent": agent})
        if self._fail:
            raise self._fail.pop(0)
        seed = hashlib.sha256((prompt + "|".join(refs) + size).encode()).digest()
        w, h = (int(x) for x in size.split("x"))
        buf = io.BytesIO()
        Image.new("RGB", (max(8, w // 16), max(8, h // 16)), tuple(seed[:3])).save(
            buf, format="PNG")
        raw = buf.getvalue()
        root = Path(work_dir)
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"stub-{seed.hex()[:12]}-{len(self.calls)}.png"
        path.write_bytes(raw)
        hashes = [hashlib.sha256(Path(r).read_bytes()).hexdigest() for r in refs]
        return {"provider": "stub", "model": "stub", "path": str(path), "image_ref": str(path),
                "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "cad": 0.0,
                "latency_ms": 0.0, "provider_receipt": {"id": f"stub-{len(self.calls)}",
                                                        "seed": None},
                "conditioning": {"reference_sha256s": hashes, "proven": bool(refs),
                                 "transmitted": len(refs), "requested": len(refs)}}


# -- references ------------------------------------------------------------------------------
def release_from_cir(cir, *, release_hash: str, out_dir: str | Path,
                     version: str | None = None) -> Release:
    """A `Release` for a certified CIR, with references 4-7 rendered from that exact version."""
    from . import pattern_refs

    manifest = pattern_refs.build(cir, release_hash=release_hash, out_dir=out_dir,
                                  version=version)
    by_role = {r["role"]: r for r in manifest["references"]}
    ordered = [by_role[r] for r in pattern_refs.ROLES]
    return Release(slug=cir.slug, version=cir.version, release_hash=release_hash,
                   title=cir.title, rules=manifest["technical_rules"],
                   pattern_refs=tuple(r["path"] for r in ordered),
                   pattern_ref_sha256s=tuple(r["sha256"] for r in ordered),
                   work_root=str(out_dir))


def canonical_laura_hashes() -> tuple[str, str, str]:
    """The three approved fingerprints, in the order they are transmitted (face, torso, body)."""
    from ..visual import canonical, conditioning

    return tuple(canonical.CURRENT_REFERENCE_HASHES[f]  # type: ignore[return-value]
                 for f in conditioning.FRAME_ORDER)


def _sha(path: str) -> str:
    p = Path(str(path))
    if not p.is_file():
        raise StageRefused(f"{p.name}: not a file on this disk; a reference that is not here "
                           f"conditions on nothing")
    return hashlib.sha256(p.read_bytes()).hexdigest()


def laura_references(laura_refs: Sequence[str] | None = None) -> list[str]:
    """The three canonical Laura originals, validated by their bytes. Never a substitute.

    With no argument, the committed files of the current canonical revision are used. With an
    argument, it must be exactly those three originals (by fingerprint) in canonical order;
    anything else (missing, extra, reordered, altered, forbidden) is refused."""
    from ..visual import canonical, conditioning

    want = canonical_laura_hashes()
    if laura_refs is None:
        paths = [canonical.reference_file(f) for f in conditioning.FRAME_ORDER]
        missing = [f for f, p in zip(conditioning.FRAME_ORDER, paths) if not p]
        if missing:
            raise StageRefused(f"canonical Laura reference(s) {missing} are missing or not the "
                               f"approved bytes; refused rather than generating with reduced "
                               f"identity conditioning")
    else:
        paths = [str(p) for p in laura_refs]
    if len(paths) != 3:
        raise StageRefused(f"{len(paths)} Laura reference(s) supplied; exactly the three "
                           f"canonical originals are required (face, torso, full length)")
    try:
        forbidden = canonical.forbidden_hashes()
    except Exception as exc:  # noqa: BLE001 - an unreadable manifest is refused, not ignored
        raise StageRefused(f"the canonical manifest cannot be read ({exc}); refused") from exc
    got = [_sha(p) for p in paths]
    for frame, g, w in zip(conditioning.FRAME_ORDER, got, want):
        if g.lower() in forbidden:
            raise StageRefused(f"{frame}: {g[:12]} is forbidden as a reference")
        if g != w:
            raise StageRefused(f"{frame}: fingerprint {g[:12]} is not the canonical "
                               f"{w[:12]}; a substituted or altered reference is refused")
    return paths


def combined_reference_sheet(paths: Sequence[str], out_path: str | Path) -> dict:
    """Merge the product references into one image, top to bottom, at full resolution.

    Legibility is kept by never scaling: each source is pasted pixel for pixel. If the merged
    sheet would exceed FLUX 3's 16 MP input bound, it is refused rather than shrunk."""
    from PIL import Image

    from . import pattern_refs

    images = []
    for p in paths:
        with Image.open(p) as im:
            images.append(im.convert("RGB"))
    pad = 24
    width = max(i.size[0] for i in images) + 2 * pad
    height = sum(i.size[1] for i in images) + pad * (len(images) + 1)
    if width * height > pattern_refs.MAX_PIXELS:
        raise StageRefused(f"a combined sheet of {len(images)} references would be "
                           f"{width}x{height}, over the 16 MP input bound; refused rather "
                           f"than shrinking it past legibility")
    sheet = Image.new("RGB", (width, height), (255, 255, 255))
    boxes, y = [], pad
    for im in images:
        x = (width - im.size[0]) // 2
        sheet.paste(im, (x, y))
        boxes.append([x, y, x + im.size[0], y + im.size[1]])
        y += im.size[1] + pad
    raw = pattern_refs._png_bytes(sheet)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(raw)
    return {"path": str(out), "sha256": hashlib.sha256(raw).hexdigest(),
            "width": width, "height": height, "boxes": boxes,
            "sources": [{"path": str(p), "sha256": _sha(str(p))} for p in paths],
            "scaled": False}


def campaign_references(release: Release, *, features_laura: bool, laura_refs=None,
                        leading: Sequence[tuple[str, str]] = (),
                        supplementary: Sequence[tuple[str, str]] = (),
                        reference_limit: int, work_dir: str) -> dict:
    """The ordered references for one generation, and how they fit the provider's limit.

    Order: Laura face, torso, body (when Laura is featured); product layout, detail, rules;
    `leading` (an edit's base image); then `supplementary` (a product candidate, the outfit, an
    approved lifestyle image). Supplementary images never replace the originals."""
    items: list[tuple[str, str]] = []
    if features_laura:
        items += list(zip(LAURA_ROLES, laura_references(laura_refs)))
    items += list(zip(PRODUCT_ROLES, release.pattern_refs))
    if len(release.pattern_refs) != len(PRODUCT_ROLES) or [
            _sha(p) for p in release.pattern_refs] != list(release.pattern_ref_sha256s):
        raise StageRefused("the product references are not the release's fingerprinted "
                           "layout, texture, chart and rules")
    items += list(leading) + list(supplementary)
    combined = None
    limitation = None
    if len(items) > reference_limit:
        # Lossless fallback: references 4-7 become one sheet. Laura originals stay separate.
        sheet = combined_reference_sheet(
            release.pattern_refs, Path(work_dir) / f"{release.slug}-{release.release_hash[:12]}"
                                                   f"-product-sheet.png")
        merged = [(r, p) for r, p in items if r not in PRODUCT_ROLES]
        at = 3 if features_laura else 0
        items = merged[:at] + [("product_combined", sheet["path"])] + merged[at:]
        combined = sheet
        limitation = (f"provider limit {reference_limit} is below the "
                      f"{len(merged) + len(PRODUCT_ROLES)} references; product layout, "
                      f"texture, chart and rules were merged losslessly into one sheet")
        if len(items) > reference_limit:
            raise StageRefused(f"{len(items)} references even after merging the product "
                               f"sheet; the provider takes {reference_limit}. Refused rather "
                               f"than dropping any")
    roles = [r for r, _ in items]
    shas = [_sha(p) for _, p in items]
    if features_laura and tuple(roles[:3]) != LAURA_ROLES:
        raise StageRefused("the three canonical Laura references must lead the request, in "
                           "order; a supplementary reference never displaces them")
    if "outfit" in roles:
        # W-VISNEXT: the approved outfit reference is clothing only. It may never be (or
        # stand in for) an identity reference, and it always comes after the canonical three.
        from ..visual import canonical

        o_sha = shas[roles.index("outfit")]
        canon = set(canonical_laura_hashes())
        try:
            canon |= set(canonical.forbidden_hashes())
        except Exception as exc:  # noqa: BLE001 - an unreadable manifest is refused
            raise StageRefused(f"the canonical manifest cannot be read ({exc}); refused") from exc
        if o_sha in canon:
            raise StageRefused("the outfit reference is a canonical (or retired) identity "
                               "reference; an outfit reference is clothing only")
        if features_laura and roles.index("outfit") < 3:
            raise StageRefused("the outfit reference may not precede the canonical three")
    return {"roles": roles, "paths": [p for _, p in items],
            "sha256s": shas, "combined_sheet": combined,
            "limitation": limitation, "reference_limit": reference_limit}


# -- the run ---------------------------------------------------------------------------------
def _measure(path: str) -> dict:
    """The output's real size, format and opacity: what the listing floor is judged on."""
    try:
        from PIL import Image

        with Image.open(path) as im:
            w, h = im.size
            fmt = str(im.format or "")
            opaque = True
            if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and
                                                  "transparency" in im.info):
                opaque = im.convert("RGBA").getchannel("A").getextrema()[0] == 255
        return {"px": [w, h], "format": fmt, "opaque": opaque,
                "meets_floor": (min(w, h) >= LISTING_MIN_PX and opaque
                                and fmt in ("PNG", "JPEG"))}
    except Exception:  # noqa: BLE001 - unreadable output: the floor is UNKNOWN, not met
        return {"px": None, "format": None, "opaque": None, "meets_floor": None}


def _attempts(max_attempts: int) -> int:
    n = int(max_attempts)
    if not 1 <= n <= MAX_ATTEMPTS:
        raise StageRefused(f"max_attempts={max_attempts}: must be 1..{MAX_ATTEMPTS}")
    return n


def _limit(renderer) -> int:
    return int(getattr(renderer, "reference_limit", 10))


def _run(stage: str, role: str, release: Release, refs: dict, built, size: str, *,
         features_laura: bool, renderer, work_dir: str, db, job_id, max_attempts: int,
         purpose: str) -> Candidate:
    if not work_dir:
        raise StageRefused("work_dir is required: the candidate's bytes must outlive the call")
    if not meets_listing_floor(size):
        w, h = expected_px(size)
        raise StageRefused(f"{size} is expected to render about {w}x{h}, under the "
                           f"{LISTING_MIN_PX} px listing floor on each side; ask for a tier "
                           f"that meets it (1:1 at 2k, 4:5 at 4k). Nothing is upscaled")
    tries = _attempts(max_attempts)
    if features_laura:
        # Checked again here, the last moment before the request: the three originals lead.
        if tuple(refs["sha256s"][:3]) != canonical_laura_hashes():
            raise StageRefused("the three canonical Laura references are not the first three "
                               "inputs; refused")
    errors: list[str] = []
    started = time.time()
    for attempt in range(1, tries + 1):
        try:
            out = renderer(built.text, reference_urls=refs["paths"], size=size,
                           work_dir=work_dir, purpose=purpose, agent=AGENT, db=db,
                           job_id=job_id)
        except TransientError as exc:          # the only failure worth another attempt
            errors.append(f"attempt {attempt}: {type(exc).__name__}: {str(exc)[:200]}")
            if attempt == tries:
                raise
            continue
        path = str(out.get("path") or "")
        out_sha = out.get("sha256") or _sha(path)
        cond = dict(out.get("conditioning") or {})
        sent = list(cond.get("reference_sha256s") or [])
        if sent != refs["sha256s"]:
            raise StageRefused(f"{stage}: the provider receipt names {len(sent)} reference "
                               f"hash(es) and the stage supplied {len(refs['sha256s'])}; a "
                               f"render whose inputs cannot be proven is not a candidate")
        pr = dict(out.get("provider_receipt") or {})
        measured = _measure(path)
        receipt = {
            "stage": stage, "role": role, "features_laura": features_laura,
            "model": out.get("model") or MODEL, "provider": out.get("provider"),
            "release_hash": release.release_hash, "product": f"{release.slug}@"
                                                             f"{release.version}",
            **built.receipt(),
            "references": [{"position": i + 1, "role": r, "sha256": h}
                           for i, (r, h) in enumerate(zip(refs["roles"], refs["sha256s"]))],
            "input_sha256s": list(refs["sha256s"]),
            # W-VISNEXT: the supplementary outfit reference, when one was sent (clothing only)
            "outfit_reference": ({"position": refs["roles"].index("outfit") + 1,
                                  "sha256": refs["sha256s"][refs["roles"].index("outfit")]}
                                 if "outfit" in refs["roles"] else None),
            "reference_limit": refs["reference_limit"],
            "combined_sheet": refs["combined_sheet"], "limitation": refs["limitation"],
            "size": size, "task_id": pr.get("task_id") or pr.get("id"), "seed": pr.get("seed"),
            "request": {"provider_task": pr, "conditioning_proven": cond.get("proven"),
                        "request_sha256": cond.get("request_sha256")},
            "cost_cad": out.get("cad"), "provider_cost_credits": pr.get("cost"),
            "cost_entry_id": out.get("cost_entry_id"), "price": cond.get("price") or {},
            "latency_ms": round((time.time() - started) * 1000, 2),
            "provider_latency_ms": out.get("latency_ms"),
            "output_sha256": out_sha, "attempts": attempt, "attempt_errors": errors,
            "expected_px": list(expected_px(size)) if not size.startswith("stub") else None,
            "output_px": measured.get("px"), "output_format": measured.get("format"),
            "opaque": measured.get("opaque"),
            "meets_listing_floor": measured.get("meets_floor"),
            "upscaled": False,
        }
        return Candidate(stage=stage, role=role, path=path, sha256=out_sha,
                         release_hash=release.release_hash, receipt=receipt)
    raise AssertionError("unreachable")  # pragma: no cover


# -- the three stages ------------------------------------------------------------------------
# The flat lay's ground (W-FIDELITY follow-up): a mid-tone surface at least MIN_SURFACE_DE CIE
# colour-distance units from every palette colour, so a cream or white piece still separates
# from it (a generic "neutral surface" came back cream and swallowed cream end bands). The first
# candidate far enough from every yarn colour is chosen; none far enough is a refusal.
MIN_SURFACE_DE = 25.0
FLAT_LAY_SURFACES: tuple[tuple[str, str], ...] = (
    ("taupe", "#7A746C"), ("slate blue-grey", "#5E6B78"), ("warm mid-brown", "#7B5E4A"),
    ("muted sage-grey", "#7E8A78"), ("dusty plum-grey", "#7A6A78"), ("terracotta", "#A0583F"),
    ("deep ink blue", "#2B3245"))


def _lab(hex_: str) -> tuple[float, float, float]:
    h = str(hex_).lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    x = (0.4124 * lin[0] + 0.3576 * lin[1] + 0.1805 * lin[2]) / 0.95047
    y = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    z = (0.0193 * lin[0] + 0.1192 * lin[1] + 0.9505 * lin[2]) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(a: str, b: str) -> float:
    """CIE76 colour distance between two hex colours."""
    la, lb = _lab(a), _lab(b)
    return sum((p - q) ** 2 for p, q in zip(la, lb)) ** 0.5


def flat_lay_surface(palette_hexes) -> dict:
    """The first surface at least MIN_SURFACE_DE from every palette colour."""
    pal = [str(h) for h in palette_hexes or () if h]
    for name, hex_ in FLAT_LAY_SURFACES:
        d = min((delta_e(hex_, p) for p in pal), default=float("inf"))
        if d >= MIN_SURFACE_DE:
            return {"name": name, "hex": hex_, "min_delta_e": round(d, 1)}
    raise StageRefused(f"no flat-lay surface is {MIN_SURFACE_DE} colour-distance units from "
                       f"every palette colour {pal}; the piece could not be separated from it")


def flat_lay_environment(palette_hexes) -> str:
    s = flat_lay_surface(palette_hexes)
    return (f"a plain, matte, mid-tone {s['name']} surface ({s['hex']}), at least "
            f"{MIN_SURFACE_DE:g} colour-distance units (CIE delta E) from every yarn colour so "
            f"every edge and band of the piece separates from it; soft, even daylight; no "
            f"white, cream or pale background")


FLAT_LAY_SCENE = {
    "environment": flat_lay_environment(()),
    "pose": ("the product laid completely flat and unfolded, seen from directly above; no "
             "folds, no drape, no rolled or tucked edges"),
    "framing": ("the whole piece in frame with a margin on every side, square to the camera, "
                "so every piece, edge, band, cable column and motif can be counted"),
}


def fidelity_verdict(candidate: Candidate, *, status: str, checker: str,
                     failures: Sequence[str] = (), notes: str = "") -> dict:
    """The record a fidelity check writes about one product-only flat lay.

    `status` is PASS, FAIL or UNKNOWN; `failures` are `failure_codes` codes. The check itself
    (Product Truth on the flat lay) belongs to the gates; this only makes its answer bindable
    to the exact candidate bytes, so a verdict cannot be reused for another image."""
    from . import failure_codes

    if status not in ("PASS", "FAIL", "UNKNOWN"):
        raise StageRefused(f"fidelity status {status!r} is not PASS, FAIL or UNKNOWN")
    unknown = sorted(set(failures) - failure_codes.ALL_CODES)
    if unknown:
        raise StageRefused(f"unknown failure codes {unknown}; use failure_codes")
    if status == "PASS" and failures:
        raise StageRefused("a PASS verdict cannot carry failure codes")
    if not checker:
        raise StageRefused("a fidelity verdict names its checker")
    return {"status": status, "candidate_sha256": candidate.sha256,
            "release_hash": candidate.release_hash, "stage": candidate.stage,
            "role": candidate.role, "checker": checker, "failures": sorted(set(failures)),
            "notes": notes}


def _require_flat_lay_pass(release: Release, product_candidate: Candidate, fidelity) -> None:
    v = dict(fidelity or {})
    if product_candidate.stage != "product_only" or product_candidate.role != "product_flat_lay":
        raise StageRefused("lifestyle comes after the product-only flat lay; this product "
                           "image is not one")
    if v.get("candidate_sha256") != product_candidate.sha256 or v.get(
            "release_hash") != release.release_hash:
        raise StageRefused("the fidelity verdict is not about this flat lay of this release")
    if v.get("status") != "PASS":
        raise StageRefused(f"the flat lay's fidelity is {v.get('status') or 'UNKNOWN'} "
                           f"{v.get('failures') or ''}; lifestyle generation is gated on PASS")


def product_only(release: Release, refs: Sequence[str] | None = None, *,
                 scene: Mapping | None = None, size: str = PRODUCT_SIZE, renderer=None,
                 work_dir: str, db=None,
                 job_id: int | None = None, max_attempts: int = DEFAULT_ATTEMPTS
                 ) -> Candidate:
    """The product alone as an unfolded, countable flat lay, conditioned on references 4-7.
    No Laura, no outfit. Its fidelity verdict gates every lifestyle image.

    `refs`, when given, must be the release's own pattern references (they cannot be swapped)."""
    if refs is not None and [str(r) for r in refs] != list(release.pattern_refs):
        raise StageRefused("product_only conditions on the release's own pattern references")
    render = renderer or flux3_renderer()
    plan = campaign_references(release, features_laura=False,
                               reference_limit=_limit(render), work_dir=work_dir)
    palette = [c.get("hex") for c in (release.rules or {}).get("colours") or []]
    built = flux_prompt.build(rules=release.rules, roles=_prompt_roles(plan),
                              role="product-only flat lay",
                              scene={**FLAT_LAY_SCENE,
                                     "environment": flat_lay_environment(palette),
                                     **dict(scene or {})})
    return _run("product_only", "product_flat_lay", release, plan, built, size,
                features_laura=False, renderer=render, work_dir=work_dir, db=db,
                job_id=job_id, max_attempts=max_attempts, purpose="image.product_only")


def lifestyle(release: Release, product_candidate: Candidate, laura_refs: Sequence[str] | None,
              outfit: Mapping, *, fidelity: Mapping | None = None,
              scene: Mapping | None = None, role: str = "lifestyle_hero",
              size: str = LIFESTYLE_SIZE, supplementary: Sequence[str] = (), renderer=None,
              work_dir: str, db=None,
              job_id: int | None = None, max_attempts: int = DEFAULT_ATTEMPTS) -> Candidate:
    """Laura with the product: the six-reference campaign set, then the product photograph,
    the outfit image and any supplementary images.

    `laura_refs`: None means the committed canonical originals; otherwise exactly those three
    files. `outfit` is W-OWNERIMG's reserved outfit {"id", "description", "image"?}, and is
    required. `scene` carries W-OWNERIMG's {environment, pose, framing}."""
    if product_candidate.release_hash != release.release_hash:
        raise StageRefused("the product candidate belongs to a different release")
    _require_flat_lay_pass(release, product_candidate, fidelity)
    outfit = dict(outfit or {})
    if not (outfit.get("id") and (outfit.get("description") or outfit.get("image"))):
        raise StageRefused("a Laura image needs the listing's reserved outfit (id and "
                           "description or image)")
    render = renderer or flux3_renderer()
    supp = [("product_candidate", product_candidate.path)]
    if outfit.get("image"):
        supp.append(("outfit", str(outfit["image"])))
    supp += [("supplementary", str(p)) for p in supplementary]
    plan = campaign_references(release, features_laura=True, laura_refs=laura_refs,
                               supplementary=supp, reference_limit=_limit(render),
                               work_dir=work_dir)
    built = flux_prompt.build(rules=release.rules, roles=_prompt_roles(plan), role=role,
                              scene={**dict(scene or {}), "outfit": outfit})
    return _run("lifestyle", f"{role}:{outfit['id']}", release, plan, built, size,
                features_laura=True, renderer=render, work_dir=work_dir, db=db,
                job_id=job_id, max_attempts=max_attempts, purpose="image.lifestyle")


SIX_REF_PRODUCT_ROLES: tuple[str, ...] = ("product_layout", "product_texture", "product_rules")


def six_reference_lifestyle(release: Release, product_refs: Sequence[str],
                            laura_refs: Sequence[str] | None, outfit: Mapping, *,
                            scene: Mapping | None = None, role: str = "lifestyle_six_ref",
                            size: str = LIFESTYLE_SIZE, renderer=None, work_dir: str, db=None,
                            job_id: int | None = None, max_attempts: int = 1,
                            extra_negatives: Sequence[str] = ()) -> Candidate:
    """The owner's proven manual method, reproduced exactly (W-VISNEXT baseline).

    Six references in one request: Laura's three canonical originals (validated by bytes,
    always first and in order), then three product references in this order: complete
    layout, stitch structure, construction rules. `product_refs` is exactly those three
    files, either the owner's committed files or the auto-generated `pattern_refs`
    equivalents. The stitch-structure image also stands for the stitch detail in the prompt.

    No flat lay is required first: this is the single-shot baseline the owner ran. The
    candidate is a claim to be verified, never evidence. Whether it may be saved for an
    uncertified product is the caller's EXPERIMENT decision, not this stage's."""
    outfit = dict(outfit or {})
    if not (outfit.get("id") and (outfit.get("description") or outfit.get("garments"))):
        raise StageRefused("a Laura image needs the listing's reserved outfit (id and "
                           "description)")
    paths = [str(p) for p in product_refs]
    if len(paths) != 3:
        raise StageRefused(f"{len(paths)} product reference(s); the six-reference method takes "
                           f"exactly three (layout, stitch structure, construction rules)")
    render = renderer or flux3_renderer()
    items = list(zip(LAURA_ROLES, laura_references(laura_refs))) + list(
        zip(SIX_REF_PRODUCT_ROLES, paths))
    if len(items) > _limit(render):
        raise StageRefused(f"six references; the provider takes {_limit(render)}. Refused "
                           f"rather than dropping or merging the owner's method")
    plan = {"roles": [r for r, _ in items], "paths": [p for _, p in items],
            "sha256s": [_sha(p) for _, p in items], "combined_sheet": None,
            "limitation": None, "reference_limit": _limit(render)}
    if tuple(plan["sha256s"][:3]) != canonical_laura_hashes():
        raise StageRefused("the three canonical Laura references must lead, in order")
    rules = dict(release.rules)
    if extra_negatives:
        rules["negatives"] = list(rules.get("negatives") or []) + [
            n for n in extra_negatives if n not in (rules.get("negatives") or [])]
    built = flux_prompt.build(rules=rules, roles=plan["roles"], role=role,
                              scene={**dict(scene or {}), "outfit": outfit},
                              alias={"product_detail": "product_texture"})
    return _run("lifestyle_six_ref", f"{role}:{outfit['id']}", release, plan, built, size,
                features_laura=True, renderer=render, work_dir=work_dir, db=db,
                job_id=job_id, max_attempts=max_attempts, purpose="image.lifestyle.six_ref")


def variant(release: Release, base_candidate: Candidate, role: str, edit_instruction: str = "",
            *, outfit: Mapping | None = None, scene: Mapping | None = None,
            laura_refs: Sequence[str] | None = None, size: str | None = None, renderer=None,
            work_dir: str, db=None,
            job_id: int | None = None, max_attempts: int = DEFAULT_ATTEMPTS) -> Candidate:
    """An edit of an existing candidate (FLUX 3 edit), in one of the closed `VARIANT_ROLES`.

    A variant of a Laura image is itself a Laura image: it carries the six-reference set again
    and the listing's outfit. A product-only variant carries references 4-7 and the base."""
    if base_candidate.release_hash != release.release_hash:
        raise StageRefused("the base candidate belongs to a different release")
    if role not in VARIANT_ROLES:
        raise StageRefused(f"unknown variant role {role!r}; known: {VARIANT_ROLES}")
    extra = (edit_instruction or "").strip()
    if len(extra) > MAX_EDIT_CHARS:
        raise StageRefused(f"edit instruction is {len(extra)} chars; at most {MAX_EDIT_CHARS}")
    laura = base_candidate.features_laura
    render = renderer or flux3_renderer()
    supp: list[tuple[str, str]] = []
    if laura:
        outfit = dict(outfit or {})
        if not outfit.get("id"):
            raise StageRefused("a variant of a Laura image needs the listing's outfit")
        if outfit.get("image"):
            supp.append(("outfit", str(outfit["image"])))
    plan = campaign_references(release, features_laura=laura, laura_refs=laura_refs,
                               leading=[("base", base_candidate.path)], supplementary=supp,
                               reference_limit=_limit(render), work_dir=work_dir)
    edit = _ROLE_EDITS[role] + (f": {extra}" if extra else "")
    built = flux_prompt.build(rules=release.rules, roles=_prompt_roles(plan), role=role,
                              edit=edit, scene={**dict(scene or {}),
                                                **({"outfit": outfit} if laura else {})})
    size = size or (LIFESTYLE_SIZE if laura else PRODUCT_SIZE)
    candidate = _run("variant", role, release, plan, built, size, features_laura=laura,
                     renderer=render, work_dir=work_dir, db=db, job_id=job_id,
                     max_attempts=max_attempts, purpose=f"image.variant.{role}")
    return candidate


def _prompt_roles(plan: dict) -> list[str]:
    """Roles by position, as the prompt builder names them."""
    return list(plan["roles"])


# -- cost model ------------------------------------------------------------------------------
def gallery_cost(*, lifestyle_count: int = 2, variant_count: int = 3,
                 expected_attempts_per_accept: float = 2.0, tier: str = "2k") -> dict:
    """Expected render spend for one complete gallery, from BFL's published FLUX 3 price.

    References are not charged on FLUX 3, so the six-reference set costs the same as one.
    `expected_attempts_per_accept` is UNKNOWN until measured and is reported at several rates."""
    from ..gateway import anthropic as gw
    from ..gateway import images

    usd = images.BFL3_TIER_USD[tier]
    accepted = 1 + int(lifestyle_count) + int(variant_count)

    def row(rate: float) -> dict:
        renders = accepted * rate
        return {"attempts_per_accept": rate, "renders": round(renders, 2),
                "usd": round(renders * usd, 4),
                "cad": round(renders * usd * images.USD_TO_CAD, 4)}

    expected = row(float(expected_attempts_per_accept))
    ceiling = gw.monthly_ceiling_cad()
    return {"model": MODEL, "tier": tier, "usd_per_image": usd,
            "references_charged": False, "accepted_images": accepted,
            "breakdown": {"product_only": 1, "lifestyle": int(lifestyle_count),
                          "variants": int(variant_count)},
            "expected": expected,
            "sensitivity": [row(r) for r in (1.0, 1.5, 2.0, 3.0)],
            "worst_case_bounded": row(float(MAX_ATTEMPTS)),
            "monthly_ceiling_cad": ceiling,
            "galleries_per_month_at_expected": (int(ceiling // expected["cad"])
                                                if expected["cad"] else None),
            "excludes": ("verification (vision-model judging) and any other model spend; "
                         "pattern references are free (deterministic)"),
            "price_basis": images.BFL_PRICE_BASIS}
