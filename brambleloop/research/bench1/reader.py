"""An independent structured reader for commercially material garment properties.

One question set, asked identically of the seller's photographs, the deterministic reference
and every generated candidate, so the answers can be compared like for like. The reader is
the same model family as the D judge (gpt-5), called with the image inline; nothing in the
prompt names what the product should be. An omitted key means the image did not show it.
"""
from __future__ import annotations
import base64, hashlib, json, os, re, time, urllib.request
MODEL = "gpt-5-2025-08-07"; PRICE = {"input": 1.25, "output": 10.0}; MAX_OUT = 3000
SYSTEM = ("You are a garment technologist describing exactly what a photograph of a knitted or crocheted garment shows. "
          "Report only what is visible. Say plainly when something cannot be seen.")
QUESTIONS = {
    "product_type": "one of: cardigan, pullover, vest, jacket, other",
    "front": "one of: open, overlapping, buttoned, zipped, tied, closed_other",
    "closure_count": "integer number of buttons, toggles or other fasteners visible (0 if none)",
    "front_band": "one of: ribbed_band, plain_band, shawl_collar, hood, none, other -- what runs along the front opening edges and neckline",
    "hem_band": "one of: ribbed, plain, none -- the band at the bottom hem",
    "cuffs": "one of: ribbed, gathered, plain, none",
    "pocket_count": "integer number of pockets visible",
    "pocket_position": "one of: hip, chest, none",
    "sleeve_length": "one of: long, three_quarter, short, sleeveless",
    "body_length": "one of: cropped, hip, mid_thigh, knee -- where the hem falls (if worn) or the body length relative to its width (if laid flat: 'hip' when about as long as wide, 'mid_thigh' when clearly longer than wide)",
    "texture": "one of: waffle_textured, ribbed_all_over, cabled, lace, smooth, other",
    "body_ridge_direction": "one of: vertical, horizontal, none -- the direction of the texture's ridge lines on the body panels",
    "colour_count": "integer number of distinct yarn colours",
    "main_colour": "a short colour name",
    "extra_features": "list of any of: stripes, hood, belt, buttons, fringe, embroidery, colour_blocks, lace_panels, none",
    "handmade_crochet": "true if it reads as hand-crocheted, false if machine-knit or other",
}


def _key() -> str:
    k = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not k and os.environ.get("OPENAI_API_KEY_FILE"):
        k = open(os.environ["OPENAI_API_KEY_FILE"]).read().strip()
    if not k: raise RuntimeError("no OpenAI credential (OPENAI_API_KEY or OPENAI_API_KEY_FILE)")
    return k


def prompt() -> str:
    lines = "\n".join(f'  "{k}": {v}' for k, v in QUESTIONS.items())
    return ("This is a photograph or image of a garment. Answer as JSON with these keys. Omit a key entirely if the image does not show enough to answer it; do not guess.\n"
            + lines + '\nAdd "notes": one short sentence on anything unusual, or an empty string.')


def read(image_path: str, timeout: float = 180.0) -> dict:
    data = open(image_path, "rb").read(); sha = hashlib.sha256(data).hexdigest()
    mime = "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
    body = {"model": MODEL, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": [{"type": "text", "text": prompt()},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.standard_b64encode(data).decode()}", "detail": "high"}}]}], "max_completion_tokens": MAX_OUT}
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode(), headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp: out = json.loads(resp.read().decode())
    u = out.get("usage", {}); tin, tout = int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0))
    text = (out.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    m = re.search(r"\{.*\}", text, re.S); answers = json.loads(m.group(0)) if m else {}
    return {"image": image_path, "image_sha256": sha, "response_id": out.get("id"), "seconds": round(time.time() - t0, 1), "prompt_tokens": tin, "completion_tokens": tout,
            "cost_usd": round(tin * PRICE["input"] / 1e6 + tout * PRICE["output"] / 1e6, 5), "raw": text, "answers": answers}
