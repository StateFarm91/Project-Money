"""W3 lane I: image upload, file attach and read-back, end to end against the local fake Etsy.

What this proves: through the real client and the real HTTP transport (loopback only), a
draft is created, the PDF is attached, real PNG/JPEG listing images are uploaded, and a
read-back confirms what was sent -- the exact bytes arrived (the fake records their sha256),
the file is on the listing by name and exact size, and every image is at its rank with its
alt text and its pixel size. It also proves the read-back *fails* when Etsy's copy differs,
and that a file or image Etsy's published rules refuse is stopped before any request.

What this does not prove: anything about Etsy. `tests/fake_etsy.py` is our reading of Etsy's
document; real-Etsy confirmation stays GATED on the owner's Etsy re-authorisation
(`publish.listing_schema` keeps these claims at LOCALLY_TESTED).

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_etsy_upload_readback.py
"""
from __future__ import annotations

import hashlib
import io
import os

from _r2_harness import run

for _k in list(os.environ):
    if _k.startswith(("ETSY", "BRAMBLELOOP_PUBLISH_AUTHORISED")):
        os.environ.pop(_k)

from PIL import Image  # noqa: E402

from brambleloop.integrations import etsy_constraints as C  # noqa: E402
from brambleloop.integrations import etsy_verify as V  # noqa: E402
from brambleloop.integrations.etsy import (Credentials, EtsyClient, EtsyRejected,  # noqa: E402
                                           build_payload)
from brambleloop.integrations.http import UrllibTransport  # noqa: E402
from brambleloop.publish import listing_schema  # noqa: E402
from brambleloop.runtime import etsy_ops  # noqa: E402
from tests.fake_etsy import FakeEtsy  # noqa: E402

PDF = b"%PDF-1.4\n% Brambleloop test pattern\n" + b"0" * 4000 + b"\n%%EOF\n"
PDF_NAME = "nordic-forest-throw-pattern-us.pdf"


def _png(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (52, 86, 62)).save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _jpg(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (236, 228, 212)).save(buf, "JPEG", quality=60)
    return buf.getvalue()


IMAGES = [("nordic-forest-throw-frame-1.png", _png(2000, 2000),
           "Digital render of the Nordic Forest throw folded on a chair; not a photograph."),
          ("nordic-forest-throw-frame-2.jpg", _jpg(2400, 2000),
           "Chart page from the pattern PDF showing rows 1 to 20.")]


def _client(fake: FakeEtsy) -> EtsyClient:
    creds = Credentials(api_key=fake.keystring, shared_secret=fake.shared_secret,
                        access_token="111.live-token", shop_id=fake.shop_id)
    return EtsyClient(UrllibTransport(), credentials=creds, phase="shadow",
                      shadow_writes_authorised=True, base=fake.base)


def _payload():
    return build_payload(title="Nordic Forest Throw Crochet Pattern PDF",
                         description="A digital crochet pattern; an instant download.",
                         price_cad=9.0, tags=["crochet pattern", "throw blanket"],
                         materials=["worsted wool"])


def _expected_images() -> list[dict]:
    out = []
    for _name, data, alt in IMAGES:
        info = C.image_info(data)
        out.append({"alt_text": alt, "width": info["width"], "height": info["height"],
                    "sha256": hashlib.sha256(data).hexdigest()})
    return out


def _draft_with_uploads(fake: FakeEtsy) -> tuple[EtsyClient, str]:
    client = _client(fake)
    lid = client.create_draft(_payload())
    assert client.attach_file(lid, filename=PDF_NAME, data=PDF) is True
    for rank, (name, data, alt) in enumerate(IMAGES, start=1):
        body = client.upload_image(lid, filename=name, data=data, rank=rank, alt_text=alt)
        assert body.get("listing_image_id"), body
    return client, lid


def test_the_images_and_file_are_within_etsys_published_rules():
    for rank, (_name, data, _alt) in enumerate(IMAGES, start=1):
        assert C.image_bytes_problems("listing_image", data, position=rank) == []
        assert len(data) < 300_000
    assert C.digital_file_problems([(PDF_NAME, len(PDF))]) == []


def test_upload_attach_and_read_back_confirm_what_was_sent():
    with FakeEtsy() as fake:
        client, lid = _draft_with_uploads(fake)
        # 1. The exact bytes arrived, in order (server-side record; Etsy exposes no hash).
        got = fake.received_images[lid]
        assert [g["sha256"] for g in got] == [e["sha256"] for e in _expected_images()]
        assert [g["rank"] for g in got] == [1, 2]
        assert fake.received_files[lid] == [{"filename": PDF_NAME, "bytes": len(PDF),
                                             "sha256": hashlib.sha256(PDF).hexdigest()}]
        # 2. Read-back of the images: rank, alt text and pixel size, via the real client.
        remote = client.get_listing_images(lid)
        images = V.verify_images(_expected_images(), remote, listing_id=lid)
        assert images.verified, images.summary()
        assert [i["etsy_px"] for i in images.images] == [[2000, 2000], [2400, 2000]]
        # 3. Read-back of the file: name and exact size against the certified hash.
        expected_files = etsy_ops.file_expectations(
            {PDF_NAME: PDF}, {PDF_NAME: hashlib.sha256(PDF).hexdigest()})
        files = V.verify_files(expected_files, client.get_listing_files(lid), listing_id=lid)
        assert files.verified, files.summary()
        # 4. The runtime's own read-back (fields + files + alt texts) agrees.
        sent = _payload().to_dict()
        rb = etsy_ops.read_back(client, lid, sent=sent, expected_files=expected_files,
                                expected_images=len(IMAGES),
                                expected_alt_texts=[a for _n, _d, a in IMAGES])
        assert rb["images"]["verified"], rb
        assert rb["files"]["verified"], rb


def test_read_back_catches_a_dropped_alt_text_a_cropped_image_and_an_extra_image():
    with FakeEtsy() as fake:
        client, lid = _draft_with_uploads(fake)
        fake.images[lid][0]["alt_text"] = ""                       # Etsy dropped the disclosure
        fake.images[lid][1]["full_width"] = 1200                   # Etsy holds a cropped copy
        fake.images[lid].append({"listing_image_id": 1, "rank": 3, "alt_text": "",
                                 "full_width": 10, "full_height": 10})
        out = V.verify_images(_expected_images(), client.get_listing_images(lid),
                              listing_id=lid)
        assert not out.verified
        text = " ".join(out.problems)
        assert "rank 1 alt_text" in text and "rank 2 is 1200x2000" in text, text
        assert "extra image" in text and "sent 2, Etsy holds 3" in text, text


def test_a_size_not_yet_processed_is_pending_never_verified():
    with FakeEtsy() as fake:
        client, lid = _draft_with_uploads(fake)
        for img in fake.images[lid]:
            img["full_width"] = img["full_height"] = None
        out = V.verify_images(_expected_images(), client.get_listing_images(lid),
                              listing_id=lid)
        assert out.pending and not out.verified, out.summary()


def test_a_scaled_copy_of_an_oversized_image_is_recognised_as_the_same_image():
    exp = [{"alt_text": "", "width": 4000, "height": 3000}]
    ok = V.verify_images(exp, [{"rank": 1, "alt_text": "", "full_width": 3000,
                                "full_height": 2250}])
    assert ok.verified and "3000 px cap" in ok.images[0]["note"], ok.summary()
    bad = V.verify_images(exp, [{"rank": 1, "alt_text": "", "full_width": 3000,
                                 "full_height": 3000}])
    assert not bad.verified


def test_a_failed_read_is_unverified():
    out = V.verify_images(_expected_images(), None, listing_id="1")
    assert not out.verified and out.problems
    assert not V.verify_images([], [], listing_id="1").verified


def test_a_file_name_etsy_cannot_hold_is_refused_before_any_request():
    with FakeEtsy() as fake:
        client = _client(fake)
        lid = client.create_draft(_payload())
        before = len(fake.requests)
        for bad in ("Nordic Forest (US).pdf", "x" * 71 + ".pdf", "pattern.webp"):
            try:
                client.attach_file(lid, filename=bad, data=PDF)
            except EtsyRejected as e:
                assert "Etsy" in str(e), e
            else:
                raise AssertionError(f"{bad!r} was attached")
        assert len(fake.requests) == before, fake.requests[before:]
        assert lid not in fake.received_files


def test_publish_preflight_stops_before_the_create_so_no_orphan_draft_is_left():
    from brambleloop.integrations import etsy as E

    problems = E.publish_preflight("Nordic Forest.pdf", PDF,
                                   [("frame.webp", b"x", ""), ("f.png", b"x", "a" * 501)])
    text = " ".join(problems)
    assert "Nordic Forest.pdf" in text and "frame.webp" in text and "alt text" in text, text
    assert E.publish_preflight(PDF_NAME, PDF, [(n, d, a) for n, d, a in IMAGES]) == []
    assert len(E.publish_preflight(PDF_NAME, PDF, [("f.png", b"x")] * 21)) == 1


def test_the_verification_state_is_still_locally_tested_not_verified_against_etsy():
    rows = {r["claim"]: r for r in listing_schema.verification_matrix()}
    assert rows["multipart_image_upload"]["state"] == listing_schema.LOCALLY_TESTED
    assert "multipart_image_upload" not in {f["key"] for f in listing_schema.ETSY_VERIFIED_FACTS}


run(globals())
