"""E4 generation: the continuous-yarn certified reference (presentation3) plus its silhouette
mask and normals -> gpt-image-2 edits. The prompt names presentation only: no stitch family,
count, construction or fold; the scene is a plain neutral product-photography surface rather
than the measurement sphere's seamless backdrop, and the ball is described as an ordinary
object so the certified deformation on it stays measurable. Ceiling US$1.00 additional."""
import hashlib, json, os, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))
from brambleloop.gateway import images as G
SCRATCH = Path("/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad")
D = HERE.parent / "d" / "out"
CAP_USD = 1.00; PROVIDER = "gpt-image-2"
PROMPT = (
    "Product photograph for a handmade craft marketplace listing of the crocheted swatch shown in the "
    "first image, resting on a plain wooden ball exactly as it does there. Keep the piece exactly as "
    "shown: the same outline, the same proportions, every strand of yarn where it is, the same colour. "
    "The second image is the outline mask of the piece and the third shows its surface orientation; use "
    "them only to keep the piece's outline, position and surface placement exactly. Photograph it as a "
    "real object made of real yarn: natural fibre texture with a little fuzz, soft window daylight from "
    "one side, on a plain linen tablecloth with its ordinary creases, an ordinary camera. No text, "
    "nothing else in frame.")


def main(kinds=("sc", "hdc"), views=("camera", "oblique"), tag="e4"):
    out = HERE / "out" / "gen"; out.mkdir(parents=True, exist_ok=True)
    env = {G.key_var("openai"): (SCRATCH / ".oaikey").read_text().strip()}
    price = G.BY_KEY[PROVIDER].usd_per_image; planned = price * len(kinds) * len(views)
    assert planned <= CAP_USD
    man = {"provider": PROVIDER, "endpoint": "images/edits (reference-conditioned)", "prompt": PROMPT,
           "package": "rgb(presentation3, continuous yarn) + mask + normal", "usd_list_price_per_image": price, "cap_usd": CAP_USD, "runs": []}
    spent = 0.0
    for kind in kinds:
        rec = json.load(open(D / f"milestone_d_{kind}_final.json"))
        for view in views:
            ref = D / f"{kind}_draped_presentation3_{view}.png"
            refs = [str(ref), str(HERE / "out" / f"{kind}_{view}_mask.png"), str(HERE / "out" / f"{kind}_{view}_normal.png")]
            row = {"kind": kind, "view": view, "reference": str(ref), "geometry_sha256": rec["geometry_sha256"]["draped"],
                   "conditioning_sha256": [hashlib.sha256(open(r, "rb").read()).hexdigest() for r in refs]}
            t0 = time.time()
            try:
                r = G.generate(PROMPT, reference_urls=refs, env=env, provider_key=PROVIDER, work_dir=str(out), size="1024x1024", timeout=240.0)
                src = Path(r["path"]); dst = out / f"{kind}_{view}_{tag}{src.suffix}"; src.replace(dst)
                row.update(ok=True, path=str(dst), output_sha256=hashlib.sha256(dst.read_bytes()).hexdigest(), seconds=round(time.time() - t0, 1), usd_list_price=price)
                spent += price
            except Exception as exc:  # noqa: BLE001
                row.update(ok=False, error=f"{type(exc).__name__}: {str(exc)[:240]}", seconds=round(time.time() - t0, 1))
            man["runs"].append(row); print(json.dumps({k: row[k] for k in row if k not in ("path", "reference", "conditioning_sha256")}))
    man["spent_usd_list_price"] = round(spent, 3)
    (HERE / "out" / f"{tag}_manifest.json").write_text(json.dumps(man, indent=1))
    print(f"spent (list) US${spent:.2f} of cap US${CAP_USD}")


if __name__ == "__main__":
    main(tag=sys.argv[1] if len(sys.argv) > 1 else "e4")
