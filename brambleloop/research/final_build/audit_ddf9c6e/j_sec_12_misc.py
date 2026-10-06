from j_sec_common import *
import concurrent.futures as cf
# CORS
c=client(); r=c.get("/api/cc/auth/status", headers={"Origin":"https://evil.example"}); print("CORS headers on status:", {k:v for k,v in r.headers.items() if k.lower().startswith("access-control")} or "none")
r=c.options("/api/cc/ask", headers={"Origin":"https://evil.example","Access-Control-Request-Method":"POST"}); print("preflight:", r.status_code, {k:v for k,v in r.headers.items() if k.lower().startswith("access-control")} or "no ACAO")
# ask on empty DB
csrf=login(c)
for q in ["how much revenue did we make?","why did profit fall?"]:
    j=c.post("/api/cc/ask", headers=fresh(csrf), json={"question":q}).json(); print("ASK", q, "->", j["status"], j["answer"][:150])
# race on login limiter
clear_events()
def attempt(i):
    return client().post("/api/cc/auth/login", json={"passphrase":f"bad{i}"}).status_code
with cf.ThreadPoolExecutor(40) as ex: codes=list(ex.map(attempt, range(60)))
print("60 concurrent bad logins: 401 =",codes.count(401),"429 =",codes.count(429),"(limit is 5/client, 20 global)")
