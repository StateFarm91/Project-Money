#!/usr/bin/env python3
"""Minimal Printify API v1 client for the owner's own shop (personal access token).
No secrets in this file. Reads PRINTIFY_TOKEN from the environment (CREDENTIALS_SETUP.md).
The shop must already be connected to the Etsy shop inside Printify (OWNER_ACTIONS Block 1
step 9); publish.json then pushes the product live on Etsy through Printify's own connection
-- this client never calls Etsy's listing API for POD products.

CLI:
  python printify_api.py shops                                  # shop ids (need one for every other call)
  python printify_api.py blueprints                              # catalog: product types (mugs, prints, totes, ...)
  python printify_api.py providers <blueprint_id>                 # print providers for a blueprint
  python printify_api.py locations                                # global print-provider list with location (filter for Canada)
  python printify_api.py variants <blueprint_id> <print_provider_id>  # sizes/colours + Printify's cost per variant
  python printify_api.py upload <file_name> <path>                # upload artwork; prints the image id to use in print_areas
  python printify_api.py orders <shop_id>
Library: PrintifyClient(...).create_product(...), .publish_product(...)
Docs: https://developers.printify.com/  (rate limits vary by endpoint; POST endpoints ~200 req/30 min)"""
import base64, json, os, pathlib, sys, time
import requests

API = "https://api.printify.com/v1"


class PrintifyClient:
    def __init__(self, token=None, session=None, sleep=time.sleep):
        self.token = token or os.environ.get("PRINTIFY_TOKEN")
        if not self.token:
            raise RuntimeError("PRINTIFY_TOKEN is not set (see CREDENTIALS_SETUP.md)")
        self.s = session or requests.Session()
        self.sleep = sleep

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "User-Agent": "MapleSheets-POD/1.0"}

    def _req(self, method, path, retries=3, **kw):
        url = path if path.startswith("http") else API + path
        for attempt in range(retries):
            r = self.s.request(method, url, headers={**self._headers(), **kw.pop("headers", {})}, timeout=60, **kw)
            if r.status_code == 429 or r.status_code >= 500:
                self.sleep(2 ** attempt)
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"Printify {method} {path} -> {r.status_code}: {r.text[:500]}")
            return r.json() if r.content else {}
        raise RuntimeError(f"Printify {method} {path}: gave up after {retries} attempts ({r.status_code})")

    # ---- catalog (reads; no shop needed) ----
    def shops(self):
        return self._req("GET", "/shops.json")

    def blueprints(self):
        return self._req("GET", "/catalog/blueprints.json")

    def blueprint(self, blueprint_id):
        return self._req("GET", f"/catalog/blueprints/{blueprint_id}.json")

    def print_providers(self, blueprint_id):
        return self._req("GET", f"/catalog/blueprints/{blueprint_id}/print_providers.json")

    def provider_locations(self):
        """Global print-provider list with location; use to find Canadian-shipping providers (D-007/D-008/C19: ship
        from Canada in 4-8 days, no cross-border duties)."""
        return self._req("GET", "/catalog/print_providers.json")

    def canadian_providers(self):
        return [p for p in self.provider_locations() if "canada" in json.dumps(p.get("location", {})).lower()]

    def variants(self, blueprint_id, print_provider_id):
        return self._req("GET", f"/catalog/blueprints/{blueprint_id}/print_providers/{print_provider_id}/variants.json")

    # ---- uploads ----
    def upload_image(self, file_name, path=None, url=None):
        assert (path is None) != (url is None), "pass exactly one of path or url"
        body = {"file_name": file_name}
        if path:
            body["contents"] = base64.b64encode(pathlib.Path(path).read_bytes()).decode()
        else:
            body["url"] = url
        return self._req("POST", "/uploads/images.json", json=body)

    def list_uploads(self):
        return self._req("GET", "/uploads.json")

    # ---- products ----
    def create_product(self, shop_id, title, description, blueprint_id, print_provider_id, variants, print_areas, tags=None):
        """variants: [{"id": <variant_id>, "price": <cents>, "is_enabled": True}, ...]
        print_areas: [{"variant_ids": [...], "placeholders": [{"position": "front", "images": [{"id": <upload_id>, "x": 0.5, "y": 0.5, "scale": 1.0, "angle": 0}]}]}]"""
        body = {"title": title, "description": description, "blueprint_id": int(blueprint_id), "print_provider_id": int(print_provider_id),
                "variants": variants, "print_areas": print_areas}
        if tags:
            body["tags"] = tags
        return self._req("POST", f"/shops/{shop_id}/products.json", json=body)

    def publish_product(self, shop_id, product_id, title=True, description=True, images=True, variants=True, tags=True):
        body = {"title": title, "description": description, "images": images, "variants": variants, "tags": tags}
        return self._req("POST", f"/shops/{shop_id}/products/{product_id}/publish.json", json=body)

    def list_orders(self, shop_id, page=1):
        return self._req("GET", f"/shops/{shop_id}/orders.json", params={"page": page})


def main(argv):
    if not argv:
        print(__doc__)
        return 0
    cmd, args = argv[0], argv[1:]
    c = PrintifyClient()
    if cmd == "shops":
        print(json.dumps(c.shops(), indent=1)); return 0
    if cmd == "blueprints":
        print(json.dumps([{k: b.get(k) for k in ("id", "title", "brand", "model")} for b in c.blueprints()], indent=1)); return 0
    if cmd == "providers":
        print(json.dumps(c.print_providers(args[0]), indent=1)); return 0
    if cmd == "locations":
        print(json.dumps(c.canadian_providers(), indent=1)); return 0
    if cmd == "variants":
        print(json.dumps(c.variants(args[0], args[1]), indent=1)); return 0
    if cmd == "upload":
        print(json.dumps(c.upload_image(args[0], path=args[1]), indent=1)); return 0
    if cmd == "orders":
        print(json.dumps(c.list_orders(args[0]), indent=1)); return 0
    print("unknown command"); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
