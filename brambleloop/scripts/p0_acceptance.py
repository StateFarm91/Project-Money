"""OPUS2-P0 §19: the revenue-workforce acceptance demonstrations, run offline on a scratch DB.

The owner's P0 directive (2026-10-27) lists eighteen things the final workforce must
demonstrate, from automatic market monitoring to performance learning. This script runs
each one against the REAL handlers in a SHADOW worker on a scratch SQLite database, with
every outbound socket refused, no provider credential present, and the model call -- where a
demonstration needs one -- substituted by a fixture generator exactly as the certification
suites do. Nothing is spent, published or written outside the scratch directory.

    PYTHONPATH=src python3 scripts/p0_acceptance.py <dir> [--as-of 2026-10-20]

It writes `<dir>/p0_acceptance.json`: one record per demonstration with a status, the rows
that evidence it, the production read that would prove the same thing on the deployed
build, and the limit of what an offline run can show.

Statuses, and what they are allowed to mean:

    OFFLINE_PASS               the real handlers produced the evidence on the scratch DB
    OFFLINE_FAIL               they did not, and the record says what is missing
    NOT_DEMONSTRABLE_OFFLINE   the demonstration needs a provider, a live listing, a buyer
                               or an owner action; the record names which, and reports
                               whatever partial measurement the run could make

**An OFFLINE_PASS is not production acceptance.** The directive's own rule is retained:
"Do not claim isolated tests prove production acceptance." The `classification` block at the
end says so in those words, and every record carries its `production_read`.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OFFLINE_PASS = "OFFLINE_PASS"
OFFLINE_FAIL = "OFFLINE_FAIL"
NOT_OFFLINE = "NOT_DEMONSTRABLE_OFFLINE"
UNKNOWN = "UNKNOWN"

# The Launch-0 product the certification chain is demonstrated on, and the radar concept
# whose promotion routes to it (PT-11: a retired alias is routed to its engineered design).
CHAIN_CONCEPT = "hexie-coaster-set"
CHAIN_SLUG = "hexagon-coaster-set"
CHAIN = ["cir.draft", "cir.compile", "gate.certify", "listing.draft", "assets.build",
         "pricing.position", "listing.seo", "launch.plan", "store.publish"]
REVIEW_CHECKS = ["cir.twin", "cir.reverse", "gate.asset_truth", "gate.policy"]

# What a premium customer booklet must carry (P0 §5), read from the document's own text.
# The two benchmark booklets the owner attached run 12 and 17 letter/A4 pages and carry
# every one of these; the words are ours, nothing of theirs is copied.
BOOKLET_SECTIONS: dict[str, tuple[str, ...]] = {
    "skill_level": ("skill level", "beginner", "intermediate", "advanced"),
    "materials_yarn": ("yarn", "materials"),
    "hook": ("hook",),
    "gauge": ("gauge",),
    "measurements": ("finished size", "measurements", "cm"),
    "abbreviations": ("abbreviations", "abbreviation"),
    "instructions_rows": ("row 1", "round 1", "row 2"),
    "stitch_counts": ("sts", "stitches"),
    "finishing": ("finishing", "fasten off", "weave in"),
    "support": ("support", "contact", "help", "questions are answered"),
    "licence": ("licence", "license", "copyright", "may not be shared", "resold"),
}
BENCHMARK_PAGES = (12, 17)

CONS = {"stocking": ("flat_rows", "in_the_round", "seamless_tube"),
        "ornament": ("flat_rows", "in_the_round", "amigurumi_shaping")}
RECIPIENTS = ("self", "partner", "new_parent", "child", "teen", "grandparent", "host",
              "pet_owner", "colleague", "teacher", "friend_who_has_everything", "newlyweds",
              "student")
MOTIFS = ("gingerbread", "lantern", "bell", "sleigh", "nutcracker", "holly", "candle",
          "mitten", "wreath", "ornament", "bow", "candy", "woodland")
FEELINGS = ("nostalgic", "festive", "heirloom", "whimsical", "celebratory", "playful",
            "tender", "folkloric")
WORDS = ("acorn birch cinder dapple ember fennel garnet hazel indigo juniper kestrel linden "
         "meadow nutmeg oriel pebble quill russet sorrel thistle umber vervain willow yarrow "
         "zephyr alder bramble clover damson elder fern gorse heath iris jasper kelp larch "
         "myrtle nettle olive pine quince rowan sloe tansy").split()


def _closed(*_a, **_k):
    raise OSError("network closed for the P0 acceptance run")


def _unique(j: int, t: int) -> str:
    return f"{WORDS[(j * 5 + t) % len(WORDS)]}q{chr(97 + j % 26)}{chr(97 + j // 26)}"


def stocking_field():
    """The certification suites' fixture generator: a varied Christmas field, model only."""
    count = {"n": 0, "form": {}}

    def gen(values, _call):
        form = values["form"].replace(" ", "_")
        out = []
        for _ in range(int(values.get("count") or 1)):
            j = count["n"]
            count["n"] += 1
            q = count["form"].setdefault(form, 0)
            count["form"][form] += 1
            u = [_unique(j, t) for t in range(4)]
            m = MOTIFS[j % len(MOTIFS)]
            out.append({
                "title": f"{u[0].title()} {m.title()} {form.title()}",
                "premise": f"a {form} whose {m} {u[0]} {u[1]} {u[2]} {u[3]} cuff",
                "construction": CONS.get(form, ("in_the_round",))[q % 3],
                "motif": f"{m} {u[1]}", "palette_story": "cranberry, cream and gold",
                "recipient": RECIPIENTS[q % len(RECIPIENTS)], "occasion": "christmas",
                "feeling": FEELINGS[j % len(FEELINGS)],
                "function": f"holds {u[2]} treats by the {u[3]} hearth", "wow": "cuff"})
        return {"concepts": out}
    return gen


class Run:
    def __init__(self, out: Path, as_of: str):
        self.out = out
        self.as_of = as_of
        self.records: list[dict] = []
        self.t0 = time.time()
        from brambleloop.agents.registry import Registry
        from brambleloop.core.db import Database
        from brambleloop.queue.durable import JobQueue
        from brambleloop.runtime import pipeline, release  # noqa: F401 - registers handlers

        self.db = Database(f"sqlite:///{out}/run.sqlite", scratch=True)
        self.db.create_all()
        Registry(self.db).seed_defaults()
        self.q = JobQueue(self.db)
        self.pipeline = pipeline

    # ---- helpers ---------------------------------------------------------------------

    def record(self, number: int, name: str, status: str, *, evidence: dict,
               production_read: str, limit: str = "", requirement: str = "") -> dict:
        rec = {"n": number, "demonstration": name, "status": status,
               "requirement": requirement, "evidence": evidence,
               "production_read": production_read, "offline_limit": limit,
               "seconds": round(time.time() - self.t0, 1)}
        self.records.append(rec)
        return rec

    def audits(self, action: str, artifact: str | None = None) -> list[dict]:
        from sqlalchemy import select

        from brambleloop.core.models import AuditLog

        with self.db.session() as s:
            q = select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id)
            if artifact is not None:
                q = q.where(AuditLog.artifact == artifact)
            return [{"id": a.id, "artifact": a.artifact, "detail": a.detail}
                    for a in s.scalars(q)]

    def jobs(self, job_type: str) -> list[dict]:
        from sqlalchemy import select

        from brambleloop.core.models import Job

        with self.db.session() as s:
            return [{"id": j.id, "status": j.status.value, "inputs": j.inputs,
                     "outputs": j.outputs, "error": j.last_error}
                    for j in s.scalars(select(Job).where(Job.job_type == job_type)
                                       .order_by(Job.id))]

    def handler(self, job_type: str, inputs: dict | None = None, *, agent: str,
                generator=None) -> dict:
        """Dispatch one job through the handler registry with a real JobContext, the model
        call substituted by `generator` (a fixture) when given."""
        from brambleloop.agents.registry import Registry
        from brambleloop.gateway import model_gateway
        from brambleloop.runtime.worker import JobContext, handlers

        job = self.q.enqueue(agent, job_type, inputs or {},
                             idempotency_key=f"p0:{job_type}:{os.urandom(4).hex()}")
        ctx = JobContext(job=job, db=self.db, queue=self.q, registry=Registry(self.db),
                         phase=None)
        saved = model_gateway.ModelGateway.complete_json
        if generator is not None:
            asked: list[dict] = []

            def fake(self_, ref, *, agent, values, required=None):
                asked.append(dict(values))
                return generator(values, len(asked))
            model_gateway.ModelGateway.complete_json = fake
        try:
            return handlers.get(job_type)(ctx)
        finally:
            model_gateway.ModelGateway.complete_json = saved

    def drain(self, job_types: list[str], *, name: str, limit: int = 2000) -> int:
        from brambleloop.core.models import Phase
        from brambleloop.runtime.worker import Worker

        w = Worker(self.db, name, phase=Phase.SHADOW, job_types=job_types, lease_seconds=1800)
        n = 0
        for _ in range(limit):
            if not w.run_once():
                break
            n += 1
        return n

    def judge(self, slug: str) -> None:
        """A fixture vision judgement on the design's board (the certification suites' stand-in
        for the image_vision judge, which does not exist offline). Labelled as a fixture."""
        from brambleloop.core.models import AuditLog
        from brambleloop.creative import intake
        from brambleloop.publish import owned_photography

        board_sha = intake.board_digest_for(self.db, slug)
        if not board_sha:
            board_sha = hashlib.sha256(f"fixture board for {slug}".encode()).hexdigest()
            with self.db.session() as s:
                s.add(AuditLog(actor="publishing", action=owned_photography.ACTION, detail={
                    "made": True, "slug": slug,
                    "method_version": owned_photography.METHOD_VERSION,
                    "image_ref": f"/fixture/boards/{slug}.png",
                    "image": {"sha256": board_sha}}))
        with self.db.session() as s:
            s.add(AuditLog(actor="creative_director", action=intake.JUDGED_ACTION,
                           artifact=slug,
                           detail={"thumbnail_reads_small": True, "craft_impression": 4.3,
                                   "judge": "FIXTURE vision judge (p0_acceptance)",
                                   "board_sha256": board_sha}))

    # ---- demonstrations ----------------------------------------------------------------

    def d1_market_monitoring(self):
        from brambleloop.core.models import BenchmarkListing
        from brambleloop.intel import benchmarks

        with self.db.session() as s:
            for i in range(12):
                s.add(BenchmarkListing(
                    benchmark_key=benchmarks.MJS_KEY, listing_ref=f"FIXTURE-S{i}",
                    title=("Festive Christmas Stocking Crochet Pattern",
                           "Christmas Ornament Crochet Pattern")[i % 2],
                    pod="stockings", price_cad=8.0, audit_state="audited",
                    detail={"num_favorers": 90}))
        snap = self.handler("radar.competitor_snapshot", {}, agent="market_radar")
        health = self.handler("intel.benchmark_health", {}, agent="market_radar")
        registry = [b.shop_name for b in benchmarks.REGISTRY]
        # The runtime's own useful-work judge, not a key this script guesses at.
        ok = (not self.pipeline.did_no_work(snap, "radar.competitor_snapshot")
              and len(registry) >= 4)
        self.record(
            1, "automatic market monitoring",
            OFFLINE_PASS if ok else OFFLINE_FAIL,
            requirement="P0 §3.1 Market Intelligence: permanent benchmark shops, authorised "
                        "collection, last-successful-scan evidence, recorded failures",
            evidence={"competitor_snapshot": {k: snap.get(k) for k in ("ran", "groups",
                                                                       "work_done")},
                      "benchmark_health": health,
                      "registry_shops": registry,
                      "fixture": "12 FIXTURE benchmark listings seeded; no network"},
            production_read="GET /api/audit?action=intel.watchlist_scan&limit=3 (every "
                            "non-anchor alias ok, listings_seen > 0); "
                            "GET /api/audit?action=mjs.benchmark_health&limit=1 (four shops "
                            "healthy or moved)",
            limit="offline the URL health is `unverified` (no fetcher) and the listings are "
                  "fixtures; the real scan needs the sanctioned Etsy read credential")

    def d2_new_opportunity(self) -> str | None:
        from brambleloop.creative import intake
        from brambleloop.radar.opportunity import POOL

        result = self.handler("creative.tournament", {}, agent="creative_director",
                              generator=stocking_field())
        rows = self.audits(intake.INTAKE_ACTION)
        row = rows[-1]["detail"] if rows else {}
        slug = (row.get("concept") or {}).get("key")
        pool = {s.slug for s in POOL}
        ok = bool(result.get("ran")) and bool(slug) and slug not in pool \
            and row.get("funnel", {}).get("carried") is True
        self.record(
            2, "new original product opportunity creation",
            OFFLINE_PASS if ok else OFFLINE_FAIL,
            requirement="P0 §3.2: a genuinely new concept not among the original 34 "
                        "(radar.opportunity.POOL)",
            evidence={"tournament": {k: result.get(k) for k in ("ran", "winner", "field")},
                      "winner_slug": slug, "in_original_pool": slug in pool,
                      "pool_size": len(pool),
                      "gate_decision": row.get("decision"),
                      "waiting_on": (row.get("gate") or {}).get("waiting_on"),
                      "funnel_carried": (row.get("funnel") or {}).get("carried"),
                      "model": "FIXTURE generator (the only substituted call)"},
            production_read="GET /api/audit?action=creative.winner_intake&limit=5: a winner "
                            "whose key is not a POOL slug, with funnel.carried true",
            limit="the field is a fixture generator; production tournaments use the model "
                  "under the creative_director ceiling")
        return slug if ok else None

    def d3_pd_handoff(self, slug: str | None):
        if not slug:
            self.record(3, "automatic Product Development handoff", OFFLINE_FAIL,
                        evidence={"why": "no winner from demonstration 2"},
                        production_read="GET /api/jobs?type=cir.draft")
            return
        before = len(self.jobs("cir.draft"))
        self.judge(slug)
        out = self.handler("mjs.seasonal_sentinel", {}, agent="market_radar",
                           generator=stocking_field())
        drafts = [j for j in self.jobs("cir.draft") if j["inputs"].get("slug") == slug]
        ok = bool(drafts)
        self.record(
            3, "automatic Product Development handoff",
            OFFLINE_PASS if ok else OFFLINE_FAIL,
            requirement="P0 §3.2 acceptance: the new concept routes automatically into "
                        "Product Development (cir.draft queued for crochet_engineer)",
            evidence={"regated": (out.get("regated") or {}).get("presented"),
                      "cir_draft_jobs_for_winner": [j["id"] for j in drafts],
                      "cir_draft_jobs_before": before,
                      "judgement": "FIXTURE vision judgement recorded against the board "
                                   "digest (concept.judged)"},
            production_read="GET /api/audit?action=concept.judged&limit=5 then "
                            "GET /api/jobs?type=cir.draft: a draft whose inputs.slug is the "
                            "judged winner",
            limit="production holds every new concept WAITING on image_vision until a vision "
                  "judge with credit records concept.judged (owner spend authority); this "
                  "run records the judgement as a fixture")

    def d4_pattern_generation(self, slug: str | None):
        if not slug:
            self.record(4, "valid crochet-pattern generation", OFFLINE_FAIL,
                        evidence={"why": "no handoff"}, production_read="")
            return
        n = self.drain(["cir.draft", "cir.compile"], name="p0-engineer")
        drafted = self.audits("cir.drafted")
        compiled = [a for a in self.audits("cir.compiled") if (a["artifact"] or "").startswith(slug)]
        refused = [a for a in self.audits("cir.draft_refused") if a["artifact"] == slug]
        ok = bool(compiled)
        self.record(
            4, "valid crochet-pattern generation (deterministic CIR for the new concept)",
            OFFLINE_PASS if ok else OFFLINE_FAIL,
            requirement="P0 §3.3: original design, written instructions, stitch and row "
                        "mathematics -- authored by code (creative.prototype.author), never "
                        "asked of a model (Master Plan §2)",
            evidence={"jobs_run": n,
                      "drafted": [a["artifact"] for a in drafted if
                                  (a["artifact"] or "").startswith(slug)],
                      "compiled": [a["artifact"] for a in compiled],
                      "refused": [a["detail"].get("reason") for a in refused][:3]},
            production_read="GET /api/audit?action=cir.compiled&limit=10 naming the winner "
                            "slug@version",
            limit="")

    def d5_technical_validation(self):
        from sqlalchemy import select

        from brambleloop.core.models import PatternVersion, Product
        from brambleloop.radar.opportunity import score_concept

        seed = self.pipeline._seed_for(CHAIN_CONCEPT)
        payload = score_concept(seed, date.fromisoformat(self.as_of)).to_dict()
        payload["as_of"] = self.as_of
        self.q.enqueue("market_radar", "radar.score", payload,
                       idempotency_key=f"score:{CHAIN_CONCEPT}:{self.as_of}:p0", priority=0)
        self.drain(["radar.score"], name="p0-radar")
        n = self.drain(["cir.draft", "cir.compile", "gate.certify"], name="p0-certify")
        with self.db.session() as s:
            p = s.scalar(select(Product).where(Product.slug == CHAIN_SLUG))
            pvs = [] if p is None else list(s.scalars(select(PatternVersion).where(
                PatternVersion.product_id == p.id)))
            cert = [{"version": v.version, "certified": bool(v.certified),
                     "release_hash": (v.release_hash or "")[:16],
                     "findings": len((v.certificate or {}).get("findings") or [])}
                    for v in pvs]
        ok = any(c["certified"] for c in cert)
        self.record(
            5, "technical validation (deterministic certification)",
            OFFLINE_PASS if ok else OFFLINE_FAIL,
            requirement="P0 §3.4 Quality & Compliance: stitch arithmetic, construction, "
                        "measurements, gauge, materials, originality -- gate.certify",
            evidence={"concept": CHAIN_CONCEPT, "routed_to": CHAIN_SLUG,
                      "routed": [a["detail"].get("routed_to") for a in
                                 self.audits("cir.draft_routed", CHAIN_CONCEPT)],
                      "jobs_run": n, "pattern_versions": cert,
                      "certified_rows": [a["artifact"] for a in self.audits("gate.certified")]},
            production_read="GET /api/audit?action=gate.certified&limit=10; "
                            "GET /api/products (certified version per slug)",
            limit="")
        return ok

    def d6_independent_review(self):
        out = self.handler("gate.quality", {}, agent="quality_director")
        n = self.drain(REVIEW_CHECKS, name="p0-review")
        done = {jt: [j["status"] for j in self.jobs(jt)] for jt in REVIEW_CHECKS}
        from sqlalchemy import select

        from brambleloop.core.models import Incident

        with self.db.session() as s:
            incidents = [i.signature for i in s.scalars(select(Incident).where(
                Incident.resolved.is_(False)))]
        ok = out.get("queued", 0) >= len(REVIEW_CHECKS) and all(
            statuses and all(x == "done" for x in statuses) for statuses in done.values())
        self.record(
            6, "independent quality review (re-verification sweep)",
            OFFLINE_PASS if ok else OFFLINE_FAIL,
            requirement="P0 §3.4: independent technical review -- the Quality & Compliance "
                        "agents re-check every certified release (W4-AGENTS batch 1, AM-10: "
                        "never a verdict path)",
            evidence={"sweep": {k: out.get(k) for k in ("releases", "queued", "unverifiable")},
                      "checks_run": n, "check_jobs": done,
                      "open_incidents": incidents},
            production_read="GET /api/audit?action=quality.reverify_planned&limit=1 and the "
                            "four check job types done for the newest certified release",
            limit="a human or vision review is not part of this sweep; the directive's "
                  "'independent' review here is the deterministic validator, twin, reverse "
                  "compile, asset-truth and policy agents")

    def d7_defect_correction(self):
        from brambleloop.cir.compiler import compile_cir
        from brambleloop.cir.model import CIR
        from brambleloop.runtime.pipeline import Concept, concept_to_cir

        bad = concept_to_cir(Concept(slug="p0-revise-fixture", title="P0 Revise Fixture Panel",
                                     category="coaster", stitch_repeat=[("sc", 2), ("dc", 2)],
                                     width_stitches=50, rows=8,
                                     colors={"A": "cream", "B": "sage"}))
        first = self.handler("cir.compile", {"cir": bad.to_dict()}, agent="validator")
        revised = None
        recompiled = None
        if first.get("revise_job"):
            self.drain(["cir.revise"], name="p0-revise")
            rev = [j for j in self.jobs("cir.revise")]
            revised = rev[-1]["outputs"] if rev else None
            nxt = [j for j in self.jobs("cir.compile") if j["inputs"].get("revision") == 1]
            if nxt:
                recompiled = compile_cir(CIR.from_dict(nxt[0]["inputs"]["cir"])).ok
        ok = (first.get("compiled") is False and bool(first.get("revise_job"))
              and bool((revised or {}).get("revised")) and recompiled is True)
        self.record(
            7, "defect rejection and correction loop",
            OFFLINE_PASS if ok else OFFLINE_FAIL,
            requirement="P0 §3.3/§3.4: failed products return automatically for correction "
                        "(cir.compile refuses; cir.revise repairs geometry once, never the "
                        "idea; the compiler decides again)",
            evidence={"first_compile": {k: first.get(k) for k in ("compiled", "revise_job",
                                                                   "errors")},
                      "revision": {k: (revised or {}).get(k) for k in ("revised", "detail")},
                      "recompiled_ok": recompiled},
            production_read="GET /api/audit?action=cir.revised&limit=5 and the following "
                            "cir.compile with inputs.revision=1",
            limit="")

    def d8_premium_pdf(self):
        from brambleloop.core.artifacts import ArtifactStore
        from brambleloop.publish.pdf import extracted_text

        n = self.drain(["listing.draft", "assets.build", "pricing.position", "listing.seo",
                        "launch.plan"], name="p0-publish")
        builds = [j for j in self.jobs("assets.build")
                  if j["inputs"].get("slug") == CHAIN_SLUG and j["status"] == "done"
                  and (j["outputs"] or {}).get("pdf_sha256")]
        found: dict[str, bool] = {}
        pages = None
        sha = None
        text_len = 0
        copyright_line = "UNKNOWN: the PDF was not read"
        if builds:
            out = builds[-1]["outputs"]
            sha, pages = out["pdf_sha256"], out.get("pages")
            try:
                data = ArtifactStore(os.environ.get("BRAMBLELOOP_ARTIFACT_DIR")).get(
                    sha, db=self.db)
                text = extracted_text(data).lower()
                text_len = len(text)
                found = {sec: any(w in text for w in words)
                         for sec, words in BOOKLET_SECTIONS.items()}
                copyright_line = ("present" if "all rights reserved" in text else
                                  "absent on this base; W-PDF (claude/w4-PDF1) adds it")
            except Exception as exc:  # noqa: BLE001
                found = {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
        missing = [k for k, v in found.items() if v is False]
        ok = bool(builds) and found and not missing
        self.record(
            8, "premium customer PDF generation",
            OFFLINE_PASS if ok else OFFLINE_FAIL,
            requirement="P0 §5: branded booklet with skill level, materials, yarn, hooks, "
                        "gauge, measurements, abbreviations, instructions, counts, "
                        "finishing, support, licence; versioned and bound to the certified "
                        "source",
            evidence={"jobs_run": n, "assets_build_jobs": [j["id"] for j in builds],
                      "pdf_sha256": sha, "pages": pages,
                      "pdf_sha256_by_terminology": (builds[-1]["outputs"].get(
                          "pdf_sha256_by_terminology") if builds else None),
                      "sections_found": found, "sections_missing": missing,
                      "copyright_line": copyright_line,
                      "extracted_chars": text_len,
                      "benchmark_pages": {"owner_benchmarks": list(BENCHMARK_PAGES),
                                          "this_booklet": pages,
                                          "within_benchmark_range": (
                                              BENCHMARK_PAGES[0] <= (pages or 0)
                                              <= BENCHMARK_PAGES[1])}},
            production_read="GET /api/audit?action=assets.built&limit=5 (pdf_sha256 per "
                            "release), and a page-by-page render review (W4-PDF1 lane)",
            limit="page-by-page visual inspection (clipping, glyphs, diagram accuracy) is "
                  "the PDF1 lane's render QA, not this text check")

    def d9_truthful_visuals(self):
        from sqlalchemy import select

        from brambleloop.core.models import ListingAsset

        with self.db.session() as s:
            assets = [{"role": a.role, "class": a.asset_class, "approved": bool(a.approved),
                       "blocked": list(a.blocked_reasons or [])[:2]}
                      for a in s.scalars(select(ListingAsset).where(
                          ListingAsset.product_slug == CHAIN_SLUG))]
        review = self.audits("assets.disclosed_hero_review")
        approved = [a for a in assets if a["approved"]]
        status = OFFLINE_PASS if approved else NOT_OFFLINE
        self.record(
            9, "truthful visual production",
            status,
            requirement="P0 §7: hero, lifestyle, close-ups, measurement graphics, "
                        "disclosures; Product Truth consistency; real photographs "
                        "distinguished from conceptual imagery",
            evidence={"listing_assets": len(assets), "approved": len(approved),
                      "blocked": [a for a in assets if a["blocked"]][:5],
                      "hero_review_rows": len(review),
                      "render_contract": "disclosed render contract 3 (D-W4-CONTRACT3)"},
            production_read="GET /api/products/<slug>/assets (approved hero, blocked reasons) "
                            "and GET /api/audit?action=assets.disclosed_hero_review",
            limit="the hero's independent vision review and model-backed lifestyle frames "
                  "need the image/vision providers (owner spend authority); offline only the "
                  "deterministic disclosed renders exist")

    def d10_laura_identity(self):
        from brambleloop.visual import canonical

        v = canonical.verify()
        ok = bool(v.get("ok", not v.get("problems")))
        self.record(
            10, "Laura identity verification",
            OFFLINE_PASS if ok else OFFLINE_FAIL,
            requirement="P0 §6: canonical identity laura-r2-a42aeac7; the three reference "
                        "files committed, byte-verified, never regenerated",
            evidence={"identity_id": canonical.IDENTITY_ID, "verify": v,
                      "owner_uploads_2026_10_27": "the three files the owner attached hash "
                                                  "to a42aeac7 / afe6191f / f32bac68, "
                                                  "byte-identical to the committed assets"},
            production_read="GET /api/visual/identity (frozen pack, drift series) and the "
                            "committed MANIFEST.json hashes at the deployed SHA",
            limit="a rendered frame's identity score needs the FLUX 3 provider and the "
                  "vision judges; nothing is rendered offline")

    def d11_listing_package(self):
        from sqlalchemy import select

        from brambleloop.core.models import Listing

        with self.db.session() as s:
            lst = s.scalar(select(Listing).where(Listing.product_slug == CHAIN_SLUG)
                           .order_by(Listing.id.desc()).limit(1))
            row = None if lst is None else {
                "version": lst.version, "state": lst.state, "title_chars": len(lst.title or ""),
                "tags": len(lst.tags or []), "price_cad": lst.price_cad,
                "seo_score": lst.seo_score, "etsy_listing_id": lst.etsy_listing_id or ""}
        seo = [j for j in self.jobs("listing.seo") if j["inputs"].get("slug") == CHAIN_SLUG]
        plan = [j for j in self.jobs("launch.plan") if j["inputs"].get("slug") == CHAIN_SLUG]
        price = [j for j in self.jobs("pricing.position")
                 if j["inputs"].get("slug") == CHAIN_SLUG]
        ok = row is not None and row["title_chars"] > 0 and row["price_cad"] > 0
        self.record(
            11, "complete Etsy listing-package assembly",
            OFFLINE_PASS if ok else OFFLINE_FAIL,
            requirement="P0 §8: SEO title, tags, category, attributes, description, price, "
                        "PDF attachments, gallery, disclosures, policy evidence, Product "
                        "Truth, physical-test state, owner approval state; exact certified "
                        "version",
            evidence={"listing": row,
                      "pricing_position": [j["status"] for j in price],
                      "listing_seo": [(j["status"], (j["outputs"] or {}).get("seo_score"))
                                      for j in seo],
                      "launch_plan": [j["status"] for j in plan]},
            production_read="GET /api/listings (draft per certified release) and "
                            "GET /api/launch (per-release package items)",
            limit="the Etsy taxonomy/category certificate reads Etsy's schema in production "
                  "(listing.taxonomy_refresh); offline it is UNKNOWN, never a pass")

    def d12_owner_review_state(self):
        from brambleloop.ops import publication_authority as pa
        from brambleloop.products import lifecycle

        from sqlalchemy import select

        from brambleloop.core.models import PatternVersion, Product

        with self.db.session() as s:
            p = s.scalar(select(Product).where(Product.slug == CHAIN_SLUG))
            pv = None if p is None else s.scalar(select(PatternVersion).where(
                PatternVersion.product_id == p.id, PatternVersion.certified.is_(True))
                .order_by(PatternVersion.id.desc()).limit(1))
            version, release = (pv.version, pv.release_hash or "") if pv else (None, "")
        packet = None
        if version:
            try:
                ev = pa.evidence(self.db, CHAIN_SLUG, version, release)
                packet = {"summary": ev["summary"],
                          "sections": {k: ev[k].get("state") for k in pa.GATED_SECTIONS}}
            except Exception as exc:  # noqa: BLE001
                packet = {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
        row = lifecycle.derive(self.db, CHAIN_SLUG)
        ok = packet is not None and "summary" in packet and row["stage"] in lifecycle.STAGES
        self.record(
            12, "correct owner-review state",
            OFFLINE_PASS if ok else OFFLINE_FAIL,
            requirement="P0 §8/§6: owner approval pending only when every gated section "
                        "passes; separate states for internal preparation, authorised "
                        "private draft and owner-approved publication",
            evidence={"approval_packet": packet,
                      "lifecycle": {k: row.get(k) for k in ("stage", "basis", "why")},
                      "owner_grants": len(self.audits(pa.APPROVED))},
            production_read="GET /api/owner/publication/preview (sections, digest) and "
                            "GET /api/products/lifecycle",
            limit="")

    def d13_safe_publication(self):
        from sqlalchemy import select

        from brambleloop.core.models import Listing

        n = self.drain(["store.publish"], name="p0-store")
        refused = self.audits("store.publish_refused", CHAIN_SLUG) or \
            self.audits("store.publish_blocked", CHAIN_SLUG)
        with self.db.session() as s:
            ids = [l.etsy_listing_id for l in s.scalars(select(Listing)) if l.etsy_listing_id]
        publish_jobs = self.jobs("store.publish")
        ok = bool(refused or publish_jobs) and not ids
        self.record(
            13, "safe publication controls",
            OFFLINE_PASS if ok else OFFLINE_FAIL,
            requirement="P0 §8: never incur fees or publish without the required approval; "
                        "SHADOW refuses; owner publication grant and LIMITED PRODUCTION "
                        "phase required",
            evidence={"jobs_run": n,
                      "store_publish": [(j["status"], (j["error"] or "")[:120])
                                        for j in publish_jobs],
                      "refusal": (refused[-1]["detail"] if refused else None),
                      "etsy_listing_ids": ids,
                      "phase": os.environ.get("BRAMBLELOOP_PHASE", "shadow")},
            production_read="GET /api/audit?action=store.publish_refused&limit=5; "
                            "GET /api/listings shows no etsy_listing_id in SHADOW",
            limit="")

    def d14_restart_recovery(self):
        from datetime import timedelta

        from sqlalchemy import select

        from brambleloop.core.models import Agent, Job, JobStatus, utcnow
        from brambleloop.runtime.worker import Worker, handlers

        with self.db.session() as s:
            a = s.scalar(select(Agent).where(Agent.name == "validator"))
            if "p0.recover" not in a.allowed_job_types:
                a.allowed_job_types = list(a.allowed_job_types) + ["p0.recover"]
        if handlers.get("p0.recover") is None:
            @handlers.register("p0.recover")
            def _recover(ctx):
                return {"recovered": True, "work_done": 1}
        job = self.q.enqueue("validator", "p0.recover", {"payload": "important"},
                             idempotency_key="p0:recover")
        claimed = self.q.claim("doomed-worker", ["p0.recover"])
        stolen = self.q.claim("eager-worker", ["p0.recover"])
        with self.db.session() as s:
            s.get(Job, job.id).lease_expires_at = utcnow() - timedelta(seconds=1)
        rescued = Worker(self.db, "rescue-worker", job_types=["p0.recover"]).run_once()
        final = self.q.get(job.id)
        ok = (claimed is not None and stolen is None and rescued
              and final.status == JobStatus.DONE and final.attempts == 2
              and final.outputs == {"recovered": True, "work_done": 1})
        self.record(
            14, "restart recovery (lease loss, idempotent completion)",
            OFFLINE_PASS if ok else OFFLINE_FAIL,
            requirement="P0 §10: durable job queues, idempotent retries, restart recovery",
            evidence={"claimed_by": getattr(claimed, "leased_by", None),
                      "stealable_while_leased": stolen is not None,
                      "rescued": rescued, "final_status": final.status.value,
                      "attempts": final.attempts, "inputs_intact": final.inputs},
            production_read="/api/verify checks (worker alive, restarts) and the "
                            "test_persistence suite at the deployed SHA",
            limit="")

    def d15_stall_recovery(self):
        from datetime import timedelta

        from sqlalchemy import select

        from brambleloop.core.models import Incident, Job, JobStatus, utcnow
        from brambleloop.ops import useful_work
        from brambleloop.ops.health import QUEUE_STALLED_AFTER_S

        job = self.q.enqueue("validator", "p0.no_handler_stall", {},
                             idempotency_key="p0:stall")
        with self.db.session() as s:
            s.get(Job, job.id).run_after = utcnow() - timedelta(seconds=QUEUE_STALLED_AFTER_S + 60)
        with self.db.session() as s:
            first = useful_work.alarm(self.db, s)
            opened = [i.signature for i in s.scalars(select(Incident).where(
                Incident.signature.like(f"{useful_work.SIGNATURE}%"),
                Incident.resolved.is_(False)))]
        with self.db.session() as s:
            s.get(Job, job.id).status = JobStatus.CANCELLED
        with self.db.session() as s:
            second = useful_work.alarm(self.db, s)
            still_open = [i.signature for i in s.scalars(select(Incident).where(
                Incident.signature.like(f"{useful_work.SIGNATURE}%"),
                Incident.resolved.is_(False)))]
        ok = bool(opened) and not still_open
        self.record(
            15, "stall detection and recovery",
            OFFLINE_PASS if ok else OFFLINE_FAIL,
            requirement="P0 §10: stall detection, failure escalation (F-720 ready-work-age "
                        "alarm with a diagnosed cause); §6 stalled workflows and loops "
                        "(W5-INVENTORY flow health, on its own branch)",
            evidence={"first_alarm": {k: first.get(k) for k in ("stale_ready", "running")},
                      "incidents_opened": opened,
                      "after_clearing": {k: second.get(k) for k in ("stale_ready", "running")},
                      "incidents_still_open": still_open},
            production_read="GET /api/useful-work (ready-work age, alarm) and "
                            "GET /api/incidents?signature=ready-work-age:",
            limit="")

    def d16_next_product_selection(self):
        from brambleloop.products import lifecycle

        scan = self.handler("radar.scan", {"as_of": self.as_of, "target": 10},
                            agent="market_radar")
        scored = self.jobs("radar.score")
        board = lifecycle.board(self.db)
        ok = bool(scan.get("selected")) and len(scored) >= len(scan["selected"])
        self.record(
            16, "continuous next-product selection",
            OFFLINE_PASS if ok else OFFLINE_FAIL,
            requirement="P0 §10: continuous selection of eligible work; §6 next required "
                        "action per product",
            evidence={"scan": {k: scan.get(k) for k in ("selected", "pool_size",
                                                        "constraints_met")},
                      "radar_score_jobs": len(scored),
                      "lifecycle_board": {k: len(v) for k, v in board["columns"].items() if v}},
            production_read="GET /api/audit?action=radar.scanned&limit=1 and "
                            "GET /api/products/lifecycle",
            limit="")

    def d17_cost_tracking(self):
        from sqlalchemy import func, select

        from brambleloop.agents.registry import BudgetExceeded, Registry
        from brambleloop.core.models import CostEntry, SpendLimit

        with self.db.session() as s:
            spent = float(s.scalar(select(func.sum(CostEntry.amount_cad))) or 0.0)
            limits = [(l.scope, l.daily_cap_cad) for l in s.scalars(select(SpendLimit))]
        refusal = None
        scope = limits[0][0] if limits else "company"
        cap = limits[0][1] if limits else 0.0
        try:
            Registry(self.db).authorize_spend(scope, cap + 1.0)
        except BudgetExceeded as exc:
            refusal = str(exc)[:160]
        except Exception as exc:  # noqa: BLE001
            refusal = f"{type(exc).__name__}: {str(exc)[:160]}"
        ok = spent == 0.0 and refusal is not None
        self.record(
            17, "cost tracking and ceilings",
            OFFLINE_PASS if ok else OFFLINE_FAIL,
            requirement="P0 §9/§10: budget enforcement in code; the CA$100 monthly company "
                        "ceiling unchanged; no paid provider activated",
            evidence={"cost_entries_cad_this_run": spent, "spend_limits": limits[:8],
                      "over_cap_refusal": refusal},
            production_read="GET /api/spend-report (what_it_bought per bucket) and "
                            "/api/finance with the monthly ceiling",
            limit="")

    def d18_performance_learning(self):
        measure = self.handler("improve.measure", {}, agent="learn")
        conclude = None
        try:
            conclude = self.handler("growth.conclude", {}, agent="experiment_steward")
        except Exception as exc:  # noqa: BLE001
            conclude = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
        self.record(
            18, "performance learning",
            NOT_OFFLINE,
            requirement="P0 §9: Etsy performance ingestion, views, favourites, orders, "
                        "revenue, conversion, Winner Amplification, recorded failed "
                        "experiments; never invented customer or sales evidence",
            evidence={"improve_measure": {k: measure.get(k) for k in ("ran", "measured",
                                                                      "unmeasured",
                                                                      "work_done")},
                      "growth_conclude": conclude},
            production_read="GET /api/audit?action=commerce.orders_ingested&limit=1, "
                            "GET /api/experiments (no_data until listings are live), "
                            "GET /api/growth/amplification",
            limit="needs live listings and real buyers; offline every cell is UNMEASURED and "
                  "no order is invented")

    # ---- run -------------------------------------------------------------------------

    def run(self) -> dict:
        self.d1_market_monitoring()
        slug = self.d2_new_opportunity()
        self.d3_pd_handoff(slug)
        self.d4_pattern_generation(slug)
        self.d5_technical_validation()
        self.d6_independent_review()
        self.d7_defect_correction()
        self.d8_premium_pdf()
        self.d9_truthful_visuals()
        self.d10_laura_identity()
        self.d11_listing_package()
        self.d12_owner_review_state()
        self.d13_safe_publication()
        self.d14_restart_recovery()
        self.d15_stall_recovery()
        self.d16_next_product_selection()
        self.d17_cost_tracking()
        self.d18_performance_learning()
        counts = {OFFLINE_PASS: 0, OFFLINE_FAIL: 0, NOT_OFFLINE: 0}
        for r in self.records:
            counts[r["status"]] += 1
        from sqlalchemy import select

        from brambleloop.core.models import Job

        with self.db.session() as s:
            jobs: dict[str, int] = {}
            for j in s.scalars(select(Job)):
                k = f"{j.job_type}:{j.status.value}"
                jobs[k] = jobs.get(k, 0) + 1
        doc = {
            "kind": "brambleloop.p0_acceptance",
            "as_of": self.as_of, "dir": str(self.out),
            "seconds": round(time.time() - self.t0, 1),
            "counts": counts, "jobs": jobs,
            "demonstrations": self.records,
            "classification": {
                "implemented": "what this run exercised exists in code at this commit",
                "integrated": "only once Opus merges the branch into the release sequence",
                "deployed": "NOT by this run",
                "production_verified": "NOT by this run: an OFFLINE_PASS is an isolated "
                                       "demonstration on a scratch database with fixtures "
                                       "standing in for the model, the vision judge and the "
                                       "Etsy read; it does not prove production acceptance",
                "end_to_end_accepted": "requires the production reads above on the deployed "
                                       "SHA and the 24-hour sustained run",
                "business_outcome_proven": "NO: no listing is live and no customer exists",
            },
        }
        (self.out / "p0_acceptance.json").write_text(json.dumps(doc, indent=1, default=str)
                                                      + "\n")
        return doc


def run(out_dir: str | os.PathLike, *, as_of: str = "2026-10-20") -> dict:
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = str(out / "art")
    os.environ["BRAMBLELOOP_PHASE"] = "shadow"   # OPUS2A F4.1: never inherit another phase
    for k in list(os.environ):
        if k.startswith(("ETSY", "ANTHROPIC_API", "OPENAI", "REPLICATE", "FAL_", "GEMINI",
                         "BFL_", "VENICE")):
            os.environ.pop(k)
    socket.socket.connect = _closed            # type: ignore[assignment]
    socket.socket.connect_ex = _closed         # type: ignore[assignment]  (OPUS2A F4.2)
    socket.socket.sendto = _closed             # type: ignore[assignment]
    socket.create_connection = _closed         # type: ignore[assignment]
    socket.getaddrinfo = _closed               # type: ignore[assignment]
    return Run(out, as_of).run()


def main(argv: list[str]) -> int:
    d = argv[0] if argv else "artifacts/p0_acceptance"
    as_of = argv[argv.index("--as-of") + 1] if "--as-of" in argv else "2026-10-20"
    doc = run(d, as_of=as_of)
    print(json.dumps({"wrote": str(Path(d).resolve() / "p0_acceptance.json"),
                      "seconds": doc["seconds"], "counts": doc["counts"],
                      "statuses": {r["n"]: r["status"] for r in doc["demonstrations"]}},
                     indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
