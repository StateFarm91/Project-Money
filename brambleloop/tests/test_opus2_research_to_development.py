"""OPUS2: research briefs reach Product Development's reusable constructions, or are held.

Before: `cir.draft` sent every non-garment tournament winner to `creative.prototype.author`,
which ignores the brief's construction, motif and palette and emits a single-crochet stripe.
Now `creative.construction_registry` reads the brief (form, construction, motif, palette
story, brief dict) into a construction request, builds it with a reusable construction and
explicit parameters, or holds it with each missing item named (`cir.draft_held`).

Part 1 drives REAL research: `creative.tournament` with only the model call substituted by a
fixture field generator (as `test_cert_design_pipeline` does), the winner intake, the vision
gate (a recorded fixture judgement, because no vision model exists in shadow), the seasonal
sentinel's re-gate, then `cir.draft` and `cir.compile` through the real worker. Whatever the
jury selects is drafted or held: the test does not pick the winner.

Part 2 feeds Product Development's own drafting step (`pipeline._draft_creative`, the code
`cir.draft` runs for a tournament winner) briefs shaped exactly as research emits them, for
constructions the research fields above did not select, and shows that materially different
constructions come out of one code path with no per-product code -- and that a brief whose
construction no engine can make is held, naming why.

What this does NOT show, stated so it is not over-read: the jury's preferences are research
behaviour (W-CONCEPT); these fields did not produce a tapestry or toy winner, and the toy pod
produced no arena at all (a research-side finding recorded on PR #3). Nothing here is a
production run.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_research_to_development.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_cert_design_pipeline as T  # noqa: E402 - the real-runtime design harness

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.model import CIR, op_colours  # noqa: E402
from brambleloop.core.models import BenchmarkListing, JobStatus  # noqa: E402
from brambleloop.creative import construction_registry as R  # noqa: E402
from brambleloop.creative.concept import Concept  # noqa: E402
from brambleloop.intel import benchmarks  # noqa: E402
from brambleloop.products import launch0 as L  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402


def _field(constructions, motifs):
    """A research field generator: varied constructions and motifs, as a real field must be to
    survive the research jury's sameness kill. The fixture stands in for the model only."""
    count = {"n": 0}

    def gen(values, _call):
        form = values["form"].replace(" ", "_")
        occasion = {"christmas": "christmas", "mother's day": "mothers_day"}.get(
            str(values.get("occasion") or values.get("event") or "").lower(), "everyday")
        out = []
        for _ in range(int(values.get("count") or 1)):
            j = count["n"]
            count["n"] += 1
            u = [T._unique(j, t) for t in range(4)]
            motif = motifs[j % len(motifs)]
            cons = constructions[(j // len(motifs)) % len(constructions)]
            out.append({"title": f"{u[0].title()} {motif.title()} {form.title()}",
                        "premise": f"a {form} whose {motif} {u[0]} {u[1]} {u[2]} {u[3]} rim",
                        "construction": cons, "motif": f"{motif} {u[1]}",
                        "palette_story": "forest and cream",
                        "recipient": T.RECIPIENTS[j % len(T.RECIPIENTS)],
                        "occasion": occasion, "feeling": T.FEELINGS[j % len(T.FEELINGS)],
                        "function": f"holds {u[2]} things by the {u[3]} door", "wow": "rim"})
        return {"concepts": out}
    return gen


def _research(pod, listing_title, generator):
    """One real research run: listings observed, a tournament, its winner and gate verdict."""
    db = T._db()
    with db.session() as s:
        for i in range(12):
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref=f"L{i}",
                                   title=listing_title, pod=pod, price_cad=8.0,
                                   audit_state="audited", detail={"num_favorers": 90}))
    result, row = T._tournament(db, generator=generator)
    assert result["ran"] is True and row, result
    return db, row


def test_part1_a_real_research_winner_reaches_product_development_and_is_engineered():
    """The full path, nothing hand-fed: listings -> tournament -> winner intake -> vision gate
    (fixture judgement) -> sentinel re-gate -> cir.draft -> cir.compile -> gate.certify."""
    db, row = _research("stockings", "Festive Christmas Stocking Crochet Pattern",
                        T.stocking_field())
    slug = row["concept"]["key"]
    assert row["funnel"]["carried"] is True and row["decision"] == "waiting", row
    T._judge(db, slug)
    out, _ = T._handler(db, "mjs.seasonal_sentinel", {}, agent="market_radar")
    assert {"slug": slug, "decision": "engineering"} in out["regated"]["presented"], out
    drafts = T._drain(db, "cir.draft")
    assert drafts and drafts[0]["status"] == JobStatus.DONE, drafts
    draft = drafts[0]["outputs"]
    concept = Concept(**{k: v for k, v in row["concept"].items()
                         if k in Concept.__dataclass_fields__})
    req = R.request_for(concept, drafts[0]["inputs"].get("brief"))
    if req is None:
        # No construction serves this (form, construction) on this branch: the existing
        # prototype path drafts it, unchanged.
        assert draft["drafted"] is True and "construction" not in draft, draft
    elif req.unresolved:
        assert draft.get("held") is True and draft["unresolved"] == req.unresolved, draft
    else:
        assert draft["drafted"] is True and draft["construction"] == req.family, draft
    if draft.get("drafted"):
        compiled = T._drain(db, "cir.compile")
        assert compiled and compiled[0]["outputs"]["compiled"] is True, compiled
        assert T._jobs(db, "gate.certify"), "a compiled winner was not sent to certification"


def test_part1_a_generic_form_winner_needs_a_silhouette_qualifier_from_research():
    """A real basket/pouch winner is refused by the pre-engineering silhouette gate (#108)
    before Product Development sees it, because the research brief carries no
    `silhouette_qualifiers`. That is a research-to-development contract item (PR #3), recorded
    here so it is not mistaken for a Product Development failure."""
    db, row = _research("bags", "Crochet Drawstring Pouch Pattern", _field(
        ("in_the_round", "seamless_tube", "flat_rows"),
        ("ridged", "ribbed", "waffle", "textured", "plain", "solid", "simple", "classic",
         "everyday", "minimal", "soft", "neat", "tidy")))
    assert row["concept"]["form"] == "pouch" and row["funnel"]["carried"] is True, row
    assert row["decision"] == "refused" and "silhouette" in row["gate"]["failed"], row["gate"]
    assert not T._jobs(db, "cir.draft")
    # Product Development would build this brief: the registry resolves it with nothing held.
    req = R.request_for(Concept(**{k: v for k, v in row["concept"].items()
                                   if k in Concept.__dataclass_fields__}))
    assert req is not None and req.family == "pouch" and not req.unresolved, req


def _ctx(db, concept: dict, brief: dict | None = None):
    emitted, audits = [], []
    job = SimpleNamespace(inputs={"slug": concept["key"], "concept": concept,
                                  "brief": brief or {}})
    ctx = SimpleNamespace(db=db, job=job,
                          audit=lambda action, **kw: audits.append((action, kw)),
                          enqueue=lambda role, kind, data, **kw: emitted.append((kind, data)))
    return ctx, emitted, audits


def _brief(key, form, construction, motif, palette="forest and cream", title=None):
    return {"key": key, "title": title or f"{motif.title()} {form.title()}",
            "premise": f"a {form} whose {motif} wall carries the room's quiet colour story",
            "pod": "home_decor", "form": form, "construction": construction, "motif": motif,
            "palette_story": palette, "recipient": "host", "occasion": "housewarming",
            "feeling": "serene", "function": f"holds the things a {form} is for",
            "make_lane": "MEDIUM"}


def test_part2_one_code_path_makes_materially_different_constructions_from_briefs():
    db = T._db()
    briefs = {
        # joined rounds, per-stitch colour from a library chart, carried strand
        "tapestry": _brief("brief-heart-basket", "basket", "tapestry", "heart"),
        # spiral-shaped stuffed pieces, a base disc, placed ears: a closed 3-D form
        "amigurumi": _brief("brief-bear-toy", "toy", "amigurumi_shaping", "bear",
                            palette="caramel"),
        # a round vessel with an eyelet round bridged by chains and a threaded cord
        "pouch": _brief("brief-soft-pouch", "pouch", "in_the_round", "soft"),
    }
    cirs = {}
    assert len(briefs) == 3
    for family, concept in briefs.items():
        ctx, emitted, audits = _ctx(db, concept)
        out = pipeline._draft_creative(ctx, concept["key"])
        assert out["drafted"] is True and out["construction"] == family, (family, out)
        cir = CIR.from_dict(emitted[0][1]["cir"])
        result = compile_cir(cir)
        assert result.ok, (family, [f.code for f in result.errors])
        prims = set(cir.provenance.primitives_used)
        assert set(R.PRIMITIVES) <= prims, prims
        cirs[family] = (cir, result)
    tap, ami, pouch = cirs["tapestry"][0], cirs["amigurumi"][0], cirs["pouch"][0]
    # Materially different stitch architecture, read from the CIRs themselves:
    # per-stitch colour only in the tapestry; stuffing and multiple pieces only in the toy;
    # bridged chains and a threaded join only in the pouch.
    assert any(op_colours(r.ops) - {r.color} for r in tap.components[0].rows)
    assert not any(op_colours(r.ops) - {r.color} for c in ami.components for r in c.rows)
    assert any(s.stuff_before_closing for s in ami.assembly) and len(ami.components) == 3
    assert any(s.method == "thread" for s in pouch.assembly)
    assert not any(s.method == "thread" for s in tap.assembly + ami.assembly)
    constructions = {f: (c.construction, tuple(sorted(x.name for x in c.components)),
                         tuple(sorted({s.method for s in c.assembly})))
                     for f, (c, _r) in cirs.items()}
    assert len(set(constructions.values())) == 3, constructions
    # Truth on each: the tapestry's name is backed by its own technique rule and its heart is
    # the chart the CIR carries; the toy is risk class C and states only a circumference.
    from brambleloop.cir.twin import build_twin

    twin = build_twin(tap, cirs["tapestry"][1])
    assert L.fabric_truth(tap, twin)["backed"]
    assert "products.motifs:heart-row:tapestry" in tap.provenance.primitives_used
    assert L.motif_promise(tap)["backed"] is True, L.motif_promise(tap)
    assert ami.risk_class == "C" and "around" in ami.finished_size_note


def test_part2_briefs_lacking_what_their_construction_needs_are_held_by_name():
    db = T._db()
    cases = {
        "construction": _brief("brief-mosaic", "basket", "mosaic_overlay", "diamond"),
        "motif": _brief("brief-fox-toy", "toy", "amigurumi_shaping", "fox"),
        "size": _brief("brief-giant", "basket", "in_the_round", "ridged"),
    }
    briefs = {"size": {"size": "giant"}}
    assert len(cases) == 3
    all_held = []
    for field, concept in cases.items():
        ctx, emitted, audits = _ctx(db, concept, briefs.get(field))
        out = pipeline._draft_creative(ctx, concept["key"])
        assert out.get("held") is True and emitted == [], (field, out)
        assert field in {u["field"] for u in out["unresolved"]}, (field, out)
        held = [kw for a, kw in audits if a == R.HELD_ACTION]
        assert held and held[0]["detail"]["unresolved"] == out["unresolved"], held
        all_held += held
    # The engine-blocked hold reaches the Learning gap system as missing capability.
    from datetime import date

    from brambleloop.core.models import AuditLog
    from brambleloop.intel import knowledge_gaps as kg

    with db.session() as s:
        for kw in all_held:
            s.add(AuditLog(actor="crochet_engineer", action=R.HELD_ACTION,
                           artifact=kw.get("artifact"), detail=kw.get("detail")))
    ev = kg.evidence(db, today=date.today())["baskets_storage"]
    assert "brief-mosaic" in ev["refused"] and any("reach" in n for n in ev["needs"]), ev
    # A held construction names the engine decision; a held motif names research enrichment.
    mosaic = R.request_for(Concept(**cases["construction"]))
    assert mosaic.unresolved[0]["resolved_by"] == R.ENGINE
    fox = R.request_for(Concept(**cases["motif"]))
    assert fox.unresolved[0]["resolved_by"] == R.ENRICH


def test_a_pair_no_construction_serves_keeps_the_existing_authoring_path():
    db = T._db()
    concept = _brief("brief-runner", "runner", "flat_rows", "ridged")
    assert R.request_for(Concept(**concept)) is None
    ctx, emitted, audits = _ctx(db, concept)
    out = pipeline._draft_creative(ctx, concept["key"])
    assert out["drafted"] is True and "construction" not in out, out   # prototype.author


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name} {exc!r}"[:600])
                import traceback
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
