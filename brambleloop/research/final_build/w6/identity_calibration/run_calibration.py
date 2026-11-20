"""Run the identity calibration on the committed set and write the evidence file.

    PYTHONPATH=src python3 research/final_build/w6/identity_calibration/run_calibration.py MODEL_DIR
"""
import json, sys, time
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[3]          # brambleloop/


def main(model_dir):
    from brambleloop.visual import face_embedder as FE, identity_calibration as C
    from brambleloop.visual.vision_judges import canonical_reference_bytes

    t0 = time.time()
    emb = FE.SFaceEmbedder.load(model_dir)
    load_s = round(time.time() - t0, 3)
    samples = C.load_set(HERE / "calibration_set.json", ROOT)
    t1 = time.time()
    ev = C.calibrate(emb, samples, canonical_reference_bytes())
    n = sum(1 for _ in ev["rows"]) + 3
    ev_perf = {"model_load_seconds": load_s,
               "seconds_per_embedding": round((time.time() - t1) / max(n, 1), 4)}
    # unlabelled probe: the owner's manual FLUX 3 attempts at Laura (never labels)
    probe = []
    refs = {f: emb.embed(d) for f, d in canonical_reference_bytes().items()}
    for p in sorted((ROOT / "research/final_build/w4/flux_experiments/2026-10-19_owner_manual_batch2").glob("*-image.*")) + \
             [ROOT / "research/final_build/w4/flux_experiments/2026-10-19_reading_nook_cable_wrap/output_image.png"]:
        try:
            v = emb.embed(p.read_bytes())
            per = {f: round(FE.cosine(v, r), 4) for f, r in refs.items()}
            probe.append({"file": str(p.relative_to(ROOT)), "per_reference": per, "score": min(per.values())})
        except Exception as exc:
            probe.append({"file": str(p.relative_to(ROOT)), "unmeasured": f"{type(exc).__name__}: {exc}"})
    out = {"evidence": ev, "performance": ev_perf, "unlabelled_probe": probe,
           "unlabelled_probe_note": ("owner's manual FLUX 3 attempts at Laura; scored against the "
                                     "calibrated thresholds for information only, never as labels")}
    (HERE / "calibration_evidence.json").write_text(json.dumps(out, indent=1, sort_keys=True))
    keys = ("total_genuine", "total_impostor", "calibration_genuine", "calibration_impostor",
            "genuine_pairs", "impostor_pairs", "derived_genuine", "match_at", "refuse_below", "far",
            "far_upper_95", "frr", "derived_frr", "genuine_min", "impostor_max", "separation",
            "production_ready", "not_ready_reasons", "evidence_sha256")
    print(json.dumps({k: ev.get(k) for k in keys} | ev_perf, indent=1))
    for r in probe:
        print(r)


if __name__ == "__main__":
    main(sys.argv[1])
