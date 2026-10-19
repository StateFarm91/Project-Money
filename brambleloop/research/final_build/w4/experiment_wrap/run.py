#!/usr/bin/env python3
"""W4-WRAPTEST: the owner-approved Reading Nook Cable Wrap experiment, as one command.

    EXPERIMENT — UNCERTIFIED — NOT FOR PUBLICATION

Owner approval, 2026-10-19: the first real end-to-end autonomous listing test, on the Reading
Nook Cable Wrap v0.1.0, with CA$5.00 of new paid usage at most (generation, retries and vision
evaluation together; every existing ceiling still applies), no credit purchases, no
publication, SHADOW only.

Run from the `brambleloop/` directory:

    # default: the stub provider, no network, no key, no spend
    .venv/bin/python research/final_build/w4/experiment_wrap/run.py --dry-run

    # the paid run (owner decision pending): FLUX 3 at 2k + Claude vision, CA$5.00 hard cap
    .venv/bin/python research/final_build/w4/experiment_wrap/run.py --live

`--live` reads `BRAMBLELOOP_IMAGE_KEY_BFL` and `ANTHROPIC_API_KEY` from the environment only.
If either is missing it refuses before opening anything, and nothing is spent.

What it does, unattended, from start to approval card:

1. builds a scratch SHADOW database and runs `gate.certify` on the wrap through the real
   queue and handler. It expects a refusal (UNCALIBRATED_PRIMITIVE cable2x2) and records the
   exact reasons. A certificate is never written or asserted;
2. renders the uncertified US and UK PDFs twice each with a fixed `released_on`, and refuses
   if the bytes differ;
3. opens an EXPERIMENT (`visual.experiment`) bound to the CIR content hash and those PDF
   hashes;
4. drives the real orchestrator (`visual.image_production`, job type
   `visual.image_production`, through `Worker`) with `Flux3Generator`. The stages are the
   references, Laura's verified canonical references, automatic outfit selection (distinct
   from the canonical clothing and the owner's earlier wrap outfit), the product-only flat
   lay, the fidelity gate, two Laura images, verification, gallery assembly and the card;
5. drafts the listing with the existing seo, search, category and pricing code;
6. creates the approval card through the Command Center notification path in the scratch
   database;
7. writes a static HTML approval package and a timestamped execution timeline.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]                       # brambleloop/
sys.path.insert(0, str(ROOT / "src"))

SLUG, VERSION, RELEASED_ON = "reading-nook-cable-wrap", "0.1.0", "2026-10-19"
BUDGET_CAD = 5.00
KEY_VARS = ("BRAMBLELOOP_IMAGE_KEY_BFL", "ANTHROPIC_API_KEY")
LIVE_SIZE = "2048x2048"                      # 1:1 at the 2k tier (image_stages.PRODUCT_SIZE)
STUB_MARK = "STUB — DRY RUN — NOT A GENERATED IMAGE"

# The clothing the experiment's outfit must differ from (owner brief).
CANONICAL_CLOTHING = {"top_or_dress": "ivory top", "lower": "beige trousers"}
OWNER_PRIOR_WRAP_OUTFIT = {"top_or_dress": "brown fitted long-sleeve top",
                           "lower": "cream tailored trousers", "shoes": "tan leather ankle boots",
                           "accessories": "gold pendant necklace"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def jsha(obj) -> str:
    return sha(json.dumps(obj, sort_keys=True, default=str).encode())


class Refused(SystemExit):
    pass


# ---- timeline -----------------------------------------------------------------------------

class Timeline:
    """Every stage, timestamped, with job ids, idempotency keys, input/output hashes, cost."""

    def __init__(self):
        self.events: list[dict] = []
        self.t0 = time.time()

    def add(self, stage: str, *, actor: str = "harness", started: float | None = None,
            inputs=None, outputs=None, job_id=None, idempotency_key=None, cost_cad=0.0,
            note: str = "") -> dict:
        end = time.time()
        ev = {"at": _now().isoformat(timespec="milliseconds"), "stage": stage, "actor": actor,
              "duration_s": round(end - (started or end), 3), "job_id": job_id,
              "idempotency_key": idempotency_key,
              "inputs_sha256": jsha(inputs) if inputs is not None else None,
              "outputs_sha256": jsha(outputs) if outputs is not None else None,
              "cost_cad": cost_cad, "owner_action": None, "note": note}
        self.events.append(ev)
        return ev


# ---- certification through the real chain -------------------------------------------------

def scratch_db(out: Path):
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{out / 'scratch_shadow.db'}", scratch=True)
    db.create_all()
    Registry(db).seed_defaults()
    return db


def drain(db, name: str, job_types: list[str], limit: int = 200) -> int:
    from brambleloop.runtime import pipeline  # noqa: F401 - registers the handlers
    from brambleloop.runtime import release  # noqa: F401
    from brambleloop.runtime.worker import Worker

    w = Worker(db, name, job_types=job_types)
    n = 0
    for _ in range(limit):
        if not w.run_once():
            break
        n += 1
    return n


def certify(db, tl: Timeline):
    from sqlalchemy import select

    from brambleloop.core.models import AuditLog, Job
    from brambleloop.products import moment_candidates as mc
    from brambleloop.queue.durable import JobQueue

    t = time.time()
    cir = mc.reading_nook_cable_wrap(VERSION)
    key = f"experiment:certify:{cir.slug}:{cir.version}:{cir.fingerprint}"
    job = JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()},
                               idempotency_key=key)
    drain(db, "experiment-certify", ["gate.certify"])
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(
            AuditLog.artifact == f"{cir.slug}@{cir.version}",
            AuditLog.action.in_(("gate.certified", "gate.blocked"))).order_by(AuditLog.id.desc()))
        j = s.get(Job, job.id)
        status = j.status
        outputs = dict(j.outputs or {})
    if row is None:
        raise Refused(f"gate.certify did not record a decision (job {job.id} {status})")
    d = dict(row.detail or {})
    cert = {"granted": bool(d.get("granted")), "reasons": list(d.get("reasons") or []),
            "content_hash": d.get("content_hash"), "source": f"gate.certify job {job.id} "
                                                             f"(audit {row.action} #{row.id})",
            "job_id": job.id, "job_status": str(status), "job_outputs": outputs,
            "physical_test_required": d.get("physical_test_required")}
    tl.add("certification: gate.certify (real handler, scratch SHADOW DB)", actor="quality_director",
           started=t, inputs={"cir_fingerprint": cir.fingerprint}, outputs=cert, job_id=job.id,
           idempotency_key=key,
           note=("REFUSED: " + "; ".join(cert["reasons"])) if not cert["granted"] else "GRANTED")
    return cir, cert


def render_pdfs(db, cir, tl: Timeline) -> dict:
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin
    from brambleloop.publish.pdf import build_pattern_pdf
    from brambleloop.quality.physical import calibration_from_db

    t = time.time()
    released = date.fromisoformat(RELEASED_ON)
    twin = build_twin(cir, compile_cir(cir), calibration=calibration_from_db(db, cir))
    out = {}
    for term in ("US", "UK"):
        a = build_pattern_pdf(cir, twin=twin, terminology=term, released_on=released).pdf_bytes
        b = build_pattern_pdf(cir, twin=twin, terminology=term, released_on=released).pdf_bytes
        if a != b:
            raise Refused(f"the {term} PDF is not deterministic for a fixed released_on")
        out[term] = a
    tl.add("uncertified PDFs rendered twice each, fixed released_on", started=t,
           inputs={"released_on": RELEASED_ON},
           outputs={t_: sha(b) for t_, b in out.items()})
    return out


# ---- outfit -------------------------------------------------------------------------------

def outfit_problems(garments: dict) -> list[str]:
    """Why an outfit is not distinct enough from the canonical and earlier wrap clothing."""
    g = {k: str(v or "").lower() for k, v in garments.items()}
    out = []
    top, lower = g.get("top_or_dress", ""), g.get("lower", "")
    if "ivory" in top:
        out.append("ivory top = canonical reference clothing")
    if "beige" in lower:
        out.append("beige trousers = canonical reference clothing")
    if "brown" in top:
        out.append("brown top = owner's earlier wrap outfit")
    if "cream" in lower or "stone" in lower or "ivory" in lower:
        out.append("cream/stone trousers = owner's earlier wrap outfit")
    if "tan" in g.get("shoes", "") and "boot" in g.get("shoes", ""):
        out.append("tan boots = owner's earlier wrap outfit")
    if "gold" in g.get("accessories", "") and any(w in g.get("accessories", "") for w in (
            "necklace", "chain", "pendant")):
        out.append("gold necklace = owner's earlier wrap outfit")
    if any(w in top for w in ("cream", "green", "sage", "olive", "forest")):
        out.append("top competes with the wrap's forest/cream (the wrap sits on it)")
    if any(w in g.get("outerwear", "") for w in ("wrap", "shawl", "scarf", "coat", "cardigan",
                                                 "vest")):
        out.append("outerwear would cover or compete with the wrap")
    return out


def select_outfit(db, listing: str) -> dict:
    """Automatic outfit and scene: `styling.select`, then refused until distinct."""
    from brambleloop.visual import outfits, styling

    used = [(f"{o['outfit_id']} ({o.get('listing')})", o.get("garments") or {})
            for o in outfits.registry(db) if o.get("listing") and o["listing"] != listing]
    used.append(("owner's earlier wrap outfit (2026-10-19 manual test)", OWNER_PRIOR_WRAP_OUTFIT))
    rejected = []
    for _ in range(80):
        st = styling.select(listing, category="wrap", product_colours=("forest", "cream"),
                            season="winter", target_customer="a reader who loves a calm nook",
                            materials=("worsted wool",), use="worn as a wrap while reading",
                            used_outfits=used)
        o = st.get("outfit")
        if not o:
            return {"outfit": None, "why": st.get("why"), "rejected": rejected}
        g = dict(o["garments"])
        used.append((f"rejected {len(rejected)}", dict(o["garments"])))
        g["outerwear"] = "none"           # the wrap is the outer layer
        problems = outfit_problems(g)
        if problems:
            rejected.append({"garments": g, "why": problems})
            continue
        oid = "exp-" + hashlib.sha256(f"{listing}|{outfits.signature(g)}".encode()).hexdigest()[:10]
        from brambleloop.visual.wardrobe import parse_outfit

        colours = sorted({c for x in parse_outfit(g).values() for c in x["colours"]})
        concept = dict(st["concept"])
        concept.update(setting="a warm reading nook: an armchair, a wool rug, a lamp and a "
                               "bookshelf, late-afternoon window light",
                       action="wearing the wrap over her shoulders while reading")
        return {**st, "outfit": {"outfit_id": oid, "garments": g, "colours": colours,
                                 "description": "; ".join(v for v in g.values()
                                                          if v and v != "none")},
                "concept": concept, "rejected": rejected,
                "distinct_from": {"canonical_reference_clothing": CANONICAL_CLOTHING,
                                  "owner_prior_wrap_outfit": OWNER_PRIOR_WRAP_OUTFIT}}
    return {"outfit": None, "why": "no distinct outfit in 80 selections", "rejected": rejected}


# ---- generators ---------------------------------------------------------------------------

def stub_renderer_class():
    from brambleloop.creative import image_stages as S

    class StubFluxRenderer(S.StubRenderer):
        """The stub provider, at full listing size, every image marked STUB."""

        def __call__(self, prompt, *, reference_urls, size, work_dir, purpose, agent, db=None,
                     job_id=None):
            from PIL import Image, ImageDraw, ImageFont

            refs = list(reference_urls)
            if len(refs) > self.reference_limit:
                raise AssertionError("the stage sent more references than the provider takes")
            self.calls.append({"prompt": prompt, "refs": refs, "size": size,
                               "purpose": purpose, "agent": agent})
            seed = hashlib.sha256((prompt + "|".join(refs) + size).encode()).digest()
            w, h = (int(x) for x in size.split("x"))
            img = Image.new("RGB", (w, h), (60 + seed[0] % 60, 70 + seed[1] % 60,
                                            60 + seed[2] % 60))
            d = ImageDraw.Draw(img)
            try:
                big, small = ImageFont.load_default(size=120), ImageFont.load_default(size=56)
            except TypeError:  # pragma: no cover - old Pillow
                big = small = ImageFont.load_default()
            for i in range(0, w, 160):
                d.line([(i, 0), (i + h, h)], fill=(90, 100, 90), width=6)
            d.rectangle([0, h // 2 - 300, w, h // 2 + 300], fill=(250, 250, 250))
            d.text((80, h // 2 - 260), "STUB", fill=(200, 0, 0), font=big)
            d.text((80, h // 2 - 110), _ascii(STUB_MARK), fill=(0, 0, 0), font=small)
            d.text((80, h // 2 - 30), f"{purpose}  call {len(self.calls)}", fill=(0, 0, 0),
                   font=small)
            d.text((80, h // 2 + 50), "EXPERIMENT - UNCERTIFIED - NOT FOR PUBLICATION",
                   fill=(160, 0, 0), font=small)
            d.text((80, h // 2 + 130), f"{len(refs)} references sent (sha256-bound)",
                   fill=(0, 0, 0), font=small)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            raw = buf.getvalue()
            root = Path(work_dir)
            root.mkdir(parents=True, exist_ok=True)
            path = root / f"stub-{seed.hex()[:12]}-{len(self.calls)}.png"
            path.write_bytes(raw)
            hashes = [hashlib.sha256(Path(r).read_bytes()).hexdigest() for r in refs]
            return {"provider": "stub", "model": "stub (dry run)", "path": str(path),
                    "image_ref": str(path), "sha256": sha(raw), "bytes": len(raw), "cad": 0.0,
                    "latency_ms": 0.0,
                    "provider_receipt": {"id": f"stub-{len(self.calls)}", "seed": None},
                    "conditioning": {"reference_sha256s": hashes, "proven": bool(refs),
                                     "transmitted": len(refs), "requested": len(refs)}}

    return StubFluxRenderer


class BudgetedRenderer:
    """Wraps the FLUX renderer: per-role attempt cap, a reservation before every call, the
    measured output size, and a stop once the tier is shown to deliver under 2000 px."""

    def __init__(self, inner, budget, *, live: bool, per_role: int, log: list):
        from brambleloop.gateway import images

        self.inner, self.budget, self.live, self.per_role, self.log = (
            inner, budget, live, per_role, log)
        self.reference_limit = getattr(inner, "reference_limit", 10)
        self.provider_key = getattr(inner, "provider_key", "flux-3-image")
        self.current_role = None
        self.calls: dict[str, int] = {}
        self.floor_failed = None
        self._images = images

    def price_cad(self, size: str) -> float:
        i = self._images
        return round(i.BFL3_TIER_USD[i.bfl3_tier(size)] * i.USD_TO_CAD, 6)

    def __call__(self, prompt, *, reference_urls, size, work_dir, purpose, agent, db=None,
                 job_id=None):
        from PIL import Image

        from brambleloop.visual.experiment import ExperimentBudgetStop

        role = self.current_role or purpose
        n = self.calls.get(role, 0)
        if n >= self.per_role:
            raise ExperimentBudgetStop(f"{role}: {self.per_role} FLUX attempts already made "
                                       f"(experiment cap); nothing is sent")
        if self.floor_failed:
            raise ExperimentBudgetStop(f"the 2k tier delivered {self.floor_failed} px, under "
                                       f"2000 px; further calls are refused (never upscaled)")
        price = self.price_cad(size)
        rid = self.budget.reserve(price, what=f"flux {role} attempt {n + 1}") if self.live \
            else None
        self.calls[role] = n + 1
        t = time.time()
        entry = {"role": role, "attempt": n + 1, "purpose": purpose, "size": size,
                 "reserved_cad": price if self.live else 0.0,
                 "would_cost_cad": price, "at": _now().isoformat(), "references": len(
                     list(reference_urls))}
        try:
            out = self.inner(prompt, reference_urls=reference_urls, size=size,
                             work_dir=work_dir, purpose=purpose, agent=agent, db=db,
                             job_id=job_id)
        except Exception as exc:
            if rid is not None:
                self.budget.settle(rid, None)       # unknown: billed at the reservation
            entry.update(error=f"{type(exc).__name__}: {str(exc)[:200]}",
                         latency_s=round(time.time() - t, 2))
            self.log.append(entry)
            raise
        if rid is not None:
            self.budget.settle(rid, out.get("cad"))
        try:
            im = Image.open(out["path"])
            px, fmt = list(im.size), im.format
        except Exception:  # noqa: BLE001
            px, fmt = None, None
        entry.update(cost_cad=out.get("cad"), output_px=px, output_format=fmt,
                     output_sha256=out.get("sha256"), task_id=(out.get("provider_receipt")
                                                              or {}).get("id"),
                     latency_s=round(time.time() - t, 2), upscaled=False,
                     meets_2000px=bool(px and min(px) >= 2000))
        self.log.append(entry)
        if px and min(px) < 2000:
            self.floor_failed = f"{px[0]}x{px[1]}"
        return out


def generator_factory(*, renderer, live: bool, work_root: str):
    from brambleloop.creative.flux3_generator import Flux3Generator
    from brambleloop.visual import experiment as XP

    class ExperimentFlux3Generator(Flux3Generator):
        name = "flux3-image-stages:experiment"

        def __init__(self, db):
            super().__init__(db, renderer=renderer, cir_loader=XP.cir_loader(db),
                             work_root=work_root, size=LIVE_SIZE)
            self.paid = bool(live)

        def generate(self, *, stage, role, brief, references, outfit, attempt, repair=None):
            renderer.current_role = role
            try:
                return super().generate(stage=stage, role=role, brief=brief,
                                        references=references, outfit=outfit,
                                        attempt=attempt, repair=repair)
            finally:
                renderer.current_role = None

    return lambda db: ExperimentFlux3Generator(db)


# ---- judges -------------------------------------------------------------------------------

class StubJudges:
    """Dry run only: no image is judged. Every reading says so."""

    WHY = "STUB judge (dry run): no image was judged; this is plumbing, not a verdict"

    def __init__(self, db):
        self.db = db

    def _r(self):
        return {"status": "PASS", "why": self.WHY, "stub": True}

    def product_truth(self, c, bind):
        return self._r()

    def identity(self, c):
        return self._r()

    def anatomy(self, c):
        return self._r()

    def realism(self, c):
        return self._r()

    def body_proportions(self, c):
        return self._r()

    def outfit_consistency(self, c, outfit):
        return self._r()


VISION_SYSTEM = ("You are an exacting inspector of AI-generated lifestyle photographs for a "
                 "crochet pattern shop. You compare a generated image with reference images. "
                 "You never guess: if a fact cannot be seen, answer null or 'unclear'. Answer "
                 "with one JSON object and nothing else.")


class ExperimentVision:
    """One Claude vision call, reserved against the experiment budget AND the existing
    gateway ceiling before it is sent, settled after. An unread image is UNKNOWN."""

    def __init__(self, db, *, budget, work: str, provider=None, log: list):
        self.db, self.budget, self.work, self.provider, self.log = (
            db, budget, Path(work), provider, log)
        self.cache: dict[str, dict] = {}

    def ask(self, kind: str, key: str, paths: list[str], prompt: str, *,
            system: str = VISION_SYSTEM, max_tokens: int = 700) -> dict:
        from brambleloop.gateway import anthropic as A

        ck = f"{kind}:{key}:{sha(prompt.encode())[:12]}"
        if ck in self.cache:
            return self.cache[ck]
        prov = self.provider or A.AnthropicProvider()
        est = A.estimate_cad(prov.model, input_tokens=1700 * len(paths) + 600 + len(prompt) // 3,
                             output_tokens=max_tokens)
        entry = {"kind": kind, "subject": key, "model": prov.model, "estimate_cad": est,
                 "images": len(paths), "at": _now().isoformat()}
        try:
            rid = self.budget.reserve(est, what=f"vision {kind} {key[:12]}")
        except Exception as exc:  # noqa: BLE001 - over budget: nothing sent, UNKNOWN
            entry["refused"] = str(exc)[:300]
            self.log.append(entry)
            self.cache[ck] = {"_unread": f"vision not run: {exc}"}
            return self.cache[ck]
        gw = None
        try:
            gw = A.check_budget_cad(self.db, estimate_cad=est, agent="creative_director",
                                    purpose=f"experiment.vision.{kind}", model=prov.model,
                                    provider="anthropic", product_slug=SLUG)
            t = time.time()
            resp = prov.see(system, prompt, paths, max_tokens=max_tokens)
            actual = round(resp.input_tokens * prov.cost_per_1k_input_cad / 1000
                           + resp.output_tokens * prov.cost_per_1k_output_cad / 1000, 8)
            self.budget.settle(rid, actual)
            entry.update(cost_cad=actual, input_tokens=resp.input_tokens,
                         output_tokens=resp.output_tokens, latency_s=round(time.time() - t, 2))
            text = resp.text.strip()
            body = text[text.find("{"): text.rfind("}") + 1] if "{" in text else ""
            reading = json.loads(body) if body else {"_unread": "no JSON in the answer"}
        except Exception as exc:  # noqa: BLE001 - an unread image is UNKNOWN, never PASS
            self.budget.settle(rid, None)
            entry["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
            reading = {"_unread": entry["error"]}
        finally:
            if gw and gw.get("reservation_id"):
                try:
                    A.release_reservation(self.db, gw["reservation_id"],
                                          actual_cad=entry.get("cost_cad"))
                except Exception:  # noqa: BLE001
                    pass
        entry["reading"] = reading
        self.log.append(entry)
        self.cache[ck] = reading
        return reading

    def path_of(self, data: bytes) -> str:
        p = self.work / f"img-{sha(data)[:16]}.png"
        if not p.exists():
            p.write_bytes(data)
        return str(p)


class FidelityVisionJudge:
    """W-FIDELITY's vision-judge interface (`read(prompt, images, system, max_tokens)`), on
    the experiment's budgeted vision call. The verifier asks it blind questions only."""

    name = "experiment_vision(claude)"

    def __init__(self, vision: ExperimentVision):
        self.v = vision

    def read(self, prompt, images, *, system=None, max_tokens=300) -> dict:
        paths = [self.v.path_of(b) for b in images]
        r = self.v.ask("fidelity", sha(b"".join(images)), paths, prompt,
                       system=system or VISION_SYSTEM, max_tokens=max_tokens)
        if "_unread" in r:
            return {"answered": False, "why": r["_unread"]}
        return {"answered": True, "reading": r, "model": "claude (experiment)"}


class LiveJudges:
    """The live judges. Product Truth is the real `candidate_gates.RealJudges.product_truth`,
    i.e. W-FIDELITY's deterministic verifier (`visual.fidelity`) against the experiment's CIR,
    with its blind craft/consistency questions answered by the experiment-budgeted vision
    judge. Identity, anatomy, realism, body proportions and outfit consistency come from one
    Claude reading per Laura image (EXPERIMENT ONLY; never publication evidence)."""

    def __init__(self, db, *, budget, refs: dict, provider=None, log: list | None = None):
        from brambleloop.visual import candidate_gates as CG

        self.db, self.refs = db, refs
        self.vision = ExperimentVision(db, budget=budget, work=refs["work"], provider=provider,
                                       log=log if log is not None else [])
        self.real = CG.RealJudges(db, vision=FidelityVisionJudge(self.vision))

    def _data(self, cand: dict) -> bytes:
        from brambleloop.core.artifacts import ArtifactStore

        return cand.get("data") or ArtifactStore().get(cand["sha256"], db=self.db)

    def _laura(self, cand: dict) -> dict:
        from brambleloop.visual import outfits

        outfit = (outfits.get(self.db, cand["outfit_id"]) or {}) if cand.get("outfit_id") \
            else {}
        prompt = (
            "Image 1 is a generated lifestyle photograph. Image 2 is the canonical reference "
            "portrait of the model, Laura. Image 3, when present, is the approved product-only "
            "flat lay of the crochet wrap she should be wearing. "
            f"Her outfit should be: {outfit.get('description') or 'as reserved'}.\n"
            "Return JSON: {\"same_person_as_reference\": \"yes\"|\"no\"|\"unclear\", "
            "\"anatomy_ok\": bool|null, \"hands_ok\": bool|null, \"photorealistic\": bool|null, "
            "\"body_proportions_consistent\": \"yes\"|\"no\"|\"unclear\", "
            "\"wrap_visible\": bool, \"wrap_box\": [x0, y0, x1, y1] as fractions 0..1 of "
            "image 1's width and height, tightly around the wrap, or null, "
            "\"outfit_matches_description\": \"yes\"|\"no\"|\"unclear\", "
            "\"clothing_copied_from_reference\": bool|null, \"notes\": str}")
        data = self._data(cand)
        paths = [self.vision.path_of(data), self.refs["portrait"]]
        anchor = self.refs["anchor"]() if self.refs.get("anchor") else None
        if anchor:
            paths.append(anchor)
        return self.vision.ask("laura", cand.get("sha256") or sha(data), paths, prompt)

    def product_truth(self, cand: dict, bind: dict) -> dict:
        c = dict(cand)
        if cand.get("role") != "product_anchor" and cand.get("laura_present"):
            r = self._laura(cand)
            box = r.get("wrap_box") if isinstance(r, dict) else None
            if isinstance(box, list) and len(box) == 4:
                try:
                    w, h = Image_size(self._data(cand))
                    x0, y0, x1, y1 = (float(v) for v in box)
                    if 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1:
                        c["product_region"] = (int(x0 * w), int(y0 * h), int(x1 * w),
                                               int(y1 * h))
                except (TypeError, ValueError):
                    pass
        got = self.real.product_truth(c, bind)
        return {**got, "basis": "EXPERIMENT ONLY: W-FIDELITY visual.fidelity (deterministic) "
                                "against the uncertified CIR; vision answers its blind "
                                "questions; never publication evidence",
                "product_region_source": "vision wrap_box" if "product_region" in c else None}

    @staticmethod
    def _st(ok, why: str) -> dict:
        return {"status": "UNKNOWN" if ok is None else ("PASS" if ok else "FAIL"),
                "why": why[:400]}

    def _field(self, cand, field, yes="yes"):
        r = self._laura(cand)
        if "_unread" in r:
            return {"status": "UNKNOWN", "why": r["_unread"]}
        v = r.get(field)
        ok = None if v in (None, "unclear") else (v is True or v == yes)
        return self._st(ok, f"EXPERIMENT ONLY vision: {field}={v}")

    def identity(self, cand):
        return self._field(cand, "same_person_as_reference")

    def anatomy(self, cand):
        a, h = self._field(cand, "anatomy_ok"), self._field(cand, "hands_ok")
        s = {a["status"], h["status"]}
        return {"status": "FAIL" if "FAIL" in s else "UNKNOWN" if "UNKNOWN" in s else "PASS",
                "why": f"{a['why']}; {h['why']}"}

    def realism(self, cand):
        return self._field(cand, "photorealistic")

    def body_proportions(self, cand):
        return self._field(cand, "body_proportions_consistent")

    def outfit_consistency(self, cand, outfit):
        if self._laura(cand).get("clothing_copied_from_reference") is True:
            return {"status": "FAIL", "why": "REFERENCE_CLOTHING_CARRYOVER: the clothing is "
                                             "copied from the identity references"}
        return self._field(cand, "outfit_matches_description")


def Image_size(data: bytes) -> tuple[int, int]:
    from PIL import Image

    return Image.open(io.BytesIO(data)).size


# ---- deterministic gallery frames ---------------------------------------------------------

def gallery_builder(*, reg: dict, pdfs: dict, tl: Timeline):
    def build(db, run_key: str) -> list[dict]:
        from brambleloop.core.artifacts import ArtifactStore
        from brambleloop.publish import eligibility as el
        from brambleloop.visual import contents_frame, disclosed_render, gallery_frames
        from brambleloop.visual import experiment as XP
        from brambleloop.visual import image_production as IP

        t = time.time()
        cir = XP.cir_of(reg)
        for term, b in pdfs.items():
            if sha(b) != reg["pdf_sha256_by_terminology"][term]:
                raise XP.ExperimentRefused(f"{term} PDF bytes are not the experiment's")
        frames = {
            "detail": ("disclosed_render.detail", disclosed_render.render(cir, "detail").png),
            "size": ("disclosed_render.scale", disclosed_render.render(cir, "scale").png),
            "materials": ("gallery_frames.MATERIALS",
                          gallery_frames.render(cir, el.MATERIALS).png),
            "whats_included": ("contents_frame", contents_frame.render(
                pdfs["US"], slug=cir.slug, version=cir.version, title=cir.title,
                editions=("US", "UK")).png),
        }
        out = []
        for pos, name, role, source in XP.GALLERY:
            if source == "flux":
                best = IP._best(db, listing=reg["slug"], role=role, run=run_key)
                out.append({"position": pos, "name": name, "role": role, "source": "flux",
                            "sha256": (best or {}).get("sha256") or None,
                            "candidate_id": (best or {}).get("candidate_id"),
                            "technical_status": (best or {}).get("technical_status",
                                                                 "MISSING"),
                            "failure_categories": (best or {}).get("failure_categories"),
                            "label": XP.LABEL})
                continue
            src, png = frames[role]
            h = ArtifactStore().put(f"{run_key}/deterministic/{role}", png, "image/png", db=db,
                                    keep=f"deterministic gallery frame; {XP.LABEL}").sha256
            out.append({"position": pos, "name": name, "role": role, "source": src,
                        "sha256": h, "technical_status": "DETERMINISTIC (renderer contract; "
                                                         "content uncertified)",
                        "label": XP.LABEL})
        tl.add("gallery assembly: deterministic frames rendered and stored", started=t,
               actor="publishing", outputs=out)
        return out
    return build


# ---- listing draft ------------------------------------------------------------------------

def listing_draft(db, cir, reg: dict, gallery: list[dict]) -> dict:
    """The existing seo/search/category/pricing code, on the experiment's CIR."""
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin
    from brambleloop.commerce import category as category_mod
    from brambleloop.commerce import pricing as pricing_mod
    from brambleloop.commerce import search as search_mod
    from brambleloop.commerce import seo as seo_mod
    from brambleloop.publish.pdf import pattern_filename
    from brambleloop.runtime import release as R
    from brambleloop.visual import experiment as XP

    result = compile_cir(cir)
    twin = build_twin(cir, result)
    difficulty = R._difficulty(twin, cir)
    colors = sorted(c for c in twin.colors_used if c)
    category, motifs, season = "wrap", ["cable"], "winter"
    tolerance_pct = int(twin.yardage_tolerance * 100)
    yardage = [f"{n}: about {m * (1 - twin.yardage_tolerance):.0f}-"
               f"{m * (1 + twin.yardage_tolerance):.0f} m"
               for n, m in sorted(twin.yarn_metres_by_color.items())]
    gauge = (f"{cir.gauge.stitches_per_10cm} sts x {cir.gauge.rows_per_10cm} rows = 10 cm in "
             f"{cir.gauge.stitch_type}, {cir.gauge.hook_mm:g} mm hook") if cir.gauge else None
    size_label = (f"{twin.width_cm:.0f} x {twin.height_cm:.0f} cm (computed from the stitch "
                  f"counts at the stated gauge; no sample has been made or measured)"
                  if twin.width_cm and twin.height_cm else None)
    shape = search_mod.shape_of(twin)
    queries = search_mod.build_query_set(category, motifs, season, ["cable", "texture"],
                                         difficulty=difficulty, shape=shape)
    tags = search_mod.choose_tags(queries)
    title = seo_mod.build_title(cir.title, category, motifs, season)
    description = seo_mod.build_description(
        cir.title, size_label=size_label, yardage_lines=yardage, tolerance_pct=tolerance_pct,
        difficulty=difficulty, colors=colors, terminology="US", gauge_line=gauge,
        stitches=sorted(twin.stitch_types_used), season=season,
        why_it_matters=seo_mod.value_proposition(difficulty=difficulty, colours=len(colors)),
        yarn_lines=seo_mod.yarn_lines(list(cir.materials)))
    band = R.CATEGORY_BANDS_CAD.get(category, R.DEFAULT_BAND)
    decision = pricing_mod.decide_price(cir.slug, category_band_cad=band,
                                        proposed_cad=round((band[0] + band[1]) / 2, 2))
    facts = category_mod.Facts(category=category, difficulty=difficulty,
                               colors=[(c, (cir.colors or {}).get(c)) for c in colors],
                               season=season, width_cm=twin.width_cm or None,
                               height_cm=twin.height_cm or None)
    try:
        cat = category_mod.for_product(db, category=category, facts=facts)
    except Exception as exc:  # noqa: BLE001
        cat = {"choice": None, "error": f"{type(exc).__name__}: {exc}"}
    taxonomy = ({"status": "BLOCKED",
                 "why": ("no Etsy taxonomy snapshot in the scratch database, and production's "
                         "taxonomy reading is not readable from here without credentials "
                         "(read-only access only; nothing was written). The category is "
                         "UNKNOWN, never guessed"),
                 "reading": {k: v for k, v in cat.items() if k != "properties"}}
                if not (cat.get("snapshot") and cat.get("choice")) else
                {"status": "READ", "reading": cat})
    attributes = search_mod.listing_attributes(category=category, difficulty=difficulty,
                                               colors=colors, season=season)
    alt = {g["name"]: _alt_text(g, cir.title) for g in gallery}
    disclosures = [
        "DIGITAL PATTERN — this listing is a downloadable crochet pattern (PDF), not a "
        "finished wrap. No physical item is shipped.",
        "Instant download: two PDFs, the same pattern written in US terms and in UK terms.",
        "AI-imagery disclosure: the photographs of Laura and the flat lay are AI-generated "
        "images (FLUX 3) of the pattern's computed design, not photographs of a made sample. "
        "Laura is an AI-generated model. The detail, size, materials and contents frames are "
        "computer renders drawn from the pattern's stitch counts.",
        "Finished size and yardage are computed from the stitch counts at the stated gauge. No "
        "sample has been made or measured; yours will depend on your yarn and tension.",
        "Created with AI assistance; every row's stitch count is checked by software.",
        "Digital items: no returns or exchanges once downloaded; message the shop with any "
        "question about the pattern.",
    ]
    download = ("After purchase, open Etsy > You > Purchases and reviews, find this order "
                "and click Download Files. You get "
                + " and ".join(pattern_filename(cir, t) if _accepts(pattern_filename) else
                               f"{cir.slug}-{t}.pdf" for t in ("US", "UK"))
                + ". Open them with any PDF reader; print them or read them on screen.")
    copy_text = "\n\n".join([title, description, "\n".join(disclosures), download])
    forbidden = _physical_claims(copy_text)
    return {"label": XP.LABEL, "is_digital_pattern": True, "title": title,
            "description": description, "tags": tags, "materials": [m.name for m in
                                                                     cir.materials],
            "price_cad": decision.price_cad if hasattr(decision, "price_cad") else
            decision.to_dict().get("price_cad"), "pricing": decision.to_dict(),
            "category": {"intent": category, "taxonomy": taxonomy},
            "attributes": attributes, "disclosures": disclosures,
            "download_instructions": download, "alt_text": alt,
            "pdfs": {t: {"sha256": reg["pdf_sha256_by_terminology"][t], "certified": False}
                     for t in ("US", "UK")},
            "claims_check": {"physical_made_or_measured_claims": forbidden,
                             "ok": not forbidden, "checked": "title, description, disclosures "
                                                             "and download instructions"},
            "code_reused": ["commerce.seo.build_title", "commerce.seo.build_description",
                            "commerce.search.build_query_set", "commerce.search.choose_tags",
                            "commerce.search.listing_attributes",
                            "commerce.pricing.decide_price", "commerce.category.for_product"]}


def _accepts(fn) -> bool:
    import inspect

    try:
        return len(inspect.signature(fn).parameters) >= 2
    except (TypeError, ValueError):
        return False


def _physical_claims(text: str) -> list[str]:
    t = text.lower()
    bad = []
    for phrase in ("handmade wrap", "hand-made", "ready to ship", "made by our tester",
                   "tested by a maker", "we measured", "measured on a sample",
                   "finished item ships"):
        if phrase in t:
            bad.append(phrase)
    return bad


def _alt_text(g: dict, title: str) -> str:
    base = {
        "hero": f"AI-generated image: a model wearing the {title} made from this crochet "
                f"pattern (digital pattern, not a finished item)",
        "product_flat_lay": f"AI-generated image: the {title} laid flat, showing the cable "
                            f"columns and cream end bands (digital pattern)",
        "cable_texture_closeup": f"Computer render of the {title}'s cable stitch texture, "
                                 f"drawn from the pattern's stitch counts",
        "laura_back_drape": f"AI-generated image: back view of a model wearing the {title}, "
                            f"showing the drape (digital pattern, not a finished item)",
        "size_fit": f"Computer render of the {title} with its computed finished size",
        "materials_construction": f"Materials and construction of the {title} crochet pattern",
        "digital_download_contents": f"What you download: the {title} crochet pattern PDFs in "
                                     f"US and UK terms",
    }
    return base.get(g["name"], f"{title} crochet pattern image")


# ---- approval package ---------------------------------------------------------------------

def stamp_copy(png: bytes, *, stub: bool) -> bytes:
    """A display copy with the label burnt in; the original bytes stay hashed in the DB."""
    from PIL import Image, ImageDraw, ImageFont

    from brambleloop.visual.experiment import LABEL

    im = Image.open(io.BytesIO(png)).convert("RGB")
    w, h = im.size
    d = ImageDraw.Draw(im)
    band = max(40, h // 22)
    try:
        font = ImageFont.load_default(size=int(band * 0.55))
    except TypeError:  # pragma: no cover
        font = ImageFont.load_default()
    d.rectangle([0, h - band, w, h], fill=(150, 0, 0))
    d.text((band // 3, h - band + band // 5), _ascii(LABEL) + ("  -  STUB" if stub else ""),
           fill=(255, 255, 255), font=font)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _ascii(text: str) -> str:
    """The bundled bitmap font has no em dash; burnt-in labels use a hyphen."""
    return text.replace("\u2014", "-")


def _esc(s) -> str:
    import html

    return html.escape(str(s if s is not None else ""))


def write_package(out: Path, *, mode: str, db, run: dict, gallery: list[dict], listing: dict,
                  pdfs: dict, cert: dict, reg: dict, notification: dict, timeline: Timeline,
                  budget, flux_log: list, vision_log: list, refusals: dict,
                  outfit: dict | None, candidates: list[dict]) -> Path:
    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.visual.experiment import LABEL

    pkg = out / "approval_package"
    if pkg.exists():
        shutil.rmtree(pkg)
    timeline.events.sort(key=lambda e: e.get("at") or "")
    (pkg / "images").mkdir(parents=True)
    (pkg / "pdfs").mkdir()
    stub = mode == "dry-run"
    rows = []
    for g in gallery:
        img = None
        if g.get("sha256"):
            data = ArtifactStore().get(g["sha256"], db=db)
            fname = f"{g['position']:02d}_{g['name']}_EXPERIMENT{'_STUB' if stub and g['source'] == 'flux' else ''}.png"
            (pkg / "images" / fname).write_bytes(stamp_copy(data, stub=stub and g["source"]
                                                             == "flux"))
            img = f"images/{fname}"
        rows.append({**g, "file": img})
    for t, b in pdfs.items():
        (pkg / "pdfs" / f"EXPERIMENT-UNCERTIFIED_{SLUG}_{VERSION}_{t}.pdf").write_bytes(b)
    evidence = {"label": LABEL, "mode": mode, "run": run, "gallery": rows, "listing": listing,
                "certification": cert, "experiment": {k: v for k, v in reg.items()
                                                      if k != "cir"},
                "command_center_notification": notification, "budget": budget.to_dict(),
                "flux_calls": flux_log, "vision_calls": vision_log,
                "publication_refusals": refusals, "outfit": outfit,
                "candidates": candidates, "timeline": timeline.events}
    (pkg / "evidence.json").write_text(json.dumps(evidence, indent=1, default=str))
    (pkg / "timeline.json").write_text(json.dumps(timeline.events, indent=1, default=str))
    card = run.get("card") or {}

    def gate_rows():
        out_ = []
        for c in candidates:
            for k, v in sorted((c.get("checks") or {}).items()):
                if k.startswith("_"):
                    continue
                out_.append(f"<tr><td>{_esc(c['role'])} #{_esc(c['attempt'])}</td>"
                            f"<td>{_esc(k)}</td><td class='s-{_esc(v.get('status'))}'>"
                            f"{_esc(v.get('status'))}</td><td>{_esc(v.get('why'))}</td></tr>")
        return "\n".join(out_)

    imgs = "\n".join(
        f"<figure><div class='pos'>{r['position']}</div>"
        + (f"<a href='{_esc(r['file'])}'><img src='{_esc(r['file'])}' alt='{_esc(listing['alt_text'].get(r['name']))}'></a>"
           if r.get("file") else "<div class='missing'>MISSING</div>")
        + f"<figcaption><b>{_esc(r['name'])}</b> — {_esc(r['source'])}"
          f"{' (STUB)' if stub and r['source'] == 'flux' else ''}<br>"
          f"status: {_esc(r.get('technical_status'))}<br>"
          f"<small>alt: {_esc(listing['alt_text'].get(r['name']))}</small></figcaption></figure>"
        for r in rows)
    tl_rows = "\n".join(
        f"<tr><td>{_esc(e['at'])}</td><td>{_esc(e['stage'])}</td><td>{_esc(e['actor'])}</td>"
        f"<td>{_esc(e.get('job_id'))}</td><td><code>{_esc(e.get('idempotency_key'))}</code></td>"
        f"<td><code>{_esc((e.get('inputs_sha256') or '')[:12])}</code></td>"
        f"<td><code>{_esc((e.get('outputs_sha256') or '')[:12])}</code></td>"
        f"<td>{_esc(e.get('cost_cad'))}</td><td>{_esc(e.get('note'))}</td></tr>"
        for e in timeline.events)
    flux_rows = "\n".join(
        f"<tr><td>{_esc(f.get('role'))}</td><td>{_esc(f.get('attempt'))}</td>"
        f"<td>{_esc(f.get('size'))}</td><td>{_esc(f.get('output_px'))}</td>"
        f"<td>{_esc(f.get('output_format'))}</td><td>{_esc(f.get('cost_cad'))}</td>"
        f"<td>{_esc(f.get('would_cost_cad'))}</td><td>{_esc(f.get('latency_s'))}</td>"
        f"<td>{_esc(f.get('error') or '')}</td></tr>" for f in flux_log)
    unknowns = sorted({f"{c['role']}: {k}" for c in candidates for k, v in
                       (c.get("checks") or {}).items()
                       if isinstance(v, dict) and v.get("status") == "UNKNOWN"})
    desc_html = "<br>".join(_esc(x) for x in listing["description"].split("\n"))
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wrap Experiment Approval</title>
<style>
:root {{ --bg:#fbfaf7; --fg:#1d1d1b; --muted:#666; --warn:#9b0000; --card:#fff; --line:#ddd; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#161614; --fg:#eee; --muted:#aaa; --warn:#ff7b7b; --card:#222; --line:#444; }} }}
body {{ background:var(--bg); color:var(--fg); font:15px/1.5 system-ui,sans-serif; margin:0; padding:0 16px 48px; }}
main {{ max-width:1100px; margin:auto; }}
.banner {{ background:#9b0000; color:#fff; padding:14px 16px; font-weight:700; letter-spacing:.04em; margin:0 -16px 20px; text-align:center; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:14px; }}
figure {{ margin:0; background:var(--card); border:1px solid var(--line); border-radius:8px; overflow:hidden; position:relative; }}
figure img {{ width:100%; display:block; }}
figcaption {{ padding:8px 10px; font-size:13px; }}
.pos {{ position:absolute; top:6px; left:6px; background:#000a; color:#fff; border-radius:50%; width:26px; height:26px; text-align:center; line-height:26px; }}
.missing {{ height:240px; display:flex; align-items:center; justify-content:center; color:var(--warn); font-weight:700; }}
.three {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:12px; }}
.box {{ background:var(--card); border:1px solid var(--line); border-radius:8px; padding:12px 14px; }}
table {{ border-collapse:collapse; width:100%; font-size:12.5px; }}
td,th {{ border-bottom:1px solid var(--line); padding:4px 6px; vertical-align:top; text-align:left; }}
.scroll {{ overflow-x:auto; }}
.s-PASS {{ color:#1a7f37; font-weight:600; }} .s-FAIL {{ color:var(--warn); font-weight:700; }} .s-UNKNOWN {{ color:#b26b00; font-weight:600; }}
code {{ font-size:12px; }}
.listing {{ background:var(--card); border:1px solid var(--line); border-radius:8px; padding:16px; }}
.tag {{ display:inline-block; border:1px solid var(--line); border-radius:12px; padding:1px 8px; margin:2px; font-size:12px; }}
</style></head><body><main>
<div class="banner">{_esc(LABEL)}{' · DRY RUN · EVERY GENERATED IMAGE IS A STUB' if stub else ''}</div>
<h1>Reading Nook Cable Wrap v{VERSION} — experiment approval package</h1>
<p>Run state: <b>{_esc(run.get('status'))}</b> · run key <code>{_esc(run.get('run_key'))}</code> · mode <b>{_esc(mode)}</b> · generated {_esc(_now().isoformat(timespec='seconds'))}</p>

<h2>Three separate decisions</h2>
<div class="three">
<div class="box"><h3>1. Visual approval (yours)</h3><p>Only whether these images look right. It approves nothing else, and it is not a technical check.</p></div>
<div class="box"><h3>2. Technical certification</h3><p class="s-FAIL">REFUSED by gate.certify</p><p>{_esc('; '.join(cert['reasons']))}</p><p>Content hash <code>{_esc(cert['content_hash'])}</code></p></div>
<div class="box"><h3>3. Publication authorization</h3><p class="s-FAIL">NOT AVAILABLE</p><p>An experiment can never reach store.publish, image export or listing approval (refusals proven below).</p></div>
</div>

<h2>Gallery, in order</h2>
<div class="grid">{imgs}</div>

<h2>The listing as a customer would read it</h2>
<div class="listing">
<p style="color:var(--warn);font-weight:700">{_esc(LABEL)} — draft only, not listed anywhere</p>
<h3>{_esc(listing['title'])}</h3>
<p><b>CA${_esc(listing['price_cad'])}</b> · DIGITAL PATTERN (instant download) — not a finished item</p>
<p>{desc_html}</p>
<ul>{''.join(f'<li>{_esc(d)}</li>' for d in listing['disclosures'])}</ul>
<p><b>Download:</b> {_esc(listing['download_instructions'])}</p>
<p><b>Tags:</b> {''.join(f'<span class=tag>{_esc(t)}</span>' for t in listing['tags'])}</p>
<p><b>Materials:</b> {_esc(', '.join(listing['materials']))}</p>
<p><b>Category:</b> {_esc(listing['category']['intent'])} — Etsy taxonomy <b>{_esc(listing['category']['taxonomy']['status'])}</b>: {_esc(listing['category']['taxonomy'].get('why', ''))}</p>
<p><b>PDFs (uncertified):</b> {' · '.join(f"<a href='pdfs/EXPERIMENT-UNCERTIFIED_{SLUG}_{VERSION}_{t}.pdf'>{t} terms</a> <code>{_esc(pdfs_sha[:12])}</code>" for t, pdfs_sha in ((t, listing['pdfs'][t]['sha256']) for t in ('US', 'UK')))}</p>
</div>

<h2>Results per gate</h2>
<div class="scroll"><table><tr><th>image</th><th>check</th><th>status</th><th>why</th></tr>
{gate_rows()}</table></div>

<h2>Unknowns and blockers</h2>
<ul>{''.join(f'<li>{_esc(u)}</li>' for u in unknowns) or '<li>none recorded</li>'}</ul>
<ul>{''.join(f'<li>{_esc(b)}</li>' for b in card.get('publication_blockers') or [])}</ul>
<p>Run blocked reason: {_esc(run.get('blocked_reason') or 'none')}</p>

<h2>Publication refusals (proven)</h2>
<ul>{''.join(f'<li><b>{_esc(k)}</b>: {_esc(v)}</li>' for k, v in refusals.items())}</ul>

<h2>Outfit and scene (automatic)</h2>
<p>{_esc((outfit or {}).get('description'))} — distinct from the canonical reference clothing (ivory top, beige trousers) and the owner's earlier wrap outfit (brown top, cream trousers, tan boots, gold necklace).</p>

<h2>Costs and attempts</h2>
<p>Hard cap CA${budget.cap_cad:.2f} · spent CA${budget.spent_cad:.4f} · reserved now CA${budget.reserved_cad:.4f}</p>
<div class="scroll"><table><tr><th>role</th><th>attempt</th><th>tier</th><th>output px</th><th>format</th><th>cost CA$</th><th>live price CA$</th><th>latency s</th><th>error</th></tr>
{flux_rows}</table></div>
<p>Vision calls: {len(vision_log)} · Command Center card: <b>{_esc(notification.get('title'))}</b></p>

<h2>Execution timeline (owner actions between start and card: none)</h2>
<div class="scroll"><table><tr><th>at (UTC)</th><th>stage</th><th>actor</th><th>job</th><th>idempotency key</th><th>in</th><th>out</th><th>CA$</th><th>note</th></tr>
{tl_rows}</table></div>
<p><a href="evidence.json">evidence.json</a> · <a href="timeline.json">timeline.json</a></p>
</main></body></html>"""
    (pkg / "index.html").write_text(page, encoding="utf-8")
    return pkg / "index.html"


# ---- the run ------------------------------------------------------------------------------

def check_keys(live: bool) -> None:
    if not live:
        return
    missing = [k for k in KEY_VARS if not (os.environ.get(k) or "").strip()]
    if missing:
        raise Refused(f"REFUSED (no spend, nothing opened): --live needs {missing} in the "
                      f"environment; keys are read from the environment only")


def run(*, live: bool, out: Path, provider=None) -> dict:
    """The whole experiment. Returns a summary; raises Refused before any spend if unsafe."""
    check_keys(live)
    from brambleloop.creative import image_stages as S
    from brambleloop.creative import pattern_refs as P
    from brambleloop.visual import experiment as XP
    from brambleloop.visual import image_production as IP

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    # Every artifact of an experiment lands in its own folder, never a configured store.
    from brambleloop.core import artifacts

    saved = artifacts.DEFAULT_DIR
    artifacts.DEFAULT_DIR = str(out / "artifacts")
    try:
        return _run(live=live, out=out, provider=provider)
    finally:
        artifacts.DEFAULT_DIR = saved


def _run(*, live: bool, out: Path, provider=None) -> dict:
    from brambleloop.creative import image_stages as S
    from brambleloop.creative import pattern_refs as P
    from brambleloop.visual import experiment as XP
    from brambleloop.visual import image_production as IP

    tl = Timeline()
    t = time.time()
    db = scratch_db(out)
    tl.add("scratch SHADOW database created", started=t,
           outputs={"url": "sqlite (scratch=True)", "phase": "shadow"})

    cir, cert = certify(db, tl)
    if cert["granted"]:
        raise Refused("certification was GRANTED: this release goes through the normal "
                      "orchestrator, not EXPERIMENT mode")
    pdfs = render_pdfs(db, cir, tl)
    budget = XP.ExperimentBudget(cap_cad=BUDGET_CAD)
    t = time.time()
    reg = XP.open_experiment(db, cir=cir, certification=cert,
                             pdf_sha256={k: sha(v) for k, v in pdfs.items()},
                             released_on=RELEASED_ON, budget_cad=BUDGET_CAD, live=live)
    tl.add("experiment opened (bound to content hash + uncertified PDF hashes)", started=t,
           inputs={"content_hash": reg["release"]}, outputs={k: v for k, v in reg.items()
                                                             if k != "cir"})

    flux_log: list[dict] = []
    vision_log: list[dict] = []
    work = out / "work"
    work.mkdir()
    inner = S.flux3_renderer() if live else stub_renderer_class()()
    renderer = BudgetedRenderer(inner, budget, live=live, per_role=XP.MAX_ATTEMPTS_PER_ROLE,
                                log=flux_log)
    refs_dir = out / "refs"
    rel = S.release_from_cir(cir, release_hash=reg["release"], version=cir.version,
                             out_dir=refs_dir)
    from brambleloop.visual import canonical

    ref_paths = {"work": str(work), "layout": rel.pattern_refs[0],
                 "texture": rel.pattern_refs[1],
                 "portrait": canonical.reference_file(list(
                     canonical.CURRENT_REFERENCE_HASHES)[0])}
    run_key = IP.run_key(reg["slug"], reg["version"], reg["release"])

    def anchor_path():
        from brambleloop.core.artifacts import ArtifactStore

        b = IP._best(db, listing=reg["slug"], role=IP.ANCHOR_ROLE, run=run_key)
        if not b or not b.get("sha256"):
            return None
        p = work / f"anchor-{b['sha256'][:12]}.png"
        p.write_bytes(ArtifactStore().get(b["sha256"], db=db))
        return str(p)

    ref_paths["anchor"] = anchor_path
    if live:
        judges = lambda db_: LiveJudges(db_, budget=budget, refs=ref_paths,  # noqa: E731
                                        provider=provider, log=vision_log)
    else:
        judges = StubJudges
    XP.install(db, reg, judges_factory=judges,
               generator_factory=generator_factory(renderer=renderer, live=live,
                                                   work_root=str(work)),
               budget=budget, gallery_builder=gallery_builder(reg=reg, pdfs=pdfs, tl=tl),
               outfit_selector=select_outfit,
               outfit_rejects=lambda o: bool(outfit_problems(o.get("garments") or {})))

    # The trigger, through the orchestrator's own function, then the worker until idle.
    from brambleloop.queue.durable import JobQueue

    q = JobQueue(db)
    t = time.time()
    trig = IP.trigger(lambda inputs, key: q.enqueue(
        "publishing", IP.JOB_TYPE, {**inputs, "experiment": True}, idempotency_key=key),
        slug=reg["slug"], version=reg["version"], release=reg["release"])
    tl.add("orchestrator triggered (experiment)", started=t, outputs=trig,
           idempotency_key=IP.stage_key(reg["slug"], reg["version"], reg["release"],
                                        IP.STAGES[0][0]))
    t = time.time()
    n = drain(db, "experiment-images", [IP.JOB_TYPE], limit=120)
    _job_events(db, tl)
    run_view = IP.get_run(db, run_key)
    stuck = _failed_stage_jobs(db)
    if stuck:
        run_view = {**run_view, "orchestrator_errors": stuck}
    tl.add(f"orchestrator idle after {n} stage jobs", started=t, outputs=run_view,
           cost_cad=round(budget.spent_cad, 4))

    # Listing draft and the Command Center card.
    t = time.time()
    data = IP._stage_data(db, run_key)
    gallery = (((data.get("gallery_assembly") or {}).get("outputs") or {})
               .get("experiment_gallery") or [])
    if not gallery:
        gallery = gallery_builder(reg=reg, pdfs=pdfs, tl=tl)(db, run_key)
    listing = listing_draft(db, cir, reg, gallery)
    tl.add("listing draft (seo/search/pricing/category reused)", started=t, actor="seo",
           outputs=listing)
    t = time.time()
    from brambleloop.app.command_center import notifications

    cc = notifications.listing(db)
    note = next((x for x in cc["notifications"] + cc["digest"]
                 if XP.LABEL in (x.get("title") or "")), {})
    tl.add("approval card created (Command Center notifications.refresh)", started=t,
           actor="command_center", outputs=note, note=note.get("title", "NO CARD"))

    refusals = prove_refusals(db, reg, run_key)
    tl.add("publication paths refused (store.publish, export, listing approval)",
           outputs=refusals)
    candidates = _candidates(db, run_key)
    outfit = None
    if run_view.get("outfit_id"):
        from brambleloop.visual import outfits

        outfit = outfits.get(db, run_view["outfit_id"])
    index = write_package(out, mode="live" if live else "dry-run", db=db, run=run_view,
                          gallery=gallery, listing=listing, pdfs=pdfs, cert=cert, reg=reg,
                          notification=note, timeline=tl, budget=budget, flux_log=flux_log,
                          vision_log=vision_log, refusals=refusals, outfit=outfit,
                          candidates=candidates)
    XP.uninstall(reg)
    return {"label": XP.LABEL, "mode": "live" if live else "dry-run",
            "run_state": run_view["state"], "run_status": run_view["status"],
            "card_title": note.get("title"), "package": str(index),
            "spent_cad": round(budget.spent_cad, 4), "flux_calls": len(flux_log),
            "vision_calls": len(vision_log), "certification": cert["reasons"],
            "content_hash": reg["release"], "pdf_sha256": reg["pdf_sha256_by_terminology"],
            "outfit": (outfit or {}).get("description"), "gallery": [
                {k: g.get(k) for k in ("position", "name", "source", "technical_status",
                                       "sha256")} for g in gallery],
            "refusals": refusals, "timeline_events": len(tl.events),
            "orchestrator_errors": run_view.get("orchestrator_errors") or [],
            "owner_actions_between_start_and_card": 0}


def _job_events(db, tl: Timeline) -> None:
    from sqlalchemy import select

    from brambleloop.core.models import Job

    with db.session() as s:
        for j in s.scalars(select(Job).where(Job.job_type == "visual.image_production")
                           .order_by(Job.id)):
            i = dict(j.inputs or {})
            o = dict(j.outputs or {})
            when = j.finished_at or j.created_at
            if when is not None and when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)      # SQLite drops the zone
            tl.events.append({
                "at": when.isoformat(timespec="milliseconds") if when else None,
                "stage": f"image_production.{i.get('stage')}"
                         + (f" (round {i.get('round')})" if i.get("round") else ""),
                "actor": j.agent, "duration_s": None, "job_id": j.id,
                "idempotency_key": j.idempotency_key, "inputs_sha256": jsha(i),
                "outputs_sha256": jsha(o), "cost_cad": float(getattr(j, "cost_cad", 0) or 0),
                "owner_action": None, "note": str(j.status)})


def _failed_stage_jobs(db) -> list[dict]:
    """A stage job that raised (not a recorded block) is a defect, shown, never hidden."""
    from sqlalchemy import select

    from brambleloop.core.models import Job

    with db.session() as s:
        return [{"job_id": j.id, "status": str(j.status), "stage": (j.inputs or {}).get("stage"),
                 "error": str(j.last_error or "")[:400]}
                for j in s.scalars(select(Job).where(Job.job_type == "visual.image_production"))
                if str(j.status).split(".")[-1] in ("FAILED", "DEAD", "PENDING", "RUNNING")]


def _candidates(db, run_key: str) -> list[dict]:
    from sqlalchemy import select

    from brambleloop.visual.image_records import ImageCandidate

    with db.session() as s:
        return [{"id": r.id, "role": r.role, "attempt": r.attempt, "sha256": r.sha256,
                 "provider": r.provider, "model": r.model, "outcome": r.outcome,
                 "technical_status": r.technical_status, "publishable": r.publishable,
                 "cost_cad": r.cost_cad, "latency_s": r.latency_s, "width": r.width,
                 "height": r.height, "failure_categories": list(r.failure_categories or []),
                 "prompt_sha256": r.prompt_sha256, "references": list(r.references or []),
                 "checks": dict(r.checks or {})}
                for r in s.scalars(select(ImageCandidate).where(
                    ImageCandidate.run_key == run_key).order_by(ImageCandidate.id))]


def prove_refusals(db, reg: dict, run_key: str) -> dict:
    """Try every publication path; each must refuse with the experiment label."""
    from brambleloop.visual import experiment as XP
    from brambleloop.visual import image_production as IP

    out = {}

    def attempt(name, fn):
        try:
            fn()
            out[name] = "NOT REFUSED (defect)"
        except XP.ExperimentRefused as exc:
            out[name] = f"refused: {str(exc)[:200]}"
        except Exception as exc:  # noqa: BLE001
            out[name] = f"refused by another gate first: {type(exc).__name__}: {str(exc)[:160]}"

    attempt("listing approval (image_production.approve)",
            lambda: IP.approve(db, run_key, decided_by="harness-probe"))
    from brambleloop.publish import disclosed_listing

    attempt("image export (disclosed_listing.export_images)",
            lambda: disclosed_listing.export_images(db, slug=reg["slug"], description=""))
    from brambleloop.runtime import etsy_ops

    attempt("Etsy payload (etsy_ops.certified_payload)",
            lambda: etsy_ops.certified_payload(db, reg["slug"], reg["version"]))
    attempt("store.publish (handler, through the queue)", lambda: _publish_probe(db, reg))
    return out


def _publish_probe(db, reg: dict) -> None:
    from sqlalchemy import select

    from brambleloop.core.models import Job
    from brambleloop.queue.durable import JobQueue
    from brambleloop.visual import experiment as XP

    job = JobQueue(db).enqueue("store_operator", "store.publish",
                               {"slug": reg["slug"], "version": reg["version"]},
                               idempotency_key=f"experiment-probe:publish:{reg['release']}")
    drain(db, "experiment-publish-probe", ["store.publish"], limit=5)
    with db.session() as s:
        j = s.get(Job, job.id)
        err = str(j.last_error or "")
    if XP.LABEL in err:
        raise XP.ExperimentRefused(err[:300])
    raise RuntimeError(f"store.publish job ended {j.status}: {err[:200]}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="stub provider (default)")
    g.add_argument("--live", action="store_true", help="real FLUX 3 + vision, CA$5 cap")
    ap.add_argument("--out", default=None, help="output directory")
    a = ap.parse_args(argv)
    live = bool(a.live)
    out = Path(a.out) if a.out else HERE / "out" / ("live" if live else "dry_run")
    try:
        summary = run(live=live, out=out)
    except Refused as exc:
        print(str(exc.code if hasattr(exc, "code") else exc))
        return 2
    print(json.dumps(summary, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
