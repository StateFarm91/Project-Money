"""W4-PIPE2: engineer, gate and file the moment-first creative candidates (shadow).

    PYTHONPATH=src python research/final_build/w4/pipe2_run.py [slug ...]

For each candidate in `emotional_brief.gate_candidates()['engineering_queue']` order that
`products.moment_candidates` engineers: the pipeline board's own stages (DESIGN -> PRODUCT ->
PRODUCT_TRUTH -> VISUAL -> SEARCH, `products.pipeline_board._advance`), the US pattern PDF
(`publish.pdf.build_pattern_pdf`), the disclosed deterministic render attempt, the concept
board for the taste gate, and the taste-gate state proven on a temporary database
(`register_for_taste_gate` + `creative.intake.regate_held`). Writes
`PIPE2_CANDIDATES.{json,md}`, files under `pipe2/<slug>/`, and replaces only the rows for
these slugs in `PIPELINE_BACKLOG.{json,md}` (W4-PIPE's other rows are kept as they are).
Scratch artefact store and DB under $TMPDIR; no network, no spend, no Etsy.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
OUT = HERE / "pipe2"
TODAY = date(2026, 10, 7)


def _db(path: Path):
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{path}")
    db.create_all()
    return db


def run(slugs: list[str]) -> dict:
    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.creative import emotional_brief as eb
    from brambleloop.creative import intake
    from brambleloop.products import moment_candidates as mc
    from brambleloop.products import pipeline_board as pb
    from brambleloop.publish.pdf import build_pattern_pdf

    scratch = Path(tempfile.mkdtemp(prefix="pipe2-"))
    store = ArtifactStore(root=scratch / "artifacts")
    db = _db(scratch / "taste.sqlite")
    gate = eb.gate_candidates(today=TODAY)
    queue = [s for s in gate["engineering_queue"] if s in pb.CREATIVE_ENGINEERED]
    if slugs:
        queue = [s for s in queue if s in slugs]
    creative = {c.slug: c for c in pb.creative_candidates()}
    rows, records = [], {}
    for slug in queue:
        c = creative[slug]
        pb._advance(c, None, {}, store, True)
        cir = mc.creative_cir(slug)
        d = OUT / slug
        d.mkdir(parents=True, exist_ok=True)
        rec: dict = {"slug": slug, "title": cir.title, "version": cir.version,
                     "fingerprint": cir.fingerprint, "risk_class": cir.risk_class,
                     "components": [(x.name, x.make, x.construction) for x in cir.components],
                     "engineered_by": ("W4-PIPE2 products.moment_candidates"
                                       if slug in mc.ENGINEERED else
                                       "W4-PIPE products.pipeline_board"),
                     "engineering_note": mc.ENGINEERING_NOTES.get(slug, "W4-PIPE's design; "
                                                                  "see handoff_PIPE.md")}
        # The deliverable: the US pattern PDF, rendered from the certified-or-refused CIR.
        try:
            doc = build_pattern_pdf(cir, released_on=TODAY)
            pdf = d / f"{slug}-{cir.version}-US.pdf"
            pdf.write_bytes(doc.pdf_bytes)
            rec["pdf"] = {"path": str(pdf.relative_to(HERE)), "pages": doc.pages,
                          "sha256": hashlib.sha256(doc.pdf_bytes).hexdigest(),
                          "finished_size_cm": doc.finished_size_cm,
                          "yardage_by_color": doc.yardage_by_color,
                          "difficulty": str(doc.difficulty)}
        except Exception as exc:  # noqa: BLE001 - a refused document is the finding
            rec["pdf"] = {"refused": f"{type(exc).__name__}: {exc}"[:300]}
        # The concept board the taste gate judges, filed where regate_held reads it.
        board = mc.file_board(db, cir, store)
        png = d / "concept-board.png"
        png.write_bytes(mc.board_png(cir))
        rec["concept_board"] = {**board, "path": str(png.relative_to(HERE)),
                                "file_sha256": hashlib.sha256(png.read_bytes()).hexdigest()}
        rec["taste_gate_registration"] = mc.register_for_taste_gate(db, slug, today=TODAY)
        rec["gate"] = {k: gate["candidates"][slug][k]
                       for k in ("decision", "failed", "unmeasured", "waiting_on")}
        rec["demand"] = gate["candidates"][slug]["demand"]
        records[slug] = rec
        rows.append(c)
        print("engineered", slug, c.current, c.stages.get(c.current, {}).get("status"),
              flush=True)
    # Runtime proof: the taste gate's own re-presentation cadence, on the scratch DB.
    regate = intake.regate_held(SimpleNamespace(db=db), today=TODAY)
    held = {h["slug"]: h["waiting_on"] for h in regate["held"]}
    for slug, rec in records.items():
        rec["taste_gate"] = {
            "state": "needs_taste" if slug in held else "not held",
            "regate_held_waiting_on": held.get(slug),
            "board_for": intake.board_for(db, slug),
            "board_digest_for": intake.board_digest_for(db, slug),
            "vision_usable": regate["vision_usable"]}
    return {"rows": [r.to_dict() for r in rows], "records": records, "queue": queue,
            "regate_held": regate}


def splice_backlog(rows: list[dict]) -> None:
    """Replace only these candidates' rows in W4-PIPE's backlog and recount its totals."""
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
    res["pipe2_rows"] = {"by": "W4-PIPE2 research/final_build/w4/pipe2_run.py",
                         "slugs": [r["slug"] for r in rows],
                         "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                         "detail": "PIPE2_CANDIDATES.json"}
    path.write_text(json.dumps(res, indent=1, default=str) + "\n")
    (HERE / "PIPELINE_BACKLOG.md").write_text(pipeline_run.md(res))


def md(res: dict) -> str:
    L = ["# W4-PIPE2 — moment-first candidates engineered (shadow)", "",
         f"Generated {res['generated_at']} at `{res['head']}` by "
         "`research/final_build/w4/pipe2_run.py`. Queue = `emotional_brief.gate_candidates()"
         "['engineering_queue']`; stocking and pencil roll CIRs are W4-PIPE's, deliverables/boards/taste registration for all eight are here. Publication is never advanced.", "",
         "| # | candidate | version | board stage | status | PDF | concept board | taste gate "
         "| remaining gate | clearer |", "|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(res["rows"], 1):
        rec = res["records"][r["slug"]]
        pdf = rec["pdf"]
        L.append(
            f"| {i} | {r['slug']} | {rec['version']} | {r['stage']} | {r['stage_status']} | "
            f"{(str(pdf.get('pages')) + ' pp') if 'pages' in pdf else 'refused'} | "
            f"`{rec['concept_board']['image']['sha256'][:12]}` | "
            f"{rec['taste_gate']['state']} ({', '.join(rec['taste_gate']['regate_held_waiting_on'] or [])}) | "
            f"{(r['next_step'] or '')[:150].replace('|', '/')} | {r['clearer']} |")
    L += ["", "## Engineering notes (where the CIR departs from the brief)", ""]
    for slug, rec in res["records"].items():
        L.append(f"- **{slug}**: {rec['engineering_note']}")
    L += ["", "## Taste gate (runtime proof on a scratch DB)", "",
          f"`creative.intake.regate_held` → vision_usable={res['regate_held']['vision_usable']}; "
          f"held {len(res['regate_held']['held'])}, presented "
          f"{len(res['regate_held']['presented'])}, queued {len(res['regate_held']['queued'])}. "
          "Each candidate has a concept board with a content digest on file and waits only on "
          "a vision judgement (owner credit/vision probe); nothing here writes "
          "`thumbnail_reads_small` or `craft_impression`."]
    return "\n".join(L) + "\n"


def main(argv: list[str]) -> None:
    res = run(argv)
    res["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    res["head"] = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                                 text=True).stdout.strip()
    path = HERE / "PIPE2_CANDIDATES.json"
    if argv and path.exists():          # a partial run updates only the slugs it ran
        old = json.loads(path.read_text())
        keep = [r for r in old.get("rows", []) if r["slug"] not in res["queue"]]
        res["rows"] = keep + res["rows"]
        res["records"] = {**{k: v for k, v in old.get("records", {}).items()
                             if k not in res["queue"]}, **res["records"]}
    path.write_text(json.dumps(res, indent=1, default=str) + "\n")
    (HERE / "PIPE2_CANDIDATES.md").write_text(md(res))
    splice_backlog(res["rows"])
    for r in res["rows"]:
        print(r["slug"], r["stage"], r["stage_status"], r["clearer"])


if __name__ == "__main__":
    main(sys.argv[1:])
