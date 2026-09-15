"""Offline tests for etsy_api.py (no network). Run: .venv/bin/python -m pytest products/etsy-templates -q  or  python test_etsy_api.py"""
import json, sys, pathlib, urllib.parse
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import etsy_api as E

def test_pkce_rfc7636_vector():
    v = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert E.pkce_pair(v)[1] == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"

def test_auth_url_contains_required_params():
    url, verifier, state = E.build_auth_url("key123", verifier="abc" * 20, state="st")
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert q["client_id"] == ["key123"] and q["code_challenge_method"] == ["S256"] and q["state"] == ["st"]
    assert q["redirect_uri"] == [E.DEFAULT_REDIRECT] and "listings_w" in q["scope"][0] and q["response_type"] == ["code"]

def test_parse_redirect():
    code, state = E.parse_redirect("https://statefarm91.github.io/Project-Money/etsy-callback?code=abc.def&state=xyz")
    assert code == "abc.def" and state == "xyz"

class FakeResp:
    def __init__(self, status, body): self.status_code = status; self._b = body; self.content = json.dumps(body).encode(); self.text = json.dumps(body)
    def json(self): return self._b
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(self.status_code)

class FakeSession:
    def __init__(self, responses): self.responses = list(responses); self.calls = []
    def request(self, method, url, **kw): self.calls.append((method, url, kw)); return self.responses.pop(0)
    def post(self, url, **kw): self.calls.append(("POST", url, kw)); return self.responses.pop(0)

def test_refresh_then_get_me_and_headers():
    s = FakeSession([FakeResp(200, {"access_token": "12345.tok", "refresh_token": "r2", "expires_in": 3600}), FakeResp(200, {"user_id": 12345, "shop_id": 777})])
    c = E.EtsyClient("key", "r1", session=s); d = c.me()
    assert d["shop_id"] == 777 and c.shop_id == 777 and c.refresh_token == "r2"
    m, url, kw = s.calls[1]; assert kw["headers"]["x-api-key"] == "key" and kw["headers"]["Authorization"] == "Bearer 12345.tok"

def test_public_search_uses_only_api_key():
    s = FakeSession([FakeResp(200, {"count": 1, "results": [{"listing_id": 1, "title": "t", "price": {"amount": 2900, "divisor": 100, "currency_code": "CAD"}}]})])
    c = E.EtsyClient("key", None, session=s); r = c.search_active("bookkeeping canada", limit=5)
    assert r["count"] == 1 and "Authorization" not in s.calls[0][2]["headers"] and s.calls[0][2]["params"]["keywords"] == "bookkeeping canada"

def test_retry_on_429_then_success():
    slept = []
    s = FakeSession([FakeResp(429, {}), FakeResp(200, {"results": []})])
    c = E.EtsyClient("key", None, session=s, sleep=slept.append); r = c.taxonomy()
    assert r == {"results": []} and slept == [1]

def test_create_listing_validates_tags_and_title():
    s = FakeSession([FakeResp(200, {"access_token": "1.t", "expires_in": 3600}), FakeResp(200, {"listing_id": 42})])
    c = E.EtsyClient("key", "r", session=s); c.shop_id = 777
    d = c.create_digital_listing("Title", "Desc", 29, 1234, ["tag one", "tag two"])
    assert d["listing_id"] == 42 and s.calls[1][2]["data"]["type"] == "download" and s.calls[1][2]["data"]["price"] == 29.0
    try:
        c.create_digital_listing("T", "D", 29, 1, ["x" * 21]); assert False
    except AssertionError: pass

def test_find_taxonomy_walks_children():
    s = FakeSession([FakeResp(200, {"results": [{"id": 1, "name": "Paper", "children": [{"id": 2, "name": "Templates", "children": [{"id": 3, "name": "Spreadsheet Templates", "children": []}]}]}]})])
    c = E.EtsyClient("key", None, session=s)
    assert c.find_taxonomy("template") == [(2, "Paper > Templates"), (3, "Paper > Templates > Spreadsheet Templates")]

if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try: fn(); print("OK ", name)
            except Exception as e: fails += 1; print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
