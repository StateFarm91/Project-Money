"""W4-GATESI: the infrastructure gates' zero-cost repo-side fixes, proven offline.

1. image_generation: `images.probe` called `generate` with no `work_dir`, so every real probe
   recorded "generate() needs a work_dir" (production, 2026-10-07T00:03Z) and the gate could
   not open on any balance. The probe now owns a scratch directory for its one render.
2. offsite_storage: the SigV4 region defaulted to us-west-004 for every endpoint, so an R2
   bucket (`auto`) or a B2 bucket in another region would fail its first signed write.
3. rendered_pages / #39: the Help-Center-hosted policies are read through Etsy's public Help
   Center article API (no browser, no evasion); `listing_image_rules` pointed at the wrong
   article. etsy.com/legal stays external (DataDome).

No network: every fetch and every render is injected.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
import urllib.error
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.core.db import Database  # noqa: E402

PASSED = FAILED = 0


def check(name, ok, detail=""):
    global PASSED, FAILED
    PASSED += bool(ok)
    FAILED += (not ok)
    print(("OK   " if ok else "FAIL ") + name + ("" if ok else f"  -- {detail}"))


def _db(d):
    db = Database(f"sqlite:///{d}/t.db")
    db.create_all()
    return db


# ---------------------------------------------------------------------------
# 1. image_generation probe owns a work_dir

from brambleloop.gateway import images  # noqa: E402

with tempfile.TemporaryDirectory() as d:
    db = _db(d)
    seen: list[dict] = []
    real_generate = images.generate

    def fake_generate(prompt, **kw):
        wd = kw.get("work_dir")
        seen.append({"work_dir": wd, "existed": bool(wd) and os.path.isdir(wd)})
        # The real function's first act is this refusal; reproduce the contract exactly.
        if not wd:
            raise images.ImagesNotConfigured("generate() needs a work_dir")
        Path(wd, "render.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
        return {"cad": 0.0274, "url": "", "cost_entry_id": 1, "latency_ms": 5.0}

    images.generate = fake_generate
    try:
        env = {"BRAMBLELOOP_IMAGE_KEY_BFL": "test-credential-placeholder"}
        rec = images.probe(db, env=env)
    finally:
        images.generate = real_generate
    check("the image probe reached generate exactly once", len(seen) == 1, str(seen))
    assert seen, "vacuity: generate was never reached"
    check("the image probe passes a work_dir that exists during the render",
          seen[0]["existed"], str(seen))
    check("the probe's scratch render directory is removed afterwards",
          not os.path.exists(seen[0]["work_dir"]), seen[0]["work_dir"])
    check("with a render that succeeds the probe records ok (the gate can open)",
          rec.get("ok") is True and images.usable(db), str(rec))
    check("the probe no longer records the work_dir refusal",
          "work_dir" not in (rec.get("reason") or ""), str(rec))

# ---------------------------------------------------------------------------
# 2. offsite region from the endpoint

from brambleloop.core import offsite  # noqa: E402

cases = {
    "https://s3.us-east-005.backblazeb2.com": "us-east-005",
    "https://s3.us-west-004.backblazeb2.com": "us-west-004",
    "https://s3.eu-central-003.backblazeb2.com": "eu-central-003",
    "https://0123456789abcdef.r2.cloudflarestorage.com": "auto",
    "https://s3.ca-central-1.amazonaws.com": "ca-central-1",
    "https://s3.amazonaws.com": "us-east-1",
    "https://s3.us-east-2.wasabisys.com": "us-east-2",
    "https://storage.example.org": offsite.DEFAULT_REGION,
}
assert cases, "vacuity"
for endpoint, want in cases.items():
    got = offsite.region_for(endpoint)
    check(f"region for {endpoint} is {want}", got == want, got)
check("an explicitly set region still wins",
      offsite.region_for("https://s3.us-east-005.backblazeb2.com", "us-west-004") == "us-west-004")
t = offsite.target({offsite.ENDPOINT_VAR: "https://abc.r2.cloudflarestorage.com",
                    offsite.BUCKET_VAR: "b", offsite.KEY_ID_VAR: "id",
                    offsite.SECRET_VAR: "placeholder-not-a-secret"})
check("target() signs an R2 endpoint for region auto", t is not None and t.region == "auto",
      str(t and t.region))

# ---------------------------------------------------------------------------
# 3. Help Center policy reader

from brambleloop.gates import platform_policy as PP  # noqa: E402
from brambleloop.gates import policy_knowledge as PK  # noqa: E402
from brambleloop.gates import policy_reader as PR  # noqa: E402

check("listing_image_rules points at the image-requirements article, not 'download listing "
      "information'", "115015663347" in PP.POLICY_SOURCES["listing_image_rules"][0])
hc = PR.help_center_sources()
check("the Help-Center-hosted sources are exactly listing_image_rules and search_guidance",
      hc == {"listing_image_rules": "115015663347", "search_guidance": "360000336307"}, str(hc))
ext = PR.external_sources()
check("every etsy.com/legal source stays external",
      ext and all("etsy.com/legal" in PP.POLICY_SOURCES[s][0] for s in ext)
      and set(ext) | set(hc) == set(PP.POLICY_SOURCES), str(ext))

check("the reader is off in a test process", PR.enabled({}) is False)
check("the reader is on by itself in the hosted container",
      PR.enabled({"RAILWAY_ENVIRONMENT": "production"}) is True)
check("BRAMBLELOOP_POLICY_READER=0 turns it off even when hosted",
      PR.enabled({"RAILWAY_ENVIRONMENT": "production", PR.ENABLE_VAR: "0"}) is False)

BODY = "<p>" + "Etsy requires listing images at least 2000 px wide. " * 10 + "</p>"


def article(aid, body=BODY, edited="2026-05-04T19:20:43Z", **kw):
    return {"article": {"id": int(aid), "title": f"article {aid}", "body": body,
                        "edited_at": edited, "draft": False, **kw}}


with tempfile.TemporaryDirectory() as d:
    db = _db(d)
    PK.seed_snapshots(db, today=date(2026, 10, 7))   # the excerpt readings exist first
    urls: list[str] = []
    sleeps: list[float] = []

    def fetch_ok(url):
        urls.append(url)
        aid = url.rsplit("/", 1)[1].split(".")[0]
        return article(aid)

    r1 = PR.read_help_center(db, fetch=fetch_ok, sleep=sleeps.append, today=date(2026, 10, 7))
    check("both Help Center sources are read through the article API",
          r1["read"] == ["listing_image_rules", "search_guidance"]
          and all("/api/v2/help_center/en-us/articles/" in u for u in urls), str(r1))
    check("a polite gap is kept between requests", sleeps == [PR.MIN_SECONDS_BETWEEN_FETCHES])
    res = r1["results"]["listing_image_rules"]
    check("the reading is a help_center_api snapshot, first on its basis, not a policy change",
          res.get("recorded") and res.get("first_reading_on_basis")
          and res.get("material_change") is False, str(res))
    check("no unreviewed change is raised by the first real reading",
          PP.unreviewed_changes(db) == [], str(PP.unreviewed_changes(db)))
    r2 = PR.read_help_center(db, fetch=fetch_ok, sleep=sleeps.append, today=date(2026, 10, 7))
    check("the same text the same day is not recorded twice",
          all(v.get("ok") and v.get("recorded") is False for v in r2["results"].values()),
          str(r2["results"]))

    def fetch_changed(url):
        aid = url.rsplit("/", 1)[1].split(".")[0]
        return article(aid, body=BODY.replace("2000", "3000"), edited="2026-10-08T10:00:00Z")

    r3 = PR.read_help_center(db, fetch=fetch_changed, sleep=sleeps.append,
                             today=date(2026, 10, 8))
    check("a changed article body is a material change on the same basis",
          all(v.get("material_change") is True for v in r3["results"].values()), str(r3))
    check("and it becomes an unreviewed change that blocks its workflows (#39)",
          {c["source"] for c in PP.unreviewed_changes(db)} == set(hc))

    def fetch_403(url):
        raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)

    before = len(PP.freshness(db, today=date(2026, 10, 8))["current"])
    r4 = PR.read_help_center(db, fetch=fetch_403, sleep=sleeps.append, today=date(2026, 10, 9))
    check("a refusal is recorded as a failure in its own words and is never a reading",
          r4["failed"] == sorted(hc) and all("403" in v["reason"]
                                             for v in r4["results"].values()), str(r4))
    check("a refusal adds no snapshot",
          len(PP.freshness(db, today=date(2026, 10, 8))["current"]) == before)
    r5 = PR.read_help_center(db, fetch=lambda u: article("1"), sleep=sleeps.append,
                             today=date(2026, 10, 9))
    check("an answer for a different article is refused", r5["read"] == [], str(r5))
    r6 = PR.read_help_center(db, fetch=lambda u: article(u.rsplit("/", 1)[1].split(".")[0],
                                                         body="<p>short</p>"),
                             sleep=sleeps.append, today=date(2026, 10, 9))
    check("a near-empty body is not a policy text", r6["read"] == [], str(r6))

# The policy watch in a test process makes no network read and says so.
with tempfile.TemporaryDirectory() as d:
    db = _db(d)
    from brambleloop.runtime import release as RL

    class Ctx:
        def __init__(self, db):
            self.db = db
            self.audits = []

        def audit(self, kind, detail=None, **kw):
            self.audits.append((kind, detail))

    saved = {k: os.environ.pop(k) for k in list(os.environ)
             if k == PR.ENABLE_VAR or k.startswith("RAILWAY_")}
    try:
        out = RL.handle_policy_watch(Ctx(db))
    finally:
        os.environ.update(saved)
    check("the policy watch skips the network read outside the hosted container",
          "skipped" in (out.get("help_center") or {}), str(out.get("help_center")))
    check("the watch's note names the Help Center reader and the etsy.com/legal block",
          "Help Center" in out["note"] and "bot" in out["note"])

print(f"\n  {PASSED} passing, {FAILED} failing")
sys.exit(1 if FAILED else 0)
