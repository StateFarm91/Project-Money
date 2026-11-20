"""Generate licence-safe NON-LAURA calibration negatives with FLUX 3 (ENG-VIS-IDENTITY).

No reference image is sent: these are text-only generations of women who are not Laura,
including deliberate look-alikes (the impostor class that matters). Hard cap: US$0.30 total at
the published FLUX 3 1k price (US$0.048/image), authorised under D-OWNER-STANDING-INTERNAL
(routine image generation inside the CA$100/month model ceiling), through the gateway's
reservation path. NOT RUN in the build session: this session's BFL key was not available.
Production needs >= 300 HELD-OUT impostor faces, and 1/3 of impostors are spent on calibration
(`identity_calibration.CALIBRATION_FRACTION`), so >= 450 in total: run with n_grids ~ 50 and
CAP_USD 2.40 (US$0.048 each), then add the files to calibration_set.json with face "all".
"""
import json, time
from pathlib import Path

OUT = Path(__file__).parent / "negatives"
CAP_USD, PRICE = 0.30, 0.048
LOOK = ("woman in her early thirties, honey light-brown hair in a loose messy bun with face-"
        "framing strands, sun-kissed skin, warm natural smile, minimal makeup")
PROMPTS = {
    "lookalike_grid_a": f"A 3x3 grid of nine separate passport-style head-and-shoulders photographs of nine DIFFERENT real women, each a {LOOK}, plain grey studio backdrop, each a distinct individual with different facial structure, photorealistic, sharp focus, even soft lighting",
    "lookalike_grid_b": f"Contact sheet: nine studio portrait photographs in a 3x3 grid, nine different unrelated women who share a similar style: {LOOK}. Each face clearly visible, looking at camera, natural photographic realism",
    "lookalike_grid_c": f"A 3x3 grid of nine candid lifestyle close-up portraits of nine different women, each a {LOOK}, cozy home interiors, each person unique, photorealistic photography",
    "diverse_grid": "A 3x3 grid of nine passport-style head-and-shoulders photographs of nine different adult women of varied ages (25 to 60) and ethnicities, plain light backdrop, looking at camera, photorealistic, even lighting",
    "lookalike_single_a": f"Photograph of a {LOOK}, standing in a bright living room wearing a cream knit sweater, looking at the camera, head and torso visible, photorealistic",
    "lookalike_single_b": f"Head-and-shoulders studio portrait photograph of a {LOOK}, neutral grey backdrop, looking at the camera, photorealistic",
}

def main(db_url: str, n_grids: int = 6):
    """Through the gateway only: `gateway.images.generate` reserves each render against the
    CA$100/month ceiling, needs the owner's `generation` activation of flux-3-image, and
    writes the one ledger row. Run where those exist (the Railway worker); the hard cap above
    is checked again here. Idempotent per prompt name (an existing file is not re-made)."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "src"))
    from brambleloop.core.db import Database
    from brambleloop.gateway import images as G

    db = Database(db_url)
    OUT.mkdir(exist_ok=True)
    rpath = OUT.parent / "receipts.json"
    receipts = json.loads(rpath.read_text()) if rpath.exists() else []
    spent = sum(float(r.get("cost_usd") or PRICE) for r in receipts)
    names = list(PROMPTS)
    # beyond the named prompts, more diverse grids up to n_grids (each ~9 impostor faces)
    for k in range(max(0, n_grids - len(names))):
        PROMPTS[f"diverse_grid_{k}"] = PROMPTS["diverse_grid"] + f" (set {k}, all new people)"
    for name, prompt in PROMPTS.items():
        if any(r["name"] == name and r.get("file") for r in receipts):
            continue
        if spent + PRICE > CAP_USD + 1e-9:
            print("cap reached", spent)
            break
        got = G.generate(prompt, provider_key="flux-3-image", size="1024x1024",
                         work_dir=str(OUT), db=db, agent="quality_director",
                         purpose="identity_calibration_negatives")
        spent += PRICE
        rec = {"name": name, "prompt": prompt, "cost_usd": PRICE,
               "cost_entry_id": got.get("cost_entry_id"),
               "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        src = Path(got.get("path") or "")
        if src.is_file():
            dst = OUT / f"{name}{src.suffix or '.png'}"
            src.replace(dst)
            rec["file"] = dst.name
        receipts.append(rec)
        rpath.write_text(json.dumps(receipts, indent=1))
        print(name, rec.get("file"))
    print("spent_usd_at_list_price", round(spent, 4))


if __name__ == "__main__":
    import sys
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 6)
