"""Numerical scoring of the E1 outputs. Crude by design and labelled as such: wine-pixel
counts say whether the two stripes exist at all, and for the outputs that have them, where
they sit as a fraction of the basket's visible height. Segmentation of a cream basket from a
white wall is not robust, so the height estimate uses the stripe rows themselves plus the
first/last strongly-textured rows in the central column band, and is reported to +-8%."""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
truth = json.load(open(OUT / "basket_large_structure.json"))
rings = truth["rings"]; H = truth["height_cm"]
wall_z = [z for r, z in rings if z > 0]
band_truth = {}
for name, rounds in truth["colour_bands_by_round"]:
    if name == "wine":
        zs = [rings[r - 1][1] for r in rounds]
        band_truth = {"wine_rounds": rounds, "wine_heights_frac": [round(z / H, 3) for z in zs]}

def wine_mask(a):
    r, g, b = a[..., 0].astype(int), a[..., 1].astype(int), a[..., 2].astype(int)
    return (r > 90) & (g < 75) & (b < 90) & (r - g > 45)

def score(path):
    a = np.asarray(Image.open(path).convert("RGB"))
    h, w, _ = a.shape
    m = wine_mask(a)
    frac = m.mean()
    # central band of columns, row profile of wine
    c0, c1 = int(w * 0.3), int(w * 0.7)
    prof = m[:, c0:c1].mean(1)
    rows = np.nonzero(prof > 0.15)[0]
    stripes = []
    if len(rows):
        groups = np.split(rows, np.nonzero(np.diff(rows) > 6)[0] + 1)
        stripes = [(int(g[0]), int(g[-1])) for g in groups if len(g) >= 3]
    # basket vertical extent: rows in the central band with high local variance (texture)
    gray = a[:, c0:c1].mean(2)
    tex = np.abs(np.diff(gray, axis=1)).mean(1)
    tr = np.nonzero(tex > np.percentile(tex, 55))[0]
    top, bot = (int(tr[0]), int(tr[-1])) if len(tr) else (0, h)
    out = {"file": Path(path).name, "wine_pixel_fraction": round(float(frac), 4),
           "stripes_found": len(stripes)}
    if stripes and bot > top:
        # heights measured from the BOTTOM as a fraction of the visible extent
        out["stripe_heights_frac_from_base"] = [round((bot - (s0 + s1) / 2) / (bot - top), 2)
                                                for s0, s1 in stripes]
        out["extent_rows"] = [top, bot]
    return out

results = {"truth": band_truth, "outputs": []}
for p in sorted((OUT / "gen").iterdir()):
    results["outputs"].append(score(p))
(OUT / "e1_measurements.json").write_text(json.dumps(results, indent=1))
for r in results["outputs"]:
    print(r)
print("truth wine heights (frac of H):", band_truth)

# contact sheet: reference | A0 | B0 | C0 | C1
tiles = [OUT / "basket_large_structural.png", OUT / "gen/A0_flux-2-pro.jpg",
         OUT / "gen/B0_flux-2-pro.jpg", OUT / "gen/C0_gpt-image-2.png", OUT / "gen/C1_gpt-image-2.png"]
ims = [Image.open(t).convert("RGB").resize((400, 400)) for t in tiles]
sheet = Image.new("RGB", (400 * len(ims), 400), (255, 255, 255))
for i, im in enumerate(ims):
    sheet.paste(im, (400 * i, 0))
sheet.save(OUT / "e1_contact_sheet.png")
print("contact sheet written")
