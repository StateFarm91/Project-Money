"""Owner-approved live FLUX 3 call (CA$5 wrap experiment). Key comes from env only; never printed."""
import hashlib, json, os, sys, time
from pathlib import Path
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
MODE = sys.argv[2]  # "plan" or "live"
from brambleloop.core.db import Database
from brambleloop.runtime.pipeline import _engineered_cir
from brambleloop.creative import image_stages as S, flux_prompt as FP
from brambleloop.gateway import images
HERE = Path(__file__).resolve().parent
EXP = Path("research/final_build/w4/flux_experiments/2026-10-19_reading_nook_cable_wrap")
cir = _engineered_cir("reading-nook-cable-wrap")
rel = S.release_from_cir(cir, release_hash="335c61ce56587a46cf60db33b3aeb6dbdab0d5404b4c4ab4e7a7453571753a24",
                         out_dir=OUT / "auto_refs")
auto = dict(zip(("layout", "texture", "detail", "rules"), rel.pattern_refs))
laura = S.laura_references(None)
refs = laura + [str(EXP / "ref4_complete_wrap_layout.png"), str(EXP / "ref5_cable_stitch_structure.png"),
                str(EXP / "ref6_construction_rules.png"),
                str(HERE / "reading-nook-cable-wrap-335c61ce5658-texture.png")]
roles = ["laura_face", "laura_torso", "laura_body", "product_layout", "product_detail", "product_rules", "product_texture"]
outfit = {"id": "exp-wrap-2026-10-20",
          "description": "black fitted long-sleeve crew-neck top; mid-wash denim midi skirt; brown leather ankle boots; small silver ring"}
scene = {"outfit": outfit,
         "environment": "quiet autumn residential street lined with golden-leaf trees, soft late-afternoon light",
         "pose": "standing relaxed, the wrap draped over both shoulders and hanging open at the front so its full length, the cable columns and both cream end bands are visible",
         "framing": "full-length vertical portrait, eye level, wrap clearly in focus"}
built = FP.build(rules=rel.rules, roles=roles, role="lifestyle_hero", scene=scene)
manifest = [{"position": i + 1, "role": r, "file": Path(p).name, "sha256": hashlib.sha256(Path(p).read_bytes()).hexdigest()}
            for i, (r, p) in enumerate(zip(roles, refs))]
plan = {"model": "flux-3-image", "size": S.LIFESTYLE_SIZE, "references": manifest,
        "prompt_builder": built.builder_version, "prompt_sha256": hashlib.sha256(built.text.encode()).hexdigest(),
        "estimated_cost_usd": images.BY_KEY["flux-3-image"].cad_per_image if False else None}
# Frozen plan: the committed prompt and fingerprints are authoritative; refuse on any drift.
frozen = json.loads((HERE / "plan.json").read_text())
assert (HERE / "prompt.txt").read_text() == built.text, "prompt drifted from the frozen plan"
assert [r["sha256"] for r in frozen["references"]] == [m["sha256"] for m in manifest], "reference drift"
(OUT / "prompt.txt").write_text(built.text)
(OUT / "plan.json").write_text(json.dumps(plan, indent=1))
print(json.dumps({k: v for k, v in plan.items() if k != "references"}, indent=1)); [print(m) for m in manifest]
print("prompt chars", len(built.text))
if MODE != "live":
    sys.exit(0)
env = {"BRAMBLELOOP_IMAGE_PROVIDER": "flux-3-image", **{k: v for k, v in os.environ.items() if k.startswith("BRAMBLELOOP_IMAGE_KEY")}}
db = Database(f"sqlite:///{OUT}/exp.sqlite", scratch=True); db.create_all()
t0 = time.time()
res = images.generate(built.text, reference_urls=refs, env=env, size=S.LIFESTYLE_SIZE, provider_key="flux-3-image",
                      work_dir=str(OUT / "render"), db=db, agent="creative_director", purpose="experiment.wrap_six_ref")
res = {k: v for k, v in res.items() if "key" not in k.lower()}
res["wall_seconds"] = round(time.time() - t0, 1)
(OUT / "result.json").write_text(json.dumps(res, indent=1, default=str))
print(json.dumps(res, indent=1, default=str)[:3000])
