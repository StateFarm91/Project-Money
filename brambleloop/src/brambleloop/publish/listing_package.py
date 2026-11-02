"""OPUS2: the automatic listing package -- what the owner reviews before any listing goes live.

W-LISTING writes `research/final_build/w4/manual_listings/<slug>-<version>/LISTING_PACKAGE.md`
by hand from a SHADOW chain run. This module assembles the same package for every certified
release automatically (integrator item INTEG-LISTING-JOB), and it invents nothing: every
field is read from what the release chain itself stored, through the functions publication
uses.

* **Copy, price, taxonomy and properties** come from `runtime.etsy_ops.certified_payload`,
  "the Etsy payload for a certified release, built exactly as store.publish builds it". Where
  it refuses, its reason is a blocker and no copy is guessed.
* **Gallery** comes from `etsy_ops.certified_frames`: the valid listing-set certificate's
  frames in certificate order, each with its disclosure label.
* **Files** come from the latest completed `assets.build` for this exact release: the PDF
  hash per terminology, the page count and the size label.
* **Blockers** come from `release_gates.for_publish(read_only=True, stage="activation")`:
  every reason a buyer-facing publication would refuse, gathered once.
* **Identity** comes from the certified pattern version and `products.launch0`: the risk class,
  the children's decision and Product Truth where the release is a Launch-0 candidate.

A package with no blocker is `ready_for_owner_review`, and only then does it raise one owner
action asking the owner to review it. Publishing stays the owner's, by hand or through the
publish gates. Otherwise it is `blocked` with every reason listed. Packages are idempotent:
the fingerprint is computed over the content, and an unchanged package is not rewritten.
Nothing here publishes, calls Etsy, a model or the network, or spends. It does write
internally (review OPUS2F A-6): the package reading, its Markdown artefact, the owner's review
request, and -- through `for_publish` -- the listing-set certificate, hero verdict and
withholding reconciliation that `store.publish` would also write. Hence action class B, like
`chain.rebuild`, not OBSERVE.

There is one current package per `slug@version`, fingerprinted over the release hash and every
field, so a new release, new copy or new frames is a new package (A-7). Once integrated, this
automatic package is the canonical one for a release; the hand-written
`manual_listings/*/LISTING_PACKAGE.md` files are W-LISTING's historical record.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

KIND = "listing.package"
ACTION_PREFIX = "listing_package:"
READY = "ready_for_owner_review"
BLOCKED = "blocked"


def _try(fn, *a, **k):
    try:
        return fn(*a, **k), None
    except Exception as exc:  # noqa: BLE001 - a reader that cannot answer is a blocker
        return None, f"{type(exc).__name__}: {str(exc)[:300]}"


def _release(db, slug: str, version: str) -> dict | None:
    from sqlalchemy import select

    from ..core.models import Listing, PatternVersion, Product

    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        pv = (s.scalar(select(PatternVersion).where(PatternVersion.product_id == product.id,
                                                    PatternVersion.version == version))
              if product is not None else None)
        if pv is None or not pv.certified:
            return None
        listings = list(s.scalars(select(Listing).where(Listing.product_slug == slug,
                                                        Listing.version == version)
                                  .order_by(Listing.id.desc())))
        listing = listings[0] if listings else None
        return {"release_hash": pv.release_hash or "", "cir": dict(pv.cir_json or {}),
                "listing_state": listing.state if listing is not None else None,
                "listing_release": (listing.release_hash or "") if listing is not None else ""}


def _files(db, slug: str, version: str, release: str) -> dict | None:
    """The PDFs certified for exactly this release, or None (review OPUS2F A-1).

    The hashes come from `pipeline._certified_pdf_hashes`, the canonical reader: it requires the
    job's own release to equal this one. An empty release is never a wildcard: it binds nothing.
    The descriptive fields come only from an `assets.build` job that names this same release.
    """
    from sqlalchemy import desc, select

    from ..core.models import Job, JobStatus
    from ..runtime import pipeline

    if not release:
        return None
    hashes = pipeline._certified_pdf_hashes(db, slug, version, release)
    if not hashes:
        return None
    meta: dict = {}
    with db.session() as s:
        for job in s.scalars(select(Job).where(Job.job_type == "assets.build",
                                               Job.status == JobStatus.DONE)
                             .order_by(desc(Job.id))):
            i, o = dict(job.inputs or {}), dict(job.outputs or {})
            if (i.get("slug"), i.get("version")) == (slug, version) and \
                    (i.get("release") or o.get("release") or "") == release:
                meta = {"pages": o.get("pages"), "size_label": o.get("size_label"),
                        "finished_size_cm": o.get("finished_size_cm"),
                        "calibrated": o.get("calibrated"), "assets_job": job.id}
                break
    return {"pdf_sha256_by_terminology": dict(hashes), **meta}


def _identity(slug: str, cir: dict) -> dict:
    from ..products import launch0

    out = {"risk_class": cir.get("risk_class"), "title_in_pattern": cir.get("title"),
           "childrens_decision": None, "product_truth": None}
    # A1R-6: the construction-aware decision the renderer holds on, never the raw one, so a
    # listing cannot say "not_for_children" for a stuffed form whose documents are held.
    def _decision(slug_):
        from ..cir.model import CIR

        return (launch0.childrens_decision_for(CIR.from_dict(cir)) if cir
                else launch0.childrens_decision(slug_))
    decision, err = _try(_decision, slug)
    out["childrens_decision"] = (list(decision) if isinstance(decision, tuple)
                                 else (decision if err is None else f"UNKNOWN: {err}"))
    cand = next((c for c in launch0.CANDIDATES
                 if any(getattr(v, "slug", None) == slug or getattr(v, "cir_slug", None) == slug
                        for v in getattr(c, "variants", ()))
                 or c.slug == slug), None)
    if cand is not None:
        truth, err = _try(launch0.product_truth, cand)
        out["product_truth"] = ({"candidate": cand.slug,
                                 "passes_gates": bool((truth or {}).get("passes_gates"))}
                                if err is None else f"UNKNOWN: {err}")
    return out


def assemble(db, slug: str, version: str) -> dict | None:
    """The listing package for one certified release, or None if it is not certified."""
    from ..publish import release_gates
    from ..runtime import etsy_ops

    rel = _release(db, slug, version)
    if rel is None:
        return None
    release = rel["release_hash"]
    blockers: list[dict] = []

    # The publication gates run FIRST: they settle the listing-set certificate the gallery is
    # read from, so the package reads one consistent state and an unchanged chain yields an
    # unchanged package.
    gate, err = _try(release_gates.for_publish, db, slug=slug, version=version,
                     read_only=True, stage=release_gates.STAGE_ACTIVATION)
    if err is not None:
        blockers.append({"source": "release_gates.for_publish", "why": err})
    else:
        for reason in gate.get("reasons") or []:
            blockers.append({"source": "release_gates.for_publish", "why": str(reason)[:300]})

    payload, err = _try(etsy_ops.certified_payload, db, slug, version)
    copy = None
    if err is not None:
        blockers.append({"source": "certified_payload", "why": err})
    else:
        fields, ferr = _try(etsy_ops.sent_fields, payload)
        copy = fields if ferr is None else None
        if ferr is not None:
            blockers.append({"source": "certified_payload", "why": ferr})

    framed, err = _try(etsy_ops.certified_frames, db, slug, version, release=release)
    frames = []
    if err is not None:
        blockers.append({"source": "certified_frames", "why": err})
    else:
        for problem in framed.get("problems") or []:
            blockers.append({"source": "certified_frames", "why": str(problem)[:300]})
        frames = [{"position": f.get("position"), "kind": f.get("kind"),
                   "sha256": f.get("sha256"), "honesty_label": f.get("honesty_label"),
                   "alt_text": f.get("alt_text")} for f in framed.get("frames") or []]

    files = _files(db, slug, version, release)
    if not release:
        blockers.append({"source": "release", "why": "the certified release has no release "
                                                     "hash, so no file can be bound to it"})
    if files is None or not files.get("pdf_sha256_by_terminology"):
        blockers.append({"source": "assets.build",
                         "why": "no assets.build certifies PDFs for exactly this release"})
    # Review OPUS2F A-4: the copy must belong to this release. (One row per slug@version is
    # already a database constraint, `listings (product_slug, version)` unique, so the row this
    # reads is the row `certified_payload` reads.)
    if rel["listing_release"] and release and rel["listing_release"] != release:
        blockers.append({"source": "listing", "why": (
            f"the drafted listing was written for release {rel['listing_release'][:12]}, not "
            f"the certified {release[:12]}")})


    package = {
        "slug": slug, "version": version, "release_hash": release,
        "state": READY if not blockers else BLOCKED,
        "identity": _identity(slug, rel["cir"]),
        "listing_state": rel["listing_state"],
        "copy": copy,
        "gallery": frames,
        "disclosures": sorted({f["honesty_label"] for f in frames if f.get("honesty_label")}),
        "files": files,
        "blockers": blockers,
        "publishes": False,
        "sources": {"copy": "runtime.etsy_ops.certified_payload",
                    "gallery": "runtime.etsy_ops.certified_frames",
                    "files": "assets.build job outputs",
                    "blockers": "publish.release_gates.for_publish(stage=activation)"},
    }
    package["fingerprint"] = hashlib.sha256(
        json.dumps(package, sort_keys=True, default=str).encode()).hexdigest()
    return package


def render(package: dict) -> str:
    """The package as the Markdown an owner reads (same sections as the manual packages)."""
    p, copy = package, package.get("copy") or {}
    lines = [f"# Listing package: `{p['slug']}@{p['version']}`", "",
             f"**State: {p['state'].replace('_', ' ').upper()}.** Assembled automatically from "
             f"the release chain's stored outputs. Nothing was published.", "",
             f"- Release hash: `{p['release_hash']}`",
             f"- Risk class: {p['identity'].get('risk_class')}",
             f"- Children's decision: {p['identity'].get('childrens_decision')}",
             f"- Product Truth: {p['identity'].get('product_truth')}", "",
             "## 1. Title", "", "```", str(copy.get("title") or "UNKNOWN: no certified copy"),
             "```", "", "## 2. Description", "", "```",
             str(copy.get("description") or "UNKNOWN: no certified copy"), "```", "",
             "## 3. Category and attributes", "",
             f"- Taxonomy id: {copy.get('taxonomy_id', 'UNKNOWN')}",
             f"- Properties: {json.dumps(copy.get('properties'), sort_keys=True)}", "",
             "## 4. Tags", "", ", ".join(copy.get("tags") or []) or "UNKNOWN", "",
             "## 5. Price", "", f"{copy.get('price', 'UNKNOWN')}", "",
             "## 6. Digital files", ""]
    files = p.get("files") or {}
    for term, sha in sorted((files.get("pdf_sha256_by_terminology") or {}).items()):
        lines.append(f"- {term} PDF: `{sha}`")
    lines += [f"- Pages: {files.get('pages')}; size: {files.get('size_label')}", "",
              "## 7. Disclosures", ""]
    lines += [f"- {d}" for d in p.get("disclosures") or []] or ["- none recorded"]
    lines += ["", "## 8. Gallery (certificate order)", ""]
    lines += [(f"{f['position']}. {f.get('kind')} `{str(f.get('sha256'))[:16]}` "
               f"{f.get('honesty_label') or ''}".rstrip()
               + (f"\n   Alt text: {f['alt_text']}" if f.get("alt_text") else ""))
              for f in p.get("gallery") or []] or ["UNKNOWN: no certified gallery"]
    lines += ["", "## 9. Outstanding publication requirements", ""]
    lines += [f"- [{b['source']}] {b['why']}" for b in p.get("blockers") or []] \
        or ["- none: ready for the owner's review"]
    return "\n".join(lines) + "\n"


def _owner_closed() -> frozenset:
    from ..ops import owner_queue

    return frozenset({owner_queue.SATISFIED, owner_queue.WITHDRAWN})


def record(db, package: dict, *, now: datetime | None = None) -> dict:
    """Store the package durably (one reading per release, rewritten only when it changed) and
    keep the owner's review request in step with its state."""
    from sqlalchemy import or_, select

    from ..core.artifacts import ArtifactStore
    from ..core.models import OperatingReading, OwnerAction
    from ..ops import owner_queue

    _OWNER_CLOSED = _owner_closed()

    now = now or datetime.now(timezone.utc)
    key = f"{package['slug']}@{package['version']}"
    action_key = f"{ACTION_PREFIX}{key}"
    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == KIND,
                                                      OperatingReading.period_key == key))
        changed = row is None or (row.payload or {}).get("fingerprint") != package["fingerprint"]
    md_sha = None
    if changed:
        stored, err = _try(ArtifactStore().put,
                           f"listing_packages/{package['slug']}/{package['version']}/"
                           f"{package['fingerprint'][:16]}.md",
                           render(package).encode(), "text/markdown")
        md_sha = stored.sha256 if stored is not None else None
    from ..runtime.release import _serialise_owner_queue

    with db.session() as s:
        # The owner-queue lock is the transaction's first statement (SQLite: BEGIN IMMEDIATE
        # cannot start inside a transaction a read already began).
        _serialise_owner_queue(s, db)
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == KIND,
                                                      OperatingReading.period_key == key))
        if changed:
            body = {**package, "markdown_sha256": md_sha, "assembled_at": now.isoformat()}
            if row is None:
                s.add(OperatingReading(kind=KIND, period_key=key, payload=body))
            else:
                row.payload = body
        # Review OPUS2F A-2/A-3: the review request names the content it asks about. A
        # request the owner already closed for THIS content is never raised again; a request
        # for older content is superseded when the content changes or is blocked again.
        current = f"{action_key}:{package['fingerprint'][:16]}"
        # Review OPUS2EF2 EF2-5: the unfingerprinted key from the first version of this job
        # (exactly `action_key`) is matched too, so a request left under it is superseded
        # rather than orphaned beside the fingerprinted one.
        rows = list(s.scalars(select(OwnerAction).where(or_(
            OwnerAction.requirement_key.like(f"{action_key}:%"),
            OwnerAction.requirement_key == action_key))))
        raised = closed = False
        for stale in rows:
            # Review OPUS2G L5-1: a request the owner PARKED (deferred) is the owner's answer;
            # a transient block leaves it parked. Changed content still supersedes it, because
            # new content is a new question.
            owner_parked = (stale.state or "") == owner_queue.PARKED
            if owner_parked and package["state"] != READY:
                continue
            if not stale.done and (package["state"] != READY
                                   or stale.requirement_key != current):
                why = ("the listing package is blocked again: "
                       + "; ".join(b["why"] for b in package["blockers"][:2])
                       if package["state"] != READY
                       else "the listing package changed; a request for the new content "
                            "replaces this one")
                owner_queue.close(stale, owner_queue.SUPERSEDED, why[:400], now=now)
                closed = True
        # Review OPUS2EF2 EF2-4: only an open request, or one the OWNER closed (satisfied or
        # withdrawn), stands for this content. A request this job superseded itself (the
        # package was blocked for a while, then came back unchanged) is not the owner's answer,
        # so the owner is asked again rather than never.
        already = any(r.requirement_key == current
                      and (not r.done or r.state in _OWNER_CLOSED) for r in rows)
        if package["state"] == READY and not already:
            title = ((package.get("copy") or {}).get("title") or key)[:90]
            s.add(OwnerAction(
                requirement_key=current,
                action=f"Review the listing package for {title!r} ({key}) before publication",
                reason=(f"Every publication gate passes for release "
                        f"{package['release_hash'][:12]} (package "
                        f"{package['fingerprint'][:12]}); the package (copy, gallery, files, "
                        f"disclosures) is assembled from the certified chain for your review. "
                        f"Publishing remains your decision."),
                max_cost_cad=0.0, minutes=15,
                consequence_of_delay="the release stays unpublished; nothing else waits on it",
                blocks="INTEG-LISTING-JOB"))
            raised = True
    return {"key": key, "state": package["state"], "changed": changed,
            "blockers": len(package["blockers"]), "markdown_sha256": md_sha,
            "review_requested": raised, "review_withdrawn": closed}


def certified_releases(db) -> list[tuple[str, str]]:
    from sqlalchemy import select

    from ..core.models import Listing, PatternVersion, Product

    with db.session() as s:
        listed = {(r.product_slug, r.version) for r in s.scalars(select(Listing))}
        out = []
        for product, pv in s.execute(select(Product, PatternVersion).join(
                PatternVersion, PatternVersion.product_id == Product.id).where(
                PatternVersion.certified == True)):  # noqa: E712
            if (product.slug, pv.version) in listed:
                out.append((product.slug, pv.version))
    return sorted(set(out))


def sweep(db) -> dict:
    """Assemble and record the package of every certified release that has a drafted listing."""
    results = []
    for slug, version in certified_releases(db):
        package, err = _try(assemble, db, slug, version)
        if err is not None or package is None:
            results.append({"key": f"{slug}@{version}", "error": err or "not certified"})
            continue
        recorded, rerr = _try(record, db, package)
        results.append(recorded if rerr is None else
                       {"key": f"{slug}@{version}", "error": rerr, "state": package["state"]})
    return {"releases": len(results), "results": results,
            "ready": sum(1 for r in results if r.get("state") == READY),
            "changed": sum(1 for r in results if r.get("changed"))}


def latest(db, slug: str, version: str) -> dict | None:
    from sqlalchemy import select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == KIND,
                                                      OperatingReading.period_key ==
                                                      f"{slug}@{version}"))
        return dict(row.payload or {}) if row is not None else None
