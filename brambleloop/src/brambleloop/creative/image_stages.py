"""Generation stages for the autonomous FLUX 3 gallery (W4-FLUXAPI; interface for W-OWNERIMG).

The owner's staged workflow, as he ran it by hand on dashboard.bfl.ai, made callable:

    canonical Laura references -> product references (pattern-derived, free) ->
    product_only -> lifestyle (Laura + outfit + the product) -> variants (edits)

Three functions, each with a stable signature the orchestrator calls:

    product_only(release, refs)                                   -> Candidate
    lifestyle(release, product_candidate, laura_refs, outfit)     -> Candidate
    variant(release, base_candidate, role, edit_instruction)      -> Candidate

Every stage:
- builds its prompt from a **pinned** prompt (`gateway.prompts`, immutable `name@version`,
  content-hashed) -- never a string assembled at the call site;
- spends only through the renderer it is given. The default renderer is
  `gateway.images.generate` on `flux-3-image`, which reserves the documented price against the
  monthly ceiling and the agent's daily permission *before* the request, transmits every
  reference (refused above 10), stores the result bytes at once and fingerprints them;
- makes at most `max_attempts` calls (hard cap `MAX_ATTEMPTS`), and retries only a transient
  failure. A refusal, a moderation verdict, an empty balance or an exhausted budget is final;
- returns a `Candidate` whose `receipt` carries model, every input's sha256, prompt ref and
  hash, the provider's task id / seed, cost, latency and the output's sha256.

`StubRenderer` has the same interface and spends nothing: tests and dry runs use it.

A candidate is *only* a candidate. Verification (identity, Product Truth, anatomy, brand QA,
disclosure) and the gallery decision are other modules' gates; nothing here approves an image.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Protocol, Sequence

from ..core.resilience import TransientError
from ..gateway import prompts

MODEL = "flux-3-image"
MAX_ATTEMPTS = 3                     # hard cap per stage call; the caller may ask for fewer
DEFAULT_ATTEMPTS = 2
AGENT = "creative_director"          # the agent whose daily permission the renders spend
PRODUCT_SIZE = "1024x1024"           # 1:1 at FLUX 3's 1k tier (US$0.048)
LIFESTYLE_SIZE = "912x1140"          # 4:5 at the 1k tier (US$0.048)
MAX_EDIT_CHARS = 400

# Variant roles the gallery may ask for. Closed, so a role is a known shot rather than free text
# that turns an edit into a new generation.
VARIANT_ROLES: tuple[str, ...] = ("detail_closeup", "flat_lay", "scale_in_hand",
                                  "styled_scene", "wardrobe_change", "colour_context")

# -- pinned prompts --------------------------------------------------------------------------
# Image prompts produce one image, not tokens. They go through the same immutable, hashed,
# versioned registry as text prompts; `output_schema` names the single artefact and
# `max_output_tokens` is the registry's minimum, which the image gateway never reads (an image
# is priced per image, `gateway.images.render_estimate_usd`).
_IMG = dict(system="", output_schema=("image",), max_output_tokens=1)

PRODUCT_ONLY = prompts.register(prompts.Prompt(
    name="image.product_only", version="1", **_IMG, template=(
        "Product photograph of the finished {title}, a real handmade crochet piece, "
        "{size}. Image 1 is its exact stitch and colour layout, image 2 an enlarged motif "
        "showing stitch placement, image 3 its construction sheet with the yarn colours "
        "{colours}. Reproduce that layout, motif, colour order and proportion exactly; it is "
        "worked in {stitch} crochet with visible yarn texture. Product only, no person, no "
        "props that hide it, soft natural daylight, neutral linen background, whole piece in "
        "frame. Do not add colours, motifs, borders, fringe, text or logos.")))

LIFESTYLE = prompts.register(prompts.Prompt(
    name="image.lifestyle", version="1", **_IMG, template=(
        "Lifestyle photograph. Image 1 is the {title}; keep it exactly as in image 1: same "
        "colours, motif, stitch texture and proportion. Images {laura_span} are the same "
        "woman, Laura: keep her face, hair, skin tone and build exactly. {outfit_clause} "
        "Laura is {action} in {setting}, natural light, candid, photorealistic, the product "
        "clearly visible and in focus. No text, logos or watermarks.")))

VARIANT = prompts.register(prompts.Prompt(
    name="image.variant", version="1", **_IMG, template=(
        "In image 1, {edit}. Keep everything else exactly unchanged: the {title} (colours, "
        "motif, stitch texture, proportion), the person's face and body, the composition and "
        "the lighting. No text, logos or watermarks.")))

_ROLE_EDITS: dict[str, str] = {
    "detail_closeup": "crop in to a close-up of the stitch texture of the crochet piece",
    "flat_lay": "show the crochet piece laid flat from directly above on the same surface",
    "scale_in_hand": "show the crochet piece held in two hands so its size is clear",
    "styled_scene": "place the scene in a calm, softly lit nursery corner",
    "wardrobe_change": "change only the person's clothing as described",
    "colour_context": "change only the background to a plain warm neutral",
}


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
    size_text: str
    colours_text: str
    stitch: str
    pattern_refs: tuple[str, ...]           # layout, motif, construction (pattern_refs.build)
    pattern_ref_sha256s: tuple[str, ...] = ()


@dataclass(frozen=True)
class Candidate:
    stage: str
    role: str
    path: str
    sha256: str
    release_hash: str
    receipt: dict = field(default_factory=dict)


class Renderer(Protocol):
    """What a stage calls. `gateway.images.generate`'s keyword contract, narrowed."""

    def __call__(self, prompt: str, *, reference_urls: Sequence[str], size: str,
                 work_dir: str, purpose: str, agent: str, db=None,
                 job_id: int | None = None) -> dict: ...


def flux3_renderer(env: Mapping[str, str] | None = None, *,
                   provider_key: str = MODEL) -> Renderer:
    """The paid renderer: `images.generate` on FLUX 3 Image (reserve -> send -> store -> bill)."""
    from ..gateway import images

    def render(prompt, *, reference_urls, size, work_dir, purpose, agent, db=None,
               job_id=None):
        return images.generate(prompt, reference_urls=list(reference_urls), env=env,
                               size=size, provider_key=provider_key, work_dir=work_dir,
                               db=db, agent=agent, purpose=purpose, job_id=job_id)
    return render


class StubRenderer:
    """Same interface, no network, no spend. Writes a deterministic PNG per call.

    `fail_with` raises the given exceptions in order before succeeding, to exercise attempts."""

    def __init__(self, fail_with: Sequence[BaseException] = ()):
        self.calls: list[dict] = []
        self._fail = list(fail_with)

    def __call__(self, prompt, *, reference_urls, size, work_dir, purpose, agent, db=None,
                 job_id=None):
        refs = list(reference_urls)
        self.calls.append({"prompt": prompt, "refs": refs, "size": size, "purpose": purpose,
                           "agent": agent})
        if self._fail:
            raise self._fail.pop(0)
        from PIL import Image
        import io

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
        ref_hashes = [hashlib.sha256(Path(r).read_bytes()).hexdigest() for r in refs]
        return {"provider": "stub", "model": "stub", "path": str(path), "image_ref": str(path),
                "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "cad": 0.0,
                "latency_ms": 0.0, "provider_receipt": {"id": f"stub-{len(self.calls)}",
                                                        "seed": None},
                "conditioning": {"reference_sha256s": ref_hashes, "proven": bool(refs),
                                 "transmitted": len(refs), "requested": len(refs)}}


# -- helpers ---------------------------------------------------------------------------------
def release_from_cir(cir, *, release_hash: str, out_dir: str | Path) -> Release:
    """A `Release` for a certified CIR, with its pattern references rendered (free)."""
    from . import pattern_refs

    manifest = pattern_refs.build(cir, release_hash=release_hash, out_dir=out_dir)
    by_role = {r["role"]: r for r in manifest["references"]}
    ordered = [by_role[r] for r in pattern_refs.ROLES]
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin

    twin = build_twin(cir, compile_cir(cir))
    size = (f"{twin.width_cm:.0f} x {twin.height_cm:.0f} cm"
            if twin.width_cm and twin.height_cm else "its true proportions")
    colours = ", ".join(f"{k} {v}" for k, v in cir.colors.items())
    return Release(slug=cir.slug, version=cir.version, release_hash=release_hash,
                   title=cir.title, size_text=size, colours_text=colours,
                   stitch=str(cir.gauge.stitch_type),
                   pattern_refs=tuple(r["path"] for r in ordered),
                   pattern_ref_sha256s=tuple(r["sha256"] for r in ordered))


def _sha(path: str) -> str:
    p = Path(str(path))
    if not p.is_file():
        raise StageRefused(f"{p.name}: not a file on this disk; a reference that is not here "
                           f"conditions on nothing")
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _attempts(max_attempts: int) -> int:
    n = int(max_attempts)
    if not 1 <= n <= MAX_ATTEMPTS:
        raise StageRefused(f"max_attempts={max_attempts}: must be 1..{MAX_ATTEMPTS}")
    return n


def _run(stage: str, role: str, release: Release, prompt: prompts.Prompt, values: dict,
         refs: list[str], size: str, *, renderer: Renderer | None, work_dir: str, db,
         job_id: int | None, max_attempts: int, purpose: str) -> Candidate:
    from ..gateway import images

    if not work_dir:
        raise StageRefused("work_dir is required: the candidate's bytes must outlive the call")
    if len(refs) > images.BY_KEY[MODEL].reference_images:
        raise StageRefused(f"{len(refs)} references exceed FLUX 3 Image's documented 10")
    input_hashes = [_sha(r) for r in refs]
    text = prompt.render(**values)
    render = renderer or flux3_renderer()
    tries = _attempts(max_attempts)
    errors: list[str] = []
    started = time.time()
    for attempt in range(1, tries + 1):
        try:
            out = render(text, reference_urls=refs, size=size, work_dir=work_dir,
                         purpose=purpose, agent=AGENT, db=db, job_id=job_id)
        except TransientError as exc:          # the only failure worth another attempt
            errors.append(f"attempt {attempt}: {type(exc).__name__}: {str(exc)[:200]}")
            if attempt == tries:
                raise
            continue
        path = str(out.get("path") or "")
        out_sha = out.get("sha256") or _sha(path)
        cond = dict(out.get("conditioning") or {})
        sent = list(cond.get("reference_sha256s") or [])
        if sent != input_hashes:
            raise StageRefused(f"{stage}: the provider's receipt names {len(sent)} reference "
                               f"hash(es), the stage supplied {len(input_hashes)}; a render "
                               f"whose inputs cannot be proven is not a candidate")
        pr = dict(out.get("provider_receipt") or {})
        receipt = {
            "stage": stage, "role": role, "model": out.get("model") or MODEL,
            "provider": out.get("provider"), "release_hash": release.release_hash,
            "prompt_ref": prompt.ref, "prompt_sha256": prompt.sha256,
            "prompt_text_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "input_sha256s": input_hashes, "size": size,
            "task_id": pr.get("task_id") or pr.get("id"), "seed": pr.get("seed"),
            "cost_cad": out.get("cad"), "provider_cost_credits": pr.get("cost"),
            "cost_entry_id": out.get("cost_entry_id"),
            "latency_ms": round((time.time() - started) * 1000, 2),
            "provider_latency_ms": out.get("latency_ms"),
            "output_sha256": out_sha, "attempts": attempt, "attempt_errors": errors,
            "price": (cond.get("price") or {}),
        }
        return Candidate(stage=stage, role=role, path=path, sha256=out_sha,
                         release_hash=release.release_hash, receipt=receipt)
    raise AssertionError("unreachable")  # pragma: no cover


# -- the three stages ------------------------------------------------------------------------
def product_only(release: Release, refs: Sequence[str] | None = None, *,
                 renderer: Renderer | None = None, work_dir: str, db=None,
                 job_id: int | None = None, max_attempts: int = DEFAULT_ATTEMPTS
                 ) -> Candidate:
    """The product alone, conditioned on its pattern references (layout, motif, sheet).

    `refs` defaults to the release's own pattern references, in that order."""
    refs = list(refs if refs is not None else release.pattern_refs)
    if not refs:
        raise StageRefused("product_only needs the pattern references; none were given")
    return _run("product_only", "hero_product", release, PRODUCT_ONLY,
                {"title": release.title, "size": release.size_text,
                 "colours": release.colours_text, "stitch": release.stitch},
                refs, PRODUCT_SIZE, renderer=renderer, work_dir=work_dir, db=db,
                job_id=job_id, max_attempts=max_attempts, purpose="image.product_only")


def lifestyle(release: Release, product_candidate: Candidate, laura_refs: Sequence[str],
              outfit: Mapping | None, *, setting: str = "a calm, sunlit nursery",
              action: str = "holding the blanket", renderer: Renderer | None = None,
              work_dir: str, db=None, job_id: int | None = None,
              max_attempts: int = DEFAULT_ATTEMPTS) -> Candidate:
    """Laura with the product. References, in order: product, Laura (1-3), outfit image.

    `outfit` comes from W-OWNERIMG's registry: {"id", "description", optional "image"}."""
    if product_candidate.release_hash != release.release_hash:
        raise StageRefused("the product candidate belongs to a different release")
    laura = list(laura_refs or [])
    if not 1 <= len(laura) <= 3:
        raise StageRefused("lifestyle needs one to three canonical Laura references")
    outfit = dict(outfit or {})
    refs = [product_candidate.path, *laura]
    span = "2" if len(laura) == 1 else f"2 to {1 + len(laura)}"
    clause = ""
    if outfit.get("image"):
        refs.append(str(outfit["image"]))
        clause = f"She wears the outfit from image {len(refs)}"
        clause += f" ({outfit['description']})." if outfit.get("description") else "."
    elif outfit.get("description"):
        clause = f"She wears {outfit['description']}."
    return _run("lifestyle", f"lifestyle:{outfit.get('id') or 'unspecified'}", release,
                LIFESTYLE, {"title": release.title, "laura_span": span,
                            "outfit_clause": clause, "action": action, "setting": setting},
                refs, LIFESTYLE_SIZE, renderer=renderer, work_dir=work_dir, db=db,
                job_id=job_id, max_attempts=max_attempts, purpose="image.lifestyle")


def variant(release: Release, base_candidate: Candidate, role: str, edit_instruction: str = "",
            *, renderer: Renderer | None = None, work_dir: str, db=None,
            job_id: int | None = None, max_attempts: int = DEFAULT_ATTEMPTS) -> Candidate:
    """An edit of an existing candidate (FLUX 3's single-reference edit): one closed `role`,
    optionally made specific by `edit_instruction` (e.g. the wardrobe change)."""
    if base_candidate.release_hash != release.release_hash:
        raise StageRefused("the base candidate belongs to a different release")
    if role not in VARIANT_ROLES:
        raise StageRefused(f"unknown variant role {role!r}; known: {VARIANT_ROLES}")
    extra = (edit_instruction or "").strip()
    if len(extra) > MAX_EDIT_CHARS:
        raise StageRefused(f"edit instruction is {len(extra)} chars; at most {MAX_EDIT_CHARS}")
    if role == "wardrobe_change" and not extra:
        raise StageRefused("wardrobe_change needs the new outfit described")
    edit = _ROLE_EDITS[role] + (f": {extra}" if extra else "")
    size = PRODUCT_SIZE if base_candidate.stage == "product_only" else LIFESTYLE_SIZE
    return _run("variant", role, release, VARIANT, {"edit": edit, "title": release.title},
                [base_candidate.path], size, renderer=renderer, work_dir=work_dir, db=db,
                job_id=job_id, max_attempts=max_attempts, purpose=f"image.variant.{role}")


# -- cost model ------------------------------------------------------------------------------
def gallery_cost(*, lifestyle_count: int = 2, variant_count: int = 3,
                 expected_attempts_per_accept: float = 2.0, tier: str = "1k") -> dict:
    """Expected render spend for one complete gallery, from BFL's published FLUX 3 price.

    `expected_attempts_per_accept` is the number of renders bought per image the verifier
    accepts (1.0 = everything passes first time). UNKNOWN until measured: the owner's hand
    runs are not a pass rate, so the figure is reported at several rates, not one."""
    from ..gateway import anthropic as gw
    from ..gateway import images

    usd = images.BFL3_TIER_USD[tier]
    accepted = 1 + int(lifestyle_count) + int(variant_count)

    def row(rate: float) -> dict:
        renders = accepted * rate
        cad = renders * usd * images.USD_TO_CAD
        return {"attempts_per_accept": rate, "renders": round(renders, 2),
                "usd": round(renders * usd, 4), "cad": round(cad, 4)}

    expected = row(float(expected_attempts_per_accept))
    ceiling = gw.monthly_ceiling_cad()
    return {"model": MODEL, "tier": tier, "usd_per_image": usd,
            "accepted_images": accepted, "breakdown": {
                "product_only": 1, "lifestyle": int(lifestyle_count),
                "variants": int(variant_count)},
            "expected": expected,
            "sensitivity": [row(r) for r in (1.0, 1.5, 2.0, 3.0)],
            "worst_case_bounded": row(float(MAX_ATTEMPTS)),
            "monthly_ceiling_cad": ceiling,
            "galleries_per_month_at_expected": (int(ceiling // expected["cad"])
                                                if expected["cad"] else None),
            "excludes": ("verification (vision-model judging) and any other model spend: "
                         "those are priced by their own gateways; pattern references are "
                         "free (deterministic)"),
            "price_basis": images.BFL_PRICE_BASIS}
