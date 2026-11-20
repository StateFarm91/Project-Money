"""Commercial benchmark 1: seller-photo reading, hero generation, gating, comparison. One
manifest (`out/bench1_manifest.json`) records every external call and its cost against the
US$5.00 ceiling; every candidate is gated automatically and nothing is cherry-picked.

Subcommands: `read_sellers` | `read_reference` | `generate <mode> <n>` | `gate` | `all`.
"""
from __future__ import annotations
import base64, hashlib, io, json, os, sys, time, urllib.request, urllib.error, uuid
from pathlib import Path
from PIL import Image
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]; OUT = HERE / "out"; GEN = OUT / "gen"; GEN.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "research" / "e5"))
import reader as R, gate as G                                                   # noqa: E402
SCRATCH = Path("/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad")
SELLER = [str(SCRATCH / "benchmark" / f"seller_{i}.jpg") for i in range(1, 5)]   # not in the repository
MANIFEST = OUT / "bench1_manifest.json"; CAP_USD = 5.00
os.environ.setdefault("OPENAI_API_KEY_FILE", str(SCRATCH / ".oaikey"))

REFS_BY = {v: {"rgb": str(OUT / f"{v}_flatlay.png"), "mask": str(OUT / f"{v}_mask.png"), "normal": str(OUT / f"{v}_normal.png")} for v in ("ref", "ref2", "ref3")}
REFS = REFS_BY["ref"]; OUT_SIZE = {"ref": "1024x1024", "ref2": "1536x1024", "ref3": "1536x1024"}
# Presentation only. Names no stitch, count, pocket, band, length or construction: everything
# structural must come from the reference. The scene is a simple neutral hero.
PROMPT = ("The first image is a flat computer rendering of a hand-crocheted garment laid out flat. Make a real product "
          "photograph of that same physical garment for a handmade marketplace listing: laid flat exactly as shown, seen "
          "from directly above, on a plain pale linen surface. Keep the garment exactly as shown: the same outline, the "
          "same proportions, every part where it is, the same colour everywhere. The second image is the outline mask and "
          "the third shows the surface relief; use them only to keep the outline, position and surface placement exactly. "
          "Replace the rendered material with real worsted-weight acrylic yarn as it actually crochets up: a matte, slightly "
          "fuzzy surface with visible stitch texture, ordinary handmade unevenness, soft window daylight from one side, "
          "gentle shadows, an ordinary camera with a little grain. No text, no props, nothing else in frame.")
# Round 2, presentation only: the judge failed round 1 on "catalogue-perfect sterility" and
# "folds naturally" (a perfectly symmetrical, perfectly flat laydown). This asks for an
# ordinary hand-placed laydown and nothing else; every structural sentence is unchanged.
PROMPT_V2 = PROMPT.replace("laid flat exactly as shown, seen from directly above, on a plain pale linen surface.",
                           "laid flat as shown, seen from directly above, on a plain pale linen cloth that has been used and has its ordinary creases. "
                           "It was placed by hand, not styled: very slightly askew, one sleeve resting a little differently from the other, the fabric "
                           "settling with small natural ripples and shadows rather than lying perfectly flat.")
PROMPTS = {"v1": PROMPT, "v2": PROMPT_V2}
MODES = {
    "oa15_hifi": dict(provider="openai", model="gpt-image-1.5", params={"input_fidelity": "high", "quality": "medium", "size": "1024x1024"}),
    "g3pro": dict(provider="google", model="gemini-3-pro-image", params={"imageSize": "1K"}, usd_list=0.134),
}
OA_RATES = {"text_in": 5.0, "image_in": 10.0, "image_out": 40.0}


def _key(name): return (SCRATCH / name).read_text().strip()
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def load():
    if MANIFEST.exists(): return json.load(open(MANIFEST))
    return {"cap_usd": CAP_USD, "prompt": PROMPT, "reference_sha256": {k: sha(v) for k, v in REFS.items()}, "calls": [], "runs": []}
def save(m): m["spent_usd"] = round(sum(c.get("usd", 0) for c in m["calls"]) + sum(r.get("usd", 0) for r in m["runs"]), 4); json.dump(m, open(MANIFEST, "w"), indent=1, default=str)


def _multipart(fields, files):
    b = f"----b1{uuid.uuid4().hex}"; out = bytearray()
    for k, v in fields.items(): out += f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    for name, fname, data in files: out += f"--{b}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{fname}\"\r\nContent-Type: image/png\r\n\r\n".encode() + data + b"\r\n"
    out += f"--{b}--\r\n".encode(); return b, bytes(out)


def draw(mode_key, PROMPT=PROMPT, refv="ref"):
    mode = MODES[mode_key]; REFS = REFS_BY[refv]
    if mode["provider"] == "openai":
        fields = {"model": mode["model"], "prompt": PROMPT, "n": "1", **{k: str(v) for k, v in mode["params"].items()}, "size": OUT_SIZE[refv]}
        files = [("image[]", Path(REFS[r]).name, Path(REFS[r]).read_bytes()) for r in ("rgb", "mask", "normal")]
        b, body = _multipart(fields, files)
        req = urllib.request.Request("https://api.openai.com/v1/images/edits", data=body, method="POST")
        req.add_header("authorization", f"Bearer {_key('.oaikey')}"); req.add_header("content-type", f"multipart/form-data; boundary={b}")
        with urllib.request.urlopen(req, timeout=400) as r: d = json.loads(r.read().decode())
        raw = base64.b64decode(d["data"][0]["b64_json"]); u = d.get("usage") or {}; det = u.get("input_tokens_details") or {}
        usd = (det.get("text_tokens", 0) * OA_RATES["text_in"] + det.get("image_tokens", 0) * OA_RATES["image_in"] + u.get("output_tokens", 0) * OA_RATES["image_out"]) / 1e6
        return raw, {"usage": u, "usd": round(usd, 5), "price_basis": "usage tokens at gpt-image-1 list rates"}
    parts = [{"text": PROMPT}] + [{"inlineData": {"mimeType": "image/png", "data": base64.b64encode(Path(REFS[r]).read_bytes()).decode()}} for r in ("rgb", "mask", "normal")]
    body = {"contents": [{"parts": parts}], "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"imageSize": mode["params"]["imageSize"]}}}
    req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{mode['model']}:generateContent", data=json.dumps(body).encode(), method="POST")
    req.add_header("content-type", "application/json"); req.add_header("x-goog-api-key", _key(".gkey"))
    with urllib.request.urlopen(req, timeout=300) as r: d = json.loads(r.read().decode())
    for c in d.get("candidates", []):
        for p in (c.get("content") or {}).get("parts", []):
            inl = p.get("inlineData") or p.get("inline_data")
            if inl and inl.get("data"): return base64.b64decode(inl["data"]), {"usage": d.get("usageMetadata"), "usd": mode["usd_list"], "price_basis": "list"}
    raise RuntimeError(f"google answered without an image: {json.dumps(d)[:200]}")


def read_images(m, label, paths):
    out = {}
    for p in paths:
        key = f"{label}:{os.path.basename(p)}"
        prior = next((c for c in m["calls"] if c["key"] == key and c["image_sha256"] == sha(p)), None)
        if prior: out[os.path.basename(p)] = prior["answers"]; continue
        r = R.read(p); m["calls"].append({"key": key, "kind": "reader", "image_sha256": r["image_sha256"], "response_id": r["response_id"], "usd": r["cost_usd"], "answers": r["answers"], "raw": r["raw"][:1500]}); save(m)
        out[os.path.basename(p)] = r["answers"]; print(key, json.dumps(r["answers"])[:300])
    return out


def cmd_read_sellers():
    m = load(); ans = read_images(m, "seller", SELLER); json.dump(ans, open(OUT / "seller_photos.json", "w"), indent=1); save(m)
    pt_props = {k: G.properties(v) for k, v in ans.items()}
    json.dump({"note": "the seller's photographs read by the same reader as every candidate; each answer judged against Product Truth's expectation", "readings": ans, "vs_product_truth": pt_props},
              open(OUT / "seller_vs_product_truth.json", "w"), indent=1)
    for k, v in pt_props.items(): print(k, {a: b["status"] for a, b in v.items()})


def cmd_read_reference():
    m = load(); ans = read_images(m, "reference", [REFS["rgb"]]); json.dump(ans, open(OUT / "reference_reading.json", "w"), indent=1); save(m)
    print("reference:", {k: v["status"] for k, v in G.properties(list(ans.values())[0]).items()})


def cmd_generate(mode_key, n, pv="v1", refv="ref"):
    m = load(); m.setdefault("prompts", {})[pv] = PROMPTS[pv]; PROMPT = PROMPTS[pv]
    m.setdefault("references", {})[refv] = {k: sha(v) for k, v in REFS_BY[refv].items()}
    for _ in range(n):
        if m.get("spent_usd", 0) + 0.30 > CAP_USD: print("ceiling reached; not drawing"); break
        k = 1 + sum(1 for r in m["runs"] if r["mode"] == mode_key); t0 = time.time()
        row = {"mode": mode_key, "draw": k, "prompt_version": pv, "reference_version": refv, "model": MODES[mode_key]["model"], "params": {**MODES[mode_key]["params"], "size": OUT_SIZE[refv]}, "reference_sha256": m["references"][refv], "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest()}
        try:
            raw, meta = draw(mode_key, PROMPT, refv); img = Image.open(io.BytesIO(raw)).convert("RGB"); dst = GEN / f"{mode_key}_{k}.png"; img.save(dst)
            row.update(ok=True, path=str(dst), output_sha256=sha(dst), seconds=round(time.time() - t0, 1), **meta)
        except urllib.error.HTTPError as exc: row.update(ok=False, error=f"{exc.code}: {exc.read().decode(errors='replace')[:300]}", usd=0.0)
        except Exception as exc: row.update(ok=False, error=f"{type(exc).__name__}: {str(exc)[:300]}", usd=0.0)  # noqa: BLE001
        m["runs"].append(row); save(m); print(json.dumps({a: row.get(a) for a in ("mode", "draw", "ok", "output_sha256", "seconds", "usd", "error")}))
    print("spent US$", m["spent_usd"])


def cmd_gate():
    m = load(); ref_ans = json.load(open(OUT / "reference_reading.json")); ref_ans = list(ref_ans.values())[0]
    from brambleloop.visual import d_judge as DJ
    results = json.load(open(OUT / "bench1_gate.json")) if (OUT / "bench1_gate.json").exists() else {}
    for run in m["runs"]:
        if not run.get("ok"): continue
        key = f"{run['mode']}_{run['draw']}"
        if key in results and results[key]["output_sha256"] == run["output_sha256"]: continue
        det = G.deterministic(run["path"], run.get("reference_version", "ref"))
        ans = read_images(m, "candidate", [run["path"]])[os.path.basename(run["path"])]
        props = G.properties(ans, ref_ans)
        cache = OUT / f"judge_{key}.json"; j = json.load(open(cache)) if cache.exists() else None
        if not (j and j["views"][0].get("image_sha256") == run["output_sha256"]):
            j = DJ.judge_views([run["path"]]); json.dump(j, open(cache, "w"), indent=1)
            m["calls"].append({"key": f"judge:{key}", "kind": "judge", "image_sha256": run["output_sha256"], "response_id": j["views"][0]["response_id"], "usd": j["total_cost_usd"]}); save(m)
        judge = {k: v["status"] for k, v in j["items"].items()}
        v = G.verdict(det, props, judge)
        results[key] = {"mode": run["mode"], "draw": run["draw"], "prompt_version": run.get("prompt_version", "v1"), "reference_version": run.get("reference_version", "ref"), "output_sha256": run["output_sha256"], "usd_generation": run.get("usd"), "deterministic": det, "properties": props, "reader_answers": ans, "judge": judge,
                        "judge_notes": j["views"][0]["reading"].get("notes", ""), "verdict": v}
        json.dump(results, open(OUT / "bench1_gate.json", "w"), indent=1, default=str)
        print(f"{key}: {v['status']} | det {det['status']} iou {det['items'].get('silhouette', {}).get('evidence', {}).get('iou_aligned')} drift {det['items'].get('proportions', {}).get('evidence', {}).get('drift')} | material fails {v['material_failures']} unknown {v['unknown_material']} | judge fails {v['judge_failures']} | {results[key]['judge_notes'][:90]}")
    save(m); print("spent US$", m["spent_usd"])


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "read_sellers": cmd_read_sellers()
    elif c == "read_reference": cmd_read_reference()
    elif c == "generate": cmd_generate(sys.argv[2], int(sys.argv[3]), sys.argv[4] if len(sys.argv) > 4 else "v1", sys.argv[5] if len(sys.argv) > 5 else "ref")
    elif c == "gate": cmd_gate()
