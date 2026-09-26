"""E3: certified structure in -> photoreal presentation out -> same product proven?

Generation only. The reference is the judged presentation render of the FROZEN assessed
geometry from commit 4a08871 (hash recorded here before the call); the provider is the one E1
showed to preserve structure (gpt-image-2 through the edits endpoint, the repository's own
`gateway.images.generate`). The prompt names NO structural fact the reference is supposed to
prove the model can preserve: no stitch family, no counts, no construction. Hard ceiling
US$1.00 at list price; the provider's bill is the authority.
"""
import hashlib, json, os, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))
from brambleloop.gateway import images as G

SCRATCH = Path("/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad")
D = HERE.parent / "d" / "out"
CAP_USD = 1.00
PROVIDER = "gpt-image-2"
PROMPT = (
    "Product photograph for a handmade craft marketplace listing of the crocheted swatch shown "
    "in the reference image, resting exactly as it does there on the same pale ball on the same "
    "surface. Keep the piece exactly as shown: the same outline, the same proportions, the same "
    "stitches in the same places, the same colour. Photograph it as a real object made of real "
    "yarn: natural fibre texture with a little fuzz, soft window daylight from one side, a plain "
    "neutral tabletop, an ordinary camera. No text, nothing else in frame.")


def main(kinds=("hdc", "sc"), views=("camera", "oblique"), per_view=1):
    out = HERE / "out" / "gen"; out.mkdir(parents=True, exist_ok=True)
    env = {G.key_var("openai"): (SCRATCH / ".oaikey").read_text().strip()}
    price = G.BY_KEY[PROVIDER].usd_per_image
    planned = price * len(kinds) * len(views) * per_view
    assert planned <= CAP_USD, planned
    man = {"provider": PROVIDER, "endpoint": "images/edits (reference-conditioned)", "prompt": PROMPT,
           "usd_list_price_per_image": price, "planned_usd": planned, "cap_usd": CAP_USD, "runs": []}
    spent = 0.0
    for kind in kinds:
        rec = json.load(open(D / f"milestone_d_{kind}_final.json"))
        for view in views:
            ref = D / f"{kind}_draped_presentation2_{view}.png"
            ref_sha = hashlib.sha256(ref.read_bytes()).hexdigest()
            for i in range(per_view):
                if spent + price > CAP_USD:
                    man["stopped"] = "ceiling"; break
                row = {"kind": kind, "view": view, "index": i, "reference": str(ref), "reference_sha256": ref_sha,
                       "geometry_sha256": rec["geometry_sha256"]["draped"]}
                t0 = time.time()
                try:
                    r = G.generate(PROMPT, reference_urls=[str(ref)], env=env, provider_key=PROVIDER,
                                   work_dir=str(out), size="1024x1024", timeout=240.0)
                    src = Path(r["path"]); dst = out / f"{kind}_{view}_{i}{src.suffix}"; src.replace(dst)
                    row.update(ok=True, path=str(dst), output_sha256=hashlib.sha256(dst.read_bytes()).hexdigest(),
                               seconds=round(time.time() - t0, 1), usd_list_price=price)
                    spent += price
                except Exception as exc:  # noqa: BLE001 -- recorded, not hidden
                    row.update(ok=False, error=f"{type(exc).__name__}: {str(exc)[:240]}", seconds=round(time.time() - t0, 1))
                man["runs"].append(row)
                print(json.dumps({k: row[k] for k in row if k not in ("path", "reference")}))
    man["spent_usd_list_price"] = round(spent, 3)
    (HERE / "out" / "e3_manifest.json").write_text(json.dumps(man, indent=1))
    print(f"spent (list) US${spent:.2f} of cap US${CAP_USD}")


if __name__ == "__main__":
    main()
