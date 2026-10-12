"""Learn PDF cross-cluster contract: static call binding plus real bytes/hash refusal.

The AST assertion is explicitly static wiring evidence, not proof of full Etsy execution.
The dynamic tests exercise actual PDF rendering, existing hash gate, and public API; no
network or external publication is attempted.
"""
import ast
import hashlib
import os
import sys
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from test_learn_launch import database, spec, approve, seed
from brambleloop.learn.service import save_lesson, pdf_help_links


def test_both_runtime_pdf_render_sites_pass_same_learn_resolver():
    for file in ("release.py", "pipeline.py"):
        tree = ast.parse((ROOT / "src/brambleloop/runtime" / file).read_text(encoding="utf-8"))
        sites = []
        for fn in (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
            calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Name) and n.func.id == "build_pattern_pdf"]
            if not calls:
                continue
            sites.extend(calls)
            assignments = {n.targets[0].id: n.value for n in ast.walk(fn)
                           if isinstance(n, ast.Assign) and len(n.targets) == 1
                           and isinstance(n.targets[0], ast.Name)}
            assert calls, 'no PDF render call site found'
            for call in calls:
                binding = next((k.value for k in call.keywords if k.arg == "lesson_links"), None)
                assert isinstance(binding, ast.Name), f"{file}:{fn.name} omits Learn links"
                resolver = assignments.get(binding.id)
                assert isinstance(resolver, ast.Call) and isinstance(resolver.func, ast.Name)
                assert resolver.func.id == "pdf_help_links", f"{file}:{fn.name} wrong resolver"
                assert [ast.unparse(a) for a in resolver.args] == ["ctx.db", "cir.to_dict()"]
        assert sites, f"no PDF render site checked in {file}"


def cloth():
    from brambleloop.cir.model import CIR, Component, Row, Op, Gauge, Material
    return CIR(slug="learn-cloth", title="Learn Cloth", version="1", construction="flat_rows",
               gauge=Gauge(stitches_per_10cm=14,rows_per_10cm=16,stitch_type="sc",hook_mm=4),
               colors={"A":"#ffffff"}, materials=[Material(name="cotton",yarn_weight="worsted",colorway="white",color_id="A")],
               components=[Component(name="cloth",construction="flat_rows",foundation=4,
                 rows=[Row(index=i,ops=[Op("sc",4)],declared_count=4,color="A",turning_chain=1) for i in range(1,5)])])


def test_approved_links_repeat_exact_bytes_and_changed_approval_trips_hash_gate():
    from brambleloop.publish.pdf import build_pattern_pdf
    from brambleloop.runtime.pipeline import check_pdf_hashes
    from brambleloop.core.models import AuditLog
    from brambleloop.core.resilience import PermanentError
    db = database(":memory:")
    cir = cloth()
    rev = save_lesson(db,"single-crochet",spec())
    approve(db,rev)
    with patch.dict(os.environ,{"BRAMBLELOOP_LEARN_PUBLIC_ORIGIN":"https://learn.example.test"}):
        def render():
            return build_pattern_pdf(cir,released_on=date(2026,9,28),
                                     lesson_links=pdf_help_links(db,cir.to_dict())).pdf_bytes
        original = render()
        with db.session() as s:
            s.add(AuditLog(actor="publisher",action="assets.built",artifact="learn-cloth@1",
                          detail={"pdf_sha256_by_terminology":{"US":hashlib.sha256(original).hexdigest()}}))
        assert check_pdf_hashes(db,slug="learn-cloth",version="1",release="",rendered={"US":render()})["verified"] == ["US"]
        modified = spec(); modified["learner_problem"] = "new revision awaiting review"
        save_lesson(db,"single-crochet",modified)
        assert pdf_help_links(db,cir.to_dict()) == []
        try:
            check_pdf_hashes(db,slug="learn-cloth",version="1",release="",rendered={"US":render()})
        except PermanentError as exc:
            assert "PDF_HASH_DRIFT" in str(exc)
        else:
            raise AssertionError("stale approved PDF content silently accepted")


def test_omitted_revision_serves_only_current_reviewed_spec_never_stale_pdf_target():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from brambleloop.learn.api import router
    with tempfile.TemporaryDirectory() as td:
        db = database(Path(td)/"routes.db")
        app=FastAPI(); app.include_router(router(db)); client=TestClient(app)
        old = save_lesson(db,"single-crochet",spec()); approve(db,old)
        modified=spec(); modified["learner_problem"]="new objective"
        new = save_lesson(db,"single-crochet",modified)
        assert client.get("/learn/single-crochet").status_code == 404
        assert client.get("/learn/single-crochet?revision="+old).status_code == 404
        approve(db,new)
        assert client.get("/learn/single-crochet").json()["revision"] == new
        assert client.get("/learn/single-crochet?revision="+old).status_code == 404
        assert client.get("/learn/single-crochet?revision="+new).status_code == 200
        db.engine.dispose()


if __name__ == "__main__":
    failures=0
    tests=[(n,f) for n,f in list(globals().items()) if n.startswith("test_") and callable(f)]
    for name,test in tests:
        try:
            test(); print("OK  ",name)
        except Exception as exc:
            failures+=1; print("FAIL",name,type(exc).__name__,str(exc))
    print(f"{len(tests)-failures}/{len(tests)} passing")
    sys.exit(bool(failures))
