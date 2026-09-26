"""Commercial benchmark 2: freeze, designer-photo reading (private), reference reading, hero
generation, gating, private comparison. One manifest (`out/bench2_manifest.json`) records the
frozen size and its reason, the Product Truth and reference digests, every external call and
its cost against the US$5.00 ceiling; every candidate is gated automatically.

Subcommands: `freeze` | `read_designer` | `read_reference` | `generate <mode> <n> [pv] [refv]` | `gate` | `compare`.
"""
from __future__ import annotations
import base64, hashlib, io, json, os, sys, time, urllib.request, urllib.error, uuid
from pathlib import Path
from PIL import Image
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]; OUT = HERE / "out"; GEN = OUT / "gen"; GEN.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT / "src"))
import reader as R, gate as G, star_identity as SI                                # noqa: E402
SCRATCH = Path("/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad")
PDF_IMAGES = SCRATCH / "bench2" / "pdf_images"   # the designer's photographs: never in the repository
DESIGNER = {"cover_flatlay": "p1_0_X0.jpg", "gallery_toddler_worn": "p13_0_X61.jpg", "gallery_baby_worn": "p13_2_X63.jpg"}
MANIFEST = OUT / "bench2_manifest.json"; CAP_USD = 5.00
os.environ.setdefault("OPENAI_API_KEY_FILE", str(SCRATCH / ".oaikey"))

REFS_BY = {v: {"rgb": str(OUT / f"{v}_flatlay.png"), "mask": str(OUT / f"{v}_mask.png"), "normal": str(OUT / f"{v}_normal.png")} for v in ("ref", "ref2", "ref3")}
OUT_SIZE = "1536x1024"
# Presentation only (Bench1's round-2 wording, D-B1-3). Names no stitch, count, band, hood,
# button, length or construction: everything structural comes from the reference. The dark
# cloth is the reference's surface (the gate segments the cream garment by lightness).
PROMPT = ("The first image is a flat computer rendering of a hand-crocheted garment laid out flat. Make a real product "
          "photograph of that same physical garment for a handmade marketplace listing: laid flat as shown, seen from directly above, "
          "on a plain dark charcoal linen cloth that has been used and has its ordinary creases. It was placed by hand, not styled: "
          "very slightly askew, one sleeve resting a little differently from the other, the fabric settling with small natural ripples "
          "and shadows rather than lying perfectly flat. Keep the garment exactly as shown: the same outline, the same proportions, "
          "every part where it is, the same colour everywhere. The second image is the outline mask and the third shows the surface "
          "relief; use them only to keep the outline, position and surface placement exactly. Replace the rendered material with real "
          "DK-weight acrylic yarn as it actually crochets up: a matte, slightly fuzzy surface with the stitch texture exactly as drawn, "
          "ordinary handmade unevenness, soft window daylight from one side, gentle shadows, an ordinary camera with a little grain. "
          "No text, no props, nothing else in frame.")
# Round 2 (D-B2-4): the generator folded the spread hood into a point and drew four or six buttons
# for the five drawn. A fidelity sentence may name a part the reference already contains and ask
# that it stay as drawn; it never names a count, a stitch or a construction detail.
PROMPT_V2 = PROMPT.replace("Keep the garment exactly as shown: the same outline, the same proportions, every part where it is, the same colour everywhere.",
                           "Keep the garment exactly as shown: the same outline, the same proportions, every part where it is, the same colour everywhere. "
                           "The hood lies open and spread flat above the shoulders exactly as it is drawn, not folded or pointed. The front is buttoned "
                           "with exactly the buttons that are drawn, each where it is drawn, none added and none removed.")
PROMPTS = {"v1": PROMPT, "v2": PROMPT_V2}
MODES = {
    "oa15_hifi": dict(provider="openai", model="gpt-image-1.5", params={"input_fidelity": "high", "quality": "medium"}),
    # gemini-3-pro-image: the justified alternative while the OpenAI account has no credit. 2K on a 3:2
    # frame keeps a star ~24 px across; list price per 2K image ASSUMED at US$0.24 (1K was 0.134 in E5)
    "g3pro": dict(provider="google", model="gemini-3-pro-image", params={"imageSize": "2K", "aspectRatio": "3:2"}, usd_list=0.24),
}
OA_RATES = {"text_in": 5.0, "image_in": 10.0, "image_out": 40.0}


def _key(name): return (SCRATCH / name).read_text().strip()
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def load():
    if MANIFEST.exists(): return json.load(open(MANIFEST))
    raise SystemExit("run `freeze` first")
def save(m): m["spent_usd"] = round(sum(c.get("usd", 0) for c in m["calls"]) + sum(r.get("usd", 0) for r in m["runs"]), 4); json.dump(m, open(MANIFEST, "w"), indent=1, default=str)


BLOCKER_GOOGLE = {"what": "Google AI Studio prepaid credit depleted (HTTP 402 RESOURCE_EXHAUSTED) on 2026-09-26T16:05Z after draw 7 of round 2",
                  "blocks": ["gemini-3-pro-image generation (the alternative provider)", "the declared substitute reader and judge (gemini-3.1-pro-preview)"],
                  "route_around": "none left: no provider with credit remains in this environment; draws 5-7 are gated deterministically only and stay UNKNOWN (never PASS) until a reader and a judge can run",
                  "owner_action_required": {"action": "add prepaid credit to the Google AI Studio project used by this benchmark (ai.studio/projects > billing), or to the OpenAI organisation (preferred: it restores the pinned reader, judge and gpt-image-1.5)",
                                            "why": "no external generation, reading or judging can run; the benchmark cannot certify without a reader and the realism judge",
                                            "max_cost": "owner's choice; US$5 covers finishing this benchmark's remaining draws and gates at the recorded rates", "minutes": 3,
                                            "consequence_of_waiting": "Bench2 closes with the round-1 and round-2 evidence as recorded: no certified hero"}}
BLOCKER = {"what": "OpenAI account credit exhausted (HTTP 429 insufficient_quota, code credit_balance_exhausted) on 2026-09-26T15:00Z during Bench2 phase 5",
           "blocks": ["gpt-image-1.5 high-input-fidelity generation (the brief's primary provider)", "the pinned gpt-5 reader", "the pinned gpt-5 D realism judge"],
           "route_around": "gemini-3-pro-image for generation (the brief's named alternative), gemini-3.1-pro-preview as a DECLARED substitute for the reader and the judge with the pinned prompts unchanged; every such call is labelled provider/model/substitute_for",
           "owner_action_required": {"action": "add prepaid credit to the OpenAI API organisation used by this benchmark (platform.openai.com > Settings > Organization > Billing)",
                                     "why": "the pinned reader, the pinned D judge and gpt-image-1.5 cannot run without it; certification on the pinned judge waits on it",
                                     "max_cost": "owner's choice; US$10 covers re-running this benchmark's reads, judgements and up to ~25 gpt-image-1.5 draws at the recorded rates",
                                     "minutes": 3, "consequence_of_waiting": "Bench2 heroes are certified on the substitute judge only; the pinned-judge re-run and any gpt-image-1.5 draws stay open"}}


def record_blocker():
    m = load(); m["blockers"] = [BLOCKER, BLOCKER_GOOGLE]; save(m); print("blockers recorded")


def cmd_freeze():
    """Phase 3: the benchmark size and its Product Truth, frozen with the reason."""
    pt = json.load(open(OUT / "product_truth.json")); row = next(r for r in pt["derived"]["per_size"] if r["size"] == "2-3T")
    m = {"benchmark": "Commercial benchmark 2 -- Mini Star Stitch Cardigan (MJ's Off The Hook Designs Inc.)", "cap_usd": CAP_USD,
         "size": "2-3T", "size_reason": ("Mid-range of the ten sizes, so every shaping element exists (front neck increases, hood increases and the 3 shaping rows, "
                                          "all sleeve rows before and after the neck); it is the size the designer photographs on a child in the gallery, so a private "
                                          "comparison of the worn garment is possible; and at the frame that fits its 73.8 cm wingspan a star is 18 px across, inside "
                                          "the identity instrument's envelope (eyes >= 1.5 px) with room for the generator's fuzz."),
         "product_truth_sha256": sha(OUT / "product_truth.json"), "product_truth_size_row": row, "cir_fingerprint": pt["cir_for_size"]["fingerprint"],
         "instrument_bars": SI.BARS, "instrument_selftest_sha256": sha(OUT / "star_identity_selftest.json") if (OUT / "star_identity_selftest.json").exists() else None,
         "prompts": PROMPTS, "references": {}, "calls": [], "runs": [], "frozen_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    for v in REFS_BY:
        if Path(REFS_BY[v]["rgb"]).exists(): m["references"][v] = {k: sha(p) for k, p in REFS_BY[v].items()}
    save(m); print(json.dumps({k: m[k] for k in ("size", "size_reason", "product_truth_sha256", "cir_fingerprint", "references")}, indent=1))


def _multipart(fields, files):
    b = f"----b2{uuid.uuid4().hex}"; out = bytearray()
    for k, v in fields.items(): out += f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    for name, fname, data in files: out += f"--{b}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{fname}\"\r\nContent-Type: image/png\r\n\r\n".encode() + data + b"\r\n"
    out += f"--{b}--\r\n".encode(); return b, bytes(out)


def draw(mode_key, prompt, refv="ref"):
    mode = MODES[mode_key]; REFS = REFS_BY[refv]
    if mode["provider"] == "openai":
        fields = {"model": mode["model"], "prompt": prompt, "n": "1", **{k: str(v) for k, v in mode["params"].items()}, "size": OUT_SIZE}
        files = [("image[]", Path(REFS[r]).name, Path(REFS[r]).read_bytes()) for r in ("rgb", "mask", "normal")]
        b, body = _multipart(fields, files)
        req = urllib.request.Request("https://api.openai.com/v1/images/edits", data=body, method="POST")
        req.add_header("authorization", f"Bearer {_key('.oaikey')}"); req.add_header("content-type", f"multipart/form-data; boundary={b}")
        with urllib.request.urlopen(req, timeout=400) as r: d = json.loads(r.read().decode())
        raw = base64.b64decode(d["data"][0]["b64_json"]); u = d.get("usage") or {}; det = u.get("input_tokens_details") or {}
        usd = (det.get("text_tokens", 0) * OA_RATES["text_in"] + det.get("image_tokens", 0) * OA_RATES["image_in"] + u.get("output_tokens", 0) * OA_RATES["image_out"]) / 1e6
        return raw, {"usage": u, "usd": round(usd, 5), "price_basis": "usage tokens at gpt-image-1 list rates"}
    parts = [{"text": prompt}] + [{"inlineData": {"mimeType": "image/png", "data": base64.b64encode(Path(REFS[r]).read_bytes()).decode()}} for r in ("rgb", "mask", "normal")]
    body = {"contents": [{"parts": parts}], "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {k: v for k, v in mode["params"].items()}}}
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
        r = R.read(p); m["calls"].append({"key": key, "kind": "reader", "provider": r.get("provider"), "model": r.get("model"), "substitute_for": r.get("substitute_for"), "image_sha256": r["image_sha256"], "response_id": r["response_id"], "usd": r["cost_usd"], "answers": r["answers"], "raw": r["raw"][:1500]}); save(m)
        out[os.path.basename(p)] = r["answers"]; print(key, json.dumps(r["answers"])[:300])
    return out


def cmd_read_designer():
    """Private: the designer's photographs read by the same reader; calibration of the reader's
    materiality (E3 rule). The photographs never enter the repository; the readings do."""
    m = load(); paths = [str(PDF_IMAGES / f) for f in DESIGNER.values()]
    ans = read_images(m, "designer", paths); ans = {k: ans[v] for k, v in DESIGNER.items()}
    json.dump(ans, open(OUT / "designer_photos.json", "w"), indent=1); save(m)
    cal = G.calibrate(ans); print("calibration:", json.dumps(cal["tally"]), "withdrawn:", cal["withdrawn_material"])
    for k, v in ans.items(): print(k, {a: b["status"] for a, b in G.properties(v).items()})


def cmd_read_reference(refv="ref"):
    m = load(); ans = read_images(m, f"reference_{refv}", [REFS_BY[refv]["rgb"]]); json.dump(ans, open(OUT / f"reference_reading_{refv}.json", "w"), indent=1); save(m)
    print("reference:", {k: v["status"] for k, v in G.properties(list(ans.values())[0]).items()})


def cmd_generate(mode_key, n, pv="v1", refv="ref"):
    m = load(); m.setdefault("prompts", {})[pv] = PROMPTS[pv]; prompt = PROMPTS[pv]
    m["references"][refv] = {k: sha(v) for k, v in REFS_BY[refv].items()}
    for _ in range(n):
        if m.get("spent_usd", 0) + 0.35 > CAP_USD: print("ceiling reached; not drawing"); break
        k = 1 + sum(1 for r in m["runs"] if r["mode"] == mode_key); t0 = time.time()
        row = {"mode": mode_key, "draw": k, "prompt_version": pv, "reference_version": refv, "model": MODES[mode_key]["model"], "params": {**MODES[mode_key]["params"], "size": OUT_SIZE}, "reference_sha256": m["references"][refv], "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()}
        try:
            raw, meta = draw(mode_key, prompt, refv); img = Image.open(io.BytesIO(raw)).convert("RGB"); dst = GEN / f"{mode_key}_{k}.png"; img.save(dst)
            row.update(ok=True, path=str(dst), output_sha256=sha(dst), seconds=round(time.time() - t0, 1), **meta)
        except urllib.error.HTTPError as exc: row.update(ok=False, error=f"{exc.code}: {exc.read().decode(errors='replace')[:300]}", usd=0.0)
        except Exception as exc: row.update(ok=False, error=f"{type(exc).__name__}: {str(exc)[:300]}", usd=0.0)  # noqa: BLE001
        m["runs"].append(row); save(m); print(json.dumps({a: row.get(a) for a in ("mode", "draw", "ok", "output_sha256", "seconds", "usd", "error")}))
    print("spent US$", m["spent_usd"])


def run_judge(paths):
    """The pinned D judge; on OpenAI insufficient_quota the declared substitute runs the same prompt."""
    from brambleloop.visual import d_judge as DJ
    if os.environ.get("BENCH2_VISION") == "substitute":
        import substitute as S; return S.judge_views(paths)
    try: return DJ.judge_views(paths)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        if exc.code == 429 and "insufficient_quota" in body:
            import substitute as S; return S.judge_views(paths)
        raise


def cmd_gate(offline=False):
    m = load()
    results = json.load(open(OUT / "bench2_gate.json")) if (OUT / "bench2_gate.json").exists() else {}
    for run in m["runs"]:
        if not run.get("ok"): continue
        key = f"{run['mode']}_{run['draw']}"; refv = run.get("reference_version", "ref")
        if key in results and results[key]["output_sha256"] == run["output_sha256"]: continue
        rr = OUT / f"reference_reading_{refv}.json"; ref_ans = list(json.load(open(rr)).values())[0] if rr.exists() else None
        det = G.deterministic(run["path"], refv)
        if offline:
            props = {k: {"status": "UNKNOWN", "got": None, "why": "BLOCKED: no provider with credit (reader could not run)", "material": mat} for k, (_, mat) in G.expectations().items()}
            v = G.verdict(det, props, None); v["blocked"] = "reader and judge could not run: OpenAI and Google credit exhausted (see manifest blockers)"
            results[key] = {"mode": run["mode"], "draw": run["draw"], "prompt_version": run.get("prompt_version", "v1"), "reference_version": refv, "output_sha256": run["output_sha256"], "usd_generation": run.get("usd"),
                            "deterministic": det, "properties": props, "reader_answers": None, "judge": None, "judge_notes": "", "verdict": v}
            json.dump(results, open(OUT / "bench2_gate.json", "w"), indent=1, default=str)
            si = det["items"].get("star_identity", {}).get("evidence", {}).get("panels", {})
            print(f"{key}: {v['status']} (offline) | det {det['status']} iou {det['items'].get('silhouette', {}).get('evidence', {}).get('iou_aligned')} drift {det['items'].get('proportions', {}).get('evidence', {}).get('drift')} "
                  f"buttons {det['items'].get('buttons', {}).get('evidence', {}).get('count')} | star {det['items'].get('star_identity', {}).get('status')}/{det['items'].get('star_gauge', {}).get('status')} {[(k, p.get('star_pitch_px'), p.get('row_pair_px'), p.get('failed')) for k, p in si.items()]}")
            continue
        ans = read_images(m, "candidate", [run["path"]])[os.path.basename(run["path"])]
        props = G.properties(ans, ref_ans)
        cache = OUT / f"judge_{key}.json"; j = json.load(open(cache)) if cache.exists() else None
        if not (j and j["views"][0].get("image_sha256") == run["output_sha256"]):
            j = run_judge([run["path"]]); json.dump(j, open(cache, "w"), indent=1)
            m["calls"].append({"key": f"judge:{key}", "kind": "judge", "provider": j.get("provider", "openai"), "model": j.get("model"), "substitute_for": j.get("substitute_for"), "image_sha256": run["output_sha256"], "response_id": j["views"][0]["response_id"], "usd": j["total_cost_usd"]}); save(m)
        judge = {k: v["status"] for k, v in j["items"].items()}
        v = G.verdict(det, props, judge)
        results[key] = {"mode": run["mode"], "draw": run["draw"], "prompt_version": run.get("prompt_version", "v1"), "reference_version": refv, "output_sha256": run["output_sha256"], "usd_generation": run.get("usd"),
                        "deterministic": det, "properties": props, "reader_answers": ans, "judge": judge, "judge_notes": j["views"][0]["reading"].get("notes", ""), "verdict": v}
        json.dump(results, open(OUT / "bench2_gate.json", "w"), indent=1, default=str)
        si = det["items"].get("star_identity", {}).get("evidence", {}).get("panels", {})
        print(f"{key}: {v['status']} | det {det['status']} iou {det['items'].get('silhouette', {}).get('evidence', {}).get('iou_aligned')} drift {det['items'].get('proportions', {}).get('evidence', {}).get('drift')} "
              f"| star {det['items'].get('star_identity', {}).get('status')}/{det['items'].get('star_gauge', {}).get('status')} {[(k, p.get('star_pitch_px'), p.get('row_pair_px'), p.get('failed')) for k, p in si.items()]} "
              f"| material fails {v['material_failures']} unknown {v['unknown_material']} | judge fails {v['judge_failures']} | {results[key]['judge_notes'][:90]}")
    save(m); print("spent US$", m["spent_usd"])


def cmd_compare():
    """Phase 7, private: the certified candidates' readings beside the designer's photographs'
    readings, property by property; evidence only."""
    g = json.load(open(OUT / "bench2_gate.json")); des = json.load(open(OUT / "designer_photos.json"))
    keys = sorted(set(G.EXPECT) | {"main_colour"}); rows = {}
    for key, res in g.items():
        if res["verdict"]["status"] != "PASS": continue
        rows[key] = {k: {"candidate": res["reader_answers"].get(k), "designer": {n: a.get(k) for n, a in des.items()}, "agree_with_designer_majority": None} for k in keys}
        for k in keys:
            dv = [a.get(k) for a in des.values() if a.get(k) is not None]
            if dv:
                maj = max(set(map(json.dumps, dv)), key=list(map(json.dumps, dv)).count); rows[key][k]["agree_with_designer_majority"] = (json.dumps(res["reader_answers"].get(k)) == maj)
    out = {"note": "private comparison of certified heroes with the designer's photographs through the same reader; evidence only, never listing assets", "certified": rows}
    json.dump(out, open(OUT / "private_comparison.json", "w"), indent=1); print(json.dumps({k: {p: v["agree_with_designer_majority"] for p, v in r.items()} for k, r in rows.items()}, indent=1))


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "freeze": cmd_freeze()
    elif c == "record_blocker": record_blocker()
    elif c == "read_designer": cmd_read_designer()
    elif c == "read_reference": cmd_read_reference(sys.argv[2] if len(sys.argv) > 2 else "ref")
    elif c == "generate": cmd_generate(sys.argv[2], int(sys.argv[3]), sys.argv[4] if len(sys.argv) > 4 else "v1", sys.argv[5] if len(sys.argv) > 5 else "ref")
    elif c == "gate": cmd_gate(offline=(len(sys.argv) > 2 and sys.argv[2] == "offline"))
    elif c == "compare": cmd_compare()
