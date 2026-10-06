"""W3 lane I: Etsy's published store/listing constraints, and the code that agrees with them.

`integrations.etsy_constraints` carries every Etsy image size, field limit and file limit the
store and publish path rely on, each quoted from an Etsy document read on 2026-10-06. These
tests pin the numbers to the quotes (so a changed number without a changed quote fails), check
the checkers on real image bytes, and check that the client's own constants agree.

No network: the evidence is recorded in the module; nothing here contacts Etsy.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_etsy_constraints.py
"""
from __future__ import annotations

import io
import json
from datetime import date

from _r2_harness import run

from PIL import Image

from brambleloop.integrations import etsy as E
from brambleloop.integrations import etsy_constraints as C


def _png(w: int, h: int, *, alpha: int | None = None) -> bytes:
    mode = "RGBA" if alpha is not None else "RGB"
    colour = (40, 80, 60, alpha) if alpha is not None else (40, 80, 60)
    buf = io.BytesIO()
    Image.new(mode, (w, h), colour).save(buf, "PNG")
    return buf.getvalue()


def _jpg(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 190, 170)).save(buf, "JPEG", quality=70)
    return buf.getvalue()


def _codes(findings: list[dict]) -> set[str]:
    return {f["code"] for f in findings}


# ---- the evidence itself ------------------------------------------------------------------

def test_every_verified_constraint_quotes_a_recorded_etsy_source():
    verified = [c for c in C.CONSTRAINTS.values() if c.verified]
    assert len(verified) >= 50, len(verified)
    for c in verified:
        assert c.quote.strip(), c.key
        src = C.SOURCES[c.source]
        assert src.url.startswith(("https://help.etsy.com/", "https://www.etsy.com/openapi")), \
            (c.key, src.url)


def test_no_constraint_rests_on_a_third_party_size_guide():
    blob = json.dumps(C.summary()).lower()
    for domain in ("linearity", "printify", "picsart", "adnabu", "canva.com"):
        assert domain not in blob, domain
    # "3360 x 840" may appear only inside the note saying no Etsy document states it.
    assert "3360" not in json.dumps([c.value for c in C.CONSTRAINTS.values()])


def test_unknown_constraints_carry_no_number_and_refuse_to_be_read():
    unknown = [c for c in C.CONSTRAINTS.values() if c.basis == C.UNKNOWN]
    assert {"announcement_max_chars", "materials_max", "description_max_chars",
            "banner_mobile_crop"} <= {c.key for c in unknown}
    for c in unknown:
        assert c.value is None and c.note, c.key
        try:
            C.value(c.key)
        except LookupError:
            continue
        raise AssertionError(f"{c.key} returned a value")


def test_a_verified_constraint_without_a_quote_cannot_be_written():
    try:
        C.Constraint("x", "s", "w", 1, C.VERIFIED_HELP, "115015663347", "")
    except ValueError:
        return
    raise AssertionError("an unquoted verified constraint was accepted")


def test_the_published_numbers():
    v = C.value
    assert v("logo_min_px") == (500, 500) and v("logo_recommended_px") == (500, 500)
    assert v("profile_min_px") == (400, 400)
    assert v("big_banner_min_px") == (1200, 300) and v("big_banner_recommended_px") == (1600, 400)
    assert v("mini_banner_min_px") == (1200, 160) and v("mini_banner_recommended_px") == (1600, 213)
    assert v("shop_title_max_chars") == 55 and v("about_max_chars") == 5000
    assert v("sections_max") == 20 and v("section_name_max_chars") == 24
    assert v("title_max_chars") == 140 and v("tags_max") == 13 and v("tag_max_chars") == 20
    assert v("listing_images_max") == 20 and v("listing_image_recommended_px") == 2000
    assert v("first_image_min_px") == 635
    assert v("digital_files_max") == 5 and v("digital_file_max_bytes") == 20 * C.MB
    assert v("digital_filename_max_chars") == 70 and v("alt_text_max_chars") == 500
    # Each number appears in its own quote, so a number edited alone fails here.
    for key in ("shop_title_max_chars", "section_name_max_chars", "title_max_chars",
                "tag_max_chars", "first_image_min_px", "listing_image_recommended_px"):
        assert str(v(key)) in C.CONSTRAINTS[key].quote, key


def test_staleness_is_visible():
    assert not C.is_stale(date(2026, 10, 6))
    assert C.is_stale(date(2026, 11, 20))


def test_summary_is_json_and_counts_every_basis():
    s = C.summary()
    json.dumps(s)
    assert sum(s["counts_by_basis"].values()) == len(C.CONSTRAINTS) == len(s["constraints"])
    assert [step["step"] for step in s["taxonomy_flow"]] == list(range(1, 9))
    assert s["taxonomy_id"]["basis"] == C.UNVERIFIED


# ---- the checkers, on real bytes ----------------------------------------------------------

def test_image_info_reads_png_jpeg_and_transparency():
    info = C.image_info(_png(1600, 400))
    assert (info["format"], info["width"], info["height"], info["transparent"]) == \
        ("png", 1600, 400, False)
    info = C.image_info(_jpg(2000, 1500))
    assert (info["format"], info["width"], info["height"]) == ("jpg", 2000, 1500)
    assert C.image_info(_png(500, 500, alpha=0))["transparent"] is True
    assert C.image_info(_png(500, 500, alpha=255))["transparent"] is False


def test_banner_and_logo_at_etsy_sizes_pass_and_below_minimum_fail():
    assert C.image_bytes_problems("big_banner", _png(1600, 400)) == []
    assert C.image_bytes_problems("shop_logo", _png(500, 500)) == []
    assert C.image_bytes_problems("profile_photo", _png(400, 400)) == []
    small = C.image_bytes_problems("big_banner", _png(1000, 250))
    assert "IMAGE_BELOW_MINIMUM" in _codes(small)
    assert any(f["severity"] == "fail" for f in small)
    wide = C.image_bytes_problems("big_banner", _png(3360, 840))   # the third-party "size"
    assert _codes(wide) == set(), wide        # bigger, same 4:1 aspect: fine, not required
    odd = C.image_bytes_problems("big_banner", _png(2000, 400))
    assert "BANNER_ASPECT_DIFFERS" in _codes(odd)
    mini = C.image_bytes_problems("mini_banner", _png(1600, 213))
    assert mini == [], mini


def test_profile_photo_must_be_square_and_logo_transparency_is_refused():
    assert "PROFILE_NOT_SQUARE" in _codes(C.image_bytes_problems("profile_photo",
                                                                 _png(600, 400)))
    found = C.image_bytes_problems("shop_logo", _png(500, 500, alpha=0))
    assert "IMAGE_TRANSPARENT" in _codes(found)


def test_listing_image_rules():
    assert C.image_bytes_problems("listing_image", _jpg(2000, 2000)) == []
    portrait = C.image_bytes_problems("listing_image", _jpg(2000, 2600), position=1)
    assert "FIRST_IMAGE_PORTRAIT" in _codes(portrait)
    assert "FIRST_IMAGE_PORTRAIT" not in _codes(
        C.image_bytes_problems("listing_image", _jpg(2000, 2600), position=2))
    tiny = C.image_bytes_problems("listing_image", _jpg(600, 600))
    assert {"FIRST_IMAGE_BELOW_635", "LISTING_IMAGE_BELOW_2000"} <= _codes(tiny)
    assert all(f["severity"] == "warn" for f in tiny), tiny     # recommendations, not refusals
    webp = C.image_problems("listing_image", width=2000, height=2000, fmt="webp")
    assert "IMAGE_FORMAT_UNSUPPORTED" in _codes(webp)
    garbage = C.image_bytes_problems("listing_image", b"not an image")
    assert _codes(garbage) == {"IMAGE_UNREADABLE"}


def test_digital_file_rules():
    good = "nordic-forest-throw-crochet-pattern-v1.pdf"
    assert C.digital_file_problems([(good, 2_000_000)]) == []
    assert "DIGITAL_NO_FILE" in _codes(C.digital_file_problems([]))
    assert "DIGITAL_FILENAME_CHARACTERS" in _codes(
        C.digital_file_problems([("Nordic Forest (US).pdf", 10)]))
    assert "DIGITAL_FILENAME_TOO_LONG" in _codes(C.digital_file_problems([("a" * 67 + ".pdf",
                                                                           10)]))
    assert "DIGITAL_FILE_TOO_LARGE" in _codes(C.digital_file_problems([(good, 21 * C.MB)]))
    assert "DIGITAL_TOO_MANY_FILES" in _codes(
        C.digital_file_problems([(f"p{i}.pdf", 10) for i in range(6)]))
    assert "DIGITAL_FILE_TYPE" in _codes(C.digital_file_problems([("p.webp", 10)]))


def test_text_rules():
    assert C.text_problems("shop_title", "x" * 55) == []
    assert "TEXT_TOO_LONG" in _codes(C.text_problems("shop_title", "x" * 56))
    assert "TEXT_TOO_LONG" in _codes(C.text_problems("section_name", "x" * 25))
    assert C.text_problems("section_name", "Collections & Bundles") == []
    unknown = C.text_problems("announcement", "Hello")
    assert _codes(unknown) == {"LIMIT_UNKNOWN"} and unknown[0]["severity"] == "unverified"
    assert "TAG_LEADING_PUNCTUATION" in _codes(C.text_problems("tag", "-granny square"))
    assert C.text_problems("tag", "granny square") == []
    assert "ALT_TEXT_OVER_ADVICE" in _codes(C.text_problems("alt_text", "a" * 300))
    assert C.shop_name_problems("BrambleloopStudio") == []
    assert "SHOP_NAME_CHARACTERS" in _codes(C.shop_name_problems("Brambleloop Studio"))


# ---- reconciliation with the code ---------------------------------------------------------

def test_reconcile_runs_and_every_status_is_known():
    rows = C.reconcile()
    json.dumps(rows)
    assert len(rows) >= 20, len(rows)
    for r in rows:
        assert r["status"] in C.STATUSES, r


def test_client_constants_now_agree_with_etsy():
    rows = {r["where"]: r for r in C.reconcile()}
    for where in ("integrations.etsy.TITLE_MAX", "integrations.etsy.TAGS_MAX",
                  "integrations.etsy.TAG_CHARS_MAX", "integrations.etsy.ALT_TEXT_MAX",
                  "integrations.etsy.IMAGE_CONTENT_TYPES", "publish.listing_schema.MAX_IMAGES",
                  "brand.storefront.BANNER_SIZE", "brand.storefront.ICON_SIZE"):
        assert rows[where]["status"] == C.AGREES, rows[where]


def test_shop_title_row_tracks_the_real_length():
    rows = [r for r in C.reconcile() if r["where"].startswith("commerce.shop_package")
            and "title" in r["where"]]
    assert len(rows) == 1
    r = rows[0]
    assert r["status"] == (C.AGREES if r["repo_value"] <= 55 else C.DISAGREES), r


def test_client_refuses_a_webp_listing_image_before_sending():
    sent = []

    class _T:
        def request(self, method, url, **kw):
            sent.append(url)
            raise AssertionError("nothing should be sent")

    client = E.EtsyClient(_T(), credentials=E.Credentials(api_key="k", access_token="t",
                                                          shop_id="S"),
                          phase="shadow", shadow_writes_authorised=True)
    assert ".webp" not in E.IMAGE_CONTENT_TYPES
    try:
        client.upload_image("1", filename="frame.webp", data=b"RIFFxxxxWEBP")
    except E.EtsyRejected as e:
        assert "not a listing-image format" in str(e)
    else:
        raise AssertionError("webp upload was not refused")
    assert sent == []


run(globals())
