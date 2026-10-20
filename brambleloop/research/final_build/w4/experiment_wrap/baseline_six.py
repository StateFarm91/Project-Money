"""The owner's six-reference single-shot method, reproduced (W-VISNEXT; owner directive).

    EXPERIMENT — UNCERTIFIED — NOT FOR PUBLICATION

STAGE 1 GENERATE. One FLUX 3 request with six references, in this order:

1. to 3. Laura's canonical neutral portrait, torso and full length (a42aeac7, afe6191f,
   f32bac68), validated by bytes and always first;
4. to 6. complete layout, stitch structure and construction rules, as one of:
   - `owner`: the owner's exact committed files (3f737a08, 10d013b8, 3638b3a5), each checked
     against RECORD.json;
   - `auto`: the `pattern_refs` equivalents rendered from the same CIR (layout, texture,
     rules).

The request also carries the auto-built prompt (`creative.flux_prompt`). The candidate is
saved with the ordered reference sha256 values, the prompt text, the provider receipt and the
actual cost. Product certification is not a precondition for saving it: the experiment labels
it UNCERTIFIED/EXPERIMENT, and it can never publish.

STAGE 2 VERIFY AND CORRECT.

1. Run the fidelity verifier's lifestyle path. With no flat lay in this method, the anchor
   reads UNKNOWN, and that is reported, never passed.
2. Run the blind vision checks (`visual.vision_judges`), reserved against the experiment
   budget.
3. Classify the result with the shared failure codes. A FAIL whose codes all have a routed
   prompt-negative repair is retried, carrying those negatives: at most `MAX_RETRIES` retries
   in the whole baseline, inside the CA$5 budget.
4. UNKNOWN and unrouted FAIL results stay as they are. Nothing publishes.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OWNER_DIR = HERE.parent / "flux_experiments" / "2026-10-19_reading_nook_cable_wrap"
OWNER_FILES = (("product_layout", "ref4_complete_wrap_layout.png"),
               ("product_texture", "ref5_cable_stitch_structure.png"),
               ("product_rules", "ref6_construction_rules.png"))
SOURCES = ("owner", "auto")
MAX_RETRIES = 2


class BaselineRefused(RuntimeError):
    pass


def _sha_file(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def owner_references() -> list[str]:
    """The owner's three product files, verified against the experiment record by sha256."""
    rec = json.loads((OWNER_DIR / "RECORD.json").read_text())
    want = {r["file"]: r["sha256"] for r in rec["references"] if r["n"] >= 4}
    out = []
    for _, name in OWNER_FILES:
        p = OWNER_DIR / name
        if not p.is_file() or _sha_file(p) != want.get(name):
            raise BaselineRefused(f"{name}: not the owner's recorded bytes; refused rather than "
                                  f"substituting")
        out.append(str(p))
    return out


def auto_references(rel) -> list[str]:
    """layout, texture (stitch structure), rules from `pattern_refs` for the same content."""
    from brambleloop.creative import pattern_refs as P

    by = dict(zip(P.ROLES, rel.pattern_refs))
    return [by["layout"], by["texture"], by["rules"]]


class Capture:
    """Pass-through renderer that keeps the exact prompt text sent with each call."""

    def __init__(self, inner):
        self.inner = inner
        self.reference_limit = getattr(inner, "reference_limit", 10)
        self.provider_key = getattr(inner, "provider_key", "flux-3-image")
        self.prompts: list[str] = []

    def __call__(self, prompt, **kw):
        self.prompts.append(prompt)
        return self.inner(prompt, **kw)


def default_verifier(*, db, cir, release_hash: str, judge, refs: dict):
    """Fidelity (lifestyle path) plus the blind vision adapters, all compared in code."""
    from brambleloop.visual import fidelity as F
    from brambleloop.visual import vision_judges as VJ

    def verify(data: bytes, cand: dict, outfit: dict) -> dict:
        region = None
        if judge is not None:
            region = VJ.locate_product(judge, data).get("patches") or None
        fid = F.verify_lifestyle(data, cir, release_hash=release_hash, anchor=None,
                                 product_region=region, judge=judge,
                                 consistency=VJ.blind_consistency)
        ad = VJ.Adapters(db, judge, references=refs)
        c = {**cand, "data": data}
        checks = {"fidelity": {"status": fid["status"], "codes": fid["codes"],
                               "failed": fid["failed"], "unknown": fid["unknown"]},
                  "identity": ad.identity(c), "body_proportions": ad.body_proportions(c),
                  "outfit_consistency": ad.outfit_consistency(c, outfit),
                  "anatomy": ad.anatomy(c), "realism": ad.realism(c)}
        return checks
    return verify


def classify(checks: dict) -> dict:
    """Status, failure codes and the routed repair for one verified candidate."""
    from brambleloop.visual import repair_routes as RR

    st = [c.get("status", "UNKNOWN") for c in checks.values()]
    status = "FAIL" if "FAIL" in st else "UNKNOWN" if "UNKNOWN" in st else "PASS"
    failed_codes = sorted({str(x) for c in checks.values() if c.get("status") == "FAIL"
                           for x in (c.get("codes") or [])})
    all_codes = sorted({str(x) for c in checks.values() if c.get("status") != "PASS"
                        for x in (c.get("codes") or [])})
    routed = RR.route(failed_codes)
    negatives = [n for d in routed["directives"] if d.get("kind") == RR.PROMPT_NEGATIVE
                 or d.get("negatives") for n in d.get("negatives") or []]
    retryable = (status == "FAIL" and bool(failed_codes) and not routed["unrouted"]
                 and bool(negatives))
    return {"status": status, "codes": all_codes, "failed_codes": failed_codes,
            "unrouted": routed["unrouted"], "negatives": negatives, "retryable": retryable,
            "failed": sorted(k for k, c in checks.items() if c.get("status") == "FAIL"),
            "unknown": sorted(k for k, c in checks.items() if c.get("status") == "UNKNOWN")}


def run_baseline(*, db, cir, reg: dict, rel, renderer, budget, outfit: dict, out: Path,
                 sources=SOURCES, verifier=None, label: str, flux_log: list) -> dict:
    """Stage 1 and stage 2 for each source in order. Returns the report."""
    from brambleloop.creative import image_stages as S
    from brambleloop.visual import experiment as XP
    from brambleloop.visual import vision_judges as VJ

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    cap = Capture(renderer)
    refs_bytes = VJ.canonical_reference_bytes()
    retries_left = MAX_RETRIES
    images = []
    spec = {"id": outfit.get("outfit_id"), "description": outfit.get("description"),
            "garments": outfit.get("garments")}
    for n, source in enumerate(sources, 1):
        if source not in SOURCES:
            raise BaselineRefused(f"unknown reference source {source!r}: {SOURCES}")
        product = owner_references() if source == "owner" else auto_references(rel)
        negatives: list[str] = []
        attempt = 0
        while True:
            attempt += 1
            renderer.current_role = f"six_ref_{source}_a{attempt}"
            t = time.time()
            entry = {"n": n, "source": source, "attempt": attempt, "label": label,
                     "extra_negatives": list(negatives)}
            try:
                cand = S.six_reference_lifestyle(
                    rel, product, None, spec, scene={"environment": outfit.get("setting") or
                                                     "a reading nook by a window",
                                                     "pose": "Laura wearing the wrap",
                                                     "framing": ""},
                    renderer=cap, work_dir=str(out / f"{n}-{source}" / f"a{attempt}"),
                    db=db, extra_negatives=negatives, size=renderer_size(renderer))
            except Exception as exc:  # noqa: BLE001 - recorded, never retried blindly
                entry.update(error=f"{type(exc).__name__}: {str(exc)[:300]}",
                             latency_s=round(time.time() - t, 2))
                images.append(entry)
                break
            finally:
                renderer.current_role = None
            data = Path(cand.path).read_bytes()
            r = cand.receipt
            folder = out / f"{n}-{source}"
            img_name = f"candidate-{n}-{source}-a{attempt}.png"
            (folder / img_name).write_bytes(data)
            (folder / f"prompt-a{attempt}.txt").write_text(cap.prompts[-1])
            entry.update(
                image=str((folder / img_name).relative_to(out)),
                sha256=hashlib.sha256(data).hexdigest(),
                transmitted_references=[{"position": x["position"], "role": x["role"],
                                         "sha256": x["sha256"]} for x in r["references"]],
                conditioning_proven=(r.get("request") or {}).get("conditioning_proven"),
                prompt_sha256=hashlib.sha256(cap.prompts[-1].encode()).hexdigest(),
                prompt_file=str((folder / f"prompt-a{attempt}.txt").relative_to(out)),
                provider_receipt={k: r.get(k) for k in ("provider", "model", "task_id",
                                                        "seed", "request", "price",
                                                        "output_px", "output_format",
                                                        "size")},
                cost_cad=r.get("cost_cad"), latency_s=round(time.time() - t, 2),
                publishable=False, certification="UNCERTIFIED")
            verify = verifier or (lambda d, c, o: {"verification": {
                "status": "UNKNOWN", "why": "no verifier configured"}})
            checks = verify(data, {"sha256": entry["sha256"], "slug": reg["slug"],
                                   "version": reg["version"], "laura_present": True,
                                   "outfit_id": outfit.get("outfit_id"),
                                   "listing": reg["slug"], "identity_evidence": r,
                                   "references": [{"sha256": x["sha256"],
                                                   "kind": ("laura_canonical"
                                                            if x["role"].startswith("laura_")
                                                            else "pattern_derived")}
                                                  for x in r["references"]]}, outfit)
            verdict = classify(checks)
            entry.update(verification={k: {kk: v.get(kk) for kk in ("status", "why", "codes",
                                                                     "failed", "unknown")}
                                       for k, v in checks.items()}, result=verdict)
            (folder / f"record-a{attempt}.json").write_text(json.dumps(entry, indent=1,
                                                                      default=str))
            images.append(entry)
            if verdict["retryable"] and retries_left > 0:
                retries_left -= 1
                negatives = sorted(set(negatives) | set(verdict["negatives"]))
                continue
            break
    report = {"label": label, "method": "six-reference single shot (owner's manual method)",
              "experiment": True, "publishable": False,
              "content_hash": reg["release"], "outfit": outfit.get("description"),
              "sources_in_order": list(sources), "max_retries": MAX_RETRIES,
              "retries_used": MAX_RETRIES - retries_left, "images": images,
              "spent_cad": round(budget.spent_cad, 4), "budget_cap_cad": budget.cap_cad,
              "flux_calls": len([f for f in flux_log if f.get("role", "").startswith(
                  "six_ref")]),
              "never_publishes": XP.LABEL}
    (out / "baseline_report.json").write_text(json.dumps(report, indent=1, default=str))
    (out / "baseline_report.html").write_text(_html(report))
    return report


def renderer_size(renderer) -> str:
    return getattr(renderer, "size", None) or "2048x2048"


def _esc(s) -> str:
    import html

    return html.escape(str(s if s is not None else ""))


def _html(rep: dict) -> str:
    rows = []
    for im in rep["images"]:
        refs = "".join(f"<li>{x['position']}. {_esc(x['role'])} <code>{_esc(x['sha256'])}"
                       f"</code></li>" for x in im.get("transmitted_references") or [])
        res = im.get("result") or {}
        rows.append(
            f"<section><h2>{im['n']}. {_esc(im['source'])} references, attempt "
            f"{im['attempt']}</h2>"
            + (f"<p><b>Error:</b> {_esc(im['error'])}</p>" if im.get("error") else
               f"<img src='{_esc(im['image'])}' alt='{_esc(rep['label'])} candidate' "
               f"style='max-width:480px;width:100%'>"
               f"<p>sha256 <code>{_esc(im['sha256'])}</code> · cost CA$"
               f"{_esc(im.get('cost_cad'))} · prompt sha256 <code>"
               f"{_esc(im.get('prompt_sha256'))}</code></p>"
               f"<h3>Transmitted references, in order</h3><ol style='list-style:none'>{refs}</ol>"
               f"<h3>Provider receipt</h3><pre>{_esc(json.dumps(im.get('provider_receipt'), indent=1, default=str))}</pre>"
               f"<h3>Verification: {_esc(res.get('status'))}</h3>"
               f"<p>failed {_esc(res.get('failed'))} · unknown {_esc(res.get('unknown'))} · "
               f"codes {_esc(res.get('codes'))}</p>")
            + "</section>")
    return ("<!doctype html><meta charset='utf-8'><title>Six-reference baseline</title>"
            f"<h1>{_esc(rep['label'])}</h1><p>{_esc(rep['method'])}. Spent CA$"
            f"{_esc(rep['spent_cad'])} of CA${_esc(rep['budget_cap_cad'])}; retries "
            f"{_esc(rep['retries_used'])}/{_esc(rep['max_retries'])}. Nothing publishes.</p>"
            + "".join(rows))
