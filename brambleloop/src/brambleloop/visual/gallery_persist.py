"""Approved gallery frames into `ListingAsset`, re-certified through `release_gates.listing_set`
(W-VISNEXT; OWNERIMG E5).

The order is fixed and nothing in it can be skipped:

1. The run must be `approved_for_publication`. `image_production.approve` only sets that when
   the owner approved the look AND no publication blocker remained.
2. Every generated frame on the card is re-verified now (`image_production.reverify`) with the
   production judges, and its publication verdict (`candidate_gates.publication_verdict`:
   F-852, the Etsy policy reading, Laura's publication status) must still be publishable.
   One refusal and nothing is written.
3. The frames are written as `ListingAsset` rows (class `AI_LIFESTYLE_CONCEPT`, never a
   photograph) at their shot-plan positions. A position already holding different bytes is
   never overwritten.
4. `release_gates.listing_set` re-judges the whole set and decides whether a listing-set
   certificate is issued. Its four gates and F-852 run unchanged on the new rows.

On the legacy campaign path step 2 still refuses: F-852 refuses generated product imagery
outside the verified-exception route. Experiments never reach it
(`experiment.refuse_if_experiment`).

**The generated-gallery route (D-OWNER-FLUX-GALLERY, `certify_gallery`).** A seven-frame FLUX
campaign (`shot_plans.flux_campaign_plan`) is judged frame by frame on a fixed gate matrix:
identity, body proportions, outfit and Laura's publication status (where she appears),
product fidelity (structural Product Truth on the exact bytes), motif fidelity against the
CIR chart, anatomy, realism, image quality, role, provenance and the route's exception, plus
the set: every slot filled, the seven-frame standard, one job per frame, one product and one
outfit across the gallery, and the deterministic download-information frame. Every reading
is PASS, FAIL, UNMEASURED or NOT_APPLICABLE; UNMEASURED never counts as PASS. Any blocker
names the frame, the gate, the reason, the owning agent and the automatic next action:
`repair` (a bounded regeneration, within image_production's per-role attempt cap),
`measure` (re-judge the same bytes; nothing is bought) or `hold` (the bound is spent or no
regeneration can change it). Only a gallery with no blocker is written as listing assets and
selected, and `release_gates.listing_set` then certifies it on its own path. The owner's
look at the images is not an input.
"""
from __future__ import annotations

from ..publish import eligibility as el
from . import candidate_gates as CG

SOURCE = "visual.image_production"
ASSET_CLASS = "AI_LIFESTYLE_CONCEPT"


def _frames_of(card: dict) -> list[dict]:
    return [{"position": r["position"], "role": r["role"], "job": r.get("job"),
             "candidate_id": (r.get("candidate") or {}).get("candidate_id"),
             "sha256": (r.get("candidate") or {}).get("sha256")}
            for r in card.get("roles") or []
            if r.get("source") == "generated" and r.get("candidate")]


def persist_approved(db, key: str, *, judges=None, store_root=None) -> dict:
    from . import experiment as XP
    from . import image_production as IP
    from .image_records import ImageCandidate

    run = IP.get_run(db, key)
    if run is None:
        return {"persisted": False, "why": "no such run"}
    try:
        XP.refuse_if_experiment(db, run["slug"], run["version"], action="listing asset write")
    except XP.ExperimentRefused as exc:
        return {"persisted": False, "why": str(exc)}
    if (run.get("card") or {}).get("experiment"):
        return {"persisted": False, "why": f"{XP.LABEL}: experiments never write listing assets"}
    if run["state"] != "approved_for_publication":
        return {"persisted": False, "why": f"run is {run['status']}; only a gallery the owner "
                                           f"approved with no publication blocker is written"}
    frames = _frames_of(run.get("card") or {})
    if not frames:
        return {"persisted": False, "why": "the approved card has no generated frame"}
    judges = judges or CG.RealJudges(db)
    blockers = []
    for f in frames:
        got = IP.reverify(db, f["candidate_id"], judges=judges)
        with db.session() as s:
            row = s.get(ImageCandidate, f["candidate_id"])
            publishable = bool(row and row.publishable and row.technical_status == "PASS")
            pub = ((row.checks or {}).get("_publication") or {}) if row else {}
        if not got.get("reverified") or not publishable:
            blockers += [f"{f['role']}: {b}" for b in (pub.get("blockers") or
                                                      [got.get("why") or "not publishable"])]
    if blockers:
        return {"persisted": False, "why": "re-verification refused the frames; nothing written",
                "blockers": sorted(set(blockers))}
    written = write_frames(db, run["slug"], run["version"], frames, run_key=key)
    if written["refused"]:
        return {"persisted": False, "why": "a frame position already holds other bytes",
                **written}
    return {"persisted": True, **written,
            "listing_set": recertify(db, run["slug"], run["version"],
                                     positions=written["written"] + written["kept"],
                                     store_root=store_root)}


def _candidate_facts(s, candidate_id) -> dict:
    from .image_records import ImageCandidate

    row = s.get(ImageCandidate, int(candidate_id)) if candidate_id else None
    if row is None:
        return {}
    return {"provenance_kind": row.provenance_kind, "method": row.method,
            "provider": row.provider, "model": row.model, "cost_cad": row.cost_cad,
            "technical_status": row.technical_status, "run_key": row.run_key,
            "prompt_sha256": row.prompt_sha256, "sha256": row.sha256}


def write_frames(db, slug: str, version: str, frames: list[dict], *, run_key: str,
                 actor: str = "publishing", route: str = "",
                 extra_claims: dict | None = None) -> dict:
    """Write verified generated frames as `ListingAsset` rows, each with its provenance.

    Called only by `persist_approved` after its re-verification. Never overwrites other
    bytes. Every written frame gets an append-only audit row and a `visual_truth` provenance
    row whose lineage says what it is: AI-generated by image production (#36 kind
    `ai_generated_*`), never a photograph, with the provider, model, cost and the candidate
    it came from, keyed to the frame row and carrying the file's sha256. A frame whose
    candidate record does not match its bytes is refused rather than given a lineage."""
    from sqlalchemy import select

    from ..core.models import AuditLog, ListingAsset
    from ..ops import artefacts as provenance

    from .experiment import refuse_if_experiment_image

    # A controlled-experiment image never becomes a listing asset (W-VISNEXT).
    refuse_if_experiment_image(db, [f.get("sha256") for f in frames],
                               action="listing asset write")
    written, refused, kept = [], [], []
    with db.session() as s:
        for f in frames:
            row = s.scalar(select(ListingAsset).where(
                ListingAsset.product_slug == slug, ListingAsset.version == version,
                ListingAsset.position == f["position"]))
            if row is not None and row.sha256 == f["sha256"]:
                kept.append(f["position"])
                continue
            if row is not None:
                refused.append({"position": f["position"], "role": f["role"],
                                "why": f"position {f['position']} holds {str(row.sha256)[:12]} "
                                       f"({row.role}); a certified frame is never overwritten"})
                continue
            facts = _candidate_facts(s, f.get("candidate_id"))
            if not facts or facts["sha256"] != f["sha256"] or not str(
                    facts.get("provenance_kind") or "").startswith("ai_generated_"):
                refused.append({"position": f["position"], "role": f["role"],
                                "why": "no generated-candidate record matches these bytes; "
                                       "a frame without a truthful provenance is not written"})
                continue
            asset = ListingAsset(
                product_slug=slug, version=version, position=f["position"],
                asset_class=ASSET_CLASS, role=f["role"], sha256=f["sha256"],
                claims={"source": SOURCE, "run_key": run_key, "candidate_id": f["candidate_id"],
                        "job": f.get("job"), "is_photograph": False,
                        "provenance_kind": facts["provenance_kind"],
                        "label": "AI-generated concept image",
                        # D-OWNER-FLUX-GALLERY: a render, never physical-sample evidence
                        "is_render": True, "physical_sample_evidence": False,
                        **({"route": route} if route else {}),
                        # ENG-OWNER-GALLERY: internal provenance only (supplied_by: owner)
                        **{k: v for k, v in (extra_claims or {}).items()
                           if k in ("supplied_by",)}},
                approved=True, blocked_reasons=[])
            s.add(asset)
            s.flush()
            audit = AuditLog(actor=str(actor)[:64], action="images.listing_asset_written",
                             artifact=f"{slug}@{version}#{asset.id}",
                             detail={"candidate_id": f["candidate_id"], "run_key": run_key,
                                     "sha256": f["sha256"], "position": f["position"],
                                     "provenance_kind": facts["provenance_kind"]})
            s.add(audit)
            s.flush()
            provenance.record_lineage(
                s, artefact_class="visual_truth",
                artefact_key=provenance.visual_key(slug, version, asset.id),
                product_slug=slug,
                inputs={f"asset:image_candidate_{int(f['candidate_id'])}": f["sha256"]},
                lineage=provenance.Lineage(
                    created_by=str(actor)[:64], model=str(facts.get("model") or "")[:80],
                    provider=str(facts.get("provider") or "")[:40],
                    cost_cad=facts.get("cost_cad"), sha256=f["sha256"],
                    validation_status="reverified", source="backfilled",
                    evidence={"matched_on": "image_candidates.sha256 == listing_assets.sha256",
                              "audit_id": audit.id, "candidate_id": f["candidate_id"],
                              "run_key": run_key, "kind": facts["provenance_kind"],
                              "method": facts.get("method"), "is_photograph": False,
                              "technical_status": facts.get("technical_status")}))
            written.append(f["position"])
        if refused:
            s.rollback()
            written = []
    return {"written": written, "kept": kept, "refused": refused}


def recertify(db, slug: str, version: str, *, positions=(), store_root=None) -> dict:
    """`release_gates.listing_set` on the set as it now stands; its verdict is the answer.

    When the listing's imagery is the disclosed render set (D-FB-7), `listing_set` certifies
    that set and does not judge `ListingAsset` frames at all. A generated frame then is NOT
    part of any certificate, and this says so (`generated_frames_judged: False`) rather than
    reading the disclosed certificate as covering it."""
    from ..publish import release_gates

    out = release_gates.listing_set(db, slug=slug, version=version, store_root=store_root,
                                    issue=True)
    frames = [f for f in out.get("frames") or [] if f.get("position") in set(positions)]
    judged = bool(frames)
    reasons = list(out.get("reasons") or [])
    if positions and not judged:
        reasons.append("the generated frames were not judged by the listing-set path in use "
                       "(the disclosed render set is certified on its own); they are not "
                       "part of any certificate")
    return {"blocks_release": bool(out.get("blocks_release")) or (bool(positions) and
                                                                 not judged),
            "reasons": reasons, "certificate": bool((out.get("certificate") or {}).get("valid")) and judged,
            "generated_frames": frames, "generated_frames_judged": judged}


# ---- D-OWNER-FLUX-GALLERY: the generated-gallery certificate route ---------------------------

PASS, FAIL, UNMEASURED, NA = "PASS", "FAIL", "UNMEASURED", "NOT_APPLICABLE"
ID_AGENT, FLUX_AGENT, GALLERY_AGENT = "ENG-VIS-IDENTITY", "ENG-VIS-FLUX", "ENG-VIS-GALLERY"
SELECTED_ACTION = "images.generated_gallery_selected"
STORED_BASE = 100        # a generated-gallery frame's ListingAsset position = 100 + its slot
CERTIFY_ACTION = "images.generated_gallery_certify"

# gate -> (candidate checks it reads, owning agent, applies only where Laura appears)
FRAME_GATES: tuple[tuple[str, tuple[str, ...], str, bool], ...] = (
    ("identity", ("identity",), ID_AGENT, True),
    ("body_proportions", ("body_proportions",), ID_AGENT, True),
    ("outfit", ("outfit", "outfit_distinctness", "outfit_consistency"), ID_AGENT, True),
    ("product_fidelity", ("binding", "product_truth"), GALLERY_AGENT, False),
    ("motif_fidelity", ("motif_fidelity",), GALLERY_AGENT, False),
    ("anatomy", ("anatomy",), ID_AGENT, False),
    ("realism", ("realism",), ID_AGENT, False),
    ("image_quality", ("quality",), FLUX_AGENT, False),
    ("role", ("role",), GALLERY_AGENT, False),
    ("provenance", ("provenance", "disclosure"), GALLERY_AGENT, False),
)
# A failure of these is repaired by regenerating (a targeted repair route exists for it in
# `repair_routes`); a failure of the rest is about the record or the policy, not the pixels.
REGENERABLE = frozenset({"identity", "body_proportions", "outfit", "product_fidelity",
                         "motif_fidelity", "anatomy", "realism", "image_quality"})


def _status(checks: dict, names: tuple[str, ...]) -> tuple[str, str]:
    """The worst of `names` as PASS / FAIL / UNMEASURED / NOT_APPLICABLE, and why.

    A missing check, an UNKNOWN reading and a fixture-labelled PASS are all UNMEASURED."""
    seen = []
    for n in names:
        c = checks.get(n)
        if not isinstance(c, dict):
            seen.append((UNMEASURED, f"{n}: no reading"))
            continue
        st = CG.gate_status(c)
        st = {CG.UNKNOWN: UNMEASURED}.get(st, st)
        if st not in (PASS, FAIL, NA):
            st = UNMEASURED
        seen.append((st, f"{n}: {str(c.get('why') or st)[:200]}"))
    real = [x for x in seen if x[0] != NA]
    if not real:
        return NA, "; ".join(w for _s, w in seen)
    for want in (FAIL, UNMEASURED):
        bad = [w for st, w in real if st == want]
        if bad:
            return want, "; ".join(bad)
    return PASS, "; ".join(w for _s, w in real)


def _row_of(db, candidate_id):
    from .image_records import ImageCandidate, ensure_tables

    ensure_tables(db)
    with db.session() as s:
        row = s.get(ImageCandidate, int(candidate_id)) if candidate_id else None
        if row is not None:
            s.expunge(row)
        return row


def frame_matrix(db, row, *, job: str, laura_expected: bool,
                 cir_references: list[str] | None = None) -> dict:
    """Every gate for one generated frame, from its own stored record.

    `cir_references`: the ordered sha256 of the deterministic CIR reference renders the run
    prepared (`creative.pattern_refs`: layout, texture, detail, rules). The frame must have
    been conditioned on exactly those, in that order."""
    checks = dict(row.checks or {})
    laura = bool(row.laura_present)
    gates: dict[str, dict] = {}
    sent = [r.get("sha256") for r in (row.references or []) if r.get("kind") == "pattern_derived"]
    if cir_references is None:
        gates["cir_references"] = {"status": UNMEASURED, "owner": GALLERY_AGENT,
                                   "why": "the run's prepared CIR references are not on file"}
    elif not cir_references or sent != list(cir_references):
        gates["cir_references"] = {"status": FAIL, "owner": FLUX_AGENT,
                                   "why": f"conditioned on {len(sent)} CIR reference(s) that "
                                          f"are not the {len(cir_references)} the release's "
                                          f"certified CIR renders, in order"}
    else:
        gates["cir_references"] = {"status": PASS, "owner": FLUX_AGENT,
                                   "why": f"conditioned on the release's {len(sent)} CIR "
                                          f"reference renders, in order"}
    for gate, names, owner, laura_only in FRAME_GATES:
        if laura_only and not laura:
            gates[gate] = {"status": NA if not laura_expected else FAIL, "owner": owner,
                           "why": ("Laura does not appear" if not laura_expected else
                                   "the plan puts Laura in this frame and she is not in it")}
            continue
        st, why = _status(checks, names)
        if gate == "anatomy" and st == NA and laura:
            st, why = UNMEASURED, "anatomy: a frame with Laura must be judged for anatomy"
        gates[gate] = {"status": st, "owner": owner, "why": why}
    if laura:
        from . import canonical

        status = canonical.asset_status(row.sha256 or "")
        ok = status == canonical.PUBLICATION_APPROVED_STATUS
        gates["laura_publication"] = {
            "status": PASS if ok else UNMEASURED, "owner": ID_AGENT,
            "why": ("these bytes are publication_approved in the canonical registry" if ok
                    else f"Laura's publication gate reads '{status}' for these bytes")}
    # The route's exception, recomputed from the record (H2): honesty label, every
    # EXCEPTION_PROVENANCE field and structural truth on these exact bytes.
    cand = {"sha256": row.sha256, "role": row.role, "model": row.model,
            "references": list(row.references or []), "prompt_version": row.prompt_version,
            "provenance_kind": row.provenance_kind, "laura_present": laura,
            "identity_evidence": checks.get("_identity_evidence") or {},
            "route": (checks.get("_route") or {}).get("route") or ""}
    other = ([] if not laura or gates["laura_publication"]["status"] == PASS
             else ["Laura publication gate"])
    ev = CG.exception_evidence(cand, {k: v for k, v in checks.items()
                                      if isinstance(v, dict)}, job, laura,
                               other_publication_blockers=other)
    if cand["route"] != el.GALLERY_ROUTE:
        gates["exception_route"] = {"status": FAIL, "owner": GALLERY_AGENT,
                                    "why": "not generated and judged under the generated-"
                                           "gallery route"}
    else:
        from ..gates.asset_truth import AssetClass

        c = el.Candidate(asset_id=f"frame-{row.id}", medium=AssetClass.AI_LIFESTYLE_CONCEPT,
                         purpose=el.CONVERSION_CREATIVE, job=job,
                         position=1 if job == el.HERO_JOB else 2)
        reasons = el.gallery_exception(c, ev)
        unmeasured_only = reasons and all(("UNKNOWN" in r or "UNMEASURED" in r
                                           or "NOT_APPLICABLE" in r) for r in reasons)
        gates["exception_route"] = {
            "status": PASS if not reasons else (UNMEASURED if unmeasured_only else FAIL),
            "owner": GALLERY_AGENT, "why": "; ".join(reasons)[:600] or "all conditions PASS",
            "evidence": {k: ev.get(k) for k in ("route", "honesty_label", "sha256",
                                                "structural_sha256", "fidelity_release",
                                                "provenance")}}
    return {"candidate_id": row.id, "sha256": row.sha256, "role": row.role, "job": job,
            "laura_present": laura, "technical_status": row.technical_status,
            "attempt": row.attempt, "gates": gates,
            "ok": all(g["status"] in (PASS, NA) for g in gates.values())}


def _next_action(db, run_key: str, frame: dict, gate: str, g: dict) -> dict:
    """The automatic next step for one blocker, always bounded."""
    from . import image_production as IP

    if g["status"] == UNMEASURED:
        return {"kind": "measure", "owner": g["owner"],
                "how": f"re-judge the same bytes for {gate} (no new image is bought); "
                       f"bounded to one re-verification per certify pass"}
    attempts = IP._attempts(db, run_key, frame["role"]) if frame.get("role") else 0
    cap = IP.MAX_ATTEMPTS_PER_ROLE
    run = IP.get_run(db, run_key) or {}
    looping = run.get("state") not in ("blocked", "ready_for_owner_review",
                                       "approved_for_publication")
    if gate in REGENERABLE and attempts < cap and looping:
        # image_production's own verification -> repair loop buys it (MAX_REPAIR_ROUNDS,
        # MAX_ATTEMPTS_PER_ROLE, the per-gallery spend cap): automatic and bounded.
        return {"kind": "repair", "owner": FLUX_AGENT, "attempt": attempts + 1, "of": cap,
                "how": f"regenerate {frame['role']} with the targeted repair for {gate} "
                       f"(attempt {attempts + 1} of {cap}, in-run repair round)"}
    if gate in REGENERABLE:
        return {"kind": "hold", "owner": g["owner"], "attempts": attempts, "of": cap,
                "how": (f"repair bound spent for {frame.get('role')} ({attempts} of {cap} "
                        f"attempts; the run's {IP.MAX_REPAIR_ROUNDS} repair rounds are "
                        f"done); held for {g['owner']}, a new release or a new run")}
    return {"kind": "hold", "owner": g["owner"],
            "how": f"{gate} is not a pixel defect a regeneration can change; held for "
                   f"{g['owner']}"}


def gallery_status(db, key: str) -> dict:
    """The full gate matrix for a generated-gallery run, the set checks and every blocker
    with its reason, owning agent and next action. Read-only."""
    from . import image_production as IP
    from . import shot_plans as SP
    from ..publish import release_gates as RG

    run = IP.get_run(db, key)
    if run is None:
        return {"ok": False, "blockers": [{"gate": "run", "status": FAIL, "owner": GALLERY_AGENT,
                                           "why": "no such run", "next": {"kind": "hold"}}]}
    if IP.route_of_key(key) != SP.FLUX_ROUTE:
        return {"ok": False, "run_key": key, "blockers": [{
            "gate": "route", "status": FAIL, "owner": GALLERY_AGENT,
            "why": "this run is not a generated-gallery (FLUX campaign) run",
            "next": {"kind": "hold", "how": "trigger image production with route "
                                            f"{SP.FLUX_ROUTE!r}"}}]}
    plan = SP.flux_campaign_plan(run["listing"])
    view = IP.readiness(db, run["listing"], run_key_=key, plan=plan)
    prepared = ((IP._stage_data(db, key).get("prepare_references") or {}).get("outputs")
                or {}).get("references")
    cir_refs = ([r["sha256"] for r in prepared if r.get("kind") == "pattern_derived"]
                if isinstance(prepared, list) else None)
    blockers: list[dict] = []
    frames: list[dict] = []
    for slot in plan["roles"]:
        if not slot["generate"]:
            cf = RG.certified_contents_frame(db, run["slug"], run["version"])
            entry = {"position": slot["position"], "role": slot["role"], "job": slot["job"],
                     "deterministic": True, "status": cf["status"], "why": cf["why"]}
            frames.append(entry)
            if cf["status"] != PASS:
                blockers.append({"position": slot["position"], "role": slot["role"],
                                 "gate": "download_information", "status": cf["status"],
                                 "why": cf["why"], "owner": GALLERY_AGENT,
                                 "next": {"kind": "measure", "owner": GALLERY_AGENT,
                                          "how": "certify the disclosed set's CONTENTS "
                                                 "preview through assets.build"}})
            continue
        best = IP._best(db, listing=run["listing"], role=slot["role"], run=key)
        if best is None:
            frames.append({"position": slot["position"], "role": slot["role"],
                           "job": slot["job"], "status": UNMEASURED, "why": "no candidate"})
            blockers.append({"position": slot["position"], "role": slot["role"],
                             "gate": "generated", "status": UNMEASURED,
                             "why": "no candidate was generated for this slot",
                             "owner": FLUX_AGENT,
                             "next": _next_action(db, key, {"role": slot["role"]},
                                                  "image_quality", {"status": FAIL,
                                                                    "owner": FLUX_AGENT})})
            continue
        m = frame_matrix(db, _row_of(db, best["candidate_id"]), job=slot["job"],
                         laura_expected=slot["laura"], cir_references=cir_refs)
        m["position"] = slot["position"]
        frames.append(m)
        for gate, g in m["gates"].items():
            if g["status"] in (PASS, NA):
                continue
            blockers.append({"position": slot["position"], "role": slot["role"],
                             "candidate_id": m["candidate_id"], "gate": gate,
                             "status": g["status"], "why": g["why"], "owner": g["owner"],
                             "next": _next_action(db, key, m, gate, g)})
    set_checks = {
        "campaign_standard": view["campaign_standard"],
        "set_check": view["set_check"],
        "campaign_consistency": {k: view["campaign_consistency"].get(k)
                                 for k in ("status", "why")},
        "naturalism": {"status": (view.get("naturalism") or {}).get("status")},
    }
    for name, ok, why in (
            ("campaign_standard", view["campaign_standard"]["ok"],
             view["campaign_standard"]["problems"]),
            ("set_check", view["set_check"]["ok"], view["set_check"]["problems"]),
            ("campaign_consistency", view["campaign_consistency"]["status"] == CG.PASS,
             view["campaign_consistency"].get("why")),
            ("naturalism", (view.get("naturalism") or {}).get("status") == "PASS",
             (view.get("naturalism") or {}).get("findings"))):
        if not ok:
            st = (UNMEASURED if name == "campaign_consistency" and
                  view["campaign_consistency"]["status"] in (CG.UNKNOWN, CG.NA) else FAIL)
            blockers.append({"position": None, "role": "gallery", "gate": name, "status": st,
                             "why": str(why)[:400], "owner": GALLERY_AGENT if name != "naturalism"
                             else ID_AGENT,
                             "next": {"kind": "measure" if st == UNMEASURED else "hold",
                                      "owner": GALLERY_AGENT}})
    return {"ok": not blockers, "run_key": key, "listing": run["listing"],
            "slug": run["slug"], "version": run["version"], "release": run["release"],
            "family": plan["family"], "frames": frames, "set": set_checks,
            "blockers": blockers,
            "unmeasured_is_never_pass": True,
            "owner_visual_approval_is_not_an_input": True}


def certify_gallery(db, key: str, *, store_root=None, actor: str = "publishing") -> dict:
    """Judge the gallery; with no blocker, write it as listing assets, select it and have
    `release_gates.listing_set` certify it. With any blocker, nothing is written."""
    from ..core.models import AuditLog
    from . import experiment as XP
    from . import image_production as IP
    from ..publish import release_gates as RG

    run = IP.get_run(db, key)
    if run is not None:
        try:
            XP.refuse_if_experiment(db, run["slug"], run["version"],
                                    action="generated gallery certification")
        except XP.ExperimentRefused as exc:
            return {"certified": False, "why": str(exc), "blockers": []}
        if (run.get("card") or {}).get("experiment"):
            return {"certified": False, "why": f"{XP.LABEL}: experiments are never certified",
                    "blockers": []}
    st = gallery_status(db, key)
    record = {"run_key": key, "ok": st["ok"],
              "blockers": [{k: b.get(k) for k in ("position", "role", "gate", "status", "why",
                                                  "owner", "next")} for b in st["blockers"]]}
    if not st["ok"]:
        with db.session() as s:
            s.add(AuditLog(actor=actor[:64], action=CERTIFY_ACTION,
                           artifact=f"{st.get('slug')}@{st.get('version')}",
                           detail={**record, "certified": False}))
        return {"certified": False, "why": f"{len(st['blockers'])} blocker(s); nothing written",
                "blockers": st["blockers"], "status": st}
    gen = [f for f in st["frames"] if not f.get("deterministic")]
    contents = next(f for f in st["frames"] if f.get("deterministic"))
    # Stored at their own positions (STORED_BASE + listing position): assets.build's
    # build-side rows hold 1..n and a held position is never overwritten. The selection maps
    # each stored row to its listing position.
    written = write_frames(db, st["slug"], st["version"],
                           [{"position": STORED_BASE + f["position"], "role": f["role"],
                             "job": f["job"], "candidate_id": f["candidate_id"],
                             "sha256": f["sha256"]}
                            for f in gen], run_key=key, actor=actor, route=el.GALLERY_ROUTE)
    if written["refused"]:
        return {"certified": False, "why": "a frame position already holds other bytes",
                "blockers": [{"gate": "write", "status": FAIL, "owner": GALLERY_AGENT,
                              "why": str(written["refused"])[:400],
                              "next": {"kind": "hold"}}], **written}
    selection = {"route": el.GALLERY_ROUTE, "run_key": key, "family": st["family"],
                 "frames": [{"position": f["position"], "role": f["role"], "job": f["job"],
                             "stored_position": STORED_BASE + f["position"],
                             "sha256": f["sha256"], "candidate_id": f["candidate_id"]}
                            for f in gen],
                 "contents": {"position": contents["position"]}}
    with db.session() as s:
        s.add(AuditLog(actor=actor[:64], action=SELECTED_ACTION,
                       artifact=f"{st['slug']}@{st['version']}", detail=selection))
    out = RG.listing_set(db, slug=st["slug"], version=st["version"], store_root=store_root,
                         issue=True, store_renders=True)
    certified = bool((out.get("certificate") or {}).get("valid")) and not out.get(
        "blocks_release")
    if not certified:
        # the listing set refused: the selection is withdrawn, never left half-applied
        with db.session() as s:
            s.add(AuditLog(actor=actor[:64], action=SELECTED_ACTION,
                           artifact=f"{st['slug']}@{st['version']}",
                           detail={**selection, "withdrawn": True,
                                   "why": out.get("reasons")}))
    with db.session() as s:
        s.add(AuditLog(actor=actor[:64], action=CERTIFY_ACTION,
                       artifact=f"{st['slug']}@{st['version']}",
                       detail={**record, "certified": certified,
                               "listing_set_reasons": out.get("reasons"),
                               "certificate_record": (out.get("certificate") or {}).get(
                                   "record_id")}))
    return {"certified": certified, "listing_set": out, "written": written,
            "selection": selection,
            "why": "every frame and set check passed; certificate issued" if certified
            else f"listing set refused: {out.get('reasons')}"}


MAX_MEASURE_PASSES = 1   # per advance call: the same bytes are re-judged at most once


def advance(db, key: str, *, follow, judges=None, by: str = "gallery_persist") -> dict:
    """Carry out each blocker's next action, bounded: re-measure UNMEASURED frames once
    (no spend), restart the run for repairs within image_production's caps, report holds."""
    from . import image_production as IP

    st = gallery_status(db, key)
    measured, repairs, holds = set(), [], []
    for b in st.get("blockers") or []:
        nxt = b.get("next") or {}
        if nxt.get("kind") == "measure" and b.get("candidate_id") and len(measured) < 64:
            if b["candidate_id"] not in measured:
                IP.reverify(db, b["candidate_id"], judges=judges or CG.RealJudges(db))
                measured.add(b["candidate_id"])
        elif nxt.get("kind") == "repair":
            repairs.append(b)          # the run's own loop is still buying it
        else:
            holds.append(b)
    restarted = None
    if measured and not repairs and IP.restartable(db, key).get("restartable"):
        # only UNKNOWN stood: resume verification on the re-judged bytes (MAX_RESTARTS bound;
        # a restart never resets attempts, calls or spend)
        restarted = IP.restart(db, key, follow=follow, by=by,
                               reason="generated gallery: re-measured "
                                      f"{len(measured)} frame(s)")
    return {"measured": sorted(measured), "repairs": [f"{b['role']}:{b['gate']}" for b in repairs],
            "restarted": restarted, "holds": [f"{b.get('role')}:{b['gate']}" for b in holds]}
