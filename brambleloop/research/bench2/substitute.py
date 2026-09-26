"""Declared substitute vision provider for Bench2: Google Gemini, used ONLY because the OpenAI
account answered `insufficient_quota` (credit balance exhausted) on 2026-09-26 during this
benchmark, which blocks the pinned reader (gpt-5), the pinned D judge (gpt-5) and
gpt-image-1.5 at once. Every call made through here is recorded with `provider: google` and
the model, so the report can say exactly which readings and judgements came from the
substitute. The prompts are the pinned ones, unchanged. Re-running the pinned models when
credit returns is the recorded follow-up; nothing here re-decides a bar.

Price basis (ASSUMED, upper bound, declared): US$2.50 per M input tokens, US$15 per M output
tokens for gemini-3.1-pro-preview; recorded per call from usage tokens.
"""
from __future__ import annotations
import base64, hashlib, json, os, re, time, urllib.request
from pathlib import Path
SCRATCH = Path("/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad")
MODEL = "gemini-3.1-pro-preview"; PRICE = {"input": 2.50, "output": 15.0}; WHY = "OpenAI credit_balance_exhausted (HTTP 429 insufficient_quota) on 2026-09-26; pinned gpt-5 reader/judge and gpt-image-1.5 unavailable"


def _key() -> str:
    k = (os.environ.get("GOOGLE_API_KEY") or "").strip()
    if not k: k = (SCRATCH / ".gkey").read_text().strip()
    return k


def vision(image_path: str, system: str, prompt: str, *, model: str = MODEL, timeout: float = 240.0) -> dict:
    """One image + the pinned system/prompt text -> the raw answer, usage and cost, nothing decided.
    Same shape as the pinned readers' answers so the callers do not change."""
    data = open(image_path, "rb").read(); sha = hashlib.sha256(data).hexdigest()
    mime = "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": prompt}, {"inlineData": {"mimeType": mime, "data": base64.standard_b64encode(data).decode()}}]}],
            "generationConfig": {"responseMimeType": "application/json"}}
    req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", data=json.dumps(body).encode(), method="POST")
    req.add_header("content-type", "application/json"); req.add_header("x-goog-api-key", _key())
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r: out = json.loads(r.read().decode())
    u = out.get("usageMetadata") or {}; tin = int(u.get("promptTokenCount", 0)); tout = int(u.get("candidatesTokenCount", 0)) + int(u.get("thoughtsTokenCount", 0))
    parts = ((out.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    return {"image": image_path, "image_sha256": sha, "model": model, "provider": "google", "substitute_for": "gpt-5-2025-08-07", "why": WHY,
            "response_id": out.get("responseId"), "seconds": round(time.time() - t0, 1), "prompt_tokens": tin, "completion_tokens": tout,
            "cost_usd": round(tin * PRICE["input"] / 1e6 + tout * PRICE["output"] / 1e6, 6), "cost_cad": round((tin * PRICE["input"] / 1e6 + tout * PRICE["output"] / 1e6) * 1.37, 6),
            "price_basis": "ASSUMED upper-bound list, USD 2.50/M in, 15/M out (incl. thinking tokens)", "raw": text}


def parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    try: return json.loads(m.group(0)) if m else {}
    except ValueError: return {}


def judge_views(image_paths: list[str]) -> dict:
    """The D judge's pinned system prompt, question set, reading and decision rule, on the
    substitute model. Same output shape as `brambleloop.visual.d_judge.judge_views`."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
    from brambleloop.visual import d_judge as DJ
    views = []
    for p in image_paths:
        ans = vision(p, DJ.SYSTEM, DJ.prompt()); ans["reading"] = DJ.read(ans); views.append(ans)
    items = {}
    for item, key in DJ.ITEM_TO_CHECK.items():
        votes = [v["reading"]["checks"].get(key) for v in views]
        status = "FAIL" if any(x is False for x in votes) else ("PASS" if votes and all(x is True for x in votes) else "UNKNOWN")
        items[item] = {"status": status, "per_view": {os.path.basename(v["image"]): v["reading"]["checks"].get(key) for v in views}}
    return {"model": MODEL, "provider": "google", "substitute_for": DJ.MODEL, "why": WHY, "system": DJ.SYSTEM, "prompt": DJ.prompt(), "views": views, "items": items,
            "total_cost_usd": round(sum(v["cost_usd"] for v in views), 6), "total_cost_cad": round(sum(v["cost_cad"] for v in views), 6), "rule": "as the pinned judge: PASS only when every view is sound on the item, FAIL when any is not, else UNKNOWN"}
