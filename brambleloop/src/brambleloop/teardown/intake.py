"""Getting a purchased benchmark from a phone into the quarantine, with nothing typed.

Requirement 170 asks that the manifest be generated rather than requested. `library.scan()`
already does the inference; what was missing was the two ends of it — a way for the files to
arrive at all, and a way for the arrival to fill in everything the catalogue already knows.

The owner buys thirteen patterns from a phone and receives thirteen downloads, most of them
zipped. Every minute of work asked of them after that is a minute in which the set does not
get analysed, so intake is built to ask for exactly one thing: which pick this is. Everything
else — the seller, the department, the price, the listing reference, why this one was bought,
what the listing promised — is already in the catalogue row that made the selection, and a
system that asks a person to retype what it already stored is a system that will be given up
on around purchase four.

Four rules, each against a specific way a file-upload path goes wrong.

**An upload is not a durable file.** This runs on a host whose disk is replaced on every
deploy. A purchase written only there is a purchase that will need making again, so intake
mirrors each file to the off-provider archive and reports `durable: false` — loudly, with the
reason — when it cannot. "Uploaded" and "kept" are different claims and this returns both.

**The quarantine boundary is at the write, not only at the read.** `library.retrieve()`
refuses a path that resolves out of the library. So does this: a multipart filename is
attacker-controlled by construction, and a zip entry doubly so. Names are reduced to a
basename, entries that climb are refused, and the expansion is bounded in count, in size and
in ratio.

**Zips are expanded, because the alternative is asking.** Etsy delivers a zip; a phone
unzips it badly or not at all. Expanding it here is the difference between a workflow and an
instruction to go and find a computer.

**The promise audit is stored as its inputs, not as its verdict.** What the listing said and
what the files are both live in the manifest row, and the comparison is recomputed on demand.
A verdict written once is a verdict that is wrong the next time the listing is re-observed.

Nothing here opens a file. Sizes and hashes come from the filesystem, roles from filenames.
The only thing that ever reads a benchmark's contents is an analyst going through
`library.retrieve()`, which is the point of the quarantine.
"""
from __future__ import annotations

import io
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

from . import library

# What a purchased crochet pattern can plausibly arrive as. An allow-list rather than a
# block-list: this writes to the filesystem of a production host, and "everything except the
# dangerous ones" requires knowing all of them.
ALLOWED_SUFFIXES: frozenset[str] = frozenset({
    ".pdf", ".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".txt", ".md", ".rtf",
    ".doc", ".docx", ".mp4", ".mov", ".m4v", ".svg", ".csv",
})

# Zips are expanded rather than stored, so the suffix is accepted at the door and never on
# disk.
ARCHIVE_SUFFIXES: frozenset[str] = frozenset({".zip"})

MAX_FILE_BYTES = 80 * 1024 * 1024
MAX_FILES_PER_PURCHASE = 60
MAX_EXPANDED_BYTES = 300 * 1024 * 1024
# A zip that expands more than this against its compressed size is not a pattern bundle.
MAX_EXPANSION_RATIO = 200

MIRROR_ACTION = "benchmark.offsite_mirror"
INTAKE_ACTION = "benchmark.intake"

# The approved set. Both numbers are the owner's decision of 2026-09-20 and are enforced in
# code rather than remembered, like every other ceiling here.
SET_SIZE = 13
SET_BUDGET_CAD = 300.0

# What the manifest's `teardown_state` means once files exist. `queued` is the default for a
# row that has none; this says the files are here and the analyst has not been through them.
AWAITING_ANALYST = "awaiting_analyst"


class IntakeRefused(Exception):
    """An upload that must not be written, or a pick that is not in the catalogue."""


# ---------------------------------------------------------------------------
# Names


def safe_name(name: str) -> str:
    """Reduce an uploaded name to something that cannot leave the purchase folder.

    A browser sends the basename; a phone sometimes sends a path; a zip entry sends whatever
    it likes. All three are handled the same way, because the one that gets handled specially
    is the one that gets handled wrong.
    """
    cleaned = (name or "").replace("\\", "/").strip()
    base = cleaned.rsplit("/", 1)[-1].strip()
    base = "".join(ch for ch in base if ch.isprintable() and ch not in '\0:*?"<>|')
    base = base.lstrip(". ")
    if not base:
        raise IntakeRefused(f"{name!r} has no usable filename")
    if len(base) > 120:
        stem, _, suffix = base.rpartition(".")
        base = f"{stem[:110]}.{suffix}" if suffix else base[:120]
    return base


def _suffix(name: str) -> str:
    return Path(name).suffix.lower()


def _check_suffix(name: str) -> None:
    suffix = _suffix(name)
    if suffix in ALLOWED_SUFFIXES or suffix in ARCHIVE_SUFFIXES:
        return
    raise IntakeRefused(
        f"{name!r} is not a pattern deliverable ({suffix or 'no extension'}). The library "
        f"accepts what a crochet purchase arrives as; anything else reaching a production "
        f"filesystem through an upload form is a different feature wearing this one's label")


# ---------------------------------------------------------------------------
# Expansion


def expand(name: str, payload: bytes) -> list[tuple[str, bytes]]:
    """One upload as the files it actually contains. Zips are opened; everything else is not.

    Bounded three ways because an archive is a size the uploader chooses: entry count, total
    expanded bytes and expansion ratio. A pattern bundle is a handful of files and a few tens
    of megabytes, so a bound that a real purchase would hit is a bound set wrong.
    """
    if _suffix(name) not in ARCHIVE_SUFFIXES:
        return [(safe_name(name), payload)]

    out: list[tuple[str, bytes]] = []
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            entries = [i for i in zf.infolist() if not i.is_dir()]
            if len(entries) > MAX_FILES_PER_PURCHASE:
                raise IntakeRefused(
                    f"{name!r} holds {len(entries)} files, past the {MAX_FILES_PER_PURCHASE} "
                    f"a purchase is expected to contain")
            declared = sum(i.file_size for i in entries)
            if payload and declared > len(payload) * MAX_EXPANSION_RATIO:
                raise IntakeRefused(
                    f"{name!r} declares {declared:,} bytes from {len(payload):,}, which is "
                    f"not a pattern bundle")
            for info in entries:
                entry = info.filename.replace("\\", "/")
                if entry.startswith("/") or ".." in entry.split("/"):
                    raise IntakeRefused(
                        f"zip entry {info.filename!r} climbs out of the purchase folder. The "
                        f"library is a quarantine; an entry that can write outside it is not "
                        f"in one")
                base = entry.rsplit("/", 1)[-1]
                if not base or base.startswith(".") or base.startswith("__MACOSX"):
                    continue
                if _suffix(base) not in ALLOWED_SUFFIXES:
                    continue  # a readme, a .DS_Store, a nested zip: not a deliverable
                data = zf.read(info)
                total += len(data)
                if total > MAX_EXPANDED_BYTES:
                    raise IntakeRefused(
                        f"{name!r} expands past {MAX_EXPANDED_BYTES:,} bytes")
                out.append((safe_name(base), data))
    except zipfile.BadZipFile as exc:
        raise IntakeRefused(f"{name!r} is not a readable zip: {exc}") from exc

    if not out:
        raise IntakeRefused(
            f"{name!r} contained nothing this library accepts. If the purchase really is "
            f"empty that is itself a finding about the seller, recorded by hand rather than "
            f"by an intake that pretends it received something")
    return out


# ---------------------------------------------------------------------------
# What the catalogue already knows


def _catalogue_row(db, listing_ref: str):
    from sqlalchemy import select

    from ..core.models import BenchmarkListing
    from ..intel import benchmarks

    with db.session() as s:
        row = s.scalar(select(BenchmarkListing).where(
            BenchmarkListing.benchmark_key == benchmarks.MJS_KEY,
            BenchmarkListing.listing_ref == str(listing_ref)))
        if row is None:
            return None
        # Detached use; copy what intake needs rather than keeping a session open across the
        # filesystem work.
        return {
            "listing_ref": row.listing_ref, "title": row.title, "pod": row.pod,
            "product_type": row.product_type, "price_cad": float(row.price_cad or 0.0),
            "on_sale": bool(row.on_sale), "media_count": int(row.media_count or 0),
            "seasonal": row.seasonal, "url": row.url, "detail": dict(row.detail or {}),
        }


def promises_from_listing(row: dict) -> dict:
    """What the listing said a buyer receives, as the small set of checkable claims.

    Absence is `unknown`, never `false`. A listing whose deliverable terms nobody has read is
    not a listing that promised nothing, and auditing delivery against an assumed promise
    manufactures a finding about the seller out of a gap in our own observation.
    """
    detail = row.get("detail") or {}
    deliverable = detail.get("deliverable") if isinstance(detail.get("deliverable"), dict) else {}

    def claim(key: str):
        if key in detail:
            return bool(detail[key])
        if deliverable and key in deliverable:
            return bool(deliverable[key])
        return None

    return {
        "format": (deliverable or {}).get("format"),
        "has_video": claim("has_video"),
        "has_chart": claim("has_chart"),
        "has_print_edition": claim("has_print_edition"),
        "pattern_count": (deliverable or {}).get("pattern_count"),
        "observed_price_cad": round(float(row.get("price_cad") or 0.0), 2),
        "media_count": row.get("media_count"),
        "source": "the observed listing, not the purchase",
    }


# The promise keys that a filename scan can genuinely answer, and the manifest field that
# answers each. Deliberately short: whether the chart is *legible* is an analyst's judgement
# and belongs in `audits.py`, not in a filename.
CHECKABLE: tuple[tuple[str, str], ...] = (
    ("has_video", "has_video"),
    ("has_chart", "has_chart"),
    ("has_print_edition", "has_print_edition"),
)


def deliverable_audit(promises: dict, inferred: dict) -> dict:
    """Promise against delivery, from filenames alone, with the unanswerable named.

    Three verdicts and no fourth: `kept`, `missing`, and `unverifiable` for a claim nobody
    observed or a promise a filename cannot settle. An audit that resolved its unknowns to
    `kept` would report a clean bill of health for a purchase nobody looked at.
    """
    kept, missing, unverifiable = [], [], []
    for promise_key, manifest_key in CHECKABLE:
        promised = (promises or {}).get(promise_key)
        delivered = bool((inferred or {}).get(manifest_key))
        if promised is None:
            unverifiable.append({
                "claim": promise_key, "delivered": delivered,
                "why": "the listing's terms for this were never observed, so there is no "
                       "promise to compare against"})
        elif promised and delivered:
            kept.append({"claim": promise_key})
        elif promised and not delivered:
            missing.append({
                "claim": promise_key,
                "why": "the listing promises it and no delivered filename indicates it. A "
                       "filename is weak evidence of absence; an analyst confirms before "
                       "this becomes a finding about the seller"})
        else:
            kept.append({"claim": promise_key, "note": "not promised, not expected"})

    pdfs = int((inferred or {}).get("pattern_pdfs") or 0)
    if not pdfs:
        missing.append({"claim": "pattern_document",
                        "why": "no delivered file reads as the pattern itself"})

    return {
        "kept": kept, "missing": missing, "unverifiable": unverifiable,
        "verdict": ("unaudited" if not (kept or missing) else
                    "gap" if missing else
                    "consistent"),
        "evidence": "filenames and the observed listing. Never the file contents (#167)",
    }


# ---------------------------------------------------------------------------
# The mirror


def mirror(db, ref: str, files: list[library.IntakeFile], folder: Path,
           *, env: dict[str, str] | None = None) -> dict:
    """Copy each delivered file to the off-provider archive, encrypted.

    These are somebody else's copyrighted files, which is exactly why they go up sealed with
    a key the bucket's credentials do not include and are never served to anybody. What is
    being protected against is this host's disk, which is replaced on every deploy: a
    purchase that exists only there has to be bought again.
    """
    from ..core import offsite
    from ..agents.registry import Registry

    if not offsite.configured(env):
        result = {"mirrored": 0, "durable": False,
                  "why": (f"{offsite.ENDPOINT_VAR} is unset, so these files exist only on a "
                          f"filesystem this host replaces on every deploy")}
        Registry(db).audit("orchestrator", MIRROR_ACTION,
                           detail={"ref": ref, "ok": False, **result})
        return result

    written, failures = [], []
    for entry in files:
        key = f"benchmark/{ref}/{entry.sha256[:16]}{Path(entry.name).suffix.lower()}.blarc"
        try:
            payload = (folder / entry.name).read_bytes()
            put = offsite.put(key, payload, env=env)
            written.append({"name": entry.name, "key": key, "bytes": put["bytes"]})
        except Exception as exc:  # noqa: BLE001 - every failure mode is "not durable"
            failures.append({"name": entry.name, "why": str(exc)[:200]})

    result = {
        "mirrored": len(written), "failed": len(failures), "failures": failures[:10],
        "durable": bool(written) and not failures,
        "keys": [w["key"] for w in written],
        "retention": ("never pruned. `offsite.prune` works from the continuity archive's own "
                      "audit rows, and a purchase is not a snapshot to age out"),
    }
    Registry(db).audit("orchestrator", MIRROR_ACTION,
                       detail={"ref": ref, "ok": result["durable"], **result})
    return result


# ---------------------------------------------------------------------------
# The one call the upload page makes


def receive(db, listing_ref: str, uploads: list[tuple[str, bytes]], *,
            env: dict[str, str] | None = None, paid_cad: float | None = None,
            purchased_on: str | None = None, mirror_files: bool = True) -> dict:
    """Write one purchase into the quarantine and generate everything derivable from it.

    `uploads` is what the form sent: (filename, bytes). Everything else is looked up.
    """
    from ..agents.registry import Registry
    from ..intel import benchmarks

    row = _catalogue_row(db, listing_ref)
    if row is None:
        raise IntakeRefused(
            f"listing {listing_ref!r} is not in the observed MJs catalogue. Intake fills the "
            f"manifest from the catalogue row that justified the purchase; without one there "
            f"is no department, no price, no promise and no recorded reason — which is the "
            f"hand-typed manifest #170 exists to avoid")
    if not uploads:
        raise IntakeRefused("no files were supplied")

    expanded: list[tuple[str, bytes]] = []
    for name, payload in uploads:
        if len(payload) > MAX_FILE_BYTES:
            raise IntakeRefused(
                f"{name!r} is {len(payload):,} bytes, past the {MAX_FILE_BYTES:,} one "
                f"deliverable is expected to be")
        _check_suffix(safe_name(name))
        expanded.extend(expand(name, payload))
    if len(expanded) > MAX_FILES_PER_PURCHASE:
        raise IntakeRefused(
            f"{len(expanded)} files is past the {MAX_FILES_PER_PURCHASE} a purchase is "
            f"expected to contain")

    ref = f"mjs-{str(listing_ref).strip()}"
    root = library.library_root(env)
    folder = (root / ref).resolve()
    if root not in folder.parents:
        raise IntakeRefused(f"{ref!r} does not resolve inside the benchmark library")
    folder.mkdir(parents=True, exist_ok=True)

    replaced = 0
    for name, payload in expanded:
        target_path = (folder / name).resolve()
        if folder not in target_path.parents:
            raise IntakeRefused(f"{name!r} does not resolve inside the purchase folder")
        if target_path.exists():
            replaced += 1
        target_path.write_bytes(payload)

    promises = promises_from_listing(row)
    price = float(paid_cad) if paid_cad is not None else float(row["price_cad"])
    scan = library.scan(folder, ref=ref, seller=benchmarks.MJS_SHOP,
                        listing_ref=str(listing_ref), paid_cad=price)
    why = _why_selected(db, str(listing_ref)) or (
        f"selected into the approved {SET_SIZE}-pattern benchmark set")

    product_id = library.register(
        db, scan, category=row["product_type"] or row["pod"], pod=row["pod"],
        listing_ref=str(listing_ref), paid_cad=price, on_sale=bool(row["on_sale"]),
        why_selected=why, listing_promises=promises,
        purchased_on=purchased_on or date.today().isoformat())

    _set_state(db, ref, AWAITING_ANALYST, title=row["title"])

    audit = deliverable_audit(promises, scan.inferred)
    mirrored = (mirror(db, ref, scan.files, folder, env=env) if mirror_files
                else {"mirrored": 0, "durable": False, "why": "mirroring was not requested"})

    result = {
        "ref": ref, "product_id": product_id, "listing_ref": str(listing_ref),
        "title": row["title"], "department": row["pod"],
        "files": [f.to_dict() for f in scan.files],
        "file_count": len(scan.files), "replaced": replaced,
        "inferred": scan.inferred,
        "paid_cad": round(price, 2),
        "paid_source": ("supplied at upload" if paid_cad is not None
                        else "the observed listing price, not a receipt"),
        "promise_audit": audit,
        "offsite": mirrored,
        "durable": bool(mirrored.get("durable")),
        "needs_owner": [n for n in scan.needs_owner
                        if "listing reference" not in n and "what was paid" not in n
                        and "purchased from" not in n],
        "next": ("nothing. The manifest, the department, the price, the reason and the "
                 "promise audit are all generated; the analyst teardown is queued"),
    }
    Registry(db).audit("orchestrator", INTAKE_ACTION,
                       detail={"ref": ref, "listing_ref": str(listing_ref),
                               "files": len(scan.files), "durable": result["durable"],
                               "verdict": audit["verdict"]})
    return result


def _why_selected(db, listing_ref: str) -> str:
    """The reason the selector recorded for this pick, so nobody retypes it."""
    from ..intel import benchmarks
    from ..intel.purchase_selection import SelectionRefused, select

    try:
        chosen = select(db, benchmarks.MJS_KEY, target=SET_SIZE,
                        budget_cad=SET_BUDGET_CAD).get("selected") or []
    except SelectionRefused:
        return ""
    for pick in chosen:
        if str(pick.get("listing_ref")) == str(listing_ref):
            return str(pick.get("answers") or "")
    return ""


def _set_state(db, ref: str, state: str, *, title: str = "") -> None:
    from sqlalchemy import select as sa_select

    from ..core.models import BenchmarkProduct

    with db.session() as s:
        row = s.scalar(sa_select(BenchmarkProduct).where(BenchmarkProduct.ref == ref))
        if row is not None:
            row.teardown_state = state
            if title and not row.title:
                row.title = title


# ---------------------------------------------------------------------------
# What the phone sees


def plan(db, *, env: dict[str, str] | None = None) -> dict:
    """The approved set, each pick marked with whether its files have arrived.

    This is the upload page's whole content: thirteen rows, tap one, choose files. The
    progress line is computed from the manifest rather than remembered, because a checklist
    somebody ticks by hand is a checklist that disagrees with the library by purchase five.
    """
    from sqlalchemy import select as sa_select

    from ..core.models import BenchmarkProduct
    from ..intel import benchmarks
    from ..intel.purchase_selection import SelectionRefused, select

    try:
        chosen = select(db, benchmarks.MJS_KEY, target=SET_SIZE,
                        budget_cad=SET_BUDGET_CAD)
    except SelectionRefused as exc:
        return {"picks": [], "refused": str(exc)}

    with db.session() as s:
        have = {r.listing_ref: r for r in s.scalars(sa_select(BenchmarkProduct))}

    picks = []
    for pick in chosen.get("selected") or []:
        ref = str(pick.get("listing_ref"))
        row = have.get(ref)
        picks.append({
            "listing_ref": ref,
            "title": pick.get("title"),
            "url": pick.get("url"),
            "price_cad": pick.get("price_cad"),
            "department": pick.get("pod"),
            "answers": pick.get("answers"),
            "received": row is not None and bool(row.files),
            "files": len(row.files or []) if row is not None else 0,
            "state": row.teardown_state if row is not None else "not purchased",
        })

    received = sum(1 for p in picks if p["received"])
    return {
        "picks": picks,
        "set_size": len(picks),
        "received": received,
        "outstanding": [p["listing_ref"] for p in picks if not p["received"]],
        "expected_cost_cad": chosen.get("total_cad"),
        "budget_cad": SET_BUDGET_CAD,
        "durable": offsite_state(db, env=env),
        "how": ("buy on Etsy, open the download, tap the pick here, choose the files. Zips "
                "are opened here; nothing needs renaming, sorting or describing"),
    }


def offsite_state(db, *, env: dict[str, str] | None = None) -> dict:
    from ..core import offsite

    configured = offsite.configured(env)
    return {
        "configured": configured,
        "warning": ("" if configured else
                    "uploads will land on a filesystem this host replaces on every deploy. "
                    "They are worth re-uploading after the archive credential is set"),
    }
