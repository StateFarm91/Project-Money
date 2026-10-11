import json, sys, time, urllib.request, http.cookiejar, os
sys.path.insert(0, "/home/user/Project-Money/.claude/worktrees/W4-CCVERIFY/brambleloop/src")
from brambleloop.app.command_center.auth import totp_code
p, t = open("test_plain.secret").read().split()
cj = http.cookiejar.CookieJar()
# __Host- Secure cookies over http: handle manually
cookies = {}
def req(path, body=None, method=None):
    h = {"origin": "http://localhost:8899"}
    if cookies: h["cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    if body is not None: h["content-type"] = "application/json"
    r = urllib.request.Request("http://localhost:8899" + path, data=json.dumps(body).encode() if body is not None else None, headers=h, method=method)
    t0 = time.time()
    try:
        with urllib.request.urlopen(r, timeout=600) as resp:
            for c in resp.headers.get_all("set-cookie") or []:
                k, v = c.split(";")[0].split("=", 1); cookies[k] = v
            return resp.status, json.loads(resp.read()), time.time() - t0
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}"), time.time() - t0
st, j, _ = req("/api/cc/auth/login", {"passphrase": p, "totp": totp_code(t)})
assert st == 200
os.makedirs("api", exist_ok=True)
for path in sys.argv[1:]:
    st, j, dt = req(path)
    name = path.strip("/").replace("/", "_").replace("?", "_").replace("=", "-")
    json.dump(j, open(f"api/{name}.json", "w"), indent=1, default=str)
    print(path, st, round(dt, 1), len(json.dumps(j)))
