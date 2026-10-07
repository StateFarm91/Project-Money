"""W4-RENDER: render the five VISUAL-blocked certified candidates and register their sets (shadow).

    PYTHONPATH=src python research/final_build/w4/render_run.py

For first-christmas-stocking, mothers-day-heart-tea-cosy, snowfall-advent-garland,
teacher-chevron-pencil-roll and housewarming-key-basket: the pipeline board's own stages
(`products.pipeline_board._advance`, which calls `publish.disclosed_listing.build`), the
disclosed listing set filed on a scratch DB with `disclosed_listing.record` and read back with
`last_asset` (the listing pipeline's registration path), the disclosed gallery frames
(`visual.gallery_frames`, each verified on its bytes), and the independent pixel verifier
run directly against each product's certified CIR (what the frames would score once the
product is a Launch-0 authority). Writes `render/<slug>/*.png`, `RENDER_STATUS.{json,md}` and
splices only these five rows into `PIPELINE_BACKLOG.{json,md}`. No network, no spend, no Etsy.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "render"
SLUGS = ("first-christmas-stocking", "mothers-day-heart-tea-cosy", "snowfall-advent-garland",
         "teacher-chevron-pencil-roll", "housewarming-key-basket")


def _db(path: Path):
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{path}")
    db.create_all()
    return db


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def run() -> dict:
    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.products import moment_candidates as mc
    from brambleloop.products import pipeline_board as pb
    from brambleloop.publish import disclosed_listing as DL
    from brambleloop.visual import disclosed_render as D
    from brambleloop.visual import gallery_frames as G
    from brambleloop.visual import render_verification as V

    scratch = Path(tempfile.mkdtemp(prefix="render-"))
    store = ArtifactStore(root=scratch / "artifacts")
    db = _db(scratch / "render.sqlite")
    creative = {c.slug: c for c in pb.creative_candidates()}
    rows, records = [], {}
    for slug in SLUGS:
        c = creative[slug]
        pb._advance(c, None, {}, store, True)
        cir = mc.creative_cir(slug)
        d = OUT / slug
        rec: dict = {"slug": slug, "version": cir.version, "fingerprint": cir.fingerprint,
                     "stage": c.current, "stage_status": c.stages[c.current]["status"],
                     "next_step": c.stages[c.current].get("next_step", "")}
        listing = DL.build(cir, store=store, db=db)
        rec["made"] = listing["made"]
        rec["usable_as_listing_asset"] = listing["usable_as_listing_asset"]
        rec["launch_blocked"] = listing["launch_blocked"]
        if not listing["made"]:
            records[slug] = rec
            rows.append(c)
            print("refused", slug, listing["launch_blocked"][:1], flush=True)
            continue
        DL.record(db, listing)
        back = DL.last_asset(db, slug=slug)
        rec["registered"] = {"action": DL.ACTION, "read_back": bool(back),
                             "frames": len((back or {}).get("frames") or [])}
        rec["qa"] = {k: bool(listing["qa"][k]["ok"])
                     for k in ("layout_qa", "asset_truth", "frame_set", "mobile")} | {
            "hero_thumbnail": bool(listing["qa"]["hero_thumbnail"]["ok"]),
            "legibility_340": {v: bool(x["legibility_340"]["ok"])
                               for v, x in listing["qa"]["frames"].items()}}
        d.mkdir(parents=True, exist_ok=True)
        frames = []
        for f in listing["frames"]:
            png = store.get(f["image"]["sha256"])
            path = d / f"{f['view']}.png"
            path.write_bytes(png)
            direct = V.verify(png, cir=cir, view=f["view"])
            m = f["disclosed_render"]
            frames.append({"view": f["view"], "path": str(path.relative_to(HERE)),
                           "sha256": _sha(png), "form": m["form"],
                           "renderer_version": m["renderer_version"],
                           "assembly": m.get("assembly"), "alt_text": f["alt_text"],
                           "structural_truth_in_pipeline": f["structural_truth"]["status"],
                           "verifier_against_certified_cir": {
                               "status": direct["status"], "failed": direct["failed"],
                               "unknown": direct["unknown"]},
                           "disclosure": f["disclosure"]})
        rec["frames"] = frames
        gallery = []
        for job in G.applicable_jobs(cir):
            fr = G.render(cir, job)
            v = G.verify(fr.png, cir, fr.manifest)
            path = d / f"gallery-{job.lower()}.png"
            path.write_bytes(fr.png)
            gallery.append({"job": job, "path": str(path.relative_to(HERE)),
                            "sha256": _sha(fr.png), "verify": v["status"],
                            "failed": v["failed"]})
        rec["gallery"] = gallery
        records[slug] = rec
        rows.append(c)
        print("rendered", slug, c.current, c.stages[c.current]["status"], flush=True)
    return {"rows": [r.to_dict() for r in rows], "records": records}


def splice_backlog(rows: list[dict]) -> None:
    """Replace only these candidates' rows in the backlog and recount its totals."""
    from brambleloop.products import pipeline_board as pb

    sys.path.insert(0, str(HERE))
    import pipeline_run  # W4-PIPE's renderer for the .md, reused as is

    path = HERE / "PIPELINE_BACKLOG.json"
    res = json.loads(path.read_text())
    mine = {r["slug"]: r for r in rows}
    res["candidates"] = [mine.pop(r["slug"], r) for r in res["candidates"]] + list(
        mine.values())
    res["at_stage"] = {s: 0 for s in pb.STAGES}
    res["passed_stage"] = {s: 0 for s in pb.STAGES}
    for r in res["candidates"]:
        res["at_stage"][r["stage"]] += 1
        for s in pb.STAGES:
            if r["stages"].get(s, {}).get("status") == pb.PASS:
                res["passed_stage"][s] += 1
    res["render_rows"] = {"by": "W4-RENDER research/final_build/w4/render_run.py",
                          "slugs": [r["slug"] for r in rows],
                          "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                          "detail": "RENDER_STATUS.json"}
    path.write_text(json.dumps(res, indent=1, default=str) + "\n")
    (HERE / "PIPELINE_BACKLOG.md").write_text(pipeline_run.md(res))


def md(res: dict) -> str:
    L = ["# W4-RENDER — VISUAL-blocked candidates rendered (shadow)", "",
         f"Generated {res['generated_at']} at `{res['head']}` by "
         "`research/final_build/w4/render_run.py`. Publication is never advanced.", "",
         "| candidate | made | frames (form) | verifier vs certified CIR | gallery | listing QA "
         "| board stage | next gate |", "|---|---|---|---|---|---|---|---|"]
    for r in res["rows"]:
        rec = res["records"][r["slug"]]
        fr = rec.get("frames") or []
        forms = ", ".join(f"{f['view']} ({f['form']})" for f in fr) or "—"
        ver = ", ".join(f"{f['view']} {f['verifier_against_certified_cir']['status']}"
                        for f in fr) or "—"
        gal = ", ".join(f"{g['job']} {g['verify']}" for g in rec.get("gallery") or []) or "—"
        qa = rec.get("qa")
        qa_s = ("all pass" if qa and all(v for k, v in qa.items() if k != "legibility_340")
                and all(qa["legibility_340"].values()) else ("—" if not qa else str(qa)))
        nxt = (rec["launch_blocked"][0] if not rec["made"] else r["next_step"])
        L.append(f"| {r['slug']} | {rec['made']} | {forms} | {ver} | {gal} | {qa_s} | "
                 f"{r['stage']} {r['stage_status']} | {nxt[:220].replace('|', '/')} |")
    L += ["", "Assembled frames: pieces placed only by the CIR's named-edge joins, hidden "
          "mirror back layers, structured folds and resumed holds (`visual.assembled_render`);"
          " what cannot be placed is listed per frame as not drawn."]
    for slug, rec in res["records"].items():
        for f in rec.get("frames") or []:
            a = f.get("assembly")
            if a and f["view"] == "hero":
                L.append(f"- **{slug}**: drawn {a['drawn']}; hidden {sorted(a['hidden'])}; "
                         f"not drawn {a['not_drawn']}")
    return "\n".join(L) + "\n"


def main() -> None:
    res = run()
    res["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    res["head"] = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                                 text=True).stdout.strip()
    (HERE / "RENDER_STATUS.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    (HERE / "RENDER_STATUS.md").write_text(md(res))
    splice_backlog(res["rows"])


if __name__ == "__main__":
    main()
