"""REDFIX-A: the owner's master-template PDF keeps the approved technique-help links.

Every runtime render site passes `lesson_links=pdf_help_links(ctx.db, cir.to_dict())`
(tests/test_learn_publish_contract.py pins that binding) into
`pdf_template.build_customer_pdf_with_layout`. The template path filtered its keywords
through an allowed-keys set that did not name `lesson_links`, and `build_template_pdf` had no
such parameter, so the illustrated customer PDF silently lost the links the engine layout
prints. Every assertion here is about the built bytes (pypdf text and link annotations) or
about the keyword set itself.
"""
from __future__ import annotations

import inspect
import io
import os
import re
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT), str(ROOT / "tests")]

from pypdf import PdfReader  # noqa: E402

from brambleloop.learn.service import pdf_help_links, save_lesson  # noqa: E402
from brambleloop.products import launch0  # noqa: E402
from brambleloop.publish import pdf as P  # noqa: E402
from brambleloop.publish import pdf_template as T  # noqa: E402
from test_learn_launch import approve, database, spec  # noqa: E402

RELEASED = date(2026, 11, 20)
ORIGIN = "https://learn.example.test"


def _cir():
    return launch0.cir_for("hexagon_coasters")


def _links():
    """Real approved links from the Learn service, as the render sites resolve them."""
    db = database(":memory:")
    rev = save_lesson(db, "single-crochet", spec())
    approve(db, rev)
    with patch.dict(os.environ, {"BRAMBLELOOP_LEARN_PUBLIC_ORIGIN": ORIGIN}):
        links = pdf_help_links(db, _cir().to_dict())
    assert links, "fixture: the approved single-crochet lesson resolves no link for an sc CIR"
    return links


def _customer_frames():
    return [dict(f, test_double=False, kind="generated") for f in T.test_double_gallery()]


def _text(pdf_bytes: bytes) -> str:
    return re.sub(r"\s+", " ", "\n".join(p.extract_text() or ""
                                         for p in PdfReader(io.BytesIO(pdf_bytes)).pages))


def _uris(pdf_bytes: bytes) -> list[str]:
    out = []
    for page in PdfReader(io.BytesIO(pdf_bytes)).pages:
        for ref in page.get("/Annots") or []:
            action = ref.get_object().get("/A") or {}
            if action.get("/URI"):
                out.append(str(action["/URI"]))
    return out


def test_the_template_keyword_set_is_the_template_signature():
    """A keyword the template takes but the filter drops is lost without an error."""
    params = set(inspect.signature(T.build_template_pdf).parameters) - {"cir"}
    assert T.TEMPLATE_KWARGS == params, sorted(T.TEMPLATE_KWARGS ^ params)
    assert "lesson_links" in T.TEMPLATE_KWARGS


def test_customer_ready_template_pdf_prints_and_links_every_approved_lesson():
    links = _links()
    doc, info = T.build_customer_pdf_with_layout(
        _cir(), terminology="US", released_on=RELEASED, gallery=_customer_frames(),
        lesson_links=links)
    # the release-default path chose the illustrated template, not the engine fall-back
    assert info["layout"] == "template" and doc.status == "customer_ready", info
    text, uris = _text(doc.pdf_bytes), _uris(doc.pdf_bytes)
    assert P.TECHNIQUE_HELP_HEADING.upper() in text.upper()
    assert links, "no approved link to look for"
    for link in links:
        assert link["url"].startswith(ORIGIN + "/learn/") and "revision=" in link["url"]
        # a long URL wraps onto a second line; the printed characters are all there
        assert link["url"] in re.sub(r"\s+", "", text), link["url"]
        assert link["url"] in uris, (link["url"], uris)
        assert ", ".join(link["topics"]) in text
    # still the sale checker's PASS on its own bytes
    assert T.audit(doc.pdf_bytes, expected_gallery=doc.gallery)["verdict"] == "PASS"


def test_explicit_template_layout_and_both_terminologies_keep_the_links():
    links = _links()
    for terminology in P.TERMINOLOGIES:
        doc, info = T.build_customer_pdf_with_layout(
            _cir(), layout="template", terminology=terminology, released_on=RELEASED,
            gallery=list(T.test_double_gallery()), lesson_links=links)
        assert info["layout"] == "template", info
        assert [u for u in _uris(doc.pdf_bytes) if u == links[0]["url"]], terminology


def test_without_links_the_template_document_has_no_technique_help():
    doc = T.build_template_pdf(_cir(), released_on=RELEASED,
                               gallery=list(T.test_double_gallery()))
    assert P.TECHNIQUE_HELP_HEADING.upper() not in _text(doc.pdf_bytes).upper()
    assert not [u for u in _uris(doc.pdf_bytes) if "/learn/" in u]


def test_an_unsafe_or_unversioned_link_refuses_the_template_document():
    good = _links()[0]
    for bad in (dict(good, url=good["url"].replace("https://", "http://")),
                dict(good, url=good["url"].split("?")[0]),
                dict(good, url=good["url"] + "#x"),
                dict(good, url=good["url"].replace("/learn/", "/elsewhere/"))):
        try:
            T.build_template_pdf(_cir(), released_on=RELEASED,
                                 gallery=list(T.test_double_gallery()), lesson_links=[bad])
        except T.TemplateBlocked as e:
            assert "unsafe or unversioned lesson link" in str(e.reason), e.reason
        else:
            raise AssertionError(f"accepted {bad['url']}")


def test_the_two_layouts_print_the_same_links():
    links = _links()
    engine = P.build_pattern_pdf(_cir(), released_on=RELEASED, lesson_links=links)
    template = T.build_template_pdf(_cir(), released_on=RELEASED,
                                    gallery=list(T.test_double_gallery()), lesson_links=links)
    want = sorted(link["url"] for link in links)
    assert sorted(u for u in _uris(engine.pdf_bytes) if "/learn/" in u) == want
    assert sorted(u for u in _uris(template.pdf_bytes) if "/learn/" in u) == want


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                failed += 1
                print("FAIL", name, repr(e)[:400])
    print(f"{failed} failing")
    sys.exit(1 if failed else 0)
