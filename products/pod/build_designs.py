#!/usr/bin/env python3
"""Render base artwork for the print-on-demand Canadian-gift line (D-008, candidate C19).
Usage: .venv/bin/python products/pod/build_designs.py [--out dist]

Each design is a parameterized function so the same code renders (a) the sample artwork used
for the Etsy listing photos and (b) production artwork once real buyer text is known. Buyer
personalization itself is handled by Printify's own Personalization Studio (confirmed via
their API docs 2026-09-17: buyers enter text at checkout, Printify renders and generates
mockups automatically) -- these files are the BASE template art with the personalizable area
left clear, not a per-order rendering pipeline. See DESIGN_SPEC.md for the Printify-side setup
(not yet done: needs a live API connection to configure the text layer, which needs
PRINTIFY_TOKEN).

Pixel sizes here are placeholders at safe high resolution (300 DPI-equivalent for the stated
print size) -- MUST be checked against the actual blueprint's print-area spec via
`printify_api.py variants <blueprint_id> <print_provider_id>` once credentials exist, and
resized/cropped to match exactly before upload."""
import argparse, pathlib
from PIL import Image, ImageDraw, ImageFont

HERE = pathlib.Path(__file__).parent
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
FONTB = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
FONTSANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
NAVY = (26, 43, 60)
PINE = (36, 74, 58)
CREAM = (250, 246, 235)
GOLD = (196, 149, 69)
WHITE = (255, 255, 255)


def font(path, sz):
    return ImageFont.truetype(path, sz)


def text_width(dr, text, f, tracking=0):
    if not tracking:
        return dr.textlength(text, font=f)
    widths = [dr.textlength(c, font=f) + tracking for c in text]
    return sum(widths) - tracking


def centered_text(dr, cx, y, text, f, fill, tracking=0):
    if tracking:
        widths = [dr.textlength(c, font=f) + tracking for c in text]
        total = sum(widths) - tracking
        x = cx - total / 2
        for c, w in zip(text, widths):
            dr.text((x, y), c, font=f, fill=fill)
            x += w
    else:
        w = dr.textlength(text, font=f)
        dr.text((cx - w / 2, y), text, font=f, fill=fill)


def fit_font(dr, text, path, start_size, max_width, tracking=0, min_size=8):
    """Personalized text (a buyer's town/surname/name) has unpredictable length -- shrink the
    font until it fits max_width rather than letting it run off the canvas."""
    size = start_size
    f = font(path, size)
    while size > min_size and text_width(dr, text, f, tracking) > max_width:
        size = int(size * 0.92)
        f = font(path, size)
    return f


def pine_tree(dr, cx, base_y, height, color):
    w = height * 0.55
    tiers = 3
    for i in range(tiers):
        t = i / tiers
        top = base_y - height + t * height * 0.6
        bottom = base_y - height * 0.15 + t * height * 0.35
        tier_w = w * (0.4 + 0.6 * (i + 1) / tiers)
        dr.polygon([(cx, top), (cx - tier_w / 2, bottom), (cx + tier_w / 2, bottom)], fill=color)
    dr.rectangle([cx - height * 0.04, base_y - height * 0.15, cx + height * 0.04, base_y], fill=color)


def maple_leaf(dr, cx, cy, size, color):
    # simplified 8-point leaf silhouette, good enough for a line-art mockup
    import math
    pts = []
    for i in range(16):
        ang = math.pi * 2 * i / 16 - math.pi / 2
        r = size if i % 2 == 0 else size * 0.55
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    dr.polygon(pts, fill=color)
    dr.line([(cx, cy + size * 0.55), (cx, cy + size * 1.15)], fill=color, width=max(2, size // 14))


def hockey_stick(dr, x, y, h, color, w=None):
    w = w or max(3, int(h * 0.04))
    dr.line([(x, y), (x, y + h * 0.82)], fill=color, width=w)
    dr.line([(x, y + h * 0.82), (x + h * 0.28, y + h)], fill=color, width=w)


def canvas(size, bg=CREAM):
    im = Image.new("RGB", size, bg)
    return im, ImageDraw.Draw(im)


# ---------- 1. Mug wrap: "Welcome to <Town>" ----------
MUG_SIZE = (3600, 1600)  # wrap art; verify exact px against the chosen blueprint before upload


def mug_welcome(town="MUSKOKA", province="ONTARIO", established=None, size=MUG_SIZE):
    im, dr = canvas(size, NAVY)
    cx, cy = size[0] // 2, size[1] // 2
    pine_tree(dr, cx - size[0] * 0.30, cy + size[1] * 0.30, size[1] * 0.55, PINE)
    pine_tree(dr, cx + size[0] * 0.30, cy + size[1] * 0.30, size[1] * 0.42, (46, 92, 72))
    safe_w = size[0] * 0.86
    centered_text(dr, cx, cy - size[1] * 0.34, "WELCOME TO", font(FONTSANS, int(size[1] * 0.10)), GOLD, tracking=int(size[1] * 0.02))
    town_f = fit_font(dr, town.upper(), FONTB, int(size[1] * 0.20), safe_w)
    centered_text(dr, cx, cy - size[1] * 0.15, town.upper(), town_f, WHITE)
    dr.line([(cx - size[0] * 0.16, cy + size[1] * 0.075), (cx + size[0] * 0.16, cy + size[1] * 0.075)], fill=GOLD, width=max(2, size[1] // 200))
    sub = province.upper() + (f" · EST. {established}" if established else "")
    sub_f = fit_font(dr, sub, FONTSANS, int(size[1] * 0.075), safe_w, tracking=int(size[1] * 0.015))
    centered_text(dr, cx, cy + size[1] * 0.13, sub, sub_f, CREAM, tracking=int(size[1] * 0.015))
    return im


# ---------- 2. Art print (8x10 @ 300dpi = 2400x3000): "The <Family> Cottage" ----------
PRINT_SIZE = (2400, 3000)


def print_cottage(family="MCKENNA", established="2024", size=PRINT_SIZE):
    im, dr = canvas(size, CREAM)
    cx = size[0] // 2
    margin = int(size[0] * 0.08)
    dr.rectangle([margin, margin, size[0] - margin, size[1] - margin], outline=PINE, width=max(3, size[0] // 300))
    dr.rectangle([margin + size[0] // 60, margin + size[0] // 60, size[0] - margin - size[0] // 60, size[1] - margin - size[0] // 60], outline=GOLD, width=max(2, size[0] // 600))
    safe_w = size[0] * 0.84
    pine_tree(dr, cx, int(size[1] * 0.40), size[1] * 0.20, PINE)
    centered_text(dr, cx, int(size[1] * 0.46), "THE", font(FONTSANS, int(size[0] * 0.045)), NAVY, tracking=int(size[0] * 0.01))
    family_f = fit_font(dr, family.upper(), FONTB, int(size[0] * 0.10), safe_w)
    centered_text(dr, cx, int(size[1] * 0.52), family.upper(), family_f, NAVY)
    centered_text(dr, cx, int(size[1] * 0.64), "COTTAGE", font(FONTSANS, int(size[0] * 0.06)), PINE, tracking=int(size[0] * 0.015))
    centered_text(dr, cx, int(size[1] * 0.76), f"EST. {established}", font(FONTSANS, int(size[0] * 0.035)), GOLD, tracking=int(size[0] * 0.02))
    return im


# ---------- 3. Tote bag: hockey family ----------
TOTE_SIZE = (4200, 4800)


def tote_hockey(name="JAMES", number="17", role="MOM", size=TOTE_SIZE):
    im, dr = canvas(size, WHITE)
    cx = size[0] // 2
    safe_w = size[0] * 0.88
    header = f"PROUD HOCKEY {role.upper()}"
    header_f = fit_font(dr, header, FONTSANS, int(size[0] * 0.075), safe_w, tracking=int(size[0] * 0.012))
    centered_text(dr, cx, int(size[1] * 0.10), header, header_f, NAVY, tracking=int(size[0] * 0.012))
    hockey_stick(dr, cx - size[0] * 0.22, int(size[1] * 0.24), size[1] * 0.34, NAVY, w=int(size[0] * 0.018))
    hockey_stick(dr, cx + size[0] * 0.14, int(size[1] * 0.24), size[1] * 0.34, GOLD, w=int(size[0] * 0.018))
    name_line = f"OF {name.upper()}"
    name_f = fit_font(dr, name_line, FONTB, int(size[0] * 0.10), safe_w)
    centered_text(dr, cx, int(size[1] * 0.62), name_line, name_f, NAVY)
    num_f = fit_font(dr, f"#{number}", FONTB, int(size[0] * 0.14), safe_w)
    centered_text(dr, cx, int(size[1] * 0.76), f"#{number}", num_f, GOLD)
    return im


DESIGNS = {
    "mug-welcome-to-town": lambda: mug_welcome(),
    "print-family-cottage": lambda: print_cottage(),
    "tote-hockey-family": lambda: tote_hockey(),
}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=str(HERE / "dist" / "designs")); a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    for name, fn in DESIGNS.items():
        img = fn()
        p = out / f"{name}.png"
        img.save(p)
        print("wrote", p, img.size)
