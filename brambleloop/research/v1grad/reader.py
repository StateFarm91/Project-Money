"""The independent structured reader for a flat textile product (throw / blanket), on the
pinned reader model (gpt-5), with one fixed question set asked identically of the reference and
of every candidate. Nothing in the prompt names what the product should be."""
from __future__ import annotations
import base64, hashlib, importlib.util, json, os, re, time, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
_spec = importlib.util.spec_from_file_location("bench1_reader", os.path.join(ROOT, "research", "bench1", "reader.py")); R1 = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(R1)

QUESTIONS = {
    "product_type": "one of: blanket_or_throw, pillow_or_cushion, garment, bag, scarf_or_wrap, rug, other",
    "shape": "one of: rectangle, square, round, other -- the outline of the piece as shown",
    "presentation": "one of: flat, folded, draped, worn, other -- how the piece is shown",
    "texture": "one of: cabled, ribbed, bobble_or_puff, waffle, star_or_cluster, colourwork_or_mosaic, lace, smooth, other -- cabled means raised twisted columns (strands crossing over each other) on the fabric",
    "cable_direction": "one of: along_the_length, across_the_width, none -- the direction the raised columns run relative to the piece's longer side",
    "cable_column_count": "integer number of raised cable columns you can count across the piece (omit if not countable)",
    "colour_count": "integer number of distinct yarn colours",
    "main_colour": "a short colour name",
    "edging": "one of: none, fringe, tassels, contrasting_border, scalloped_border, other -- the finish at the piece's edges",
    "extra_features": "list of any of: pockets, buttons, stripes, applique, embroidery, hood, ties, none",
    "handmade_crochet": "true if it reads as hand-crocheted, false if machine-knit or other",
}


def prompt() -> str:
    lines = "\n".join(f'  "{k}": {v}' for k, v in QUESTIONS.items())
    return ("This is a photograph or image of a textile product. Answer as JSON with these keys. Omit a key entirely if the image does not show enough to answer it; do not guess.\n"
            + lines + '\nAdd "notes": one short sentence on anything unusual, or an empty string.')


def read(image_path: str, timeout: float = 180.0) -> dict:
    data = open(image_path, "rb").read(); sha = hashlib.sha256(data).hexdigest()
    mime = "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
    body = {"model": R1.MODEL, "messages": [{"role": "system", "content": R1.SYSTEM}, {"role": "user", "content": [{"type": "text", "text": prompt()},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.standard_b64encode(data).decode()}", "detail": "high"}}]}], "max_completion_tokens": R1.MAX_OUT}
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode(), headers={"Authorization": f"Bearer {R1._key()}", "Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp: out = json.loads(resp.read().decode())
    u = out.get("usage", {}); tin, tout = int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0))
    text = (out.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    m = re.search(r"\{.*\}", text, re.S); answers = json.loads(m.group(0)) if m else {}
    return {"image": image_path, "image_sha256": sha, "model": R1.MODEL, "provider": "openai", "response_id": out.get("id"), "seconds": round(time.time() - t0, 1), "prompt_tokens": tin, "completion_tokens": tout,
            "cost_usd": round(tin * R1.PRICE["input"] / 1e6 + tout * R1.PRICE["output"] / 1e6, 5), "raw": text, "answers": answers}
