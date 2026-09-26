"""The independent judge for Milestone D's photographic items, and the record it leaves.

WHAT IT IS. `milestone_d.assess` measures everything about the draped fabric that a ruler can
measure and leaves seven items UNKNOWN because they are judgements about a photograph:
whether the fabric reads as folding naturally, whether the light and shadows read as one real
light, whether the frame has ordinary photographic imperfection, and whether the yarn reads
as melted, the stitches as synthetic, the scene as sterile catalogue perfection. This module
puts those questions to a vision model that had no part in making the image -- the renders
are Mitsuba path traces of the certified geometry -- and records exactly what was asked, of
which model, at what cost, and what came back, criterion by criterion.

THE RULES, carried from `photoreal` (the committed realism judge) unchanged:

  * The judge never sees the standard as a checklist to agree with. Each item is put in the
    vocabulary of the FAILURE, True meaning the image is sound on that axis.
  * Unjudged is not passed. A key the model omits is UNKNOWN, never True.
  * This module decides; the model reports. An item is PASS only when every authoritative
    presentation view is sound on it, FAIL when any view is not, UNKNOWN otherwise.

WHY NOT `photoreal.judge` ITSELF. Its checks are the owner's rejections for a photograph of
a person wearing the garment (skin, hands, anatomy) and its provider is the Anthropic
gateway, for which this environment holds no credential. The seven D items are the
fabric-relevant half of the same B-700 standard. The provider here is OpenAI's chat
completions with the image inline; the model is pinned by its dated id and its list price is
written beside the tokens so the cost is arithmetic, not an estimate.

WHAT IS JUDGED. Only the authoritative renders already produced -- the draped views, camera
and oblique, of each swatch, at the geometry hash recorded in `milestone_d_<kind>.json`.
Nothing is re-rendered to please the judge.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import urllib.request

# The D items that are judgements, phrased so that True means the image is SOUND on that axis.
CHECKS: dict[str, str] = {
    "fabric_folds_naturally": ("the fabric's bends and hang read as cloth under its own weight "
                               "rather than a stiff, posed or arbitrarily warped shape"),
    "lighting_is_realistic": ("the light on the object is what a real lamp or window would "
                              "produce, with no contradictory or impossible illumination"),
    "shadows_are_coherent": ("shadows and highlights agree with one light situation"),
    "has_ordinary_photographic_imperfection": (
        "the frame has the ordinary imperfection of a photograph -- grain, slight unevenness "
        "of tone or focus, an unstyled detail -- rather than frictionless synthetic cleanliness"),
    "yarn_is_not_melted": ("the yarn reads as twisted, plied fibre with real surface rather "
                           "than a melted, smooth or plastic rope"),
    "stitch_texture_is_not_synthetic": ("the stitch texture reads as hand-worked crochet fabric "
                                        "rather than a tiled, repeated or computer-generated "
                                        "pattern"),
    "not_catalogue_perfect_sterility": ("the image is not sterile catalogue perfection: something "
                                        "in it is ordinary, imperfect or unarranged"),
}

# How `milestone_d`'s item names map onto the judge's keys (the rejects are inverted there).
ITEM_TO_CHECK = {
    "fabric_folds_naturally": "fabric_folds_naturally",
    "lighting_is_realistic": "lighting_is_realistic",
    "shadows_are_coherent": "shadows_are_coherent",
    "has_ordinary_photographic_imperfection": "has_ordinary_photographic_imperfection",
    "melted_yarn": "yarn_is_not_melted",
    "synthetic_stitch_texture": "stitch_texture_is_not_synthetic",
    "catalogue_perfect_sterility": "not_catalogue_perfect_sterility",
}

SYSTEM = (
    "You are a working photographer looking at an image and deciding whether it reads as a "
    "real photograph of a real object or as a computer-generated image. You are not judging "
    "whether it is attractive. Report what you can actually see, and say plainly when the "
    "image does not show you enough to tell."
)

# Pinned by dated id. Price basis: OpenAI list price for gpt-5 at the time of writing,
# USD 1.25 per million input tokens and USD 10.00 per million output tokens; the tokens are
# the provider's own usage report, so the cost is arithmetic on a stated basis.
MODEL = "gpt-5-2025-08-07"
PRICE_USD_PER_M = {"input": 1.25, "output": 10.00}
USD_TO_CAD = 1.37       # the same assumed rate the gateway's ledger uses
MAX_OUTPUT_TOKENS = 4000     # gpt-5 reasons inside this budget; 1500 left one view with no answer


def prompt() -> str:
    lines = [
        "This is an image of a crochet swatch. Answer as JSON. For each key give true if the "
        "statement holds, false if it does not, and omit the key entirely if the image does not "
        "show you enough to judge it. Do not guess: an omitted key is a useful answer and a "
        "wrong one is not.",
        "",
    ]
    for key, what in CHECKS.items():
        lines.append(f'  "{key}": {what}')
    lines.append("")
    lines.append('Add "notes": one or two short sentences naming anything that made the image '
                 "read as generated, or an empty string.")
    return "\n".join(lines)


def _key() -> str:
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        path = os.environ.get("OPENAI_API_KEY_FILE", "")
        if path and os.path.exists(path):
            key = open(path).read().strip()
    if not key:
        raise RuntimeError("no OpenAI credential in this environment (OPENAI_API_KEY or "
                           "OPENAI_API_KEY_FILE); the judge cannot run and nothing is judged")
    return key


def see(image_path: str, *, model: str = MODEL, timeout: float = 180.0) -> dict:
    """One call: the image inline, the prompt, the raw answer and the usage, nothing decided."""
    data = open(image_path, "rb").read()
    sha = hashlib.sha256(data).hexdigest()
    mime = "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": [
                {"type": "text", "text": prompt()},
                {"type": "image_url", "image_url": {
                    "url": f"data:{mime};base64,{base64.standard_b64encode(data).decode()}",
                    "detail": "high"}},
            ]},
        ],
        "max_completion_tokens": MAX_OUTPUT_TOKENS,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        out = json.loads(resp.read().decode())
    usage = out.get("usage", {})
    tin, tout = int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
    cost_usd = tin * PRICE_USD_PER_M["input"] / 1e6 + tout * PRICE_USD_PER_M["output"] / 1e6
    text = (out.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    return {"image": image_path, "image_sha256": sha, "model": out.get("model", model),
            "response_id": out.get("id"), "seconds": round(time.time() - t0, 1),
            "prompt_tokens": tin, "completion_tokens": tout,
            "reasoning_tokens": int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)),
            "cost_usd": round(cost_usd, 6), "cost_cad": round(cost_usd * USD_TO_CAD, 6),
            "price_basis": f"list, USD {PRICE_USD_PER_M['input']}/M in, {PRICE_USD_PER_M['output']}/M out",
            "raw": text}


def read(answer: dict) -> dict:
    """The closed vocabulary and real booleans only, as `photoreal.judge` reads its answer."""
    import re
    m = re.search(r"\{.*\}", answer.get("raw") or "", re.S)
    if not m:
        return {"judged": False, "error": "no JSON in the answer", "checks": {}, "notes": ""}
    try:
        parsed = json.loads(m.group(0))
    except ValueError as exc:
        return {"judged": False, "error": f"unreadable: {exc}"[:200], "checks": {}, "notes": ""}
    checks = {k: bool(parsed[k]) for k in CHECKS if k in parsed and isinstance(parsed[k], bool)}
    return {"judged": True, "checks": checks, "notes": str(parsed.get("notes") or "")[:400]}


def judge_views(image_paths: list[str], *, model: str = MODEL) -> dict:
    """Judge every authoritative view and decide each D item from ALL of them."""
    views = []
    for p in image_paths:
        ans = see(p, model=model)
        ans["reading"] = read(ans)
        views.append(ans)
    items = {}
    for item, key in ITEM_TO_CHECK.items():
        votes = [v["reading"]["checks"].get(key) for v in views]
        if any(x is False for x in votes):
            status = "FAIL"
        elif votes and all(x is True for x in votes):
            status = "PASS"
        else:
            status = "UNKNOWN"
        items[item] = {"status": status, "per_view": {os.path.basename(v["image"]): v["reading"]["checks"].get(key)
                                                      for v in views}}
    return {"model": model, "system": SYSTEM, "prompt": prompt(), "views": views, "items": items,
            "total_cost_usd": round(sum(v["cost_usd"] for v in views), 6),
            "total_cost_cad": round(sum(v["cost_cad"] for v in views), 6),
            "rule": ("an item is PASS only when every authoritative view is sound on it, FAIL when "
                     "any view is not, UNKNOWN when the judge could not tell on any view")}


if __name__ == "__main__":                              # pragma: no cover
    import sys
    kind, out_dir = sys.argv[1], sys.argv[2]
    tag = sys.argv[3] if len(sys.argv) > 3 else "plied"        # which authoritative set
    paths = [os.path.join(out_dir, f"{kind}_draped_{tag}_{v}.png") for v in ("camera", "oblique")]
    res = judge_views(paths)
    res["tag"] = tag
    name = f"judge_{kind}.json" if tag == "plied" else f"judge_{kind}_{tag}.json"
    with open(os.path.join(out_dir, name), "w") as f:
        json.dump(res, f, indent=1)
    for item, r in res["items"].items():
        print(f"{r['status']:7s} {item}: {r['per_view']}")
    for v in res["views"]:
        print(os.path.basename(v["image"]), v["model"], v["response_id"], f"{v['prompt_tokens']}+{v['completion_tokens']} tok",
              f"US${v['cost_usd']:.4f}", "notes:", v["reading"].get("notes", "")[:200])
    print("TOTAL US$%.4f (CA$%.4f)" % (res["total_cost_usd"], res["total_cost_cad"]))
