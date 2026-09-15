#!/usr/bin/env python3
"""Minimal Etsy Open API v3 client for the owner's own shop (seller app, OAuth 2.0 + PKCE).
No secrets in this file. Reads ETSY_KEYSTRING and ETSY_REFRESH_TOKEN from the environment.

CLI:
  python etsy_api.py auth-url                      # prints the URL the owner opens; stores the PKCE verifier in ~/.etsy_pkce.json
  python etsy_api.py exchange "<redirect url>"     # exchanges the pasted redirect URL for tokens; prints the refresh token ONCE
  python etsy_api.py me                            # user + shop ids
  python etsy_api.py search "bookkeeping spreadsheet canada" [limit]   # public findAllListingsActive competitor pull (keystring only)
  python etsy_api.py taxonomy "template"           # find taxonomy node ids by name fragment
  python etsy_api.py listings                      # own active listings with views/favourites
  python etsy_api.py receipts                      # recent orders (for the ledger)
Library: EtsyClient(...).create_digital_listing(...), .upload_file(...), .upload_image(...), .activate(...)
Docs: https://developers.etsy.com/documentation/  (rate limit 10 req/s, 10k/day per app)"""
import base64, hashlib, json, os, secrets, sys, time, urllib.parse, pathlib
import requests

API = "https://api.etsy.com/v3/application"
TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"
CONNECT_URL = "https://www.etsy.com/oauth/connect"
SCOPES = "listings_r listings_w listings_d shops_r shops_w transactions_r feedback_r"
DEFAULT_REDIRECT = "https://statefarm91.github.io/Project-Money/etsy-callback"
PKCE_FILE = pathlib.Path(os.environ.get("ETSY_PKCE_FILE", pathlib.Path.home() / ".etsy_pkce.json"))

def pkce_pair(verifier=None):
    verifier = verifier or base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge

def build_auth_url(keystring, redirect_uri=DEFAULT_REDIRECT, scopes=SCOPES, state=None, verifier=None):
    verifier, challenge = pkce_pair(verifier)
    state = state or secrets.token_urlsafe(16)
    q = {"response_type": "code", "redirect_uri": redirect_uri, "scope": scopes, "client_id": keystring,
         "state": state, "code_challenge": challenge, "code_challenge_method": "S256"}
    return CONNECT_URL + "?" + urllib.parse.urlencode(q), verifier, state

def parse_redirect(url):
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url.strip()).query)
    if "error" in q: raise RuntimeError(f"Etsy returned error: {q.get('error')} {q.get('error_description')}")
    return q["code"][0], q.get("state", [None])[0]

class EtsyClient:
    def __init__(self, keystring=None, refresh_token=None, session=None, sleep=time.sleep):
        self.keystring = keystring or os.environ.get("ETSY_KEYSTRING")
        self.refresh_token = refresh_token or os.environ.get("ETSY_REFRESH_TOKEN")
        if not self.keystring: raise RuntimeError("ETSY_KEYSTRING is not set (see CREDENTIALS_SETUP.md)")
        self.s = session or requests.Session(); self.access_token = None; self.expires_at = 0; self.sleep = sleep
        self.user_id = None; self.shop_id = None

    # ---- auth ----
    def exchange_code(self, code, verifier, redirect_uri=DEFAULT_REDIRECT):
        r = self.s.post(TOKEN_URL, json={"grant_type": "authorization_code", "client_id": self.keystring, "redirect_uri": redirect_uri, "code": code, "code_verifier": verifier}, timeout=30)
        r.raise_for_status(); d = r.json(); self._store(d); return d

    def refresh(self):
        if not self.refresh_token: raise RuntimeError("ETSY_REFRESH_TOKEN is not set; run the auth flow (OWNER_ACTIONS Block 1 step 7)")
        r = self.s.post(TOKEN_URL, json={"grant_type": "refresh_token", "client_id": self.keystring, "refresh_token": self.refresh_token}, timeout=30)
        r.raise_for_status(); d = r.json(); self._store(d); return d

    def _store(self, d):
        self.access_token = d["access_token"]; self.refresh_token = d.get("refresh_token", self.refresh_token)
        self.expires_at = time.time() + int(d.get("expires_in", 3600)) - 60
        self.user_id = self.access_token.split(".")[0] if "." in self.access_token else self.user_id

    def _headers(self, auth=True):
        h = {"x-api-key": self.keystring}
        if auth:
            if not self.access_token or time.time() > self.expires_at: self.refresh()
            h["Authorization"] = f"Bearer {self.access_token}"
        return h

    def _req(self, method, path, auth=True, retries=3, **kw):
        url = path if path.startswith("http") else API + path
        for attempt in range(retries):
            r = self.s.request(method, url, headers={**self._headers(auth), **kw.pop("headers", {})}, timeout=60, **kw)
            if r.status_code == 429 or r.status_code >= 500:
                self.sleep(2 ** attempt); continue
            if r.status_code >= 400: raise RuntimeError(f"Etsy {method} {path} -> {r.status_code}: {r.text[:500]}")
            return r.json() if r.content else {}
        raise RuntimeError(f"Etsy {method} {path}: gave up after {retries} attempts ({r.status_code})")

    # ---- reads ----
    def me(self):
        d = self._req("GET", "/users/me"); self.user_id = d.get("user_id"); self.shop_id = d.get("shop_id"); return d
    def shop(self, shop_id=None): return self._req("GET", f"/shops/{shop_id or self.shop_id}")
    def search_active(self, keywords, limit=50, offset=0, sort_on="score", extra=None):
        """Public search (no user token). Returns dict with count and results (listing_id, title, price, num_favorers, views, creation_timestamp, shop_id, tags)."""
        params = {"keywords": keywords, "limit": limit, "offset": offset, "sort_on": sort_on}; params.update(extra or {})
        return self._req("GET", "/listings/active", auth=False, params=params)
    def taxonomy(self): return self._req("GET", "/seller-taxonomy/nodes", auth=False)
    def find_taxonomy(self, fragment):
        out = []
        def walk(nodes, path):
            for n in nodes:
                p = path + [n["name"]]
                if fragment.lower() in n["name"].lower(): out.append((n["id"], " > ".join(p)))
                walk(n.get("children", []), p)
        walk(self.taxonomy().get("results", []), []); return out
    def own_listings(self, state="active", limit=100):
        return self._req("GET", f"/shops/{self.shop_id}/listings", params={"state": state, "limit": limit, "includes": "Images"})
    def listing(self, listing_id): return self._req("GET", f"/listings/{listing_id}", auth=False)
    def receipts(self, limit=50, min_created=None):
        params = {"limit": limit}
        if min_created: params["min_created"] = int(min_created)
        return self._req("GET", f"/shops/{self.shop_id}/receipts", params=params)

    # ---- writes ----
    def create_digital_listing(self, title, description, price_cad, taxonomy_id, tags, materials=None, quantity=999, who_made="i_did", when_made="2020_2026", state="draft"):
        assert len(tags) <= 13 and all(len(t) <= 20 for t in tags), "Etsy: max 13 tags, 20 chars each"
        assert len(title) <= 140, "Etsy: title max 140 chars"
        body = {"quantity": quantity, "title": title, "description": description, "price": float(price_cad), "who_made": who_made, "when_made": when_made,
                "taxonomy_id": int(taxonomy_id), "type": "download", "tags": tags, "materials": materials or ["Excel", "Google Sheets"], "state": state,
                "is_supply": False, "should_auto_renew": True, "is_customizable": False, "is_personalizable": False}
        return self._req("POST", f"/shops/{self.shop_id}/listings", data=body)
    def upload_file(self, listing_id, path, name=None, rank=1):
        p = pathlib.Path(path)
        with p.open("rb") as f:
            return self._req("POST", f"/shops/{self.shop_id}/listings/{listing_id}/files", files={"file": (name or p.name, f)}, data={"name": name or p.name, "rank": rank})
    def upload_image(self, listing_id, path, rank=1, alt_text=None):
        p = pathlib.Path(path)
        with p.open("rb") as f:
            data = {"rank": rank}
            if alt_text: data["alt_text"] = alt_text[:250]
            return self._req("POST", f"/shops/{self.shop_id}/listings/{listing_id}/images", files={"image": (p.name, f)}, data=data)
    def update_listing(self, listing_id, **fields): return self._req("PATCH", f"/shops/{self.shop_id}/listings/{listing_id}", data=fields)
    def activate(self, listing_id): return self.update_listing(listing_id, state="active")

def main(argv):
    if not argv: print(__doc__); return 0
    cmd, args = argv[0], argv[1:]
    key = os.environ.get("ETSY_KEYSTRING")
    if cmd == "auth-url":
        if not key: print("ETSY_KEYSTRING not set"); return 2
        url, verifier, state = build_auth_url(key)
        PKCE_FILE.write_text(json.dumps({"verifier": verifier, "state": state, "created": time.time()})); PKCE_FILE.chmod(0o600)
        print(url); return 0
    if cmd == "exchange":
        d = json.loads(PKCE_FILE.read_text()); code, state = parse_redirect(args[0])
        if state != d["state"]: print("state mismatch: generate a new auth-url"); return 2
        c = EtsyClient(key); tok = c.exchange_code(code, d["verifier"])
        print("ETSY_REFRESH_TOKEN (store in environment variables + GitHub Actions secret; shown once):"); print(tok["refresh_token"]); PKCE_FILE.unlink(missing_ok=True); return 0
    c = EtsyClient(key)
    if cmd == "me": print(json.dumps(c.me(), indent=1)); return 0
    if cmd == "search":
        r = c.search_active(args[0], limit=int(args[1]) if len(args) > 1 else 50)
        print(json.dumps({"count": r.get("count"), "results": [{k: x.get(k) for k in ("listing_id", "title", "num_favorers", "views", "creation_timestamp", "shop_id", "tags")} | {"price": (x.get("price") or {}).get("amount", 0) / max(1, (x.get("price") or {}).get("divisor", 100)), "currency": (x.get("price") or {}).get("currency_code")} for x in r.get("results", [])]}, indent=1)); return 0
    if cmd == "taxonomy":
        for i, p in c.find_taxonomy(args[0]): print(i, p)
        return 0
    c.me()
    if cmd == "listings": print(json.dumps([{k: x.get(k) for k in ("listing_id", "title", "state", "views", "num_favorers", "quantity", "url")} for x in c.own_listings().get("results", [])], indent=1)); return 0
    if cmd == "receipts": print(json.dumps(c.receipts(), indent=1)[:5000]); return 0
    print("unknown command"); return 2

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
