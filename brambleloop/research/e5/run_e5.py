"""E5 — structure-locked photorealisation benchmark, generation side.

One frozen package (research/e5/frozen.py), many provider/model/modes. Each mode is a named,
fully recorded configuration: provider, endpoint, every control parameter, which frozen
images are sent and as what, and the prompt. Every draw records the request digest, output
digest, latency and cost -- measured where the provider reports it (OpenAI usage tokens,
BFL credit balance before and after), list price otherwise, with the basis named.

The prompts name presentation only. No stitch family, count, construction, fold or answer
is put into the text to force compliance; the structure has to be held by the mode.

Ceiling US$3.00 for the whole of E5 (generation and judge together); the manifest carries
the running total and this refuses to draw past it.
"""
import base64, hashlib, io, json, os, sys, time, urllib.request, urllib.error, uuid
from pathlib import Path
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT / "src"))
import frozen as F
from PIL import Image

SCRATCH = Path("/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad")
OUT = HERE / "out"; GEN = OUT / "gen"; GEN.mkdir(parents=True, exist_ok=True)
MANIFEST = OUT / "e5_manifest.json"
CAP_USD = 3.00

# --- prompts (presentation only) -------------------------------------------------------
PROMPT_EDIT_3REF = (  # E4 round 2, verbatim: the prompt that produced real wool on 5 of 10 draws
    "The first image is a computer rendering of a crocheted swatch resting on a plain wooden ball. "
    "Make a real product photograph of that same physical object for a handmade craft marketplace "
    "listing. Keep the piece exactly as shown: the same outline, the same proportions, every strand "
    "of yarn where it is, the same colour. The second image is the outline mask of the piece and "
    "the third shows its surface orientation; use them only to keep the piece's outline, position "
    "and surface placement exactly. Replace the rendered material with real spun wool yarn: a matte "
    "surface with a fine fibre halo, a slightly uneven twist, no plastic sheen, no stripes, no beads "
    "or knobs anywhere along the strands. Soft "
    "window daylight from one side, a plain linen tablecloth with its ordinary creases, an ordinary "
    "camera with a little grain. No text, nothing else in frame.")
PROMPT_EDIT_1REF = (  # the same, without the sentence about images that are not sent
    "This image is a computer rendering of a crocheted swatch resting on a plain wooden ball. "
    "Make a real product photograph of that same physical object for a handmade craft marketplace "
    "listing. Keep the piece exactly as shown: the same outline, the same proportions, every strand "
    "of yarn where it is, the same colour. Replace the rendered material with real spun wool yarn: a matte "
    "surface with a fine fibre halo, a slightly uneven twist, no plastic sheen, no stripes, no beads "
    "or knobs anywhere along the strands. Soft window daylight from one side, a plain linen "
    "tablecloth with its ordinary creases, an ordinary camera with a little grain. No text, nothing "
    "else in frame.")
PROMPT_INPAINT = (  # mask modes: only the yarn region is editable, so the scene is not described
    "Replace the rendered yarn in the editable region with real spun wool yarn photographed with an "
    "ordinary camera: a matte surface with a fine fibre halo, a slightly uneven twist, no plastic "
    "sheen, no stripes, no beads or knobs anywhere along the strands, the same colour, every strand "
    "exactly where it is. Soft daylight from one side, a little grain.")

REF = {"rgb": F.path("reference_rgb"), "mask": F.path("mask"), "normal": F.path("normal"),
       "editmask_openai": str(OUT / "sc_camera_editmask_openai.png"), "editmask_bfl": str(OUT / "sc_camera_editmask_bfl.png")}

# --- modes ------------------------------------------------------------------------------
# price_basis: "usage" = computed from the provider's own token report at the listed rates;
# "credits" = BFL balance delta at US$0.01 per credit (BFL's published rate); "list" = table.
MODES = {
    "oa1_hifi": dict(provider="openai", model="gpt-image-1", endpoint="images/edits", refs=["rgb", "mask", "normal"], prompt=PROMPT_EDIT_3REF,
                     params={"input_fidelity": "high", "quality": "medium", "size": "1024x1024"}, price_basis="usage",
                     why="the one OpenAI image model with an explicit reference-fidelity control (verified on the wire: gpt-image-2 and 2.5 refuse it)"),
    "oa15_hifi": dict(provider="openai", model="gpt-image-1.5", endpoint="images/edits", refs=["rgb", "mask", "normal"], prompt=PROMPT_EDIT_3REF,
                      params={"input_fidelity": "high", "quality": "medium", "size": "1024x1024"}, price_basis="usage",
                      why="the newer model that still accepts input_fidelity (verified); rates assumed equal to gpt-image-1 until billed"),
    "oa1_hifi_mask": dict(provider="openai", model="gpt-image-1", endpoint="images/edits", refs=["rgb"], mask="editmask_openai", prompt=PROMPT_INPAINT,
                          params={"input_fidelity": "high", "quality": "medium", "size": "1024x1024"}, price_basis="usage",
                          why="regional edit: only the yarn region (silhouette dilated 3 px) is editable, so silhouette and proportions are locked by construction"),
    "bfl_fill": dict(provider="bfl", model="flux-pro-1.0-fill", endpoint="/v1/flux-pro-1.0-fill", refs=["rgb"], mask="editmask_bfl", prompt=PROMPT_INPAINT,
                     params={"guidance": 60, "steps": 50, "prompt_upsampling": False, "output_format": "png"}, price_basis="credits",
                     why="mask inpainting with an explicit guidance control; the silhouette is locked by construction"),
    "bfl_flex": dict(provider="bfl", model="flux-2-flex", endpoint="/v1/flux-2-flex", refs=["rgb"], prompt=PROMPT_EDIT_1REF,
                     params={"guidance": 5.0, "steps": 50, "prompt_upsampling": False, "width": 1024, "height": 1024, "output_format": "png"}, price_basis="credits",
                     why="the FLUX.2 variant that exposes guidance and steps and is documented for preserving small details"),
    "bfl_2max": dict(provider="bfl", model="flux-2-max", endpoint="/v1/flux-2-max", refs=["rgb"], prompt=PROMPT_EDIT_1REF,
                     params={"disable_pup": True, "width": 1024, "height": 1024, "output_format": "png"}, price_basis="credits",
                     why="documented as the strongest editing consistency in the FLUX.2 family"),
    "bfl_kmax": dict(provider="bfl", model="flux-kontext-max", endpoint="/v1/flux-kontext-max", refs=["rgb"], prompt=PROMPT_EDIT_1REF,
                     params={"prompt_upsampling": False, "output_format": "png"}, price_basis="credits",
                     why="the dedicated editing model of the previous generation, for comparison"),
    "g3pro": dict(provider="google", model="gemini-3-pro-image", refs=["rgb", "mask", "normal"], prompt=PROMPT_EDIT_3REF,
                  params={"imageSize": "1K"}, price_basis="list", usd_list=0.134,
                  why="Google's high-fidelity editing model, takes several images; no fidelity parameter exists to set"),
    "g31flash": dict(provider="google", model="gemini-3.1-flash-image", refs=["rgb", "mask", "normal"], prompt=PROMPT_EDIT_3REF,
                     params={"imageSize": "1K"}, price_basis="list", usd_list=0.067,
                     why="the gateway's own Google candidate at 1K"),
}
# OpenAI image-token rates (gpt-image-1 list, USD per million): text in 5, image in 10, image out 40.
OA_RATES = {"text_in": 5.0, "image_in": 10.0, "image_out": 40.0}


def _key(name):
    return (SCRATCH / name).read_text().strip()


def _b64(p):
    return base64.b64encode(Path(p).read_bytes()).decode()


def _post_json(url, headers, body, timeout=300):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST")
    req.add_header("content-type", "application/json")
    for k, v in headers.items(): req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _get_json(url, headers, timeout=60):
    req = urllib.request.Request(url, method="GET")
    for k, v in headers.items(): req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _multipart(fields, files):
    boundary = f"----e5{uuid.uuid4().hex}"; out = bytearray()
    for k, v in fields.items():
        out += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    for name, fname, data in files:
        out += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{fname}\"\r\nContent-Type: image/png\r\n\r\n".encode() + data + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return boundary, bytes(out)


def _http_error(exc):
    try:
        return f"{exc.code}: {exc.read().decode(errors='replace')[:400]}"
    except Exception:  # noqa: BLE001
        return str(exc)


# --- provider clients -------------------------------------------------------------------
def draw_openai(mode):
    key = _key(".oaikey")
    fields = {"model": mode["model"], "prompt": mode["prompt"], "n": "1", **{k: str(v) for k, v in mode["params"].items()}}
    files = [("image[]", Path(REF[r]).name, Path(REF[r]).read_bytes()) for r in mode["refs"]]
    if mode.get("mask"): files.append(("mask", "mask.png", Path(REF[mode["mask"]]).read_bytes()))
    boundary, body = _multipart(fields, files)
    req = urllib.request.Request("https://api.openai.com/v1/images/edits", data=body, method="POST")
    req.add_header("authorization", f"Bearer {key}"); req.add_header("content-type", f"multipart/form-data; boundary={boundary}")
    with urllib.request.urlopen(req, timeout=400) as r:
        d = json.loads(r.read().decode())
    raw = base64.b64decode(d["data"][0]["b64_json"]); u = d.get("usage") or {}
    det = u.get("input_tokens_details") or {}
    cost = (det.get("text_tokens", 0) * OA_RATES["text_in"] + det.get("image_tokens", 0) * OA_RATES["image_in"] + u.get("output_tokens", 0) * OA_RATES["image_out"]) / 1e6
    return raw, {"usage": u, "usd": round(cost, 5), "price_basis": "usage tokens at gpt-image-1 list rates (5/10/40 USD per M)"}


def draw_bfl(mode):
    key = _key(".bflkey"); h = {"x-key": key}
    before = _get_json("https://api.bfl.ai/v1/credits", h)["credits"]
    body = {"prompt": mode["prompt"], **mode["params"]}
    if mode.get("mask"):
        body["image"] = _b64(REF["rgb"]); body["mask"] = _b64(REF[mode["mask"]])
    else:
        body["input_image"] = _b64(REF[mode["refs"][0]])
        for i, r in enumerate(mode["refs"][1:], start=2): body[f"input_image_{i}"] = _b64(REF[r])
    d = _post_json("https://api.bfl.ai" + mode["endpoint"], h, body)
    poll = d["polling_url"]; status = ""
    for _ in range(200):
        d = _get_json(poll, h); status = str(d.get("status", "")).lower()
        if status in ("ready", "succeeded", "complete", "completed"): break
        if status in ("error", "failed", "content_moderated", "request_moderated"): raise RuntimeError(f"bfl {status}: {json.dumps(d)[:300]}")
        time.sleep(2)
    else:
        raise RuntimeError("bfl did not finish in 400 s")
    url = d["result"]["sample"]
    with urllib.request.urlopen(url, timeout=120) as r: raw = r.read()
    after = _get_json("https://api.bfl.ai/v1/credits", h)["credits"]
    return raw, {"credits_before": before, "credits_after": after, "credits_used": round(before - after, 3), "usd": round((before - after) * 0.01, 4), "price_basis": "BFL credit balance delta at US$0.01 per credit"}


def draw_google(mode):
    key = _key(".gkey")
    parts = [{"text": mode["prompt"]}] + [{"inlineData": {"mimeType": "image/png", "data": _b64(REF[r])}} for r in mode["refs"]]
    body = {"contents": [{"parts": parts}], "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"imageSize": mode["params"]["imageSize"]}}}
    d = _post_json(f"https://generativelanguage.googleapis.com/v1beta/models/{mode['model']}:generateContent", {"x-goog-api-key": key}, body)
    raw = None
    for c in d.get("candidates", []):
        for p in (c.get("content") or {}).get("parts", []):
            inl = p.get("inlineData") or p.get("inline_data")
            if inl and inl.get("data"): raw = base64.b64decode(inl["data"]); break
        if raw: break
    if raw is None: raise RuntimeError(f"google answered without an image: {json.dumps(d)[:300]}")
    return raw, {"usage": d.get("usageMetadata"), "usd": mode["usd_list"], "price_basis": f"list, US${mode['usd_list']} per image (gateway table / Google pricing page, 1K)"}


CLIENTS = {"openai": draw_openai, "bfl": draw_bfl, "google": draw_google}


def load_manifest():
    if MANIFEST.exists(): return json.load(open(MANIFEST))
    return {"cap_usd": CAP_USD, "frozen": F.verify(), "geometry_sha256": F.GEOMETRY_SHA256, "modes": {k: {a: b for a, b in v.items()} for k, v in MODES.items()}, "runs": []}


def spent(man):
    return round(sum(r.get("usd", 0.0) for r in man["runs"]) + man.get("judge_usd", 0.0), 4)


def run(mode_key, draws=1, tag=None):
    man = load_manifest(); man["frozen"] = F.verify()  # every test starts by re-hashing the package
    mode = MODES[mode_key]; man["modes"][mode_key] = dict(mode)
    for _ in range(draws):
        if spent(man) + 0.20 > CAP_USD:
            print(f"ceiling: spent US${spent(man)} of {CAP_USD}; not drawing"); break
        n = 1 + sum(1 for r in man["runs"] if r["mode"] == mode_key)
        row = {"mode": mode_key, "draw": n, "provider": mode["provider"], "model": mode["model"], "params": mode["params"], "refs": mode["refs"], "mask": mode.get("mask"),
               "conditioning_sha256": {r: F.sha256(REF[r]) for r in mode["refs"] + ([mode["mask"]] if mode.get("mask") else [])},
               "prompt_sha256": hashlib.sha256(mode["prompt"].encode()).hexdigest(), "geometry_sha256": F.GEOMETRY_SHA256, "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        t0 = time.time()
        try:
            raw, meta = CLIENTS[mode["provider"]](mode)
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            dst = GEN / f"{mode_key}_{n}.png"; img.save(dst)
            row.update(ok=True, path=str(dst), output_sha256=F.sha256(str(dst)), size=list(img.size), seconds=round(time.time() - t0, 1), **meta)
        except urllib.error.HTTPError as exc:
            row.update(ok=False, error=_http_error(exc), seconds=round(time.time() - t0, 1), usd=0.0)
        except Exception as exc:  # noqa: BLE001
            row.update(ok=False, error=f"{type(exc).__name__}: {str(exc)[:300]}", seconds=round(time.time() - t0, 1), usd=0.0)
        man["runs"].append(row); man["spent_usd"] = spent(man)
        json.dump(man, open(MANIFEST, "w"), indent=1)
        print(json.dumps({k: row.get(k) for k in ("mode", "draw", "ok", "output_sha256", "seconds", "usd", "credits_used", "error")}))
    print(f"E5 spent so far US${spent(man)} of {CAP_USD}")


if __name__ == "__main__":
    modes = sys.argv[1].split(",") if len(sys.argv) > 1 else list(MODES)
    draws = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    for m in modes: run(m, draws)
