"""W-OWNERIMG's `visual.image_production.Generator`, implemented on the FLUX 3 stages (their E1).

The orchestrator calls two methods:

    prepare_references(*, slug, version, release, cir_fingerprint) -> [{"kind", "data", "label"}]
    generate(*, stage, role, brief, references, outfit, attempt, repair=None) -> {
        "data", "provider", "model", "prompt", "cost_cad", "latency_s", "identity_evidence",
        "cost_basis"}

and reads `name`, `paid` and `max_cost_cad_per_call`.

Two facts the protocol does not carry, and how this adapter recovers them without trusting
anything it cannot check:

- **Which release.** `generate` is not told the slug, version or release. The orchestrator
  stores each prepared reference's `kind`, `sha256` and `label`, so the label carries the binding
  (`"<role>|<slug>@<version>|<release>"`). On `generate`, the CIR is reloaded and its content
  hash must equal that release, and the references are re-rendered and must hash to exactly the
  bytes handed in. Anything else is refused.
- **That the flat lay passed.** Lifestyle is gated on a PASS for that exact flat lay
  (`image_stages.lifestyle`). The orchestrator only reaches lifestyle after its fidelity gate,
  and the verdict is re-read rather than assumed: `anchor_lookup(db, slug, version, release)`
  returns the anchor's bytes and technical status (by default from W-OWNERIMG's `_best` and the
  artifact store). Anything but PASS is refused.

Roles: `product_anchor` maps to `product_only` (the unfolded flat lay). A role with canonical Laura
references maps to `lifestyle` with the reserved outfit. Any other role maps to a `variant` of the
anchor (`styled_scene`, with the brief as the instruction). Repair directives add their
negatives to the certified ones; they never remove one.
"""
from __future__ import annotations

import hashlib
import tempfile
import time
from pathlib import Path
from typing import Callable

from . import image_stages as S
from . import pattern_refs as P

ANCHOR_ROLE = "product_anchor"
_KIND_PRODUCT = "pattern_derived"
_KIND_LAURA = "laura_canonical"


class GeneratorRefused(RuntimeError):
    """The orchestrator's inputs cannot be bound to a certified release honestly."""


def _default_cir_loader(db):
    """The certified CIR for slug@version, as `runtime.release._load_cir` reads it: refused
    when there is no product, no version, or the version is not certified."""
    def load(slug: str, version: str):
        from sqlalchemy import select

        from ..cir.model import CIR
        from ..core.models import PatternVersion, Product

        with db.session() as s:
            product = s.scalar(select(Product).where(Product.slug == slug))
            pv = product and s.scalar(select(PatternVersion).where(
                PatternVersion.product_id == product.id, PatternVersion.version == version))
            if pv is None or not pv.certified:
                raise GeneratorRefused(f"{slug}@{version} has no certified release; no "
                                       f"references or images for an uncertified pattern")
            return CIR.from_dict(pv.cir_json)
    return load


def _default_anchor_lookup(db):
    def lookup(slug: str, version: str, release: str):
        from ..core.artifacts import ArtifactStore
        from ..visual import image_production as IP
        from ..visual import outfits

        best = IP._best(db, listing=outfits.listing_of(slug), role=IP.ANCHOR_ROLE,
                        run=IP.run_key(slug, version, release))
        if not best or not best.get("sha256"):
            return None
        return {"data": ArtifactStore().get(best["sha256"], db=db),
                "sha256": best["sha256"], "status": best.get("technical_status") or "UNKNOWN",
                "checker": f"candidate_gates product_truth (candidate {best.get('candidate_id')})"}
    return lookup


class Flux3Generator:
    """FLUX 3 Image through `image_stages`: reserve before the call, every reference sent."""

    name = "flux3-image-stages"
    paid = True

    def __init__(self, db=None, *, renderer=None, cir_loader: Callable | None = None,
                 anchor_lookup: Callable | None = None, work_root: str | None = None,
                 size: str = S.PRODUCT_SIZE):
        self.db = db
        self.renderer = renderer
        self.cir_loader = cir_loader or _default_cir_loader(db)
        self.anchor_lookup = anchor_lookup or _default_anchor_lookup(db)
        # Owned by the caller in production (a job's work dir); a private temp root otherwise.
        self.work_root = Path(work_root or tempfile.mkdtemp(prefix="flux3-generator-"))
        self.size = size
        # A stub renderer spends nothing; the paid flag is what opens W-OWNERIMG's gate check.
        self.paid = not isinstance(renderer, S.StubRenderer)
        from ..gateway import images

        tier_usd = images.BFL3_TIER_USD[images.bfl3_tier(size)]
        self.max_cost_cad_per_call = round(tier_usd * images.USD_TO_CAD, 6)

    # -- references --------------------------------------------------------------------------
    def _release(self, slug: str, version: str, release: str) -> S.Release:
        cir = self.cir_loader(slug, version)
        if P.release_hash_of(cir) != release:
            raise GeneratorRefused(f"{slug}@{version}: the stored CIR is not release "
                                   f"{release[:12]}; references are never built for other "
                                   f"content")
        return S.release_from_cir(cir, release_hash=release, version=version,
                                  out_dir=self.work_root / f"{slug}-{release[:12]}")

    def prepare_references(self, *, slug: str, version: str, release: str,
                           cir_fingerprint: str | None = None) -> list[dict]:
        rel = self._release(slug, version, release)
        return [{"kind": _KIND_PRODUCT, "data": Path(p).read_bytes(),
                 "label": f"{role}|{slug}@{version}|{release}"}
                for role, p in zip(S.PRODUCT_ROLES, rel.pattern_refs)]

    def _bind(self, references: list[dict]) -> tuple[S.Release, str, str, str]:
        product = [r for r in references if r.get("kind") == _KIND_PRODUCT]
        labels = {str(r.get("label") or "").split("|", 1)[-1] for r in product}
        if len(product) != len(S.PRODUCT_ROLES) or len(labels) != 1 or "" in labels:
            raise GeneratorRefused("the product references do not name one release")
        ident, release = labels.pop().split("|")
        slug, version = ident.rsplit("@", 1)
        rel = self._release(slug, version, release)
        given = [r.get("sha256") or hashlib.sha256(r["data"]).hexdigest() for r in product]
        if given != list(rel.pattern_ref_sha256s):
            raise GeneratorRefused("the product references handed in are not the bytes this "
                                   "release renders; refused")
        return rel, slug, version, release

    def _laura_paths(self, references: list[dict]) -> list[str] | None:
        laura = [r for r in references if r.get("kind") == _KIND_LAURA]
        if not laura:
            return None
        out = []
        root = self.work_root / "laura"
        root.mkdir(parents=True, exist_ok=True)
        for r in laura:
            sha = hashlib.sha256(r["data"]).hexdigest()
            p = root / f"{sha}.img"
            p.write_bytes(r["data"])
            out.append(str(p))
        return out          # `image_stages.laura_references` validates every byte

    # -- generation --------------------------------------------------------------------------
    def generate(self, *, stage: str, role: str, brief: str, references: list[dict],
                 outfit: dict | None, attempt: int, repair: dict | None = None) -> dict:
        started = time.time()
        rel, slug, version, release = self._bind(references)
        extra = _repair_negatives(repair)
        if extra:
            rules = dict(rel.rules)
            rules["negatives"] = list(rules.get("negatives") or []) + extra
            rel = S.Release(**{**rel.__dict__, "rules": rules})
        work = str(self.work_root / f"{slug}-{release[:12]}" / f"{role}-{attempt}")
        laura = self._laura_paths(references)
        kw = dict(renderer=self.renderer, work_dir=work, db=self.db)
        if role == ANCHOR_ROLE:
            cand = S.product_only(rel, size=self.size, **kw)
        else:
            anchor = self._anchor(rel, slug, version, release)
            if laura is not None:
                o = dict(outfit or {})
                cand = S.lifestyle(
                    rel, anchor["candidate"], laura,
                    {"id": o.get("outfit_id") or o.get("id"),
                     "description": o.get("description")},
                    fidelity=anchor["verdict"], role=role, size=self.size,
                    scene={"environment": o.get("setting") or "",
                           "pose": brief or "", "framing": ""}, **kw)
            else:
                cand = S.variant(rel, anchor["candidate"], "styled_scene",
                                 (brief or "")[:S.MAX_EDIT_CHARS], size=self.size, **kw)
        r = cand.receipt
        return {"data": Path(cand.path).read_bytes(), "provider": r.get("provider"),
                "model": r.get("model"), "prompt": r.get("prompt_ref"),
                "cost_cad": r.get("cost_cad"), "latency_s": round(time.time() - started, 3),
                "cost_basis": (r.get("price") or {}).get("basis") or "generator receipt",
                "identity_evidence": r}

    def _anchor(self, rel: S.Release, slug: str, version: str, release: str) -> dict:
        got = self.anchor_lookup(slug, version, release)
        if not got or not got.get("data"):
            raise GeneratorRefused("no product-only flat lay for this release; lifestyle and "
                                   "other roles come after it")
        sha = hashlib.sha256(got["data"]).hexdigest()
        if got.get("sha256") and got["sha256"] != sha:
            raise GeneratorRefused("the anchor's bytes are not the recorded anchor")
        p = self.work_root / f"{slug}-{release[:12]}" / f"anchor-{sha[:12]}.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(got["data"])
        cand = S.Candidate(stage="product_only", role="product_flat_lay", path=str(p),
                           sha256=sha, release_hash=release,
                           receipt={"features_laura": False})
        status = got.get("status") or "UNKNOWN"
        verdict = S.fidelity_verdict(cand, status=status if status in ("PASS", "FAIL")
                                     else "UNKNOWN", checker=got.get("checker") or "unknown")
        return {"candidate": cand, "verdict": verdict}


def _repair_negatives(repair: dict | None) -> list[str]:
    out: list[str] = []
    for d in (repair or {}).get("directives") or []:
        for n in d.get("negatives") or []:
            if isinstance(n, str) and n not in out:
                out.append(n)
    return out


def register(register_generator=None) -> None:
    """Register with W-OWNERIMG's orchestrator: `image_production.register_generator`."""
    if register_generator is None:
        from ..visual import image_production as IP

        register_generator = IP.register_generator
    register_generator("flux3-image-stages", lambda db: Flux3Generator(db))
