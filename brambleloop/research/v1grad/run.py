"""Product-only Visual V1 graduation: freeze, generate, gate, report. One manifest
(`out/v1grad_manifest.json`) records the firewall, every asset supplied to every stage with its
digest, every external call and its cost against the ceiling, and every candidate's verdict.

Subcommands: `freeze` | `read_reference` | `generate <n> [pv]` | `gate` | `report`.
Generation is refused unless the manifest records BLIND DETERMINISTIC CHAIN: PASS.
"""
from __future__ import annotations
import base64, hashlib, io, json, os, sys, time, urllib.request, urllib.error, uuid
from pathlib import Path
from PIL import Image
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]; OUT = HERE / "out"; GEN = OUT / "gen"; GEN.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT / "src"))
import reader as R, gate as G                                                      # noqa: E402
SCRATCH = Path("/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad")
MANIFEST = OUT / "v1grad_manifest.json"; CAP_USD = 5.00
os.environ.setdefault("OPENAI_API_KEY_FILE", str(SCRATCH / ".oaikey"))
REFS_BY = {v: {"rgb": str(OUT / f"{v}_flatlay.png"), "mask": str(OUT / f"{v}_mask.png"), "normal": str(OUT / f"{v}_normal.png")} for v in ("ref", "ref2", "ref3")}
REFS = REFS_BY["ref"]
OUT_SIZE = "1024x1536"; OUT_SIZE_BY = {"ref": "1024x1536", "ref2": "1024x1536", "ref3": "1536x1024"}
# The strongest previously evidenced OpenAI route for structural preservation (E5, Bench1's
# certified hero): gpt-image-1.5, input_fidelity high, quality medium, the rgb + mask + normal
# package. Presentation only (Bench1 round-2 wording, D-B1-3 / D-B2-4): names no stitch, count,
# construction or feature; the dark cloth is the reference's surface.
PROMPT = ("The first image is a flat computer rendering of a hand-crocheted textile laid out flat. Make a real product "
          "photograph of that same physical piece for a handmade marketplace listing: laid flat as shown, seen from directly above, "
          "on a plain dark charcoal linen cloth that has been used and has its ordinary creases. It was placed by hand, not styled: "
          "very slightly askew, the fabric settling with small natural ripples and shadows rather than lying perfectly flat. "
          "Keep the piece exactly as shown: the same outline, the same proportions, every part where it is, the same colour everywhere. "
          "The second image is the outline mask and the third shows the surface relief; use them only to keep the outline, position and "
          "surface placement exactly. Replace the rendered material with real worsted-weight acrylic yarn as it actually crochets up: a matte, "
          "slightly fuzzy surface with the stitch texture exactly as drawn, ordinary handmade unevenness, soft window daylight from one side, "
          "gentle shadows, an ordinary camera with a little grain. No text, no props, nothing else in frame.")
# Round 3 (D-B2-4 rule): a fidelity sentence may name a part the reference already contains and
# ask that it stay as drawn; it never names a count, a stitch or a construction detail. Round 1
# drew the raised columns 1.3-1.6x too far apart (columns merged) and the judge read the
# ruler-straight edges as computer-generated; both are presentation, not design.
PROMPT_V2 = PROMPT.replace("Keep the piece exactly as shown: the same outline, the same proportions, every part where it is, the same colour everywhere.",
                           "Keep the piece exactly as shown: the same outline, the same proportions, every part where it is, the same colour everywhere. "
                           "Keep exactly the raised columns that are drawn, each one where it is drawn and as narrow as it is drawn, none merged, none added, "
                           "none removed, with the recessed channels between them as drawn. The edges are the plain edges of the crocheted fabric itself, "
                           "with no added border, lying as a heavy crocheted blanket lies when set down by hand: slightly uneven, not ruler-straight.")
PROMPTS = {"v1": PROMPT, "v2": PROMPT_V2}
MODE = dict(provider="openai", model="gpt-image-1.5", params={"input_fidelity": "high", "quality": "medium"})
OA_RATES = {"text_in": 5.0, "image_in": 10.0, "image_out": 40.0}


def _key(): return (SCRATCH / ".oaikey").read_text().strip()
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def load():
    if MANIFEST.exists(): return json.load(open(MANIFEST))
    raise SystemExit("run `freeze` first")
def save(m): m["spent_usd"] = round(sum(c.get("usd", 0) for c in m["calls"]) + sum(r.get("usd", 0) for r in m["runs"]), 4); json.dump(m, open(MANIFEST, "w"), indent=1, default=str)


def cmd_freeze():
    """Phase 3: the blind deterministic chain, checked and frozen with digests."""
    pt = json.load(open(OUT / "product_truth.json")); meta = json.load(open(OUT / "ref_meta.json")); st = json.load(open(OUT / "cable_identity_selftest.json"))
    checks = {
        "product_truth_compiles_and_cross_checks_pass": all(c["status"] == "PASS" for c in pt["checks"]),
        "cir_validates": pt["cir"]["compile_ok"],
        "reference_exists_and_draws_every_cell_row_and_crossing": all(meta["validation"][k] for k in ("every_cell_drawn", "every_row_drawn", "crossings_drawn_equals_truth", "every_region_present", "extent_matches_truth")),
        "reference_dimensions_are_product_truth": meta["dimensions_cm"]["width"] == pt["derived"]["width_cm"] and meta["dimensions_cm"]["height"] == pt["derived"]["height_cm"],
        "reference_inputs_are_the_frozen_product_truth": meta["inputs"]["product_truth_sha256"] == sha(OUT / "product_truth.json") and meta["inputs"]["cir_fingerprint"] == pt["cir"]["fingerprint"],
        "instrument_reads_reference_as_cable_at_gauge": st["results"]["reference"]["status"] == "PASS",
        "instrument_rejects_rotated_plain_star_waffle": all(v["identity"] != "PASS" for k, v in st["results"].items() if "must_fail" in k and "gauge" not in k),
        "instrument_gauge_fails_at_2x_scale": st["results"]["reference_2x_scale(gauge_must_fail)"]["gauge"]["status"] == "FAIL",
        "reference_passes_its_own_gate": G.deterministic(REFS["rgb"])["status"] == "PASS",
        "firewall_statement_true": pt["firewall"]["statement"] == "EXTERNAL FINISHED-PRODUCT VISUAL REFERENCES USED BY PRODUCT CONSTRUCTION OR GENERATION: NONE" and pt["firewall"]["web_search"] == "none",
    }
    passed = all(checks.values())
    m = {"benchmark": "Product-only Visual V1 graduation -- blind Brambleloop product (Heirloom Cable Throw)", "cap_usd": CAP_USD, "frozen_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
         "firewall": pt["firewall"], "blind_deterministic_chain": {"checks": checks, "verdict": "PASS" if passed else "FAIL"},
         "frozen_digests": {"product_truth.json": sha(OUT / "product_truth.json"), "ref_meta.json": sha(OUT / "ref_meta.json"), **{f"ref_{k}": sha(v) for k, v in REFS.items()}, "ref_regions.png": sha(OUT / "ref_regions.png"),
                            "cable_identity_selftest.json": sha(OUT / "cable_identity_selftest.json"), "gate.py": sha(HERE / "gate.py"), "reference.py": sha(HERE / "reference.py"), "product_truth.py": sha(HERE / "product_truth.py"), "reader.py": sha(HERE / "reader.py"), "run.py": sha(HERE / "run.py")},
         "generation_package": {"provider": MODE["provider"], "model": MODE["model"], "params": {**MODE["params"], "size": OUT_SIZE}, "images_in_order": ["ref_flatlay.png (rgb)", "ref_mask.png (outline)", "ref_normal.png (relief)"], "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(), "prompt": PROMPT},
         "assets_by_stage": {"product_truth": ["src/brambleloop/products/texture.py", "cir.stitches / compiler / twin", "visual.fabric"], "reference": ["out/product_truth.json", "the CIR's cells"], "generation": ["out/ref_flatlay.png", "out/ref_mask.png", "out/ref_normal.png", "the prompt"],
                             "gate": ["out/ref_mask.png", "out/ref_regions.png", "out/ref_meta.json", "the reader", "the D judge"], "finished_product_images": "NONE at any stage"},
         "instrument_bars": G.BARS, "prompts": PROMPTS, "calls": [], "runs": []}
    save(m); print("BLIND DETERMINISTIC CHAIN:", m["blind_deterministic_chain"]["verdict"]); print(json.dumps(checks, indent=1))


def _multipart(fields, files):
    b = f"----v1{uuid.uuid4().hex}"; out = bytearray()
    for k, v in fields.items(): out += f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    for name, fname, data in files: out += f"--{b}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{fname}\"\r\nContent-Type: image/png\r\n\r\n".encode() + data + b"\r\n"
    out += f"--{b}--\r\n".encode(); return b, bytes(out)


def draw(prompt, refv="ref"):
    REFS = REFS_BY[refv]
    fields = {"model": MODE["model"], "prompt": prompt, "n": "1", **{k: str(v) for k, v in MODE["params"].items()}, "size": OUT_SIZE_BY[refv]}
    files = [("image[]", Path(REFS[r]).name, Path(REFS[r]).read_bytes()) for r in ("rgb", "mask", "normal")]
    b, body = _multipart(fields, files)
    req = urllib.request.Request("https://api.openai.com/v1/images/edits", data=body, method="POST")
    req.add_header("authorization", f"Bearer {_key()}"); req.add_header("content-type", f"multipart/form-data; boundary={b}")
    with urllib.request.urlopen(req, timeout=400) as r: d = json.loads(r.read().decode())
    raw = base64.b64decode(d["data"][0]["b64_json"]); u = d.get("usage") or {}; det = u.get("input_tokens_details") or {}
    usd = (det.get("text_tokens", 0) * OA_RATES["text_in"] + det.get("image_tokens", 0) * OA_RATES["image_in"] + u.get("output_tokens", 0) * OA_RATES["image_out"]) / 1e6
    return raw, {"usage": u, "usd": round(usd, 5), "price_basis": "usage tokens at gpt-image-1 list rates"}


def read_images(m, label, paths):
    out = {}
    for p in paths:
        key = f"{label}:{os.path.basename(p)}"
        prior = next((c for c in m["calls"] if c["key"] == key and c["image_sha256"] == sha(p)), None)
        if prior: out[os.path.basename(p)] = prior["answers"]; continue
        r = R.read(p); m["calls"].append({"key": key, "kind": "reader", "provider": r["provider"], "model": r["model"], "image_sha256": r["image_sha256"], "response_id": r["response_id"], "usd": r["cost_usd"], "answers": r["answers"], "raw": r["raw"][:1500]}); save(m)
        out[os.path.basename(p)] = r["answers"]; print(key, json.dumps(r["answers"])[:300])
    return out


def cmd_read_reference():
    m = load(); ans = read_images(m, "reference", [REFS["rgb"]]); json.dump(ans, open(OUT / "reference_reading.json", "w"), indent=1); save(m)
    print("reference:", {k: v["status"] for k, v in G.properties(list(ans.values())[0]).items()})


def cmd_generate(n, pv="v1", refv="ref"):
    m = load()
    if m["blind_deterministic_chain"]["verdict"] != "PASS": raise SystemExit("refused: BLIND DETERMINISTIC CHAIN is not PASS")
    prompt = PROMPTS[pv]; REFS = REFS_BY[refv]
    if refv != "ref":
        # a later reference version is a re-statement of the same frozen Product Truth (same cells,
        # same geometry); it is frozen here with its digests and its own self-gate before use
        meta = json.load(open(OUT / f"{refv}_meta.json")); assert meta["inputs"]["product_truth_sha256"] == m["frozen_digests"]["product_truth.json"], "reference version not built from the frozen Product Truth"
        assert G.deterministic(REFS["rgb"], refv)["status"] == "PASS", "reference version fails its own gate"
        m.setdefault("reference_versions", {})[refv] = {k: sha(v) for k, v in REFS.items()} | {"meta_sha256": sha(OUT / f"{refv}_meta.json"), "conventions": meta["conventions_DECLARED"]}
    for _ in range(n):
        if m.get("spent_usd", 0) + 0.35 > CAP_USD: print("ceiling reached; not drawing"); break
        k = 1 + len(m["runs"]); t0 = time.time()
        row = {"draw": k, "prompt_version": pv, "reference_version": refv, "model": MODE["model"], "params": {**MODE["params"], "size": OUT_SIZE_BY[refv]}, "reference_sha256": {kk: sha(v) for kk, v in REFS.items()}, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()}
        if refv == "ref": assert row["reference_sha256"]["rgb"] == m["frozen_digests"]["ref_rgb"], "the reference changed after the freeze"
        else: assert row["reference_sha256"]["rgb"] == m["reference_versions"][refv]["rgb"]
        try:
            raw, meta = draw(prompt, refv); img = Image.open(io.BytesIO(raw)).convert("RGB"); dst = GEN / f"oa15_hifi_{k}.png"; img.save(dst)
            row.update(ok=True, path=str(dst), output_sha256=sha(dst), seconds=round(time.time() - t0, 1), **meta)
        except urllib.error.HTTPError as exc: row.update(ok=False, error=f"{exc.code}: {exc.read().decode(errors='replace')[:300]}", usd=0.0)
        except Exception as exc: row.update(ok=False, error=f"{type(exc).__name__}: {str(exc)[:300]}", usd=0.0)  # noqa: BLE001
        m["runs"].append(row); save(m); print(json.dumps({a: row.get(a) for a in ("draw", "ok", "output_sha256", "seconds", "usd", "error")}))
    print("spent US$", m["spent_usd"])


def cmd_gate():
    m = load(); from brambleloop.visual import d_judge as DJ
    rr = OUT / "reference_reading.json"; ref_ans = list(json.load(open(rr)).values())[0] if rr.exists() else None
    results = json.load(open(OUT / "v1grad_gate.json")) if (OUT / "v1grad_gate.json").exists() else {}
    for run in m["runs"]:
        if not run.get("ok"): continue
        key = f"oa15_hifi_{run['draw']}"
        if key in results and results[key]["output_sha256"] == run["output_sha256"]: continue
        det = G.deterministic(run["path"], run.get("reference_version", "ref"))
        ans = read_images(m, "candidate", [run["path"]])[os.path.basename(run["path"])]; props = G.properties(ans, ref_ans, run.get("reference_version", "ref"))
        cache = OUT / f"judge_{key}.json"; j = json.load(open(cache)) if cache.exists() else None
        if not (j and j["views"][0].get("image_sha256") == run["output_sha256"]):
            j = DJ.judge_views([run["path"]]); json.dump(j, open(cache, "w"), indent=1)
            m["calls"].append({"key": f"judge:{key}", "kind": "judge", "provider": "openai", "model": j.get("model"), "image_sha256": run["output_sha256"], "response_id": j["views"][0]["response_id"], "usd": j["total_cost_usd"]}); save(m)
        judge = {k: v["status"] for k, v in j["items"].items()}; v = G.verdict(det, props, judge)
        results[key] = {"draw": run["draw"], "prompt_version": run.get("prompt_version", "v1"), "reference_version": run.get("reference_version", "ref"), "output_sha256": run["output_sha256"], "usd_generation": run.get("usd"), "deterministic": det, "properties": props, "reader_answers": ans, "judge": judge,
                        "judge_notes": j["views"][0]["reading"].get("notes", ""), "verdict": v}
        json.dump(results, open(OUT / "v1grad_gate.json", "w"), indent=1, default=str)
        ci = det["items"].get("cable_identity", {}).get("evidence", {})
        print(f"{key}: {v['status']} | det {det['status']} iou {det['items'].get('silhouette', {}).get('evidence', {}).get('iou_aligned')} drift {det['items'].get('proportions', {}).get('evidence', {}).get('drift')} "
              f"| cable {det['items'].get('cable_identity', {}).get('status')}/{det['items'].get('cable_gauge', {}).get('status')} col {ci.get('column_pitch_px')} cross {ci.get('crossing_period_px')} dom {ci.get('column_dominance')} failed {ci.get('failed')} "
              f"| material fails {v['material_failures']} unknown {v['unknown_material']} | judge fails {v['judge_failures']} | {results[key]['judge_notes'][:90]}")
    save(m); print("spent US$", m["spent_usd"])


def cmd_regate():
    """Offline: recompute every candidate's deterministic result and verdict from the stored
    reader answers and judge items (no provider call), e.g. after a gate-code correction. The
    readings never change; the record says the gate version that judged them."""
    m = load(); g = json.load(open(OUT / "v1grad_gate.json")); rr = OUT / "reference_reading.json"; ref_ans = list(json.load(open(rr)).values())[0] if rr.exists() else None
    for key, r in g.items():
        run = next(x for x in m["runs"] if x.get("ok") and f"oa15_hifi_{x['draw']}" == key)
        det = G.deterministic(run["path"], r.get("reference_version", "ref")); props = G.properties(r["reader_answers"], ref_ans, r.get("reference_version", "ref")); v = G.verdict(det, props, r["judge"])
        r.update(deterministic=det, properties=props, verdict=v, gate_sha256=sha(HERE / "gate.py"))
        print(f"{key}: {v['status']} | det {det['status']} | material fails {v['material_failures']} unknown {v['unknown_material']} | judge fails {v['judge_failures']}")
    json.dump(g, open(OUT / "v1grad_gate.json", "w"), indent=1, default=str)


def cmd_report():
    m = load(); g = json.load(open(OUT / "v1grad_gate.json")) if (OUT / "v1grad_gate.json").exists() else {}
    ok = [r for r in m["runs"] if r.get("ok")]; cert = [k for k, r in g.items() if r["verdict"]["status"] == "PASS"]
    gen_usd = sum(r.get("usd", 0) for r in m["runs"]); val_usd = sum(c["usd"] for c in m["calls"])
    rep = {"attempts": len(m["runs"]), "succeeded": len(ok), "certified": cert, "rejected": {k: r["verdict"]["material_failures"] + r["verdict"]["judge_failures"] + r["verdict"].get("unknown_material", []) for k, r in g.items() if r["verdict"]["status"] != "PASS"},
           "generation_usd": round(gen_usd, 4), "validation_usd": round(val_usd, 4), "spent_usd": m["spent_usd"], "cost_per_certified_usd": round((gen_usd + val_usd) / len(cert), 4) if cert else None, "yield": f"{len(cert)}/{len(ok)}"}
    json.dump(rep, open(OUT / "v1grad_report.json", "w"), indent=1); print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "freeze": cmd_freeze()
    elif c == "read_reference": cmd_read_reference()
    elif c == "generate": cmd_generate(int(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else "v1", sys.argv[4] if len(sys.argv) > 4 else "ref")
    elif c == "gate": cmd_gate()
    elif c == "regate": cmd_regate()
    elif c == "report": cmd_report()
