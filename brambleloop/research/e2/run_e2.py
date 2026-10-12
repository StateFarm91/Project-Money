"""E2 step 3: the pattern-derived structural reference through the E1-proven path.

Reference images sent: the front three-quarter and the flat-lay, both built from structure.json
(the purchased pattern's counts and gauge) -- NEVER a seller photograph. Prompts name the
scene only; they do not name pockets, ribbing, texture direction, open front or length, so
whatever the output preserves of those came from the reference. Three shots: hero, lifestyle,
on-model. Provider: gpt-image-2 via the edits endpoint, the only mode E1 showed to work.
Hard cap US$0.30 list price."""
from __future__ import annotations
import json, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src")); sys.path.insert(0, str(HERE.parent / "e1"))
from brambleloop.gateway import images as G           # noqa: E402
from run_e1 import env_from_files                     # noqa: E402

OUT = HERE / "out" / "gen"; OUT.mkdir(parents=True, exist_ok=True)
REF34, REFFLAT = str(HERE / "out" / "cardigan_front34.png"), str(HERE / "out" / "cardigan_flatlay.png")
CAP = 0.30
KEEP = ("Keep the cardigan exactly as the reference images show it: the same shape, the same proportions, "
        "the same construction and the same placement of every part. Render it as a real hand-crocheted "
        "garment in real yarn with natural fibre texture. No text.")
SHOTS_ALL = [
    ("hero", [REFFLAT, REF34], "Clean product photograph for a handmade marketplace listing: the cardigan laid flat, "
                               "open, on white linen, shot from directly above in soft daylight, nothing else in frame. " + KEEP),
    ("lifestyle", [REF34], "Lifestyle photograph: the cardigan draped open over the back of a light wooden chair in a "
                           "bright, calm room with a window, soft daylight. " + KEEP),
    ("on_model", [REF34], "Full-length photograph of a woman wearing the cardigan open over a plain white t-shirt and "
                          "light blue jeans, standing relaxed facing the camera, arms at her sides, in soft daylight "
                          "against a plain pale wall. " + KEEP),
]
import os
SHOTS = [s for s in SHOTS_ALL if not os.environ.get("E2_ONLY") or s[0] in os.environ["E2_ONLY"].split(",")]

def main():
    env = env_from_files(); price = G.BY_KEY["gpt-image-2"].usd_per_image
    assert price * len(SHOTS) <= CAP
    man = {"references": [REF34, REFFLAT], "provider": "gpt-image-2 (edits)", "runs": [], "spent_usd_list_price": 0.0}
    for name, refs, prompt in SHOTS:
        t0 = time.time(); row = {"shot": name, "references": refs, "prompt": prompt}
        try:
            r = G.generate(prompt, reference_urls=refs, env=env, provider_key="gpt-image-2",
                           work_dir=str(OUT), size="1024x1024", timeout=180.0)
            dst = OUT / f"{name}{Path(r['path']).suffix}"; Path(r["path"]).replace(dst)
            row.update(ok=True, path=str(dst), seconds=round(time.time() - t0, 1)); man["spent_usd_list_price"] += price
        except Exception as exc:  # noqa: BLE001
            row.update(ok=False, error=f"{type(exc).__name__}: {str(exc)[:200]}")
        man["runs"].append(row); print(json.dumps({k: v for k, v in row.items() if k != "prompt"}))
    man["spent_usd_list_price"] = round(man["spent_usd_list_price"], 2)
    (HERE / "out" / "e2_manifest.json").write_text(json.dumps(man, indent=1))
    print(f"spent US${man['spent_usd_list_price']:.2f} list price (cap {CAP})")
if __name__ == "__main__":
    main()
