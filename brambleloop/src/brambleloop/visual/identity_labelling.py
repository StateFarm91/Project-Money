"""Owner Decision 2: a 24-frame contact sheet of Laura for the owner to label (ENG-VIS-IDENTITY).

Production calibration needs at least 30 HELD-OUT genuine samples (`identity_calibration`), and
a genuine label can only come from a human: the system labelling its own output as Laura would
be circular. This module is the whole loop, end to end, without ever deciding a label itself:

1. `plan(n)` -- n deterministic, varied shots (framing, angle, light, expression, setting). Every
   one is conditioned on ALL THREE of her canonical references (face, torso, full body), each
   read from the committed pack and verified by sha256. A missing or altered reference refuses
   the plan: nothing is generated against a reference that is not hers.
2. `generate(db, out_dir)` -- renders the plan through `gateway.images.generate` (the FLUX 3
   provider ENG-VIS-FLUX owns): the CA$100 ceiling reservation, the owner's `generation`
   activation of `flux-3-image`, one ledger row per render. It refuses BEFORE any reservation
   unless the BFL key is present AND the activation is active (`readiness`; ENG-VIS-FLUX's
   `gateway.flux_provider.readiness` when that module is present). Hard cap `CAP_USD`.
   Idempotent: a frame already on disk with its recorded sha is not re-bought.
3. `contact_sheet(manifest)` -- one numbered PNG grid of the frames, and `labelling_page`, a
   self-contained HTML page with a Laura / not Laura choice per frame that prints the exact
   labelling command.
4. `apply_labels(manifest, labels, labelled_by=...)` -- records the owner's labels. Every frame
   must be labelled exactly once, by a named human; there is no default label. Frames marked
   "Laura" become genuine samples; frames marked "not Laura" become impostors (look-alike
   negatives generated on her references: the hardest impostors there are).
   `add_to_calibration_set` then appends them to the committed manifest.

Nothing here spends unless `generate` is called on a worker where the key and the owner's
activation both exist.
"""
from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

PROVIDER = "flux-3-image"
SIZE = "1024x1024"
N_FRAMES = 24
COLUMNS = 6
PURPOSE = "identity_calibration_genuine"
AGENT = "quality_director"
MANIFEST_VERSION = "identity-contact-sheet/1"
LAURA, NOT_LAURA = "laura", "not_laura"


def price_usd() -> float:
    from ..gateway import images

    return float(images.BFL3_TIER_USD["1k"])          # US$0.048, references not charged


# 24 x US$0.048 = US$1.152; the cap leaves no room for a 25th render.
CAP_USD = 1.16


class NotReady(RuntimeError):
    """Generation refused before any reservation. `.code` is the reason; nothing was spent."""

    def __init__(self, code: str, message: str):
        super().__init__(f"UNKNOWN [{code}] {message}")
        self.code = code


class LabelsRefused(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ---- 1. the plan ---------------------------------------------------------------------------

FRAMINGS = ("head-and-shoulders portrait", "waist-up photograph", "three-quarter-length photograph",
            "full-length photograph")
ANGLES = ("facing the camera", "turned about thirty degrees to her left, eyes to camera",
          "turned about thirty degrees to her right, eyes to camera")
LIGHTS = ("soft window daylight", "bright overcast daylight outdoors", "warm late-afternoon sun",
          "even soft studio light", "warm lamp light in the evening", "cool morning light")
EXPRESSIONS = ("a relaxed natural smile", "a calm neutral expression", "a laugh mid-moment",
               "a focused, gentle expression")
SETTINGS = ("in a cosy living room with a knitted throw",
            "in front of a plain light-grey studio backdrop", "on a garden path by green hedges",
            "in a bright kitchen", "in a reading nook by a window", "at a small cafe table")
WARDROBE = "a plain oatmeal knit jumper and dark trousers"


def _reference_paths() -> list[dict]:
    from . import canonical
    from .vision_judges import REF_ORDER

    out = []
    for frame in REF_ORDER:
        want = canonical.CURRENT_REFERENCE_HASHES[frame]
        path = canonical.reference_file(frame)
        data = Path(path).read_bytes() if path else b""
        got = hashlib.sha256(data).hexdigest() if data else ""
        if got != want:
            raise NotReady("reference_mismatch",
                           f"canonical reference {frame} is {got[:12] or 'missing'}, not the "
                           f"recorded {want[:12]}; nothing is generated against it")
        out.append({"frame": frame, "path": path, "sha256": want})
    return out


def plan(n: int = N_FRAMES) -> list[dict]:
    """n varied shots, each conditioned on all three canonical references (verified)."""
    refs = _reference_paths()
    shots = []
    for i in range(n):
        framing = FRAMINGS[i % len(FRAMINGS)]
        angle = ANGLES[(i // len(FRAMINGS)) % len(ANGLES)]
        light = LIGHTS[i % len(LIGHTS)]
        # i // 12 shifts the expression so the second dozen never repeats the first
        expr = EXPRESSIONS[(i + i // 12) % len(EXPRESSIONS)]
        setting = SETTINGS[(i * 7 + 3) % len(SETTINGS)]
        prompt = (f"The same woman as in the three reference images: the same face, the same "
                  f"person, unchanged. A {framing} of her, {angle}, with {expr}, {setting}, "
                  f"{light}, wearing {WARDROBE}. Only her in the photograph. Her face clearly "
                  f"visible and in focus. Natural photographic realism, no text")
        shots.append({"n": i + 1, "id": f"genuine-{i + 1:02d}", "prompt": prompt,
                      "framing": framing, "angle": angle, "light": light,
                      "expression": expr, "setting": setting,
                      "references": [{"frame": r["frame"], "sha256": r["sha256"]} for r in refs]})
    return shots


# ---- 2. generation (refuses unless the key and the owner's activation exist) ---------------

def readiness(db, env: dict | None = None) -> dict:
    """{state: READY|UNKNOWN, code, reason}. Never raises, never spends."""
    try:
        from ..gateway import flux_provider          # ENG-VIS-FLUX, when it has landed
    except ImportError:
        flux_provider = None
    if flux_provider is not None:
        got = flux_provider.readiness(db, env=env)
        return {"state": got["state"], "code": got.get("code", ""),
                "reason": got.get("reason", ""), "via": "gateway.flux_provider"}
    from ..gateway import images, paid_provider_gate as gate

    if not images.key_for(PROVIDER, env):
        return {"state": "UNKNOWN", "code": "no_bfl_credential", "via": "gateway.images",
                "reason": "no BFL credential in this environment; nothing reserved or spent"}
    act = gate.activation_state(db, PROVIDER, gate.GENERATION)
    if not act["active"]:
        return {"state": "UNKNOWN", "code": act["reason"], "via": "paid_provider_gate",
                "reason": f"{PROVIDER} has no active owner activation for generation "
                          f"({act['reason']}); nothing reserved or spent"}
    return {"state": "READY", "code": "", "via": "paid_provider_gate",
            "reason": "BFL credential present and the owner's generation activation is active"}


def generate(db, out_dir, *, n: int = N_FRAMES, env: dict | None = None,
             generator=None, ready=readiness) -> dict:
    """Render the plan into `out_dir` and write `contact_sheet.json` there. Refuses with
    `NotReady` before anything is reserved unless `ready(db, env)` is READY."""
    st = ready(db, env)
    if st.get("state") != "READY":
        raise NotReady(st.get("code") or "not_ready", st.get("reason") or "not ready")
    if n * price_usd() > CAP_USD + 1e-9:
        raise NotReady("cap", f"{n} frames x US${price_usd()} exceeds the US${CAP_USD} cap")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    mpath = out / "contact_sheet.json"
    man = (json.loads(mpath.read_text()) if mpath.exists() else
           {"version": MANIFEST_VERSION, "provider": PROVIDER, "size": SIZE,
            "created_at": _now(), "frames": []})
    have = {f["id"]: f for f in man["frames"]}
    refs = _reference_paths()
    if generator is None:
        from ..gateway import images

        def generator(prompt, reference_urls):
            return images.generate(prompt, reference_urls=reference_urls, provider_key=PROVIDER,
                                   size=SIZE, work_dir=str(out), db=db, agent=AGENT,
                                   purpose=PURPOSE, env=env)
    spent = sum(float(f.get("cost_usd") or 0) for f in man["frames"])
    for shot in plan(n):
        old = have.get(shot["id"])
        if old and (out / old["file"]).is_file() and \
                hashlib.sha256((out / old["file"]).read_bytes()).hexdigest() == old["sha256"]:
            continue
        if spent + price_usd() > CAP_USD + 1e-9:
            break
        got = generator(shot["prompt"], [r["path"] for r in refs])
        spent += price_usd()
        src = Path(got.get("path") or "")
        if not src.is_file():
            raise RuntimeError(f"{shot['id']}: the provider returned no image file")
        dst = out / f"{shot['id']}{src.suffix or '.png'}"
        if src.resolve() != dst.resolve():
            src.replace(dst)
        data = dst.read_bytes()
        rec = {**{k: shot[k] for k in ("n", "id", "prompt", "references")},
               "file": dst.name, "sha256": hashlib.sha256(data).hexdigest(),
               "cost_usd": price_usd(), "cost_entry_id": got.get("cost_entry_id"),
               "generated_at": _now(), "label": None}
        have[shot["id"]] = rec
        man["frames"] = sorted(have.values(), key=lambda f: f["n"])
        mpath.write_text(json.dumps(man, indent=1))
    man["spent_usd_at_list_price"] = round(spent, 4)
    mpath.write_text(json.dumps(man, indent=1))
    return man


# ---- 3. what the owner looks at ------------------------------------------------------------

def _verified(man: dict, out_dir) -> list[tuple[dict, bytes]]:
    out = []
    for f in man["frames"]:
        data = (Path(out_dir) / f["file"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != f["sha256"]:
            raise LabelsRefused(f"frame {f['n']} ({f['file']}) bytes do not match its sha256")
        out.append((f, data))
    return out


def contact_sheet(man: dict, out_dir, *, tile: int = 320) -> bytes:
    """A numbered PNG grid of every frame (COLUMNS wide), each verified by sha256."""
    from PIL import Image, ImageDraw, ImageFont

    frames = _verified(man, out_dir)
    rows = max(1, -(-len(frames) // COLUMNS))
    pad, label_h = 8, 34
    sheet = Image.new("RGB", (COLUMNS * (tile + pad) + pad, rows * (tile + label_h + pad) + pad),
                      (250, 248, 244))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 24)
    except OSError:
        font = ImageFont.load_default()
    for k, (f, data) in enumerate(frames):
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.thumbnail((tile, tile))
        x = pad + (k % COLUMNS) * (tile + pad)
        y = pad + (k // COLUMNS) * (tile + label_h + pad)
        sheet.paste(img, (x + (tile - img.width) // 2, y + label_h))
        draw.text((x + 4, y + 4), f"{f['n']}", fill=(40, 40, 40), font=font)
    b = io.BytesIO()
    sheet.save(b, "PNG")
    return b.getvalue()


def labelling_page(man: dict, sheet_file: str = "contact_sheet.png") -> str:
    """A self-contained HTML page: the sheet, one Laura / not Laura choice per frame, and the
    exact command that records the choices. The page decides nothing and sends nothing."""
    import html

    rows = "\n".join(
        f'<tr><td>{f["n"]}</td><td><img src="{html.escape(f["file"])}" alt="frame {f["n"]}">'
        f'</td><td><label><input type="radio" name="f{f["n"]}" value="laura"> Laura</label> '
        f'<label><input type="radio" name="f{f["n"]}" value="not_laura"> not Laura</label>'
        f'</td></tr>' for f in man["frames"])
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Laura labelling</title>
<style>
:root{{--bg:#faf8f4;--fg:#222;--line:#ddd}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#1b1a18;--fg:#eee;--line:#444}}}}
:root[data-theme="dark"]{{--bg:#1b1a18;--fg:#eee;--line:#444}}
body{{background:var(--bg);color:var(--fg);font:16px/1.4 system-ui,sans-serif;margin:0 16px}}
img{{max-width:220px;width:100%;height:auto}} table{{border-collapse:collapse;width:100%}}
td{{border-bottom:1px solid var(--line);padding:6px;vertical-align:middle}}
pre{{white-space:pre-wrap;word-break:break-all;border:1px solid var(--line);padding:8px}}
</style></head><body>
<h1>Is this Laura?</h1>
<p>Each frame was generated on Laura's three canonical references. Mark every frame. Only your
own judgement counts: a frame that is "nearly" her is <b>not Laura</b>.</p>
<p><img src="{html.escape(sheet_file)}" alt="contact sheet" style="max-width:100%"></p>
<table>{rows}</table>
<p><button id="go">Make the labelling command</button></p><pre id="out"></pre>
<script>
document.getElementById('go').onclick=function(){{
  var n={len(man["frames"])},l=[],u=[],m=[];
  for(var i=1;i<=n;i++){{var c=document.querySelector('input[name=f'+i+']:checked');
    if(!c)m.push(i);else if(c.value==='laura')l.push(i);else u.push(i);}}
  document.getElementById('out').textContent=m.length?('Unlabelled frames: '+m.join(', ')):
   ('python3 scripts/identity_contact_sheet.py label DIR --by "YOUR NAME" --laura '+
    (l.join(',')||'none')+' --not-laura '+(u.join(',')||'none'));
}};
</script></body></html>
"""


# ---- 4. the owner's labels -----------------------------------------------------------------

def parse_numbers(spec: str) -> list[int]:
    """'1,2,5-9' -> [1, 2, 5, 6, 7, 8, 9]; 'none' or '' -> []."""
    spec = (spec or "").strip().lower()
    if spec in ("", "none"):
        return []
    out = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = (int(x) for x in part.split("-", 1))
            out.extend(range(a, b + 1))
        elif part:
            out.append(int(part))
    return out


def apply_labels(man: dict, out_dir, *, laura: list[int], not_laura: list[int],
                 labelled_by: str) -> dict:
    """The manifest with the owner's labels. Refused unless every frame is labelled exactly
    once by a named person and every frame's bytes still match their sha256."""
    who = str(labelled_by or "").strip()
    if not who:
        raise LabelsRefused("a label must name the person who made it (labelled_by)")
    nums = {f["n"] for f in man["frames"]}
    both = set(laura) & set(not_laura)
    if both:
        raise LabelsRefused(f"frames {sorted(both)} are labelled both ways")
    given = set(laura) | set(not_laura)
    if given - nums:
        raise LabelsRefused(f"frames {sorted(given - nums)} are not on the sheet")
    if nums - given:
        raise LabelsRefused(f"frames {sorted(nums - given)} are unlabelled; every frame needs "
                            f"the owner's label (there is no default)")
    _verified(man, out_dir)
    at = _now()
    frames = [{**f, "label": LAURA if f["n"] in laura else NOT_LAURA,
               "labelled_by": who, "labelled_at": at} for f in man["frames"]]
    return {**man, "frames": frames, "labelled_at": at, "labelled_by": who}


def add_to_calibration_set(man: dict, out_dir, set_path, repo_root) -> dict:
    """Append the labelled frames to the committed calibration set (idempotent by sha256)."""
    if any(f.get("label") not in (LAURA, NOT_LAURA) for f in man["frames"]):
        raise LabelsRefused("the sheet is not fully labelled by the owner")
    root = Path(repo_root).resolve()
    sp = Path(set_path)
    cal = json.loads(sp.read_text())
    have = {s["sha256"] for s in cal["samples"]}
    added = 0
    for f, _ in _verified(man, out_dir):
        if f["sha256"] in have:
            continue
        rel = (Path(out_dir).resolve() / f["file"]).relative_to(root).as_posix()
        genuine = f["label"] == LAURA
        cal["samples"].append({
            "id": f"contact/{f['id']}", "path": rel, "label": f["label"], "face": "single",
            "sha256": f["sha256"],
            "source": (f"FLUX 3 frame generated on Laura's three canonical references "
                       f"({', '.join(r['sha256'][:8] for r in f['references'])}); labelled "
                       f"{'Laura' if genuine else 'NOT Laura'} by {f['labelled_by']} at "
                       f"{f['labelled_at']} (owner Decision 2)"),
            "licence": "Brambleloop-generated asset (no real person)"})
        added += 1
    sp.write_text(json.dumps(cal, indent=1) + "\n")
    return {"added": added, "samples": len(cal["samples"])}
