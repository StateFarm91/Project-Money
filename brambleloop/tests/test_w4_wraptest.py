"""W4-WRAPTEST: the uncertified wrap experiment, EXPERIMENT mode and its one-command harness.

Offline: no network, no key, no spend. The "live rehearsal" replaces the BFL transport and the
Anthropic HTTP send with local fakes (as test_w4_fluxapi does) so the --live code path runs
end to end without leaving the process.

Proves:
- gate.certify, run through the real queue and handler in a scratch SHADOW DB, refuses the
  wrap (UNCALIBRATED_PRIMITIVE cable2x2), and its content hash is the CIR's;
- the orchestrator refuses the uncertified release without EXPERIMENT mode, and EXPERIMENT
  mode is refused on a non-scratch DB, without an opened experiment, or without an install;
- an experiment never reaches store.publish, image export, the Etsy payload/images, the
  publication or activation grant, or listing approval; experiment candidates are never
  publishable and carry the label;
- the dry run produces an approval card unattended, every generated image a labelled STUB;
- --live without keys refuses before anything is opened; the live path, rehearsed, reserves
  before every call, caps attempts at 2 per role, stops early on a hard flat-lay failure, and
  stays inside CA$5.00.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_wraptest.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import importlib.util
import io
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = tempfile.mkdtemp(prefix="wraptest-art-")

from PIL import Image  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.visual import experiment as XP  # noqa: E402

FAILED: list[str] = []
HARNESS = ROOT / "research" / "final_build" / "w4" / "experiment_wrap" / "run.py"


def check(name, cond, detail=""):
    print(("OK " if cond else "FAIL ") + name + (f" -- {str(detail)[:600]}" if not cond else ""))
    if not cond:
        FAILED.append(name)


def harness():
    spec = importlib.util.spec_from_file_location("wraptest_run", HARNESS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


H = harness()


def scratch(name="s"):
    d = Path(tempfile.mkdtemp(prefix=f"wraptest-{name}-"))
    db = Database(f"sqlite:///{d / 'x.db'}", scratch=True)
    db.create_all()
    Registry(db).seed_defaults()
    return db, d


def raises(fn, exc=XP.ExperimentRefused):
    try:
        fn()
    except exc as e:
        return str(e)
    except Exception as e:  # noqa: BLE001
        return f"WRONG {type(e).__name__}: {e}"
    return None


_CERT = {}


def certified_reading():
    """gate.certify through the real handler, once per process."""
    if not _CERT:
        db, d = scratch("cert")
        tl = H.Timeline()
        cir, cert = H.certify(db, tl)
        pdfs = H.render_pdfs(db, cir, tl)
        _CERT.update(cir=cir, cert=cert, pdfs=pdfs)
    return _CERT["cir"], _CERT["cert"], _CERT["pdfs"]


def opened(db, *, live=False):
    import hashlib

    cir, cert, pdfs = certified_reading()
    return XP.open_experiment(db, cir=cir, certification=cert,
                              pdf_sha256={k: hashlib.sha256(v).hexdigest()
                                          for k, v in pdfs.items()},
                              released_on=H.RELEASED_ON, budget_cad=5.0, live=live)


# ---- certification ------------------------------------------------------------------------

def test_certification_refuses_the_wrap_through_the_real_chain():
    from brambleloop.creative.pattern_refs import release_hash_of

    cir, cert, pdfs = certified_reading()
    check("cert_refused", cert["granted"] is False, cert)
    check("cert_reason_is_uncalibrated_cable2x2",
          any("UNCALIBRATED_PRIMITIVE" in r and "cable2x2" in r for r in cert["reasons"]),
          cert["reasons"])
    check("cert_only_that_reason", all("UNCALIBRATED_PRIMITIVE" in r for r in cert["reasons"]),
          cert["reasons"])
    check("cert_content_hash_is_the_cirs", cert["content_hash"] == release_hash_of(cir))
    check("cert_ran_as_a_queued_job", isinstance(cert["job_id"], int) and cert["job_id"] > 0)
    check("pdfs_us_and_uk", set(pdfs) == {"US", "UK"} and all(
        b[:5] == b"%PDF-" for b in pdfs.values()))


# ---- opening ------------------------------------------------------------------------------

def test_experiment_is_scratch_only_and_content_bound():
    from brambleloop.core.models import AuditLog

    cir, cert, pdfs = certified_reading()
    d = Path(tempfile.mkdtemp(prefix="wraptest-prod-"))
    prod = Database(f"sqlite:///{d / 'p.db'}")          # explicit, NOT scratch
    prod.create_all()
    check("open_refused_on_non_scratch", raises(lambda: opened(prod)) is not None)
    # Even a forged row on a non-scratch database enables nothing.
    with prod.session() as s:
        s.add(AuditLog(actor="x", action=XP.ACTION_OPENED, artifact=f"{cir.slug}@{cir.version}",
                       detail={"release": cert["content_hash"], "slug": cir.slug}))
    check("registration_none_on_non_scratch",
          XP.registration(prod, cir.slug, cir.version) is None)
    check("context_refused_on_non_scratch",
          raises(lambda: XP.context_for(prod, cir.slug, cir.version, cert["content_hash"]))
          is not None)
    check("but_publication_still_refuses_the_forged_row",
          raises(lambda: XP.refuse_if_experiment(prod, cir.slug, cir.version, action="t"))
          is not None)

    db, _ = scratch("open")
    hashes = {k: __import__("hashlib").sha256(v).hexdigest() for k, v in pdfs.items()}
    base = dict(cir=cir, pdf_sha256=hashes, released_on=H.RELEASED_ON, budget_cad=5.0,
                live=False)
    check("open_refuses_a_granted_certificate",
          raises(lambda: XP.open_experiment(db, certification={**cert, "granted": True},
                                            **base)) is not None)
    check("open_refuses_another_content_hash",
          raises(lambda: XP.open_experiment(db, certification={**cert,
                                                               "content_hash": "0" * 64},
                                            **base)) is not None)
    check("open_refuses_a_missing_uk_pdf",
          raises(lambda: XP.open_experiment(db, certification=cert, **{
              **base, "pdf_sha256": {"US": hashes["US"]}})) is not None)
    check("open_refuses_a_budget_over_5",
          raises(lambda: XP.open_experiment(db, certification=cert,
                                            **{**base, "budget_cad": 5.01})) is not None)
    check("open_refuses_without_reasons",
          raises(lambda: XP.open_experiment(db, certification={**cert, "reasons": []},
                                            **base)) is not None)
    reg = opened(db)
    check("opened_is_uncertified_and_labelled",
          reg["certified"] is False and reg["label"] == XP.LABEL
          and reg["release"] == cert["content_hash"])
    check("open_is_idempotent", opened(db)["opened_at"] == reg["opened_at"])
    # Nothing certified was written.
    from sqlalchemy import select

    from brambleloop.core.models import PatternVersion

    with db.session() as s:
        pv = list(s.scalars(select(PatternVersion)))
    check("no_certificate_or_pattern_version_written", all(not p.certified for p in pv), pv)


# ---- the orchestrator ---------------------------------------------------------------------

def test_orchestrator_refuses_the_uncertified_release_without_experiment_mode():
    from brambleloop.visual import image_production as IP

    cir, cert, _ = certified_reading()
    db, _ = scratch("orch")
    inputs = {"slug": cir.slug, "version": cir.version, "release": cert["content_hash"],
              "stage": "retrieve_release", "round": 0}
    out = IP.run_stage(db, inputs, follow=lambda *a: None)
    check("plain_run_waits_for_certification", out.get("state") ==
          "awaiting_certified_pattern", out)
    exp_in = {**inputs, "experiment": True}
    check("experiment_flag_without_an_open_experiment_refused",
          raises(lambda: IP.run_stage(db, exp_in, follow=lambda *a: None)) is not None)
    reg = opened(db)
    out_plain = IP.run_stage(db, inputs, follow=lambda *a: None)
    check("plain_run_not_bound_by_an_open_experiment",
          out_plain.get("state") == "awaiting_certified_pattern", out_plain)
    check("open_but_not_installed_refused",
          raises(lambda: IP.run_stage(db, exp_in, follow=lambda *a: None)) is not None)
    XP.install(db, reg, judges_factory=H.StubJudges)
    sent = []
    out = IP.run_stage(db, exp_in, follow=lambda i, k: sent.append((i, k)))
    check("installed_experiment_passes_retrieve", out.get("next") == "prepare_references", out)
    check("next_stage_keeps_the_flag", sent and sent[0][0].get("experiment") is True, sent)
    rec = IP._stage_data(db, IP.run_key(cir.slug, cir.version, reg["release"]))
    r0 = rec["retrieve_release"]
    check("stage_record_stamped", r0.get("label") == XP.LABEL and r0["evidence"].get(
        "certified") is False and XP.LABEL in r0["evidence"]["why"], r0)
    XP.uninstall(reg)


def test_experiment_candidates_are_never_publishable():
    from brambleloop.visual import candidate_gates as CG

    cir, cert, _ = certified_reading()
    db, _ = scratch("cand")
    opened(db)
    buf = io.BytesIO()
    Image.new("RGB", (2048, 2048), (10, 80, 40)).save(buf, format="PNG")
    cand = {"data": buf.getvalue(), "slug": cir.slug, "version": cir.version,
            "release": cert["content_hash"], "role": "lifestyle", "provider": "stub",
            "model": "stub", "prompt": "p", "references": [], "laura_present": False,
            "experiment": True}
    v = CG.evaluate(db, cand, judges=H.StubJudges(db))
    check("experiment_binding_pass_is_content_identity_only",
          v["checks"]["binding"]["status"] == "PASS"
          and v["checks"]["binding"]["certified"] is False
          and XP.LABEL in v["checks"]["binding"]["why"], v["checks"]["binding"])
    check("never_publishable", v["publishable"] is False and v["publication"][
        "may_export"] is False)
    check("label_is_the_first_blocker", XP.LABEL in v["publication"]["blockers"][0])
    plain = CG.evaluate(db, {**cand, "experiment": False}, judges=H.StubJudges(db))
    check("without_the_flag_binding_fails", plain["checks"]["binding"]["status"] == "FAIL",
          plain["checks"]["binding"])


def test_publication_paths_refuse_an_experiment():
    from brambleloop.ops import activation_authority, publication_authority
    from brambleloop.publish import disclosed_listing
    from brambleloop.runtime import etsy_ops
    from brambleloop.visual import image_production as IP

    cir, cert, _ = certified_reading()
    db, _ = scratch("pub")
    reg = opened(db)
    for name, fn in (
            ("certified_payload", lambda: etsy_ops.certified_payload(db, cir.slug, cir.version)),
            ("certified_images", lambda: etsy_ops.certified_images(db, cir.slug, cir.version)),
            ("export_images", lambda: disclosed_listing.export_images(db, slug=cir.slug,
                                                                      description="")),
            ("publication_authority.approve", lambda: publication_authority.approve(
                db, authorization="x", slug=cir.slug, version=cir.version,
                release=reg["release"], expected_digest="d", reason="r")),
            ("activation_authority.approve", lambda: activation_authority.approve(
                db, authorization="x", slug=cir.slug, version=cir.version,
                expected_digest="d", reason="r"))):
        got = raises(fn)
        check(f"refused:{name}", got is not None and XP.LABEL in got, got)
    # store.publish through the real queue and handler, by the agent allowed to run it.
    try:
        H._publish_probe(db, reg)
        check("refused:store.publish", False, "probe returned")
    except XP.ExperimentRefused as exc:
        check("refused:store.publish", XP.LABEL in str(exc), exc)
    except Exception as exc:  # noqa: BLE001
        check("refused:store.publish", False, exc)
    # listing approval on an experiment run
    key = IP._ensure_run(db, cir.slug, cir.version, reg["release"])
    IP._update(db, key, stage="owner_card", status="ready_for_owner_review",
               card={"experiment": True, "label": XP.LABEL})
    got = raises(lambda: IP.approve(db, key, decided_by="owner"))
    check("refused:image_production.approve", got is not None and XP.LABEL in got, got)
    check("run_not_approved", IP.get_run(db, key)["state"] != "approved_for_publication")
    # A non-experiment product is untouched by the guard.
    check("guard_is_silent_for_other_products",
          raises(lambda: XP.refuse_if_experiment(db, "cloudline-baby-blanket", "1.2.0",
                                                 action="t")) is None)


# ---- budget, attempts, outfit -------------------------------------------------------------

def test_budget_reserves_before_every_call_and_caps_attempts():
    b = XP.ExperimentBudget(cap_cad=0.30)
    r = b.reserve(0.14, what="a")
    check("reserved_counts_against_headroom", abs(b.headroom() - 0.16) < 1e-9)
    check("over_cap_refused", raises(lambda: b.reserve(0.17, what="b"),
                                     XP.ExperimentBudgetStop) is not None)
    check("zero_price_refused", raises(lambda: b.reserve(0.0, what="c"),
                                       XP.ExperimentBudgetStop) is not None)
    b.settle(r, None)
    check("unknown_actual_billed_at_reservation", abs(b.spent_cad - 0.14) < 1e-9)

    log = []
    calls = []

    def inner(prompt, *, reference_urls, size, work_dir, purpose, agent, db=None, job_id=None):
        calls.append(purpose)
        p = Path(work_dir) / f"o{len(calls)}.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1824, 2280)).save(p, format="PNG")
        return {"path": str(p), "sha256": "x", "cad": 0.1399}

    rend = H.BudgetedRenderer(inner, XP.ExperimentBudget(cap_cad=5.0), live=True, per_role=2,
                              log=log)
    rend.current_role = "product_anchor"
    w = tempfile.mkdtemp()
    rend("p", reference_urls=[], size="2048x2048", work_dir=w, purpose="x", agent="a")
    check("under_2000px_recorded_never_upscaled", log[0]["meets_2000px"] is False
          and log[0]["upscaled"] is False and log[0]["output_px"] == [1824, 2280], log[0])
    check("floor_failure_stops_further_calls",
          raises(lambda: rend("p", reference_urls=[], size="2048x2048", work_dir=w,
                              purpose="x", agent="a"), XP.ExperimentBudgetStop) is not None
          and len(calls) == 1)
    rend2 = H.BudgetedRenderer(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")),
                               XP.ExperimentBudget(cap_cad=5.0), live=True, per_role=2,
                               log=[])
    rend2.current_role = "lifestyle"
    for _ in range(2):
        raises(lambda: rend2("p", reference_urls=[], size="2048x2048", work_dir=w,
                             purpose="x", agent="a"), RuntimeError)
    check("third_attempt_per_role_refused",
          raises(lambda: rend2("p", reference_urls=[], size="2048x2048", work_dir=w,
                               purpose="x", agent="a"), XP.ExperimentBudgetStop) is not None)
    check("failed_calls_billed_conservatively", abs(rend2.budget.spent_cad - 2 * 0.13986) < 1e-6,
          rend2.budget.to_dict())


def test_outfit_is_automatic_and_distinct():
    db, _ = scratch("outfit")
    st = H.select_outfit(db, "reading-nook-cable-wrap")
    o = st.get("outfit") or {}
    check("outfit_selected", bool(o.get("garments")), st)
    check("outfit_distinct", H.outfit_problems(o.get("garments") or {}) == [], o)
    check("no_outerwear_over_the_wrap", (o.get("garments") or {}).get("outerwear") == "none")
    check("canonical_clothing_rejected", H.outfit_problems(
        {"top_or_dress": "ivory tank", "lower": "beige trousers", "shoes": "flats"}) != [])
    check("owner_prior_wrap_outfit_rejected", len(H.outfit_problems(
        {"top_or_dress": "brown fitted long-sleeve top", "lower": "cream tailored trousers",
         "shoes": "tan leather ankle boots", "accessories": "gold pendant necklace"})) >= 4)
    check("deterministic", H.select_outfit(db, "reading-nook-cable-wrap")["outfit"] == o)


# ---- the whole run ------------------------------------------------------------------------

def test_dry_run_reaches_the_approval_card_unattended():
    out = Path(tempfile.mkdtemp(prefix="wraptest-dry-")) / "run"
    s = H.run(live=False, out=out)
    check("dry_ready_for_owner_review", s["run_state"] == "ready_for_owner_review", s)
    check("dry_card_through_command_center", XP.LABEL in (s.get("card_title") or ""), s)
    check("dry_no_spend", s["spent_cad"] == 0.0 and s["vision_calls"] == 0)
    check("dry_three_flux_roles_one_call_each", s["flux_calls"] == 3, s["flux_calls"])
    check("dry_gallery_seven_in_order", [g["position"] for g in s["gallery"]] ==
          [1, 2, 3, 4, 5, 6, 7] and all(g["sha256"] for g in s["gallery"]), s["gallery"])
    check("dry_every_publication_path_refused",
          all(v.startswith("refused:") for v in s["refusals"].values()), s["refusals"])
    check("dry_owner_does_nothing", s["owner_actions_between_start_and_card"] == 0)
    ev = json.loads((Path(s["package"]).parent / "evidence.json").read_text())
    cands = ev["candidates"]
    check("dry_stub_images_are_labelled", all(c["provider"] == "stub" for c in cands)
          and all(f.endswith("_STUB.png") for f in os.listdir(Path(s["package"]).parent /
                                                               "images") if "0" in f and (
              "hero" in f or "flat_lay" in f or "back_drape" in f)), cands)
    check("dry_stub_judges_say_so", all(
        "STUB" in (c["checks"].get("product_truth") or {}).get("why", "") for c in cands))
    html = Path(s["package"]).read_text()
    check("dry_package_stamped_and_separated", XP.LABEL in html and "STUB" in html and
          "Visual approval" in html and "Technical certification" in html and
          "Publication authorization" in html)
    check("dry_listing_is_a_digital_pattern",
          ev["listing"]["is_digital_pattern"] and ev["listing"]["claims_check"]["ok"]
          and any("DIGITAL PATTERN" in d for d in ev["listing"]["disclosures"])
          and any("AI-generated" in d for d in ev["listing"]["disclosures"]))
    check("dry_taxonomy_blocked_not_guessed",
          ev["listing"]["category"]["taxonomy"]["status"] == "BLOCKED")
    tl = ev["timeline"]
    check("dry_timeline_has_job_ids_and_keys",
          sum(1 for e in tl if e.get("job_id") and e.get("idempotency_key")) >= 12, len(tl))
    check("dry_timeline_in_time_order", [e["at"] for e in tl] == sorted(e["at"] for e in tl))
    check("dry_pdf_hashes_bound", ev["listing"]["pdfs"]["US"]["sha256"] ==
          ev["experiment"]["pdf_sha256_by_terminology"]["US"])


def test_live_refuses_without_keys():
    out = Path(tempfile.mkdtemp(prefix="wraptest-nokey-")) / "run"
    saved = {k: os.environ.pop(k, None) for k in H.KEY_VARS}
    try:
        got = raises(lambda: H.run(live=True, out=out), H.Refused)
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
    check("live_without_keys_refused", got is not None and "no spend" in got, got)
    check("live_without_keys_opened_nothing", not out.exists())
    code = H.main(["--live", "--out", str(out)]) if not any(os.environ.get(k) for k in
                                                             H.KEY_VARS) else 2
    check("cli_exit_code_2", code == 2)


class FakeNetwork:
    """BFL and Anthropic, locally. Records every request; returns 2048 px PNGs and readings."""

    def __init__(self, flat_lay_reading: dict):
        self.posts, self.vision = [], []
        self.flat = flat_lay_reading
        buf = io.BytesIO()
        Image.new("RGB", (2048, 2048), (30, 70, 45)).save(buf, format="PNG")
        self.png = buf.getvalue()

    def __enter__(self):
        import urllib.request

        from brambleloop.gateway import anthropic as A
        from brambleloop.gateway import images as I
        from brambleloop.gateway.model_gateway import ModelResponse

        net = self

        def post(url, headers, payload, *, label, timeout):
            net.posts.append(json.loads(payload))
            n = len(net.posts)
            return {"id": f"task-{n}", "polling_url": f"https://api.bfl.ai/v1/get_result?id={n}",
                    "cost": 10.0, "input_mp": 4.0, "output_mp": 4.19}

        def get(url, headers, *, label, timeout):
            return {"id": "t", "status": "Ready", "result": {
                "sample": "https://delivery.eu.bfl.ai/x.png", "prompt": "e", "duration": 1.0}}

        def urlopen(url, timeout=None):
            class _R(io.BytesIO):
                headers = {"content-type": "image/png"}

                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False
            return _R(net.png)

        def send(self_, payload, key):
            body = json.loads(payload)
            text = body["messages"][0]["content"][-1]["text"]
            net.vision.append(text[:80])
            reading = net.flat if "laid flat" in text or "ONE crochet wrap" in text else {
                "same_person_as_reference": "yes", "anatomy_ok": True, "hands_ok": True,
                "photorealistic": True, "body_proportions_consistent": "yes",
                "wrap_visible": True, "wrap_matches_flat_lay": "yes", "craft": "crochet",
                "end_bands": "plain_cream", "edging_present": False,
                "outfit_matches_description": "yes", "clothing_copied_from_reference": False,
                "notes": "fake"}
            return ModelResponse(text=json.dumps(reading), provider="anthropic",
                                 model=self_.model, input_tokens=6000, output_tokens=400,
                                 latency_ms=1.0, stop_reason="end_turn")

        self._saved = (I._post, I._get, urllib.request.urlopen, I.BFL_POLL_SECONDS,
                       A.AnthropicProvider._send)
        I._post, I._get, urllib.request.urlopen, I.BFL_POLL_SECONDS = post, get, urlopen, 0.0
        A.AnthropicProvider._send = send
        self._env = {k: os.environ.get(k) for k in H.KEY_VARS}
        for k in H.KEY_VARS:
            os.environ[k] = "stand-in-not-a-key"
        return self

    def __exit__(self, *exc):
        import urllib.request

        from brambleloop.gateway import anthropic as A
        from brambleloop.gateway import images as I

        (I._post, I._get, urllib.request.urlopen, I.BFL_POLL_SECONDS,
         A.AnthropicProvider._send) = self._saved
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return False


GOOD_FLAT = {"whole_piece_visible": True, "flat_unfolded": True, "craft": "crochet",
             "cable_columns_counted": 8, "end_bands": "plain_cream",
             "side_edging_present": False, "extra_pieces_or_props_on_product": False,
             "colours_match": True, "notes": "fake"}


def test_live_path_rehearsed_offline():
    out = Path(tempfile.mkdtemp(prefix="wraptest-live-")) / "run"
    with FakeNetwork(GOOD_FLAT) as net:
        s = H.run(live=True, out=out)
    ev = json.loads((Path(s["package"]).parent / "evidence.json").read_text())
    check("live_reaches_the_card", s["run_state"] == "ready_for_owner_review"
          and XP.LABEL in (s["card_title"] or ""), s)
    check("live_three_flux_posts_at_2k", len(net.posts) == 3 and all(
        p.get("resolution") == "2k" for p in net.posts), [p.get("resolution")
                                                           for p in net.posts])
    check("live_every_flux_call_reserved_first", all(
        f["reserved_cad"] > 0 for f in ev["flux_calls"]) and len(ev["flux_calls"]) == 3)
    check("live_lifestyle_sent_laura_and_product_refs", all(
        len(p.get("images") or []) == 8 for p in net.posts[1:]), [len(p.get("images") or [])
                                                                   for p in net.posts])
    check("live_vision_reserved_and_counted", s["vision_calls"] == len(net.vision) >= 3
          and all(v.get("cost_cad") for v in ev["vision_calls"]), ev["vision_calls"])
    check("live_inside_budget", 0 < s["spent_cad"] <= 5.0, s["spent_cad"])
    check("live_still_never_publishable", all(not c["publishable"] for c in ev["candidates"]))
    check("live_vision_basis_labelled", all(
        "EXPERIMENT ONLY" in (c["checks"]["product_truth"].get("why") or "")
        for c in ev["candidates"]), [c["checks"]["product_truth"].get("why")
                                     for c in ev["candidates"]])
    check("live_refusals", all(v.startswith("refused:") for v in s["refusals"].values()),
          s["refusals"])


def test_live_stops_early_on_a_hard_flat_lay_failure():
    out = Path(tempfile.mkdtemp(prefix="wraptest-stop-")) / "run"
    bad = {**GOOD_FLAT, "cable_columns_counted": 6}
    with FakeNetwork(bad) as net:
        s = H.run(live=True, out=out)
    check("stop_blocked_after_one_flat_lay", s["run_state"] == "blocked"
          and len(net.posts) == 1, (s["run_status"], len(net.posts)))
    check("stop_says_why", "no bounded correction" in s["run_status"], s["run_status"])
    check("stop_card_still_reaches_command_center", XP.LABEL in (s["card_title"] or ""), s)
    # A routable failure (invented end bands) gets exactly one bounded correction.
    out2 = Path(tempfile.mkdtemp(prefix="wraptest-fix-")) / "run"
    with FakeNetwork({**GOOD_FLAT, "end_bands": "ribbed"}) as net2:
        s2 = H.run(live=True, out=out2)
    check("routable_failure_retried_once_then_stopped",
          len(net2.posts) == 2 and s2["run_state"] == "blocked", (len(net2.posts), s2[
              "run_status"]))
    neg = json.dumps(net2.posts[1])
    check("retry_carries_the_repair_negatives", "no ribbing in the end bands" in neg)


if __name__ == "__main__":
    test_certification_refuses_the_wrap_through_the_real_chain()
    test_experiment_is_scratch_only_and_content_bound()
    test_orchestrator_refuses_the_uncertified_release_without_experiment_mode()
    test_experiment_candidates_are_never_publishable()
    test_publication_paths_refuse_an_experiment()
    test_budget_reserves_before_every_call_and_caps_attempts()
    test_outfit_is_automatic_and_distinct()
    test_live_refuses_without_keys()
    test_dry_run_reaches_the_approval_card_unattended()
    test_live_path_rehearsed_offline()
    test_live_stops_early_on_a_hard_flat_lay_failure()
    print(f"{'FAIL' if FAILED else 'OK'} test_w4_wraptest ({len(FAILED)} failed)")
    sys.exit(1 if FAILED else 0)
