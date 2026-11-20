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
# Round 2 (tag e4r2). Round 1 localised the sc-oblique and hdc failures to the generator's
# presentation authority: it copied the reference's synthetic striped yarn and its fibre caps
# almost literally instead of re-photographing the object in real yarn (judge: "plasticky,
# uniformly striped, no visible fibers"; hdc: "bead-like clumps"). This prompt changes only the
# material and photographic description. It still names no stitch family, count, construction
# or fold, and the conditioning package is byte-identical to round 1.
PROMPT_R2 = (
    "The first image is a computer rendering of a crocheted swatch resting on a plain wooden ball. "
    "Make a real product photograph of that same physical object for a handmade craft marketplace "
    "listing. Keep the piece exactly as shown: the same outline, the same proportions, every strand "
    "of yarn where it is, the same colour. The second image is the outline mask of the piece and "
    "the third shows its surface orientation; use them only to keep the piece's outline, position "
    "and surface placement exactly. Replace the rendered material with real spun wool yarn: a matte "
    "surface with a fine fibre halo, a slightly uneven twist, no plastic sheen, no stripes, no beads "
    "or knobs anywhere along the strands. Soft "
    "window daylight from one side, a plain linen tablecloth with its ordinary creases, an ordinary "
    "camera with a little grain. No text, nothing else in frame.")
# Round 3 (tag e4r3): the round-2 prompt unchanged, plus the edits endpoint's own
# `input_fidelity=high`, which asks the model to keep the uploaded reference's detail. Round 2
# localised the remaining failures to generator structural drift (aspect drift 0.18-0.24 on
# the oblique views against a 0.10 bar; hdc camera structure NCC 0.21 against 0.30) and to
# generator variance on realism (the sc camera view kept the rendered look on one draw and
# not the other). The package and geometry are byte-identical to rounds 1 and 2.
# Round 3 was refused before any spend: gpt-image-2 answered 400 "does not support the
# 'input_fidelity' parameter" on all four requests (research/e4/out/e4r3_manifest.json).
# Yield round (tag e4y): the round-2 prompt, unchanged, drawn several times on the sc views
# to measure the gated pipeline's per-attempt yield rather than tune anything further.
PROMPTS = {"e4": PROMPT, "e4r2": PROMPT_R2, "e4r3": PROMPT_R2, "e4y": PROMPT_R2}
EXTRA = {"e4r3": {"input_fidelity": "high"}}
DRAWS = {"e4y": [("sc", "oblique")] * 4 + [("sc", "camera")] * 2}


def main(kinds=("sc", "hdc"), views=("camera", "oblique"), tag="e4"):
    prompt = PROMPTS[tag]
    out = HERE / "out" / "gen"; out.mkdir(parents=True, exist_ok=True)
    env = {G.key_var("openai"): (SCRATCH / ".oaikey").read_text().strip()}
    plan = DRAWS.get(tag) or [(k, v) for k in kinds for v in views]
    price = G.BY_KEY[PROVIDER].usd_per_image; planned = price * len(plan) * (2 if EXTRA.get(tag) else 1)
    assert planned <= CAP_USD
    man = {"provider": PROVIDER, "endpoint": "images/edits (reference-conditioned)", "prompt": prompt, "round_tag": tag, "extra_fields": EXTRA.get(tag, {}),
           "price_note": "list price per image from the gateway's table; input_fidelity=high bills the uploaded reference's input tokens on top, a cost not on file here, so the ceiling is checked at twice the list price for that round",
           "package": "rgb(presentation3, continuous yarn) + mask + normal", "usd_list_price_per_image": price, "cap_usd": CAP_USD, "runs": []}
    spent = 0.0
    seen = {}
    for kind, view in plan:
            rec = json.load(open(D / f"milestone_d_{kind}_final.json"))
            draw = seen[(kind, view)] = seen.get((kind, view), 0) + 1
            suffix = f"_{draw}" if len([1 for kv in plan if kv == (kind, view)]) > 1 else ""
            ref = D / f"{kind}_draped_presentation3_{view}.png"
            refs = [str(ref), str(HERE / "out" / f"{kind}_{view}_mask.png"), str(HERE / "out" / f"{kind}_{view}_normal.png")]
            row = {"kind": kind, "view": view, "draw": draw, "reference": str(ref), "geometry_sha256": rec["geometry_sha256"]["draped"],
                   "conditioning_sha256": [hashlib.sha256(open(r, "rb").read()).hexdigest() for r in refs]}
            t0 = time.time()
            try:
                r = G.generate(prompt, reference_urls=refs, env=env, provider_key=PROVIDER, work_dir=str(out), size="1024x1024", timeout=240.0, extra_fields=EXTRA.get(tag))
                src = Path(r["path"]); dst = out / f"{kind}_{view}_{tag}{suffix}{src.suffix}"; src.replace(dst)
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
