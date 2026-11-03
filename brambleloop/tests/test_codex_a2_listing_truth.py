"""A listing cannot add an unsupported motif to a plain certified release."""
import tempfile
from pathlib import Path

from brambleloop.core.db import Database
from brambleloop.core.models import PatternVersion, Product
from brambleloop.creative import fallback_constructions as fallback
from brambleloop.gates.certificate import GAUGE_STANDARD
from brambleloop.publish import eligibility
from brambleloop.runtime import pipeline


def test_persistent_publication_verdict_checks_listing_copy_and_tags():
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{Path(tmp) / 'publication.sqlite'}"
        db = Database(url, scratch=True)
        db.create_all()
        seed = pipeline._seed_for("nordic-forest-basket")
        geo = pipeline.concept_geometry(seed)
        cir = fallback.vessel(pipeline.Concept(
            slug="codex-plain-basket", title="Crochet Storage Basket", category="basket",
            stitch_repeat=[tuple(x) for x in geo["stitch_repeat"]], width_stitches=10,
            rows=4, colors=geo["colors"]))
        with db.session() as s:
            p = Product(slug=cir.slug, title=cir.title, status="certified")
            s.add(p)
            s.flush()
            s.add(PatternVersion(product_id=p.id, version=cir.version, certified=True,
                cir_json=cir.to_dict(), release_hash="a" * 64,
                certificate={"granted": True, "gauge_standard": GAUGE_STANDARD}))
        reopened = Database(url, scratch=True)
        good = {"title": "Crochet Storage Basket", "description": "Plain basket", "tags": ["storage"]}
        verdict = eligibility.product_publication(reopened, cir.slug, cir.version, listing=good)
        assert not any(r["code"] == eligibility.NAME_OUTRUNS_PATTERN for r in verdict["reasons"]), verdict
        for bad in ({**good, "title": "Heart Basket"},
                    {**good, "description": "A \u041deart motif"},
                    {**good, "tags": ["snowflake basket"]},
                    {**good, "tags": "heart"}):
            verdict = eligibility.product_publication(reopened, cir.slug, cir.version, listing=bad)
            assert not verdict["publishable"], verdict
            assert any(r["code"] == eligibility.NAME_OUTRUNS_PATTERN and
                       "motif:" in r["why"] for r in verdict["reasons"]), verdict


if __name__ == "__main__":
    test_persistent_publication_verdict_checks_listing_copy_and_tags()
    print("PASS persistent publication rejects listing-only false motif claims")
