"""The continuous product pipeline board: many products, each at its own stage.

W4-PIPE. Intelligence -> Design -> Product -> Product Truth -> Visual -> Search -> Listing
Readiness -> (Publication: owner-gated, never advanced here).

The release chain (`plan.cycle` -> `cir.draft` -> ... -> `store.publish`) already carries a
product the radar *selected* from start to refusal-in-shadow. What it did not have is a board:
one place that holds every candidate the company has -- the radar's whole pool, every built
product, and new designs proposed here -- says which stage each is at with the evidence for it,
and advances each one as far as deterministic validation and current authority allow. That is
what turns a one-shot chain into a pipeline with several products at several stages at once.

Rules, all enforced by construction:

* **Deterministic validation wins.** A stage passes on a measurement made here, now (compile,
  certify, name truth, renderer + pixel verifier, listing-copy gates). A score, a model opinion
  or an old certificate is evidence for Intelligence only.
* **A stage is reached only through the stage before it.** No skipping; the first stage that
  does not pass is the candidate's current stage, with its reason and its next step.
* **UNKNOWN is never PASS.** A check that could not run is UNKNOWN and stops the candidate.
* **Publication is never advanced.** The last stage is reported, with the owner gates named;
  `advances_publication` is the constant False.
* **New designs are pattern software.** Each proposal is a `products.builder.Design` -- motif
  library x palette x size, gauge derived from the declared yarn's published band -- built by
  the same deterministic tiler as the catalogue and named for the fabric it actually works
  (one colour per row, a dc relief on an sc ground: "relief"/"textured", never "mosaic").
  Proposals are pre-release (0.x versions) and are not catalogue products until they clear
  Product Truth and are adopted into the release registry.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any

STAGES: tuple[str, ...] = ("INTELLIGENCE", "DESIGN", "PRODUCT", "PRODUCT_TRUTH", "VISUAL",
                           "SEARCH", "LISTING_READINESS", "PUBLICATION")
PASS, FAIL, UNKNOWN, BLOCKED, NOT_RUN = "PASS", "FAIL", "UNKNOWN", "BLOCKED", "NOT_RUN"
ADVANCES_PUBLICATION = False
AUDIT_ACTION = "pipeline.board"


@dataclass(frozen=True)
class Proposal:
    """A new product design proposed by the pipeline, with its demand basis labelled."""

    slug: str
    title: str
    motif: str
    palette: str
    width_cm: float
    height_cm: float
    category: str              # the commerce/radar category word
    motifs: tuple[str, ...]    # listing qualifiers (what the fabric shows)
    season: str | None
    demand_basis: str          # SOURCED/DERIVED/ESTIMATED/UNKNOWN, with the source
    rationale: str
    yarn: str = "worsted cotton"
    yarn_weight: str = "worsted"
    pieces: int = 1
    note: str = ""
    finding: str = ""          # intel.findings key whose observation this answers, if any


# The pipeline's own proposals. Each names its demand basis honestly: the radar pool and
# radar/market.py OBSERVATIONS are the only sourced market evidence in the repository, and a
# proposal outside them says ESTIMATED.
PROPOSALS: tuple[Proposal, ...] = (
    Proposal("diamond-lattice-dishcloth", "Diamond Lattice Textured Dishcloth",
             "diamond-lattice", "cottage", 22.0, 22.0, "dishcloth", ("diamond", "lattice"),
             None,
             "ESTIMATED: kitchen quick-makes sit in the CA$4-12 cluster recorded in "
             "radar/market.py OBSERVATIONS; no dishcloth-specific listing was observed",
             "a one-evening make at the bottom of the price ladder, reusing the Cloudline "
             "lattice the renderer and verifier already draw truthfully",
             note="The lattice is a relief: double crochet standing above a single-crochet "
                  "ground, one colour per row."),
    Proposal("basketweave-textured-washcloth", "Basketweave Textured Washcloth",
             "basketweave", "cloudline", 22.0, 22.0, "washcloth", ("basketweave",), None,
             "ESTIMATED: same cluster as the dishcloth; no washcloth listing observed",
             "a second texture at the price floor, so a buyer of one can bundle the other"),
    Proposal("chevron-relief-scarf", "Chevron Relief Scarf", "chevron-band", "nordic",
             20.0, 150.0, "scarf", ("chevron",), "winter",
             "SOURCED (pool): radar.opportunity scores the scarf category (chunky-ribbed-scarf "
             "0.599) and the scarf is blocked on uncalibrated post stitches; this is a scarf "
             "that needs no new primitive",
             "a scarf the company can certify today: sc/dc relief only, no fpdc/bpdc"),
    Proposal("heart-relief-table-runner", "Heart Relief Table Runner", "heart-row", "cottage",
             32.0, 120.0, "runner", ("heart",), "valentines",
             "SOURCED (pool): runner category scored (harvest-table-runner 0.551) and the "
             "valentine-heart-garland concept 0.573; a runner needs no assembly, the garland does",
             "the Valentine's demand the garland targets, in a form whose name the pattern backs"),
    Proposal("snowfall-textured-throw", "Snowfall Textured Throw", "snowfall", "nordic",
             100.0, 130.0, "blanket", ("snowfall",), "christmas",
             "SOURCED (pool): winter-village-graphghan scored 0.729, but its graphghan claim "
             "fails fabric truth; this is the same demand with a truthful name",
             "replaces a false colourwork claim with the relief the tiler actually makes"),
    Proposal("pumpkin-relief-table-runner", "Pumpkin Relief Table Runner", "pumpkin-row",
             "cottage", 32.0, 120.0, "runner", ("pumpkin",), "autumn",
             "SOURCED (pool): spooky-garland 0.682 and harvest-table-runner 0.551 carry the "
             "autumn demand; the garland fails assembly truth",
             "autumn demand in a form that needs no assembly"),
    # Answers to the competitor findings (intel.findings, W4-MJS): demand and merchandising
    # intelligence only -- counts and shares about a category, never a competitor's design.
    Proposal("fir-star-relief-table-runner", "Fir and Star Relief Table Runner",
             "fir-and-star", "nordic", 32.0, 120.0, "runner", ("fir", "star"), "christmas",
             "SOURCED (mjs.findings seasonality): Christmas is inside the buying window and the "
             "benchmark's seasonal shelf is stockings and ornaments only; a table piece is an "
             "open Christmas form",
             "Christmas demand now, in a flat relief the tiler, renderer and verifier draw",
             finding="seasonality"),
    Proposal("basketweave-textured-hand-towel", "Basketweave Textured Hand Towel",
             "basketweave", "cloudline", 30.0, 45.0, "towel", ("basketweave",), None,
             "SOURCED (mjs.findings coverage_gaps): 'Kitchen and bath textiles' is an uncovered "
             "benchmark arena; demand per listing there is a favourites proxy, not sales",
             "the third kitchen-and-bath texture, so the family can carry a priced bundle "
             "(mjs.findings bundle_premium)", finding="coverage_gaps"),
)

# Benchmark arenas (intel.coverage via mjs.findings) the board already answers with a
# candidate; an arena not listed here becomes an INTELLIGENCE candidate awaiting a brief.
ARENA_ANSWERS: dict[str, tuple[str, ...]] = {
    "Kitchen and bath textiles": ("diamond-lattice-dishcloth", "basketweave-textured-washcloth",
                                  "basketweave-textured-hand-towel"),
    "Christmas stockings": ("first-christmas-stocking",),
    "Multi-pattern collections and ebooks": ("diamond-lattice-dishcloth",),  # BUNDLE_FAMILIES
}
# Launch families that should carry a priced bundle from day one (mjs.findings bundle_premium).
BUNDLE_FAMILIES: dict[str, tuple[str, ...]] = {
    "kitchen_texture": ("diamond-lattice-dishcloth", "basketweave-textured-washcloth",
                        "basketweave-textured-hand-towel", "mosaic-placemat-pair"),
    "table_runners": ("heart-relief-table-runner", "pumpkin-relief-table-runner",
                      "fir-star-relief-table-runner"),
}


def proposal_cir(p: Proposal, version: str = "0.1.0"):
    """Build a proposal through the catalogue's own deterministic tiler.

    The size is the input: typed counts are drawn at the builder's 16 sc/10cm intent and then
    re-derived from the declared yarn's published band (`builder._derive_from_yarn`), exactly
    as every catalogue design is, so no proposal can carry a gauge its yarn cannot hold.
    """
    from . import builder
    from .motifs import get

    motif = get(p.motif)
    across = max(1, round(p.width_cm * 16 / (10.0 * motif.width)))
    from ..cir import stitches

    repeat_cm = builder._repeat_height_cm(motif, 18, stitches)
    repeats = max(1, round(p.height_cm / repeat_cm))
    design = builder.Design(slug=p.slug, title=p.title, motif=p.motif, palette=p.palette,
                            width_stitches=across * motif.width, motif_repeats=repeats,
                            yarn=p.yarn, yarn_weight=p.yarn_weight, note=p.note,
                            pieces=p.pieces)
    return builder.build(builder._derive_from_yarn(design), version=version)


# ---- candidates --------------------------------------------------------------------------

@dataclass
class Candidate:
    slug: str
    title: str
    source: str                       # radar_pool|catalogue|launch0|proposal|creative|intelligence
    stages: dict[str, dict] = field(default_factory=dict)

    def set(self, stage: str, status: str, evidence: Any, next_step: str = "",
            clearer: str = "COMPANY") -> None:
        self.stages[stage] = {"status": status, "evidence": evidence,
                              "next_step": next_step, "clearer": clearer}

    @property
    def current(self) -> str:
        for s in STAGES:
            if self.stages.get(s, {}).get("status") != PASS:
                return s
        return STAGES[-1]

    @property
    def highest_passed(self) -> str | None:
        passed = None
        for s in STAGES:
            if self.stages.get(s, {}).get("status") == PASS:
                passed = s
            else:
                break
        return passed

    def to_dict(self) -> dict:
        cur = self.stages.get(self.current, {})
        return {"slug": self.slug, "title": self.title, "source": self.source,
                "stage": self.current, "highest_passed": self.highest_passed,
                "stage_status": cur.get("status", NOT_RUN),
                "next_step": cur.get("next_step", ""), "clearer": cur.get("clearer", ""),
                "stages": {s: self.stages[s] for s in STAGES if s in self.stages}}


def _cir_for(slug: str, source: str):
    if source == "proposal":
        p = next(x for x in PROPOSALS if x.slug == slug)
        return proposal_cir(p)
    from ..runtime.pipeline import _engineered_cir

    return _engineered_cir(slug)


def _finding_ref(findings: dict | None, key: str) -> dict | None:
    for f in (findings or {}).get("findings") or []:
        if f.get("key") == key:
            return {"key": key, "statement": f.get("statement"),
                    "confidence": f.get("confidence"), "opportunity": f.get("opportunity")}
    return None


def _intelligence(c: Candidate, scored: dict, proposal: Proposal | None,
                  findings: dict | None = None) -> None:
    if proposal is not None:
        basis = proposal.demand_basis.split(":", 1)[0].split()[0]
        ev = {"demand_basis": proposal.demand_basis, "rationale": proposal.rationale}
        status = PASS if basis in ("SOURCED", "DERIVED", "ESTIMATED") else UNKNOWN
        if proposal.finding:
            ref = _finding_ref(findings, proposal.finding)
            ev["finding"] = ref
            if ref is None:
                # A demand case that cites a finding the board cannot read is not evidence.
                status = UNKNOWN
        c.set("INTELLIGENCE", status, ev,
              "measure demand once the shop has search data (DATA)" if status == PASS else
              "refresh intel.findings (mjs.findings) so the cited observation is on file",
              "DATA")
        return
    sc = scored.get(c.slug)
    if sc is not None:
        c.set("INTELLIGENCE", PASS, {"radar_score": round(sc.score, 3),
                                     "components": sc.components,
                                     "category": sc.seed.category,
                                     "risk_class": sc.seed.risk_class})
    else:
        c.set("INTELLIGENCE", PASS, {"basis": "a built product (Launch-0 or catalogue); its "
                                              "demand case is recorded on its candidate"})


def _design(c: Candidate) -> None:
    from ..products import launch0

    retired = launch0.LEGACY_DUPLICATES.get(c.slug)
    if retired is not None:
        c.set("DESIGN", BLOCKED, {"retired": retired},
              f"retired concept: its design ships as {', '.join(retired['superseded_by'])}")
        return
    try:
        cir = _cir_for(c.slug, c.source)
    except Exception as exc:  # noqa: BLE001 - a design that cannot be built is the finding
        c.set("DESIGN", FAIL, f"{type(exc).__name__}: {exc}"[:300], "fix the design")
        return
    if cir is None:
        from ..creative import prototype
        from ..radar.opportunity import _pool

        seed = next((s for s in _pool() if s.slug == c.slug), None)
        why = "no engineered design and no catalogue Design for this concept"
        if seed is not None:
            why += f" (radar category {seed.category!r}, risk {seed.risk_class})"
        nxt = ("engineer a deterministic design (products.builder Design or a dedicated "
               "builder); prototype.FORM_GEOMETRY sizes: " + ", ".join(sorted(prototype.FORM_GEOMETRY)))
        if seed is not None and seed.risk_class == "C":
            nxt = "Class C: needs physical testing and graded sizing before design (OWNER/tester)"
        c.set("DESIGN", NOT_RUN, why, nxt)
        return
    c.set("DESIGN", PASS, {"builder": c.source, "construction": cir.construction,
                           "components": [(x.name, x.make) for x in cir.components]})
    c._cir = cir  # type: ignore[attr-defined]


def _product_and_truth(c: Candidate) -> None:
    from ..cir.compiler import compile_cir
    from ..gates.certificate import certify
    from ..publish.eligibility import name_truth

    cir = c._cir  # type: ignore[attr-defined]
    result = compile_cir(cir)
    c.set("PRODUCT", PASS if result.ok else FAIL,
          {"version": cir.version, "compiles": result.ok, "errors": len(result.errors),
           "warnings": len(result.warnings)},
          "" if result.ok else "fix the compile errors")
    if not result.ok:
        return
    cert = certify(cir)
    names = name_truth(cir)
    errs = [str(f)[:240] for f in cert.findings
            if str(getattr(f, "severity", "")).upper().endswith("ERROR")]
    ok = bool(cert.granted) and not names and not result.warnings
    physical = any("UNCALIBRATED_PRIMITIVE" in e for e in errs)
    c.set("PRODUCT_TRUTH", PASS if ok else FAIL,
          {"certified": bool(cert.granted),
           "release_hash": (cert.release_hash or "")[:12] or None,
           "certificate_errors": errs, "name_truth": names,
           "compile_warnings": len(result.warnings)},
          ("" if ok else
           "; ".join(x for x in (
               "rename to what the fabric makes or change the CIR (new version)"
               if (names or not physical) else "",
               "a pattern tester works the new stitch (physical calibration)"
               if physical else "") if x)),
          # Company work is never reported as somebody else's: a name the pattern does not
          # back is the company's to fix even while a stitch also awaits a tester.
          "OWNER" if physical and not names else "COMPANY")


def _visual(c: Candidate, store) -> None:
    from ..products import launch0
    from ..publish import disclosed_listing

    cir = c._cir  # type: ignore[attr-defined]
    try:
        rec = disclosed_listing.build(cir, store=store)
    except Exception as exc:  # noqa: BLE001
        c.set("VISUAL", FAIL, f"{type(exc).__name__}: {exc}"[:300], "W4-CREATIVE: renderer")
        return
    frames = [(f["view"], f["structural_truth"]["status"]) for f in rec.get("frames") or []]
    in_scope = c.slug in launch0.launch_scope_slugs()
    evidence = {"made": bool(rec.get("made")), "usable": bool(rec.get("usable_as_listing_asset")),
                "frames": frames, "launch_blocked": (rec.get("launch_blocked") or [])[:4],
                "launch_scope": in_scope}
    if rec.get("usable_as_listing_asset"):
        c.set("VISUAL", PASS, evidence)
    elif not rec.get("made"):
        c.set("VISUAL", FAIL, evidence,
              "renderer refused this design (W4-CREATIVE owns the renderer; the gate is not "
              "relaxed): change the palette/design to one it can draw and verify")
    else:
        status = UNKNOWN if all(s == UNKNOWN for _, s in frames) else FAIL
        c.set("VISUAL", status, evidence,
              ("the pixel verifier's authority is the Launch-0 registry (D-FB-7): structural "
               "truth is UNKNOWN until the product is registered as a Launch-0 candidate "
               "(cap 5 products; promotion is a catalogue decision, see backlog notes)")
              if status == UNKNOWN and not in_scope else
              "repair the frames the verifier/QA refused (W4-CREATIVE)")


def _search(c: Candidate, proposal: Proposal | None, scored: dict) -> None:
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin
    from ..commerce import seo
    from ..publish.listing_schema import tag_problems, title_problems

    cir = c._cir  # type: ignore[attr-defined]
    if proposal is not None:
        category, motifs, season = proposal.category, list(proposal.motifs), proposal.season
    else:
        sc = scored.get(c.slug)
        category = sc.seed.category if sc else "crochet"
        motifs = [w for w in c.slug.split("-") if w.isalpha()][:2]
        season = sc.seed.season if sc else None
    twin = build_twin(cir, compile_cir(cir))
    title = seo.build_title(cir.title, category, motifs, season)
    tags = seo.build_tags(category, motifs, season)
    copy = seo.ListingCopy(title=title, tags=tags, description="", materials=[cir.materials[0].name],
                           price_cad=0.0)
    problems = (title_problems(title) + tag_problems(tags) + [
        p for p in seo.check_listing_limits(copy) if not p.startswith(("LISTING_NO_DESC",
                                                                       "LISTING_PRICE"))])
    from ..gates.first_customer import colourwork_findings

    problems += colourwork_findings(cir, twin, title=title, tags=tags)
    ev = {"title": title, "tags": tags, "copy_problems": problems[:6],
          "category": "UNKNOWN until an Etsy-read taxonomy snapshot exists (listing."
                      "taxonomy_refresh); none is assumed"}
    if problems:
        c.set("SEARCH", FAIL, ev, "fix the listing copy the gates refuse")
    else:
        # Copy passes every deterministic gate; the category is external, so the stage is
        # UNKNOWN, never PASS, until the taxonomy snapshot exists.
        c.set("SEARCH", UNKNOWN, ev, "listing.taxonomy_refresh with the deployed app's Etsy "
                                     "read access (EXTERNAL), then listing.seo", "EXTERNAL")


# Constructions the deterministic builder makes today (flat rows of one colour per row).
BUILDER_CONSTRUCTIONS = ("flat_rows",)


def creative_candidates() -> list[Candidate]:
    """W4-CREATIVE's moment-first concepts, carried to the stage their engineering allows.

    INTELLIGENCE is the creative brief (validated by `creative.emotional_brief`; a refused
    brief stops there). DESIGN needs a deterministic CIR; none of these has one yet, and the
    stage says exactly what has to be engineered -- a construction the builder does not make,
    or an assembled form (pocket fold, tie, closing seam) a flat panel cannot honestly carry.
    """
    from ..creative import emotional_brief as eb
    from . import launch0

    concepts, refused = eb.candidate_concepts()
    ok = {k.key for k in concepts}
    out: list[Candidate] = []
    for raw in eb.NEW_CANDIDATES:
        brief = raw["brief"]
        c = Candidate(slug=raw["key"], title=brief.title, source="creative")
        if raw["key"] in refused:
            c.set("INTELLIGENCE", FAIL, {"brief_refused": refused[raw["key"]][:3]},
                  "W4-CREATIVE: repair the brief")
            out.append(c)
            continue
        c.set("INTELLIGENCE", PASS, {"premise": brief.premise, "function": brief.function,
                                     "occasion": brief.occasion, "pod": raw["pod"],
                                     "demand_basis": "ESTIMATED: creative brief; demand is "
                                                     "unmeasured until the shop has search data",
                                     "concept_accepted": raw["key"] in ok})
        named = [f for f in launch0.ASSEMBLED_FORMS if f in brief.title.lower()]
        if raw["construction"] not in BUILDER_CONSTRUCTIONS:
            nxt = (f"engineer a {raw['construction']} builder for a {raw['form']} "
                   f"({raw['motif']}, {raw['palette_story']}); the products.builder tiler makes "
                   "flat rows only")
        elif named:
            nxt = (f"the title names an assembled form ({named[0]!r}): engineer the extra "
                   "components and named-edge Seams in cir.assembly (pocket fold, tie cord); a "
                   "flat panel under this name fails name truth")
        else:
            nxt = "build it as a products.builder Design proposal"
        c.set("DESIGN", NOT_RUN, {"construction": raw["construction"], "form": raw["form"],
                                  "motif": raw["motif"], "assembled_form_named": named},
              nxt)
        out.append(c)
    return out


def intelligence_candidates(findings: dict | None, answered: set[str]) -> list[Candidate]:
    """Benchmark arenas with no Brambleloop answer, from the stored competitor findings.

    Demand and merchandising intelligence only: the candidate carries the arena name, the
    finding's statement and its confidence grade, never a competitor's design. An arena the
    board already answers (ARENA_ANSWERS with a live candidate) is not repeated.
    """
    ref = _finding_ref(findings, "coverage_gaps")
    if ref is None:
        return []
    f = next(x for x in findings["findings"] if x.get("key") == "coverage_gaps")
    pods = (_finding_ref(findings, "demand_by_pod") or {})
    out: list[Candidate] = []
    for gap in (f.get("metrics") or {}).get("top") or []:
        arena = gap.get("arena") or ""
        if not arena or any(s in answered for s in ARENA_ANSWERS.get(arena, ())):
            continue
        slug = "gap-" + "-".join(w for w in arena.lower().replace("&", "and").split()
                                  if w.isalnum())
        c = Candidate(slug=slug, title=arena, source="intelligence")
        c.set("INTELLIGENCE", PASS, {"finding": ref, "arena_state": gap.get("state"),
                                     "demand_proxy": pods.get("statement")})
        c.set("DESIGN", NOT_RUN, "no original concept yet for this arena",
              "W4-CREATIVE: write a moment-first brief (creative.emotional_brief) for this "
              "arena, then engineer a deterministic design; never copy the benchmark")
        out.append(c)
    return out


def board(*, today: date | None = None, store=None, visual: bool = True,
          include_pool: bool = True, findings: dict | None = None) -> dict:
    """Evaluate every candidate as far as it can go. Pure apart from rendering to `store`."""
    from ..products import inventory
    from ..radar.opportunity import score_pool

    today = today or date.today()
    scored = {s.seed.slug: s for s in score_pool(today=today)}
    slugs: dict[str, str] = {}
    for slug in inventory.universe():
        from ..products import launch0
        slugs[slug] = "launch0" if slug in launch0.launch_scope_slugs() else "catalogue"
    if include_pool:
        for slug in scored:
            slugs.setdefault(slug, "radar_pool")
    for p in PROPOSALS:
        slugs[p.slug] = "proposal"
    cands: list[Candidate] = []
    for slug, source in sorted(slugs.items()):
        proposal = next((p for p in PROPOSALS if p.slug == slug), None)
        sc = scored.get(slug)
        c = Candidate(slug=slug, title=(proposal.title if proposal else
                                        sc.seed.title if sc else slug), source=source)
        _intelligence(c, scored, proposal, findings)
        if c.stages["INTELLIGENCE"]["status"] != PASS:
            cands.append(c)
            continue
        _design(c)
        if c.stages["DESIGN"]["status"] == PASS:
            c.title = c._cir.title  # type: ignore[attr-defined]
            _product_and_truth(c)
            if c.stages.get("PRODUCT_TRUTH", {}).get("status") == PASS:
                if visual:
                    _visual(c, store)
                if visual and c.stages.get("VISUAL", {}).get("status") == PASS:
                    _search(c, proposal, scored)
                elif not visual:
                    c.set("VISUAL", NOT_RUN, "visual stage not run in this pass")
            if c.stages.get("SEARCH", {}).get("status") == PASS:
                c.set("LISTING_READINESS", NOT_RUN, "read from the release chain")
        cands.append(c)
    cands += creative_candidates()
    cands += intelligence_candidates(findings, {c.slug for c in cands})
    rows = [c.to_dict() for c in cands]
    counts: dict[str, int] = {s: 0 for s in STAGES}
    passed: dict[str, int] = {s: 0 for s in STAGES}
    for r in rows:
        counts[r["stage"]] += 1
        for s in STAGES:
            if r["stages"].get(s, {}).get("status") == PASS:
                passed[s] += 1
    by = {r["slug"]: r for r in rows}
    bundles = {}
    for fam, members in BUNDLE_FAMILIES.items():
        present = [m for m in members if m in by]
        truthful = [m for m in present
                    if by[m]["stages"].get("PRODUCT_TRUTH", {}).get("status") == PASS]
        bundles[fam] = {"members": present, "product_truth_passed": truthful,
                        "bundle_ready_for_pricing": len(truthful) >= 2,
                        "basis": "mjs.findings bundle_premium (listed prices; whether bundles "
                                 "sell is unmeasured)"}
    return {"as_of": today.isoformat(), "stages": list(STAGES), "candidates": rows,
            "at_stage": counts, "passed_stage": passed, "bundle_families": bundles,
            "findings_as_of": (findings or {}).get("as_of"),
            "advances_publication": ADVANCES_PUBLICATION,
            "publication_gate": "owner: shop/KYC, payout, fees, phase, sealed publication grant "
                                "per release (D-FB-10); never advanced by this board"}


def merge_chain(result: dict, db, *, today: date | None = None) -> dict:
    """Attach the release chain's listing-readiness verdict for candidates it has built.

    The LISTING_READINESS stage is the verdict `store.publish` computes
    (`publish.release_gates.for_publish`), read off a shadow database the chain ran on.
    """
    from . import inventory

    for row in result["candidates"]:
        if row["stage"] not in ("SEARCH", "LISTING_READINESS") or row["source"] == "proposal":
            continue
        version = (row["stages"].get("PRODUCT") or {}).get("evidence", {}).get("version")
        ev = inventory.chain_evidence(db, row["slug"], version, today=today)
        verdict = ev.get("publish_verdict")
        if not verdict:
            row["stages"]["LISTING_READINESS"] = {
                "status": NOT_RUN, "evidence": {"jobs": ev.get("jobs")},
                "next_step": "the chain has not built this product: enqueue cir.draft",
                "clearer": "COMPANY"}
            continue
        reasons = verdict.get("reasons") or []
        clearers = sorted({inventory.classify_reason(r)[1] for r in reasons})
        company = [r for r in reasons if inventory.classify_reason(r)[1] == "COMPANY"]
        row["stages"]["LISTING_READINESS"] = {
            "status": PASS if not reasons else BLOCKED,
            "evidence": {"reasons": reasons, "clearers": clearers},
            "next_step": ("company: " + "; ".join(company[:3])) if company else
                         "only owner/external gates remain: " + ", ".join(clearers),
            "clearer": "COMPANY" if company else ",".join(clearers)}
    return result


def record(db, result: dict) -> None:
    """File the board as one audit row, so the Command Center and the next run can read it."""
    from ..core.models import AuditLog

    slim = {"as_of": result["as_of"], "at_stage": result["at_stage"],
            "passed_stage": result["passed_stage"],
            "candidates": [{k: r[k] for k in ("slug", "stage", "stage_status", "next_step",
                                              "clearer")} for r in result["candidates"]]}
    with db.session() as s:
        s.add(AuditLog(actor="product_pipeline", action=AUDIT_ACTION, detail=slim))
        s.commit()


def launch_scope_drafts() -> list[str]:
    """Every Launch-0 CIR slug the release chain must draft, whatever the radar selected.

    The radar's portfolio selects concept slugs; `hexagon-coaster-set` is a Launch-0 product
    whose retired concept slug (`hexie-coaster-set`) the radar does not select, so the
    autonomous plan.cycle never builds it (W4 scratch run, 2026-10-07). A cadence that
    enqueues `cir.draft` for these slugs closes that gap (WIRING REQUEST to W4-AUTO).
    """
    from ..products import builder, launch0
    from ..runtime.pipeline import ENGINEERED

    return sorted(s for s in launch0.launch_scope_slugs()
                  if s in ENGINEERED or s in builder.CATALOGUE)


def built_releases(db) -> set[str]:
    """Slugs with at least one PatternVersion on file in `db`."""
    from sqlalchemy import select

    from ..core.models import PatternVersion, Product

    with db.session() as s:
        ids = {pv.product_id for pv in s.scalars(select(PatternVersion))}
        return {p.slug for p in s.scalars(select(Product)) if p.id in ids}


def handle_product_pipeline(ctx) -> dict:
    """Job handler body for `product.pipeline` (registered by W4-AUTO, see WIRING REQUEST).

    One pass of the board, recorded as a `pipeline.board` audit row, plus the only advance this
    board is authorised to make on its own: a Launch-0 product the chain has never built is
    queued at `cir.draft` (the radar's portfolio does not select every Launch-0 slug). Nothing
    is queued past certification by this handler and publication is never touched.
    """
    inputs = dict(ctx.job.inputs or {})
    today = date.fromisoformat(inputs["as_of"]) if inputs.get("as_of") else date.today()
    from ..intel import findings as intel_findings

    result = board(today=today, visual=bool(inputs.get("visual")),
                   findings=intel_findings.latest(ctx.db))
    if inputs.get("merge_chain"):
        merge_chain(result, ctx.db, today=today)
    record(ctx.db, result)
    built = built_releases(ctx.db)
    queued = []
    for slug in launch_scope_drafts():
        if slug not in built:
            ctx.enqueue("crochet_engineer", "cir.draft", {"slug": slug},
                        idempotency_key=f"pipeline-draft:{slug}")
            queued.append(slug)
    return {"at_stage": result["at_stage"], "passed_stage": result["passed_stage"],
            "candidates": len(result["candidates"]), "queued_cir_draft": queued,
            "advances_publication": ADVANCES_PUBLICATION}
