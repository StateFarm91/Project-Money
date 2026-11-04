"""Explicit French stripe claims must agree with the compiled design."""
import dataclasses
import tempfile
from pathlib import Path

from brambleloop.core.db import Database
from brambleloop.core.models import PatternVersion, Product
from brambleloop.gates.certificate import GAUGE_STANDARD
from brambleloop.publish import eligibility
from brambleloop.runtime.pipeline import Concept, concept_to_cir


def test_publication_checks_french_stripe_claims_against_real_bands():
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{Path(tmp) / 'french-stripes.sqlite'}"
        db = Database(url, scratch=True)
        db.create_all()
        base = Concept(slug="french-plain", title="Everyday Blanket", category="blanket",
                       stitch_repeat=[("sc", 4)], width_stitches=40, rows=10,
                       colors={"a": "#fff"})
        plain = concept_to_cir(base)
        striped = concept_to_cir(dataclasses.replace(base, slug="french-striped",
                                  colors={"a": "#fff", "b": "#245050"}))
        for cir in (plain, striped):
            with db.session() as session:
                product = Product(slug=cir.slug, title=cir.title, status="certified")
                session.add(product)
                session.flush()
                session.add(PatternVersion(product_id=product.id, version=cir.version,
                    certified=True, cir_json=cir.to_dict(), release_hash="a" * 64,
                    certificate={"granted": True, "gauge_standard": GAUGE_STANDARD}))
        reopened = Database(url, scratch=True)
        for listing in ({"title": "Couverture rayée", "tags": []},
                        {"title": "Blanket", "description": "Avec des rayures", "tags": []},
                        {"title": "Blanket", "tags": ["RAYÉS"]},
                        {"title": "Blanket", "tags": ["ｒａｙｕｒｅｓ"]}):
            bad = eligibility.product_publication(reopened, plain.slug, plain.version,
                                                   listing=listing)
            assert any(row["code"] == eligibility.NAME_OUTRUNS_PATTERN and "stripe" in row["why"]
                       for row in bad["reasons"]), (listing, bad)
            good = eligibility.product_publication(reopened, striped.slug, striped.version,
                                                    listing=listing)
            assert not any(row["code"] == eligibility.NAME_OUTRUNS_PATTERN and "stripe" in row["why"]
                           for row in good["reasons"]), (listing, good)
        control = {"title": "Rayon de soleil", "description": "Soft blanket", "tags": []}
        result = eligibility.product_publication(reopened, plain.slug, plain.version,
                                                  listing=control)
        assert not any(row["code"] == eligibility.NAME_OUTRUNS_PATTERN and "stripe" in row["why"]
                       for row in result["reasons"]), result
