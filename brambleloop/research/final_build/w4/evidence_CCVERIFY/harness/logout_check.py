import json, time, uuid, sys
exec(open("fetch.py").read().split("os.makedirs")[0])
import urllib.request
st, j, _ = req("/api/cc/company")
print("authed company:", st)
csrf = None
# re-login to get csrf
st, j, _ = req("/api/cc/auth/login", {"passphrase": p, "totp": totp_code(t)})
csrf = j["csrf_token"]
saved = dict(cookies)
h = {"origin": "http://localhost:8899", "content-type": "application/json", "X-CSRF-Token": csrf, "X-CC-Nonce": uuid.uuid4().hex, "X-CC-Timestamp": str(int(time.time())), "cookie": "; ".join(f"{k}={v}" for k, v in cookies.items())}
r = urllib.request.Request("http://localhost:8899/api/cc/auth/logout", data=b"{}", headers=h, method="POST")
with urllib.request.urlopen(r) as resp: print("logout:", resp.status)
cookies.clear(); cookies.update(saved)
st, j, _ = req("/api/cc/company"); print("old cookie after logout:", st)
# cross-origin mutation refused
h2 = dict(h); h2["origin"] = "https://evil.example"; h2["X-CC-Nonce"] = uuid.uuid4().hex
st2, j2, _ = req("/api/cc/auth/login", {"passphrase": p, "totp": totp_code(t)})
csrf2 = j2["csrf_token"]
h2["cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items()); h2["X-CSRF-Token"] = csrf2
r = urllib.request.Request("http://localhost:8899/api/cc/home/seen", data=b"{}", headers=h2, method="POST")
try:
    with urllib.request.urlopen(r) as resp: print("cross-origin POST:", resp.status)
except urllib.error.HTTPError as e: print("cross-origin POST:", e.code)
h3 = dict(h2); h3["origin"] = "http://localhost:8899"; del h3["X-CSRF-Token"]; h3["X-CC-Nonce"] = uuid.uuid4().hex
r = urllib.request.Request("http://localhost:8899/api/cc/home/seen", data=b"{}", headers=h3, method="POST")
try:
    with urllib.request.urlopen(r) as resp: print("no-CSRF POST:", resp.status)
except urllib.error.HTTPError as e: print("no-CSRF POST:", e.code)
r = urllib.request.Request("http://localhost:8899/api/cc/emergency/pause", data=json.dumps({"reason": "ccverify probe"}).encode(), headers={**h3, "X-CSRF-Token": csrf2, "X-CC-Nonce": uuid.uuid4().hex}, method="POST")
try:
    with urllib.request.urlopen(r) as resp: print("emergency pause without step-up:", resp.status, resp.read()[:200])
except urllib.error.HTTPError as e: print("emergency pause without step-up:", e.code, e.read()[:200])
