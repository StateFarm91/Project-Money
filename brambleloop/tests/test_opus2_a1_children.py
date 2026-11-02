"""A1 (P0-SAFETY-CHILDREN): on a durable store, through the real worker and the registered
cir.draft handler, a stuffed toy titled in look-alike letters or with no child word at all is
drafted only to be refused by the PDF renderer until a children's decision exists; a plain
basket is unaffected.

The construction triggers the gate (`launch0.stuffed_figure`), and child words are read
NFKC-folded (OPUS2T-4). assets.build renders through the same `build_pattern_pdf`.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_a1_children.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import dataclasses
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.cir.model import CIR  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Job, PatternVersion, Product  # noqa: E402
from brambleloop.products import launch0 as L  # noqa: E402
from brambleloop.publish import pdf  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402
from brambleloop.runtime.worker import Worker  # noqa: E402


def _store(seed_slug):
    path = f"{tempfile.mkdtemp(prefix='opus2_a1_')}/a1.sqlite"
    db = Database(f"sqlite:///{path}")
    db.create_all()
    Registry(db).seed_defaults()
    seed = pipeline._seed_for(seed_slug)
    with db.session() as s:
        p = Product(slug=seed.slug, title=seed.title)
        s.add(p)
        s.flush()
        # an established earlier version: the real handler takes the radar fallback
        s.add(PatternVersion(product_id=p.id, version="0.9.0", cir_json={}, certified=True))
    return db, path, seed


def _draft_through_the_worker(seed_slug, title):
    db, path, seed = _store(seed_slug)
    inputs = {k: v for k, v in dataclasses.asdict(seed).items() if not isinstance(v, tuple)}
    inputs.update(pipeline.concept_geometry(seed))
    inputs["title"] = title
    JobQueue(db).enqueue("crochet_engineer", "cir.draft", inputs, priority=0)
    restarted = Database(f"sqlite:///{path}")               # the worker reads the durable row
    assert Worker(restarted, "a1", job_types=["cir.draft"]).run_once()
    with restarted.session() as s:
        draft = s.scalar(select(Job).where(Job.job_type == "cir.draft"))
        compile_job = s.scalar(select(Job).where(Job.job_type == "cir.compile"))
        outputs = dict(draft.outputs or {})
        cir = CIR.from_dict(compile_job.inputs["cir"]) if compile_job else None
    return outputs, cir


def test_toys_titled_in_look_alike_letters_or_with_no_child_word_never_render():
    titles = ("Ｂear", "\U0001d401ear", "Cosy Ｒabbit", "Ｔeddy Ｂear")
    assert titles
    refused = 0
    for title in titles:
        outputs, cir = _draft_through_the_worker("pocket-penguin-trio", title)
        if not outputs.get("drafted"):
            refused += 1                                # held at drafting: also safe
            continue
        assert cir is not None and L.stuffed_figure(cir), (title, outputs)
        try:
            pdf.build_pattern_pdf(cir)
        except Exception as exc:  # noqa: BLE001
            assert "child" in str(exc).lower() or "stuffed figure" in str(exc), (title, exc)
            refused += 1
        else:
            raise AssertionError(f"{title!r} rendered with no children's decision")
    assert refused == len(titles)
    # A drafted toy renamed to a title with no child word, or none, is refused by construction.
    outputs, cir = _draft_through_the_worker("pocket-penguin-trio", "Ｂear")
    assert outputs.get("drafted") and cir is not None
    for title, slug in (("Juniper Friend", "t3-home_decor-toy-0"), ("", "design-96cff5a5")):
        renamed = dataclasses.replace(cir, title=title, slug=slug)
        try:
            pdf.build_pattern_pdf(renamed)
        except Exception as exc:  # noqa: BLE001
            # refused by a child word in the slug ("toy") or by the construction itself
            assert "stuffed figure" in str(exc) or "children's product" in str(exc), (title, exc)
        else:
            raise AssertionError(f"{title!r} rendered with no children's decision")


def test_a_plain_basket_is_unaffected():
    outputs, cir = _draft_through_the_worker("nordic-forest-basket", "Crochet Storage Basket")
    assert outputs.get("drafted") is True and cir is not None, outputs
    assert not L.stuffed_figure(cir) and not L.child_words_in(cir.title, cir.slug)
    pdf._refuse_an_undecided_childrens_title(cir, None)        # no refusal


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name} {exc!r}"[:700])
                import traceback
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
