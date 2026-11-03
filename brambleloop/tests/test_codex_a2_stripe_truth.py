"""Stripe claims require visible bands in the actual compiled pattern."""
import dataclasses
import tempfile
from pathlib import Path

from brambleloop.core.db import Database
from brambleloop.core.models import Product, PatternVersion
from brambleloop.gates.certificate import GAUGE_STANDARD
from brambleloop.publish import eligibility
from brambleloop.runtime.pipeline import Concept, concept_to_cir


def test_persistent_publication_checks_whether_stripes_are_really_written():
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{Path(tmp) / 'stripe.sqlite'}"
        db = Database(url, scratch=True)
        db.create_all()
        base = Concept(slug="codex-stripe", title="Striped Blanket", category="blanket",
            stitch_repeat=[("sc", 4)], width_stitches=40, rows=10, colors={"a": "#fff"})
        plain = concept_to_cir(base)
        striped = concept_to_cir(dataclasses.replace(base, slug="codex-striped",
                                  colors={"a": "#fff", "b": "#245050"}))
        same_colour = concept_to_cir(dataclasses.replace(base, slug="codex-same-colour",
                                     colors={"a": "#fff", "b": "#ffffff"}))
        for cir in (plain, striped, same_colour):
            with db.session() as s:
                p = Product(slug=cir.slug, title=cir.title, status="certified")
                s.add(p)
                s.flush()
                s.add(PatternVersion(product_id=p.id, version=cir.version, certified=True,
                    cir_json=cir.to_dict(), release_hash="a" * 64,
                    certificate={"granted": True, "gauge_standard": GAUGE_STANDARD}))
        reopened = Database(url, scratch=True)
        for cir in (plain, same_colour):
            result = eligibility.product_publication(reopened, cir.slug, cir.version)
            assert not result["publishable"], result
            assert any(r["code"] == eligibility.NAME_OUTRUNS_PATTERN and "stripe" in r["why"]
                       for r in result["reasons"]), result
        result = eligibility.product_publication(reopened, striped.slug, striped.version)
        assert not any(r["code"] == eligibility.NAME_OUTRUNS_PATTERN for r in result["reasons"]), result
        neutral = dataclasses.replace(plain, title="Everyday Blanket")
        for claim in ("A ｓｔｒｉｐｅｄ blanket", "contrasting striping", "a stripey blanket",
                      "a stripy blanket"):
            assert any("stripe" in reason for reason in eligibility.name_truth(neutral, {
                "description": claim, "tags": []})), claim


if __name__ == "__main__":
    test_persistent_publication_checks_whether_stripes_are_really_written()
    print("PASS publication refuses unbacked stripe claims")
