"""Calibration and qualification evidence for the identity biometric floor (ENG-VIS-IDENTITY).

An embedder becomes Laura's biometric floor only through a qualification record
(`identity_gate.validate_qualification`). This module produces the *evidence* that record cites:

1. Her three canonical references are read and verified by sha256
   (`canonical.CURRENT_REFERENCE_HASHES`). One mismatched byte and calibration refuses
   (`ReferenceMismatch`): nothing is measured against a reference that is not hers.
2. Every labelled sample is embedded and compared with each reference frame; the WORST of the
   three similarities is its score, exactly as `identity_gate.measure_biometric` scores a
   frame at run time.
3. The measured samples are split deterministically into a CALIBRATION subset and a disjoint
   HELD-OUT subset (`assign_split`). Thresholds are derived from the calibration subset only,
   never chosen to pass:
   `match_at` = highest calibration impostor score + `MARGIN_ACCEPT`, rounded up;
   `refuse_below` = lowest calibration genuine score - `MARGIN_REFUSE`, rounded down.
4. False-accept and false-reject rates are measured at `match_at` on the HELD-OUT subset only,
   with exact one-sided 95% upper bounds (Clopper-Pearson). Measuring FAR on the impostors
   that set `match_at` would make it 0 by construction. A small held-out set cannot hide
   behind "0 false accepts" either: 0 of 10 is an upper bound of 26%.
5. `production_ready` is true only when the HELD-OUT sample sizes and bounds meet the
   production floors below. The evidence is content-hashed (`evidence_sha256`), and
   `qualification` re-derives the split, thresholds and rates from the rows
   (`audit_split`) and refuses in-sample evidence (`InSampleEvidence`).

Labelled samples are only ever: her canonical references and owner-viewed images generated on
her face (genuine), and generated non-Laura people (impostors). No real person's photograph is
used. Derived (augmented) genuine samples are reported separately and never counted toward the
sample-size floors, because they are not independent.

Nothing here generates or spends; `research/final_build/w6/identity_calibration/
generate_negatives.py` is the (budget-reserved) way to grow the impostor set.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
from datetime import datetime, timezone

CALIBRATION_VERSION = "identity-calibration/2"   # /2: held-out split (F2)
GENUINE, IMPOSTOR = "laura", "not_laura"

MARGIN_ACCEPT = 0.05
MARGIN_REFUSE = 0.15

# Production floors. 0 false accepts in 300 impostor faces bounds the false-accept rate at
# about 1% (one-sided 95%); fewer impostors cannot support a 1% claim whatever they scored.
MIN_GENUINE_PRODUCTION = 30
MIN_IMPOSTOR_PRODUCTION = 300
MAX_FAR_UPPER_95 = 0.01
MAX_FRR = 0.10


class ReferenceMismatch(ValueError):
    """A canonical reference's bytes are not the recorded sha256: refuse, measure nothing."""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def verified_references(references: dict) -> dict:
    """{frame: bytes} for her three current reference frames, each verified by sha256."""
    from . import canonical

    out = {}
    for frame, want in canonical.CURRENT_REFERENCE_HASHES.items():
        data = (references or {}).get(frame) or b""
        got = hashlib.sha256(data).hexdigest() if data else ""
        if got != want:
            raise ReferenceMismatch(
                f"canonical reference {frame} sha256 {got[:12] or 'missing'} is not the "
                f"recorded {want[:12]}; refused")
        out[frame] = data
    return out


def binomial_upper_95(errors: int, n: int) -> float:
    """Exact one-sided 95% Clopper-Pearson upper bound on a rate of `errors` in `n`."""
    if n <= 0:
        return 1.0
    if errors >= n:
        return 1.0
    if errors == 0:
        return 1.0 - 0.05 ** (1.0 / n)

    def cdf(p):           # P(X <= errors) for Binomial(n, p)
        return sum(math.comb(n, k) * p ** k * (1 - p) ** (n - k) for k in range(errors + 1))

    lo, hi = errors / n, 1.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if cdf(mid) > 0.05:
            lo = mid
        else:
            hi = mid
    return hi


def _ceil2(x: float) -> float:
    return math.ceil(x * 100 - 1e-9) / 100


def _floor2(x: float) -> float:
    return math.floor(x * 100 + 1e-9) / 100


def _faces(embedder, sample: dict) -> list[list[float]]:
    """Embeddings for one sample. `face`: "single" (exactly one person, as at run time) or
    "all" (a contact sheet of distinct impostors: every detected face is one impostor)."""
    data = sample["data"]
    if sample.get("face", "single") == "all":
        img, faces = embedder.faces(data)
        return [embedder.embed_face(embedder.align(img, f["landmarks"])) for f in faces]
    return [embedder.embed(data)]


AUGMENTATIONS = ("crop90", "jpeg60", "dark80", "bright120", "half_res")


def augment(data: bytes) -> dict[str, bytes]:
    """Derived variants of a genuine image (robustness only; never counted as samples)."""
    from PIL import Image, ImageEnhance

    img = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = img.size
    out = {}

    def png(im):
        b = io.BytesIO()
        im.save(b, "PNG")
        return b.getvalue()

    out["crop90"] = png(img.crop((int(w * .05), int(h * .05), int(w * .95), int(h * .95))))
    b = io.BytesIO()
    img.save(b, "JPEG", quality=60)
    out["jpeg60"] = b.getvalue()
    out["dark80"] = png(ImageEnhance.Brightness(img).enhance(0.8))
    out["bright120"] = png(ImageEnhance.Brightness(img).enhance(1.2))
    out["half_res"] = png(img.resize((w // 2, h // 2)))
    return out


def _cos(a, b) -> float:
    from .face_embedder import cosine

    return cosine(a, b)


def calibrate(embedder, samples: list[dict], references: dict, *,
              with_augmentations: bool = True) -> dict:
    """Measure the embedder on labelled samples against her verified references.

    `samples`: [{"id", "label": "laura"|"not_laura", "sha256", "data", "source", "licence",
    "face": "single"|"all"}]. A sample whose bytes do not match its own `sha256` is refused."""
    refs = verified_references(references)
    ref_vecs = {f: embedder.embed(d) for f, d in refs.items()}
    rows, unmeasured = [], []
    for s in samples:
        if s.get("label") not in (GENUINE, IMPOSTOR):
            raise ValueError(f"sample {s.get('id')} has no label")
        if hashlib.sha256(s["data"]).hexdigest() != s.get("sha256"):
            raise ReferenceMismatch(f"sample {s.get('id')} bytes do not match its sha256")
        if s["data"] in refs.values():
            unmeasured.append({"id": s["id"], "why": "is a canonical reference itself"})
            continue
        try:
            vecs = _faces(embedder, s)
        except Exception as exc:  # noqa: BLE001 - a sample that cannot be read is reported
            unmeasured.append({"id": s["id"], "why": f"{type(exc).__name__}: {exc}"[:200]})
            continue
        for i, v in enumerate(vecs):
            per = {f: round(_cos(v, rv), 6) for f, rv in ref_vecs.items()}
            rows.append({"id": s["id"] + (f"#face{i}" if len(vecs) > 1 or
                                          s.get("face") == "all" else ""),
                         "label": s["label"], "sha256": s["sha256"],
                         "source": s.get("source", ""), "licence": s.get("licence", ""),
                         "per_reference": per, "score": min(per.values()), "derived": False})
        if with_augmentations and s["label"] == GENUINE and s.get("face", "single") == "single":
            for name, d in augment(s["data"]).items():
                try:
                    v = embedder.embed(d)
                except Exception as exc:  # noqa: BLE001
                    unmeasured.append({"id": f"{s['id']}~{name}",
                                       "why": f"{type(exc).__name__}: {exc}"[:200]})
                    continue
                per = {f: round(_cos(v, rv), 6) for f, rv in ref_vecs.items()}
                rows.append({"id": f"{s['id']}~{name}", "label": GENUINE, "sha256": s["sha256"],
                             "source": s.get("source", ""), "per_reference": per,
                             "score": min(per.values()), "derived": True})
    return summarise(rows, unmeasured, embedder)


# ---- held-out split (F2) --------------------------------------------------------------------
# Thresholds are fixed on a CALIBRATION subset and the rates are measured only on the disjoint
# HELD-OUT subset. Measuring FAR on the impostors that set `match_at` makes it 0 by
# construction (match_at sits above the highest of them), which proves nothing.
#
# The split is deterministic: units are ordered by sha256(salt:unit:sample_sha256) and the
# first ceil(n * fraction) of each label go to calibration. A unit is one independent sample:
# a genuine image together with its augmentations (they are never split across subsets), or
# one impostor face. Genuine samples need only a small calibration share because they set only
# `refuse_below`; impostors set `match_at`, so a third of them are spent on it.
SPLIT_METHOD = "held-out/1"
SPLIT_SALT = "brambleloop-identity-split-v1"
CALIBRATION_FRACTION = {GENUINE: 1 / 6, IMPOSTOR: 1 / 3}
CALIBRATION, HELD_OUT = "calibration", "held_out"


class InSampleEvidence(ValueError):
    """Evidence whose rates were not measured on a held-out subset: refused for production."""


def _unit(row: dict) -> str:
    return str(row["id"]).split("~", 1)[0]


def _order_key(unit: str, sha: str) -> str:
    return hashlib.sha256(f"{SPLIT_SALT}:{unit}:{sha}".encode()).hexdigest()


def assign_split(rows: list[dict]) -> dict[str, str]:
    """{unit: CALIBRATION | HELD_OUT}, deterministic from the rows' ids and sha256s."""
    out: dict[str, str] = {}
    for label in (GENUINE, IMPOSTOR):
        units = {}
        for r in rows:
            if r["label"] == label and not r.get("derived"):
                units[_unit(r)] = r.get("sha256", "")
        order = sorted(units, key=lambda u: _order_key(u, units[u]))
        n_cal = math.ceil(len(order) * CALIBRATION_FRACTION[label]) if order else 0
        if len(order) >= 2:
            n_cal = min(max(n_cal, 1), len(order) - 1)   # both subsets non-empty
        for i, u in enumerate(order):
            out[u] = CALIBRATION if i < n_cal else HELD_OUT
    return out


def _measure(rows: list[dict]) -> dict:
    """Thresholds from the calibration subset, rates from the held-out subset only."""
    split = assign_split(rows)
    for r in rows:
        r["split"] = split.get(_unit(r), HELD_OUT)

    def pick(label, part, derived=False):
        return [r["score"] for r in rows if r["label"] == label and r["split"] == part
                and bool(r.get("derived")) == derived]

    cal_gen, cal_imp = pick(GENUINE, CALIBRATION), pick(IMPOSTOR, CALIBRATION)
    gen, imp = pick(GENUINE, HELD_OUT), pick(IMPOSTOR, HELD_OUT)
    der = pick(GENUINE, HELD_OUT, derived=True)
    out = {"split": {"method": SPLIT_METHOD, "salt": SPLIT_SALT,
                     "calibration_fraction": dict(CALIBRATION_FRACTION),
                     "calibration_units": sorted(u for u, p in split.items() if p == CALIBRATION),
                     "held_out_units": sorted(u for u, p in split.items() if p == HELD_OUT)},
           "evaluation": HELD_OUT,
           "calibration_genuine": len(cal_gen), "calibration_impostor": len(cal_imp),
           "total_genuine": len(cal_gen) + len(gen), "total_impostor": len(cal_imp) + len(imp),
           # the counts the production floors apply to: held-out only
           "genuine_pairs": len(gen), "impostor_pairs": len(imp),
           "derived_genuine": len(der)}
    if not (cal_gen and cal_imp and gen and imp):
        out["thresholds"] = None
        return out
    match_at = min(_ceil2(max(cal_imp) + MARGIN_ACCEPT), 0.99)
    refuse_below = _floor2(min(min(cal_gen) - MARGIN_REFUSE, match_at - 0.05))
    if refuse_below <= 0:
        refuse_below = 0.01
    out["thresholds"] = {"match_at": match_at, "refuse_below": refuse_below}
    fa = sum(1 for x in imp if x >= match_at)
    fr = sum(1 for x in gen if x < match_at)
    out.update({
        "far": round(fa / len(imp), 6), "false_accepts": fa,
        "far_upper_95": round(binomial_upper_95(fa, len(imp)), 6),
        "frr": round(fr / len(gen), 6), "false_rejects": fr,
        "frr_upper_95": round(binomial_upper_95(fr, len(gen)), 6),
        "derived_frr": round(sum(1 for x in der if x < match_at) / len(der), 6) if der else None,
        "genuine_min": round(min(gen), 6), "genuine_median": round(sorted(gen)[len(gen) // 2], 6),
        "impostor_max": round(max(imp), 6),
        "impostor_median": round(sorted(imp)[len(imp) // 2], 6),
        "separation": round(min(gen) - max(imp), 6),
        "calibration_impostor_max": round(max(cal_imp), 6),
        "calibration_genuine_min": round(min(cal_gen), 6)})
    return out


def summarise(rows: list[dict], unmeasured: list[dict], embedder) -> dict:
    """Thresholds (calibration subset), rates and sufficiency (held-out subset). Deterministic."""
    from . import canonical

    m = _measure(rows)
    thresholds = m.pop("thresholds")
    reasons = []
    out = {"version": CALIBRATION_VERSION, "measured_at": _now(),
           "embedder": getattr(embedder, "name", ""),
           "embedder_version": getattr(embedder, "version", ""),
           "weights_sha256": getattr(embedder, "weights_sha256", ""),
           "identity_id": canonical.IDENTITY_ID,
           "canonical_references": dict(canonical.CURRENT_REFERENCE_HASHES),
           "reference_frames": sorted(canonical.CURRENT_REFERENCE_HASHES),
           "score_rule": "worst (minimum) cosine similarity over the three reference frames",
           "margins": {"accept": MARGIN_ACCEPT, "refuse": MARGIN_REFUSE},
           "rows": rows, "unmeasured": unmeasured, **m}
    if not thresholds:
        reasons.append("calibration needs at least one genuine and one impostor sample in "
                       "each of the calibration and held-out subsets")
    else:
        out.update(thresholds)
        gen, imp = out["genuine_pairs"], out["impostor_pairs"]
        if gen < MIN_GENUINE_PRODUCTION:
            reasons.append(f"{gen} held-out genuine samples; production needs "
                           f">= {MIN_GENUINE_PRODUCTION}")
        if imp < MIN_IMPOSTOR_PRODUCTION:
            reasons.append(f"{imp} held-out impostor faces; production needs >= "
                           f"{MIN_IMPOSTOR_PRODUCTION} ({out['false_accepts']} false accepts "
                           f"in {imp} bounds FAR only at {out['far_upper_95']:.1%})")
        if out["far_upper_95"] > MAX_FAR_UPPER_95:
            reasons.append(f"held-out FAR upper bound {out['far_upper_95']:.2%} > "
                           f"{MAX_FAR_UPPER_95:.0%}")
        if out["frr"] > MAX_FRR:
            reasons.append(f"held-out FRR {out['frr']:.1%} > {MAX_FRR:.0%}")
    out["production_ready"] = not reasons
    out["not_ready_reasons"] = reasons
    out["evidence_sha256"] = evidence_sha256(out)
    return out


_AUDITED = ("match_at", "refuse_below", "far", "frr", "far_upper_95", "genuine_pairs",
            "impostor_pairs", "calibration_genuine", "calibration_impostor", "split")


def audit_split(ev: dict) -> list[str]:
    """Why this evidence is not a held-out measurement ([] when it is). The split, the
    thresholds and the rates are recomputed from the rows: evidence that set its thresholds on
    the same samples it measured (in-sample), or claims a split its rows do not reproduce, is
    refused whatever it declares."""
    ev = ev or {}
    out = []
    if ev.get("version") != CALIBRATION_VERSION:
        out.append(f"evidence version {ev.get('version')!r} is not {CALIBRATION_VERSION}: "
                   f"rates were not measured on a held-out subset")
        return out
    if ev.get("evaluation") != HELD_OUT:
        out.append("evidence does not declare a held-out evaluation")
    rows = [{k: v for k, v in r.items() if k != "split"} for r in ev.get("rows") or ()]
    if not rows:
        return out + ["evidence carries no measured rows to audit"]
    declared = {_unit(r): r.get("split") for r in ev.get("rows") or ()}
    again = _measure(rows)
    th = again.pop("thresholds") or {}
    again.update(th)
    for k in _AUDITED:
        if again.get(k) != ev.get(k):
            out.append(f"{k} does not reproduce from the rows under {SPLIT_METHOD} "
                       f"(declared {ev.get(k)!r}, recomputed {again.get(k)!r})")
    redo = {_unit(r): r["split"] for r in rows}
    if declared != redo:
        out.append("rows' declared split is not the deterministic held-out split")
    sp = ev.get("split") or {}
    if set(sp.get("calibration_units") or ()) & set(sp.get("held_out_units") or ()):
        out.append("a sample is in both the calibration and the held-out subset")
    return out


def evidence_sha256(ev: dict) -> str:
    body = {k: v for k, v in (ev or {}).items() if k not in ("evidence_sha256", "measured_at")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


def verify_evidence(ev: dict) -> bool:
    return bool(ev) and ev.get("evidence_sha256") == evidence_sha256(ev)


def calibration_block(ev: dict) -> dict:
    """The `calibration` field of a qualification record, from verified evidence."""
    if not verify_evidence(ev):
        raise ValueError("calibration evidence does not match its evidence_sha256")
    keys = ("match_at", "refuse_below", "evidence_sha256", "genuine_pairs", "impostor_pairs",
            "far", "far_upper_95", "frr", "production_ready", "evaluation",
            "calibration_genuine", "calibration_impostor")
    blk = {k: ev.get(k) for k in keys}
    blk["canonical_references"] = sorted(ev["canonical_references"].values())
    blk["reference_frames"] = list(ev["reference_frames"])
    blk["calibration_version"] = ev["version"]
    blk["split_method"] = (ev.get("split") or {}).get("method")
    return blk


def qualification(ev: dict, *, owner_decision: dict) -> dict:
    """A production qualification record built from evidence. Building one admits nothing:
    `identity_gate.validate_qualification` decides, and production also needs the record on
    `identity_gate.PRODUCTION_QUALIFICATIONS`."""
    from . import identity_gate

    if not verify_evidence(ev):
        raise ValueError("calibration evidence does not match its evidence_sha256")
    in_sample = audit_split(ev)
    if in_sample:
        raise InSampleEvidence("refused: " + "; ".join(in_sample))
    return identity_gate.qualification_record(
        embedder=ev["embedder"], embedder_version=ev["embedder_version"],
        weights_sha256=ev["weights_sha256"], calibration=calibration_block(ev),
        owner_decision=owner_decision, fixture_only=False)


# ---- the committed calibration set ---------------------------------------------------------

def load_set(manifest_path, repo_root) -> list[dict]:
    """Samples from a committed manifest: [{"id", "path", "label", "sha256", "source",
    "licence", "face"}]. Bytes are read from the repo and verified by sha256 in `calibrate`."""
    from pathlib import Path

    root = Path(repo_root)
    items = json.loads(Path(manifest_path).read_text())["samples"]
    out = []
    for it in items:
        data = (root / it["path"]).read_bytes()
        out.append({**it, "data": data})
    return out
