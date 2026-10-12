"""Commercial benchmark 2: the independent structured reader, Bench1's reader with the question
set extended for this product (hood, hood edge, button band, star-stitch texture, row
direction of the clusters). One question set, asked identically of the designer's photographs
(privately), the deterministic reference and every candidate. Nothing in the prompt names what
the product should be. An omitted key means the image did not show it.
"""
from __future__ import annotations
import base64, hashlib, json, os, re, sys, time, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
import importlib.util as _ilu   # the Bench1 reader under its own name (both files are called reader.py): model, price, system prompt, credential lookup
_spec = _ilu.spec_from_file_location("bench1_reader", os.path.join(ROOT, "research", "bench1", "reader.py")); R1 = _ilu.module_from_spec(_spec); _spec.loader.exec_module(R1)

QUESTIONS = dict(R1.QUESTIONS)
QUESTIONS["texture"] = ("one of: star_stitch, waffle_textured, ribbed_all_over, puff_or_bobble, shell_or_fan, cabled, lace, smooth, other -- "
                        "star_stitch means rows of star-shaped clusters whose loops converge on a small central eye, with a thin plain row between the rows of stars")
QUESTIONS["front_band"] = "one of: ribbed_band, plain_band, shawl_collar, none, other -- what runs along the front opening edges (answer for the band, not the hood)"
QUESTIONS["hood"] = "one of: attached_hood, collar, none"
QUESTIONS["hood_edge"] = "one of: ribbed_band, plain, none -- the finish along the hood's face edge (omit if there is no hood)"
QUESTIONS["cluster_rows_direction"] = "one of: horizontal, vertical, none -- the direction of the rows of textured clusters on the body panels"
QUESTIONS["extra_features"] = "list of any of: stripes, hood, belt, buttons, pockets, fringe, embroidery, colour_blocks, lace_panels, none"


def prompt() -> str:
    lines = "\n".join(f'  "{k}": {v}' for k, v in QUESTIONS.items())
    return ("This is a photograph or image of a garment. Answer as JSON with these keys. Omit a key entirely if the image does not show enough to answer it; do not guess.\n"
            + lines + '\nAdd "notes": one short sentence on anything unusual, or an empty string.')


def read(image_path: str, timeout: float = 180.0) -> dict:
    """The pinned reader (gpt-5). When the OpenAI account has no credit (429 insufficient_quota),
    the declared substitute (see substitute.py) answers the same prompt; the record says so."""
    import urllib.error
    if os.environ.get("BENCH2_VISION") == "substitute": return read_substitute(image_path)
    try: return read_pinned(image_path, timeout)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        if exc.code == 429 and "insufficient_quota" in body: return read_substitute(image_path)
        raise


def read_substitute(image_path: str) -> dict:
    import substitute as S
    r = S.vision(image_path, R1.SYSTEM, prompt()); r["answers"] = S.parse_json(r["raw"]); return r


def read_pinned(image_path: str, timeout: float = 180.0) -> dict:
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
