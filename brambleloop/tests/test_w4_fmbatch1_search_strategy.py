"""F-421/F-422/F-423: iterative internal search (terminology, discovered terms, broadened,
cross-domain) recorded per round; F-413: method adoption lists existing methods considered."""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Lesson  # noqa: E402
from brambleloop.intel import research as R, search_strategy as S  # noqa: E402

NOW = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)
_TMP = tempfile.mkdtemp(prefix="fmb1ss_")
_n = [0]
# The repository's own documents and test names are internal corpora too; point them at an
# empty sandbox so the rounds below are decided by the rows this test writes.
(Path(_TMP) / "docs").mkdir()
(Path(_TMP) / "tests").mkdir()
R.DOCUMENTS = {"BUILD_STATE.md": Path(_TMP) / "docs" / "BUILD_STATE.md",
               "DECISION_LOG.md": Path(_TMP) / "docs" / "DECISION_LOG.md"}
R.TESTS_DIR = Path(_TMP) / "tests"
SPEC = {"stop_condition": "three internal pieces of evidence or the strategy exhausted",
        "evidence_needed": "what this company already measured about the question",
        "if_unresolved": "owner swatches and records the measurement"}


def _db():
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/d{_n[0]}.sqlite")
    db.create_all()
    return db


def _lesson(db, subject, statement):
    with db.session() as s:
        s.add(Lesson(origin_cell="learn", subject=subject, statement=statement))


def _open(db, terms, q="How does yarn weight change the gauge of a blanket swatch?"):
    return R.open_question(db, question=q, trigger=f"t:{'-'.join(terms)}",
                           decision_ref="product.sizing", domain="techniques",
                           query_terms=terms, now=NOW, **SPEC)["task"]


def test_terminology_discovery_and_cross_domain_find_what_the_literal_search_missed():
    db = _db()
    _lesson(db, "tension", "worsted tension swatch measured 16 stitches per 10 cm on a 5 mm hook")
    _lesson(db, "tension", "aran tension swatch blocked wider than the unblocked swatch")
    _lesson(db, "density", "textile stitch density tables put worsted at 18 to 20 stitches")
    tid = _open(db, ["gauge"])
    with db.session() as s:
        assert s.get(R.ResearchTask, tid).internal_evidence == []   # literal search: nothing
    out = S.run(db, tid, need=3)
    assert out["evidence"] == 3 and out["stopped"] == "enough evidence", out
    rounds = [r["round"] for r in out["rounds"]]
    assert rounds[0] == "exact" and "terminology" in rounds and "cross_domain" in rounds
    with db.session() as s:
        row = s.get(R.ResearchTask, tid)
        found_by = {e["found_by"] for e in row.internal_evidence}
        assert found_by == {"terminology", "cross_domain"}
        assert row.detail["search_rounds"] == out["rounds"]


def test_discovered_terms_and_broadening_are_planned():
    hits = [{"text": "mosaic stripes in worsted"}, {"text": "mosaic chart, worsted cotton"}]
    assert S.discover_terms(hits, ["blanket"])[:2] == ["mosaic", "worsted"]
    steps = S.plan(["granny square", "blanket"], [])
    kinds = {(st["round"], tuple(st["terms"])) for st in steps}
    assert ("terminology", ("motif", "blanket")) in kinds
    assert ("terminology", ("granny square", "afghan")) in kinds
    assert ("broadened", ("blanket",)) in kinds


def test_exhausted_strategy_says_so():
    db = _db()
    tid = _open(db, ["zzqx"], q="Does the unknown zzqx property matter at all here?")
    out = S.run(db, tid)
    assert out["evidence"] == 0 and out["stopped"] == "strategy exhausted"


def _method_task(db):
    tid = R.open_question(db, question="Does a knitting yarn model transfer to crochet charts?",
                          trigger="t:m", decision_ref="visual.renderer", domain="mathematical",
                          query_terms=("yarn",), kind=R.METHOD_ADOPTION, now=NOW, **SPEC)["task"]
    R.add_source(db, tid, source="paper", citation="https://arxiv.org/abs/9",
                 retrieval="fetched", read_on=NOW.date())
    R.add_finding(db, tid, statement="the model assumes knitted loops in rows",
                  claim_class="fact", rests_on=("S1",))
    return tid


def _conclusion(**kw):
    app = {k: {"verdict": "does_not_transfer", "why": "topology"}
           for k in R.APPLICABILITY_DIMENSIONS}
    c = {"alternatives": [], "constraints": ["crochet topology"], "unresolved": [],
         "next_test": None, "applicability": app}
    c.update(kw)
    return c


def test_f413_method_adoption_needs_existing_methods_and_new_builds_a_rejection():
    db = _db()
    eff = {"kind": "constraint_established", "statement": "topology differs"}
    tid = _method_task(db)
    for bad in (None, [], [{"method": "x", "source": "", "verdict": "rejected", "why": "w"}],
                [{"method": "x", "source": "s", "verdict": "maybe", "why": "w"}]):
        try:
            R.answer(db, tid, outcome="x", effect=eff, now=NOW,
                     conclusion=_conclusion(existing_methods=bad))
        except R.ResearchRefused as exc:
            assert "F-413" in str(exc)
        else:
            raise AssertionError(f"accepted {bad!r}")
    adopted = [{"method": "pypdfium2 rasteriser", "source": "repo:requirements.txt",
                "verdict": "adopted", "why": "already a dependency"}]
    try:
        R.answer(db, tid, outcome="x", effect=eff, now=NOW,
                 conclusion=_conclusion(existing_methods=adopted, build_new=True))
    except R.ResearchRefused as exc:
        assert "rejected" in str(exc)
    else:
        raise AssertionError("a new build with nothing rejected was accepted")
    ok = [{"method": "knitting yarn simulation", "source": "https://arxiv.org/abs/9",
           "verdict": "rejected", "why": "assumes knitted loops"}]
    out = R.answer(db, tid, outcome="build our own", effect=eff, now=NOW,
                   conclusion=_conclusion(existing_methods=ok, build_new=True))
    assert out["conclusion"]["existing_methods"] == ok


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
