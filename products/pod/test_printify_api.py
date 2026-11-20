"""Offline tests for printify_api.py (no network). Run: .venv/bin/python products/pod/test_printify_api.py"""
import json, sys, pathlib, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import printify_api as P


class FakeResp:
    def __init__(self, status, body):
        self.status_code = status
        self._b = body
        self.content = json.dumps(body).encode()
        self.text = json.dumps(body)

    def json(self):
        return self._b


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kw):
        self.calls.append((method, url, kw))
        return self.responses.pop(0)


def test_requires_token():
    try:
        P.PrintifyClient(token=None, session=FakeSession([]))
        assert False, "should have raised without PRINTIFY_TOKEN"
    except RuntimeError as e:
        assert "PRINTIFY_TOKEN" in str(e)


def test_shops_uses_bearer_header():
    s = FakeSession([FakeResp(200, [{"id": 1, "title": "MapleSheets"}])])
    c = P.PrintifyClient("tok", session=s)
    d = c.shops()
    assert d == [{"id": 1, "title": "MapleSheets"}]
    method, url, kw = s.calls[0]
    assert method == "GET" and url == "https://api.printify.com/v1/shops.json"
    assert kw["headers"]["Authorization"] == "Bearer tok"


def test_retry_on_429_then_success():
    slept = []
    s = FakeSession([FakeResp(429, {}), FakeResp(200, {"id": 5})])
    c = P.PrintifyClient("tok", session=s, sleep=slept.append)
    d = c.blueprint(5)
    assert d == {"id": 5} and slept == [1]


def test_retry_gives_up_after_max_attempts():
    s = FakeSession([FakeResp(500, {}), FakeResp(500, {}), FakeResp(500, {})])
    c = P.PrintifyClient("tok", session=s, sleep=lambda _: None)
    try:
        c.blueprints(); assert False
    except RuntimeError:
        pass
    assert len(s.calls) == 3


def test_4xx_raises_immediately_with_body():
    s = FakeSession([FakeResp(422, {"errors": {"title": ["is required"]}})])
    c = P.PrintifyClient("tok", session=s)
    try:
        c.create_product(1, "", "d", 3, 24, [], []); assert False
    except RuntimeError as e:
        assert "422" in str(e) and "is required" in str(e)
    assert len(s.calls) == 1  # no retry on a 4xx


def test_canadian_providers_filters_by_location():
    providers = [
        {"id": 1, "title": "US Print Co", "location": {"country": "US"}},
        {"id": 2, "title": "MapleWorks Toronto", "location": {"country": "CA", "region": "Canada"}},
    ]
    s = FakeSession([FakeResp(200, providers)])
    c = P.PrintifyClient("tok", session=s)
    result = c.canadian_providers()
    assert len(result) == 1 and result[0]["id"] == 2


def test_upload_image_from_path_base64_encodes():
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        f.write(b"not a real png, just bytes"); f.flush()
        s = FakeSession([FakeResp(200, {"id": "upload123", "file_name": "test-design.png"})])
        c = P.PrintifyClient("tok", session=s)
        d = c.upload_image("test-design.png", path=f.name)
    assert d["id"] == "upload123"
    method, url, kw = s.calls[0]
    assert url.endswith("/uploads/images.json")
    assert kw["json"]["file_name"] == "test-design.png"
    assert kw["json"]["contents"]  # base64 string present, non-empty


def test_upload_image_requires_exactly_one_source():
    c = P.PrintifyClient("tok", session=FakeSession([]))
    try:
        c.upload_image("x.png"); assert False
    except AssertionError:
        pass
    try:
        c.upload_image("x.png", path="a", url="b"); assert False
    except AssertionError:
        pass


def test_create_product_body_shape():
    s = FakeSession([FakeResp(200, {"id": "prod1"})])
    c = P.PrintifyClient("tok", session=s)
    variants = [{"id": 17390, "price": 2500, "is_enabled": True}]
    print_areas = [{"variant_ids": [17390], "placeholders": [{"position": "front", "images": [{"id": "upload123", "x": 0.5, "y": 0.5, "scale": 1.0, "angle": 0}]}]}]
    d = c.create_product(999, "Muskoka Mug", "desc", 3, 24, variants, print_areas, tags=["canada", "gift"])
    assert d["id"] == "prod1"
    method, url, kw = s.calls[0]
    assert method == "POST" and url.endswith("/shops/999/products.json")
    assert kw["json"]["blueprint_id"] == 3 and kw["json"]["print_provider_id"] == 24
    assert kw["json"]["variants"] == variants and kw["json"]["tags"] == ["canada", "gift"]


def test_publish_product_defaults_all_true():
    s = FakeSession([FakeResp(200, {"status": "ok"})])
    c = P.PrintifyClient("tok", session=s)
    c.publish_product(999, "prod1")
    method, url, kw = s.calls[0]
    assert url.endswith("/shops/999/products/prod1/publish.json")
    assert all(kw["json"].values())


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn(); print("OK ", name)
            except Exception as e:
                fails += 1; print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
