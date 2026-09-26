"""E2 step 2: the finished cardigan as a deterministic structural reference, from structure.json.

Layer 1 for a garment: the panels the pattern makes, at the dimensions the counts and gauge
give, assembled the way the assembly page says, on a simple torso form. Texture is a
PROCEDURAL cue at the gauge's row pitch, oriented the way construction dictates (vertical on
the body, lengthwise on the sleeves); ribbing bands at their measured widths; two pockets at
an ASSUMED placement the pattern leaves to the maker (declared). No mechanics, no yarn path.
Colour is neutral because the text does not give one.

Three views: front three-quarter on the form, back on the form, and an open flat-lay.
"""
from __future__ import annotations

import json, math, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
S = json.load(open(HERE / "out" / "structure.json"))
D = S["derived_cm"]; F = S["facts"]
ROW = 10.0 / F["gauge_rows_per_10cm"]      # cm per row  (texture line pitch)
BASE = (214, 206, 194); RIB = BASE; LINE = (150, 142, 130); POCKET = BASE; BG = (236, 236, 232)
MODEL_HEIGHT_CM = 160.0   # p2: "shown on a 5'3\" model" -- the only body scale the pattern gives
ST = 10.0 / 14.5          # cm per stitch (structure.json gauge), for the waffle dash cue

def pocket_placement():
    # ASSUMED (pattern: "try on to double-check placement"): centred on each front panel,
    # bottom of pocket 6 cm above the hem rib.
    return {"above_hem_rib_cm": 6.0, "centred_on_front": True, "assumed": True}

# ---- geometry: a torso form and the panels wrapped on it -----------------------------------
L = D["body_length_cm"]; BW = D["back_width_cm"]; FW = D["front_panel_width_cm"]
SL = D["sleeve_length_cm"]; SC = D["sleeve_circumference_cm"]; OPEN = D["sleeve_opening_depth_cm"]
HEM = D["hem_rib_height_cm"]; CUFF = D["cuff_rib_length_cm"]; NB = D["neckband_width_cm"]
PH, PW = D["pocket_h_cm"], D["pocket_w_cm"]
# Form: ellipse with circumference ~ back_width*2*0.85 (the cardigan is oversized; the form is the body)
a, b = 15.0, 10.5                                    # semi-axes cm (bust ~81 cm)
def ell_point(theta, r_off=0.0):
    return np.array([(a + r_off) * math.cos(theta), (b + r_off) * math.sin(theta)])
def arc_len(t0, t1, r_off, n=400):
    ts = np.linspace(t0, t1, n); pts = np.array([ell_point(t, r_off) for t in ts])
    return float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))
def theta_for_arc(t0, target, r_off, direction=1):
    lo, hi = 0.0, 2 * math.pi
    for _ in range(40):
        mid = (lo + hi) / 2
        if arc_len(t0, t0 + direction * mid, r_off) < target: lo = mid
        else: hi = mid
    return t0 + direction * (lo + hi) / 2

OFF = 3.5  # cardigan ellipse: (18.5, 14.0) ~ 103 cm round; 94.8 cm of panels leaves ~8 cm open at the front
# Back panel: centred on theta = -pi/2 (the back, -y), spanning BW along the arc.
tb0 = theta_for_arc(-math.pi / 2, BW / 2, OFF, -1); tb1 = theta_for_arc(-math.pi / 2, BW / 2, OFF, +1)
# Fronts: from each side seam (tb0 / tb1) toward the front (+y), spanning FW.
tfL0, tfL1 = tb1, theta_for_arc(tb1, FW, OFF, +1)
tfR0, tfR1 = tb0, theta_for_arc(tb0, FW, OFF, -1)

def panel_quads(t0, t1, z0, z1, colour, n_cols, texture_pitch, rib_rows=None, rib_from_bottom=0.0):
    """Curved panel on the form between angles t0..t1, heights z0..z1 (z up). Returns quads with
    per-column shading; vertical texture lines are added later by drawing quad edges."""
    quads = []
    ts = np.linspace(t0, t1, n_cols + 1)
    for i in range(n_cols):
        p0, p1 = ell_point(ts[i], OFF), ell_point(ts[i + 1], OFF)
        nrm = np.array([(p0[0] + p1[0]) / 2 / a ** 2, (p0[1] + p1[1]) / 2 / b ** 2, 0.0]); nrm /= np.linalg.norm(nrm)
        # hem rib band and main field are separate quads so the band can be shaded differently
        zs = [(z0, z0 + rib_from_bottom, RIB, "rib"), (z0 + rib_from_bottom, z1, colour, "vline")] if rib_from_bottom else [(z0, z1, colour, "vline")]
        for za, zb, col, tex in zs:
            if zb <= za: continue
            quads.append((np.array([[p0[0], p0[1], za], [p1[0], p1[1], za], [p1[0], p1[1], zb], [p0[0], p0[1], zb]]), nrm, col, tex))
    return quads

def sleeve_quads(side, droop_deg=62.0, n=28):
    """A tube of circumference SC and length SL hanging from the shoulder line at the side seam,
    drop-shoulder: attached along the top OPEN cm of the body edge. Angled down from horizontal."""
    r = SC / (2 * math.pi)
    theta_attach = tb1 if side == "L" else tb0
    root = ell_point(theta_attach, OFF); root = np.array([root[0], root[1], L - OPEN / 2])
    outward = np.array([math.copysign(1.0, root[0]), 0.0, 0.0])
    d = math.radians(droop_deg)
    axis = np.array([outward[0] * math.cos(d), 0.0, -math.sin(d)])       # sleeve direction
    u = np.array([0.0, 1.0, 0.0]); v = np.cross(axis, u); v /= np.linalg.norm(v)
    quads = []
    phis = np.linspace(0, 2 * math.pi, n + 1)
    for i in range(n):
        c0 = np.cos(phis[i]) * u + np.sin(phis[i]) * v; c1 = np.cos(phis[i + 1]) * u + np.sin(phis[i + 1]) * v
        for za, zb, col, tex in ((0.0, SL - CUFF, BASE, "hline"), (SL - CUFF, SL, RIB, "ribh")):
            q = np.array([root + r * c0 + axis * za, root + r * c1 + axis * za, root + r * c1 + axis * zb, root + r * c0 + axis * zb])
            quads.append((q, (c0 + c1) / 2, col, tex))
    return quads

def pockets_quads():
    out = []
    pl = pocket_placement()
    for t0, t1 in ((tfL0, tfL1), (tfR0, tfR1)):
        lo, hi = min(t0, t1), max(t0, t1)
        # centred on the front panel's arc, measured along the pocket's own (slightly raised) surface
        tc = theta_for_arc(lo, arc_len(lo, hi, OFF) / 2, OFF, +1)
        ta = theta_for_arc(tc, PW / 2, OFF + 0.6, -1); tb = theta_for_arc(tc, PW / 2, OFF + 0.6, +1)
        z0 = HEM + pl["above_hem_rib_cm"]; z1 = z0 + PH
        ts = np.linspace(min(ta, tb), max(ta, tb), 8)
        for i in range(7):
            p0, p1 = ell_point(ts[i], OFF + 0.6), ell_point(ts[i + 1], OFF + 0.6)
            nrm = np.array([(p0[0] + p1[0]) / 2 / a ** 2, (p0[1] + p1[1]) / 2 / b ** 2, 0.0]); nrm /= np.linalg.norm(nrm)
            tag = "pocket_end" if i in (0, 6) else "pocket"
            out.append((np.array([[p0[0], p0[1], z0], [p1[0], p1[1], z0], [p1[0], p1[1], z1], [p0[0], p0[1], z1]]), nrm, POCKET, tag))
    return out

def neckband_quads():
    out = []
    # along each front edge (a vertical strip NB wide, at the front edge angle, full length)
    for te, sgn in ((tfL1, +1), (tfR1, -1)):
        ta = theta_for_arc(te, NB, OFF + 0.3, -sgn)
        ts = sorted([ta, te])
        p0, p1 = ell_point(ts[0], OFF + 0.3), ell_point(ts[1], OFF + 0.3)
        nrm = np.array([(p0[0] + p1[0]) / 2 / a ** 2, (p0[1] + p1[1]) / 2 / b ** 2, 0.0]); nrm /= np.linalg.norm(nrm)
        out.append((np.array([[p0[0], p0[1], 0.0], [p1[0], p1[1], 0.0], [p1[0], p1[1], L], [p0[0], p0[1], L]]), nrm, RIB, "rib"))
    # across the back neck: a strip NB tall at the top of the back panel
    ts = np.linspace(tb0, tb1, 24)
    for i in range(23):
        p0, p1 = ell_point(ts[i], OFF + 0.3), ell_point(ts[i + 1], OFF + 0.3)
        nrm = np.array([(p0[0] + p1[0]) / 2 / a ** 2, (p0[1] + p1[1]) / 2 / b ** 2, 0.0]); nrm /= np.linalg.norm(nrm)
        out.append((np.array([[p0[0], p0[1], L - NB], [p1[0], p1[1], L - NB], [p1[0], p1[1], L], [p0[0], p0[1], L]]), nrm, RIB, "rib"))
    return out

def form_quads(n=40):
    """A neutral figure at MODEL_HEIGHT_CM: torso (the ellipse), a head, and legs, so the
    cardigan's length is seen against a body of the size the pattern names (p2). The shoulder
    line is at 0.82 of height; the cardigan hangs from it. Nothing about the figure is styled."""
    out = []; ts = np.linspace(0, 2 * math.pi, n + 1); grey = (150, 150, 152)
    shoulder = 0.82 * MODEL_HEIGHT_CM; floor = shoulder - L - (0.82 * MODEL_HEIGHT_CM - L)  # z=L is the shoulder line
    z_floor = L - shoulder                                    # floor in cardigan coordinates
    for i in range(n):
        p0, p1 = ell_point(ts[i]), ell_point(ts[i + 1])
        nrm = np.array([(p0[0] + p1[0]) / 2 / a ** 2, (p0[1] + p1[1]) / 2 / b ** 2, 0.0]); nrm /= np.linalg.norm(nrm)
        out.append((np.array([[p0[0], p0[1], z_floor + 0.45 * MODEL_HEIGHT_CM], [p1[0], p1[1], z_floor + 0.45 * MODEL_HEIGHT_CM],
                              [p1[0], p1[1], L + 2], [p0[0], p0[1], L + 2]]), nrm, grey, None))
        # legs: two cylinders from the hip down to the floor
        for cx in (-7.5, 7.5):
            rr = 6.0
            q0 = np.array([cx + rr * math.cos(ts[i]), rr * math.sin(ts[i]) * 0.9, 0]); q1 = np.array([cx + rr * math.cos(ts[i + 1]), rr * math.sin(ts[i + 1]) * 0.9, 0])
            ln = np.array([math.cos(ts[i]), math.sin(ts[i]), 0.0])
            out.append((np.array([q0 + [0, 0, z_floor], q1 + [0, 0, z_floor], q1 + [0, 0, z_floor + 0.47 * MODEL_HEIGHT_CM], q0 + [0, 0, z_floor + 0.47 * MODEL_HEIGHT_CM]]), ln, grey, None))
        # head: a sphere-ish stack above the shoulder (neck 4 cm, head 22 cm tall)
        for zk in range(8):
            z0 = L + 6 + zk * 2.75; z1 = z0 + 2.75; rad = 9.5 * math.sin(math.pi * (zk + 0.5) / 8) + 1.0
            q0 = np.array([rad * math.cos(ts[i]), rad * math.sin(ts[i]) * 0.85, z0]); q1 = np.array([rad * math.cos(ts[i + 1]), rad * math.sin(ts[i + 1]) * 0.85, z0])
            q2 = np.array([rad * math.cos(ts[i + 1]), rad * math.sin(ts[i + 1]) * 0.85, z1]); q3 = np.array([rad * math.cos(ts[i]), rad * math.sin(ts[i]) * 0.85, z1])
            out.append((np.array([q0, q1, q2, q3]), np.array([math.cos(ts[i]), math.sin(ts[i]), 0.0]), grey, None))
    return out

def scene():
    q = form_quads()
    q += panel_quads(tb0, tb1, 0.0, L, BASE, int(BW / ROW), ROW, rib_from_bottom=HEM)
    q += panel_quads(tfL0, tfL1, 0.0, L, BASE, int(FW / ROW), ROW, rib_from_bottom=HEM)
    q += panel_quads(tfR1, tfR0, 0.0, L, BASE, int(FW / ROW), ROW, rib_from_bottom=HEM)
    q += sleeve_quads("L") + sleeve_quads("R") + pockets_quads() + neckband_quads()
    return q

def render(quads, out_png, elev_deg, azim_deg, size=1024, ortho_span=None):
    el, az = math.radians(elev_deg), math.radians(azim_deg)
    view = np.array([math.cos(el) * math.sin(az), -math.cos(el) * math.cos(az), math.sin(el)])
    up = np.array([0, 0, 1.0]); right = np.cross(up, view); right /= np.linalg.norm(right); sup = np.cross(view, right)
    light = view * 0.75 + np.array([-0.3, 0.0, 0.6]); light /= np.linalg.norm(light)   # from the camera side, a little high-left
    faces = []
    for quad, nrm, col, tex in quads:
        n3 = nrm if len(nrm) == 3 else np.array([nrm[0], nrm[1], 0.0])
        if n3 @ view < -0.02:
            continue                                            # back-face cull
        shade = 0.42 + 0.58 * max(0.0, float(n3 @ light))
        faces.append((float(quad.mean(0) @ view), quad, tuple(int(c * shade) for c in col), tex))
    faces.sort(key=lambda f: f[0])
    allp = np.concatenate([f[1] for f in faces]); sx, sy = allp @ right, allp @ sup
    span = ortho_span or max(sx.max() - sx.min(), sy.max() - sy.min()) * 1.12
    cx, cy = (sx.max() + sx.min()) / 2, (sy.max() + sy.min()) / 2; sc = size / span
    P = lambda p: ((p @ right - cx) * sc + size / 2, size / 2 - (p @ sup - cy) * sc)
    img = Image.new("RGB", (size, size), BG); d = ImageDraw.Draw(img)
    projected = [([P(p) for p in quad], col, tex) for _, quad, col, tex in faces]
    for pts, col, _ in projected:
        d.polygon(pts, fill=col)
    for pts, _, tex in projected:
        if tex == "vline":      # waffle field, rows vertical: a staggered dash per stitch along the row
            (x1, y1), (x2, y2) = pts[1], pts[2]
            n = max(2, int(abs(y2 - y1) / (ST * sc)))
            for k in range(n):
                if (k + int(x1 / 3)) % 2:      # stagger between neighbouring rows
                    ya = y1 + (y2 - y1) * (k + 0.15) / n; yb = y1 + (y2 - y1) * (k + 0.85) / n
                    d.line([(x1, ya), (x2, yb)], fill=LINE, width=1)
        elif tex == "rib":      # ribbing: dense parallel lines, same colour as the field
            (x1, y1), (x2, y2) = pts[1], pts[2]
            d.line([pts[1], pts[2]], fill=LINE, width=1)
            d.line([((pts[0][0] + x1) / 2, (pts[0][1] + y1) / 2), ((pts[3][0] + x2) / 2, (pts[3][1] + y2) / 2)], fill=LINE, width=1)
        elif tex == "hline":    # sleeve field, rows lengthwise: staggered dashes along the length
            (x1, y1), (x2, y2) = pts[0], pts[3]
            n = max(2, int(math.hypot(x2 - x1, y2 - y1) / (ST * sc)))
            for k in range(n):
                if (k + int(y1 / 3)) % 2:
                    xa = x1 + (x2 - x1) * (k + 0.15) / n; ya = y1 + (y2 - y1) * (k + 0.15) / n
                    xb = x1 + (x2 - x1) * (k + 0.85) / n; yb = y1 + (y2 - y1) * (k + 0.85) / n
                    d.line([(xa, ya), (xb, yb)], fill=LINE, width=1)
        elif tex in ("pocket", "pocket_end"):   # a patch pocket's edge is a seam: draw it
            d.line([pts[0], pts[1]], fill=LINE, width=2); d.line([pts[3], pts[2]], fill=LINE, width=2)
            if tex == "pocket_end":
                d.line([pts[0], pts[3]], fill=LINE, width=2); d.line([pts[1], pts[2]], fill=LINE, width=2)
            (x1, y1), (x2, y2) = pts[1], pts[2]          # and the waffle continues inside it
            n = max(2, int(abs(y2 - y1) / (ST * sc)))
            for k in range(n):
                if (k + int(x1 / 3)) % 2:
                    d.line([(x1, y1 + (y2 - y1) * (k + 0.15) / n), (x2, y1 + (y2 - y1) * (k + 0.85) / n)], fill=LINE, width=1)
        elif tex == "ribh":     # cuff ribbing: dense lines across the sleeve
            d.line([pts[0], pts[1]], fill=LINE, width=1); d.line([pts[3], pts[2]], fill=LINE, width=1)
    img.save(out_png)

def flat_lay(out_png, size=1024):
    """Open flat-lay, top-down: back panel centre, fronts folded out flat either side, sleeves out."""
    W = 2 * FW + BW + 2 * SL + 8; H = L + 8
    sc = size / max(W, H) * 0.92; ox = (size - W * sc) / 2; oy = (size - H * sc) / 2
    img = Image.new("RGB", (size, size), BG); d = ImageDraw.Draw(img)
    X = lambda x: ox + x * sc; Y = lambda z: oy + (H - z) * sc
    def rect(x0, x1, z0, z1, col): d.rectangle([X(x0), Y(z1), X(x1), Y(z0)], fill=col)
    def vlines(x0, x1, z0, z1, pitch):
        x = x0
        while x <= x1: d.line([(X(x), Y(z0)), (X(x), Y(z1))], fill=LINE, width=1); x += pitch
    def hlines(x0, x1, z0, z1, pitch):
        z = z0
        while z <= z1: d.line([(X(x0), Y(z)), (X(x1), Y(z))], fill=LINE, width=1); z += pitch
    xb0 = SL + 4 + FW; xb1 = xb0 + BW
    # body: front L | back | front R, all L tall, hem rib at the bottom
    for x0, x1 in ((xb0 - FW, xb0), (xb0, xb1), (xb1, xb1 + FW)):
        rect(x0, x1, 0, L, BASE); vlines(x0, x1, HEM, L, ROW)
        vlines(x0, x1, 0, HEM, ROW / 2)                                    # hem rib: dense lines, same colour
        d.line([(X(x0), Y(HEM)), (X(x1), Y(HEM))], fill=LINE, width=1)      # the rib/field boundary is a real row change
    # neckband strips along the two front edges and across the back neck
    for x0, x1 in ((xb0 - FW, xb0 - FW + NB), (xb1 + FW - NB, xb1 + FW)):
        rect(x0, x1, 0, L, BASE); hlines(x0, x1, 0, L, ROW / 2)             # front bands: BLO rib across the band
        d.line([(X(x1 if x0 < xb0 else x0), Y(0)), (X(x1 if x0 < xb0 else x0), Y(L))], fill=LINE, width=1)
    rect(xb0, xb1, L - NB, L, BASE); vlines(xb0, xb1, L - NB, L, ROW / 2)  # back neck band
    d.line([(X(xb0), Y(L - NB)), (X(xb1), Y(L - NB))], fill=LINE, width=1)
    # sleeves: flat tubes SC/2 wide, SL long, attached at the top OPEN cm of each side, angled out horizontally
    for x0, x1 in ((xb0 - FW - SL, xb0 - FW), (xb1 + FW, xb1 + FW + SL)):
        z1 = L; z0 = L - SC / 2
        rect(x0, x1, z0, z1, BASE); hlines(x0, x1, z0, z1, ROW)
        cx0, cx1 = (x0, x0 + CUFF) if x0 < xb0 else (x1 - CUFF, x1)
        rect(cx0, cx1, z0, z1, BASE); vlines(cx0, cx1, z0, z1, ROW / 3)   # cuff rib: dense lines across the sleeve
        d.line([(X(cx1 if x0 < xb0 else cx0), Y(z0)), (X(cx1 if x0 < xb0 else cx0), Y(z1))], fill=LINE, width=1)
    # pockets, assumed placement
    pl = pocket_placement(); z0 = HEM + pl["above_hem_rib_cm"]
    for xc in ((xb0 - FW / 2), (xb1 + FW / 2)):
        rect(xc - PW / 2, xc + PW / 2, z0, z0 + PH, POCKET); vlines(xc - PW / 2, xc + PW / 2, z0, z0 + PH, ROW)
        d.rectangle([X(xc - PW / 2), Y(z0 + PH), X(xc + PW / 2), Y(z0)], outline=LINE, width=2)  # a patch pocket's edge is a seam
    img.save(out_png)

if __name__ == "__main__":
    out = HERE / "out"; q = scene()
    # Camera convention: azimuth 0 looks at -y, and the back panel is centred on -y. So the FRONT
    # is seen from azimuth 180. The first version had these two swapped and labelled the closed
    # back "front"; caught by looking, which is the only way that bug could have been caught.
    render(q, out / "cardigan_front34.png", 12.0, 180.0 + 30.0)
    render(q, out / "cardigan_back.png", 10.0, 25.0)
    flat_lay(out / "cardigan_flatlay.png")
    circ = arc_len(0, 2 * math.pi, OFF); gap = circ - (BW + 2 * FW)
    meta = {"views": ["cardigan_front34.png", "cardigan_back.png", "cardigan_flatlay.png"],
            "front_gap_cm_on_form": round(gap, 1), "cardigan_ellipse_circumference_cm": round(circ, 1),
            "form_semi_axes_cm": [a, b], "pocket_placement": pocket_placement(),
            "texture": "PROCEDURAL row lines at gauge row pitch; vertical on body, lengthwise on sleeves",
            "colour": "neutral; not derivable from the pattern text"}
    (out / "reference_meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta))
