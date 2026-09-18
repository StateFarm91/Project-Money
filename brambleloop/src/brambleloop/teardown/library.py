"""The benchmark library: purchased competitor products, quarantined by construction.

Requirements 148, 149, 150, 167, 170. The owner will buy about ten representative patterns so
this company can study what a customer actually receives after paying. That is legitimate,
valuable and ordinary — and it puts a folder of somebody else's copyrighted instructions on
the same disk as a system that writes crochet patterns.

So the boundary is built before the files arrive, because a boundary added afterwards is one
that was absent exactly when it mattered:

**The library is a quarantine, not a corpus.** `retrieve()` is the only reader, it refuses a
path outside the library root, and it refuses every caller that is not an analyst. Pattern
generation, listing copy, customer support and marketing cannot reach it — not by policy, by
`PermissionError`.

**Nothing from a benchmark is ever stored as content.** The manifest holds filenames, sizes
and hashes. Findings hold mechanisms and scores. No table in this system has a column for a
competitor's instructions, and `record_finding()` refuses text that reads like one.

**The manifest is generated, not requested.** #170: when the owner drops files in, the system
works out what it can from filenames and listing references and asks only about what it
genuinely cannot infer. Making somebody describe forty files by hand is how ten purchases
become a task nobody finishes.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# Outside the repository tree on purpose, and in `.gitignore` as belt and braces. An ignore
# rule only stops the accident it happens to match; this path is also checked in code.
LIBRARY_ENV = "BRAMBLELOOP_BENCHMARK_LIBRARY"
DEFAULT_LIBRARY = "benchmark_library"

# Who may open a benchmark file. Deliberately short, and deliberately not "orchestrator":
# the analyst role exists so that reaching into the library is a visible, separate act.
ANALYST_ROLES: frozenset[str] = frozenset({"teardown_analyst", "quality_director"})

# Roles that must never reach it, listed explicitly so the refusal names the reason rather
# than reporting a generic permission error.
FORBIDDEN_ROLES: dict[str, str] = {
    "crochet_engineer": "pattern authoring must never read a competitor's instructions",
    "validator": "validation reads the CIR, never somebody else's pattern",
    "listing": "listing copy must not be written beside a competitor's words",
    "support": "customer answers come from our own pattern version, never a benchmark",
    "growth": "marketing must not quote a purchased product",
    "publishing": "rendered assets are built from the certified CIR alone",
}


class LibraryRefused(Exception):
    """An attempt to read the library from somewhere it must not be read."""


class ContentRefused(Exception):
    """An attempt to store a competitor's expression rather than an observation about it."""


def library_root(env: dict[str, str] | None = None) -> Path:
    e = env if env is not None else os.environ
    return Path(e.get(LIBRARY_ENV) or DEFAULT_LIBRARY).resolve()


def retrieve(relative_path: str, role: str, env: dict[str, str] | None = None) -> bytes:
    """Open one benchmark file. The only reader, and it argues with you first."""
    reason = FORBIDDEN_ROLES.get(role)
    if reason:
        raise LibraryRefused(f"{role!r} may not read the benchmark library: {reason}")
    if role not in ANALYST_ROLES:
        raise LibraryRefused(
            f"{role!r} is not an analyst role. Reading a purchased competitor product is a "
            f"separate, visible act; add the role to ANALYST_ROLES deliberately or use "
            f"the manifest, which carries everything derived from these files")

    root = library_root(env)
    target = (root / relative_path).resolve()
    if root not in target.parents and target != root:
        # `../../src/brambleloop` is the interesting case, not a typo.
        raise LibraryRefused(
            f"{relative_path!r} resolves outside the benchmark library. The library is a "
            f"quarantine; a reader that can walk out of it is not one")
    if not target.is_file():
        raise LibraryRefused(f"no such benchmark file: {relative_path!r}")
    return target.read_bytes()


# ---------------------------------------------------------------------------
# Intake (#170)

# Patterns that identify a file's role from its name, which is most of what the owner would
# otherwise have to type. Ordered: the first match wins.
_FILE_ROLES: tuple[tuple[str, str], ...] = (
    (r"chart|graph|grid|symbol", "chart"),
    (r"video|tutorial|\.mp4$|\.mov$", "video"),
    (r"print|printable|bw|black.?white", "print_edition"),
    (r"bonus|extra|supplement", "bonus"),
    (r"photo|image|\.jpe?g$|\.png$", "photo"),
    (r"\.pdf$", "pattern_pdf"),
    (r"\.txt$|\.md$|\.docx?$", "text"),
)

_SELLER_FROM_NAME = re.compile(r"^([A-Za-z0-9]+?)[-_ ]")


def classify_file(name: str) -> str:
    low = name.lower()
    for pattern, role in _FILE_ROLES:
        if re.search(pattern, low):
            return role
    return "unclassified"


@dataclass(frozen=True)
class IntakeFile:
    name: str
    role: str
    bytes: int
    sha256: str

    def to_dict(self) -> dict:
        return {"name": self.name, "role": self.role, "bytes": self.bytes,
                "sha256": self.sha256}


@dataclass
class IntakeResult:
    """What the system worked out, and the short list of what it genuinely cannot."""

    ref: str
    seller: str
    files: list[IntakeFile] = field(default_factory=list)
    inferred: dict = field(default_factory=dict)
    needs_owner: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"ref": self.ref, "seller": self.seller,
                "files": [f.to_dict() for f in self.files],
                "inferred": self.inferred, "needs_owner": list(self.needs_owner)}


def scan(folder: Path | str, *, ref: str = "", seller: str = "",
         listing_ref: str = "", paid_cad: float | None = None) -> IntakeResult:
    """Read a purchase folder's *filenames* and work out everything inferable.

    Deliberately never opens a file: intake produces a manifest, and a manifest that had to
    parse a competitor's PDF to exist would be reading the thing this module exists to keep
    unread. Sizes and hashes come from the filesystem.
    """
    folder = Path(folder)
    if not folder.is_dir():
        raise LibraryRefused(f"{folder} is not a purchase folder")

    ref = ref or folder.name
    if not seller:
        m = _SELLER_FROM_NAME.match(folder.name)
        seller = m.group(1) if m else ""

    files: list[IntakeFile] = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files.append(IntakeFile(name=str(path.relative_to(folder)),
                                role=classify_file(path.name),
                                bytes=path.stat().st_size, sha256=digest))

    roles = {f.role for f in files}
    inferred = {
        "file_count": len(files),
        "has_chart": "chart" in roles,
        "has_video": "video" in roles,
        "has_print_edition": "print_edition" in roles,
        "has_bonus": "bonus" in roles,
        "pattern_pdfs": sum(1 for f in files if f.role == "pattern_pdf"),
        "unclassified": sorted(f.name for f in files if f.role == "unclassified"),
    }

    needs: list[str] = []
    if not seller:
        needs.append("which shop this was purchased from")
    if not listing_ref:
        needs.append("the Etsy listing reference, so the promise-to-delivery audit has "
                     "something to compare against")
    if paid_cad is None:
        needs.append("what was paid, and whether it was on sale")
    if not files:
        needs.append("the files themselves — this folder is empty")
    return IntakeResult(ref=ref, seller=seller, files=files, inferred=inferred,
                        needs_owner=needs)


def register(db, result: IntakeResult, *, category: str = "", pod: str = "",
             listing_ref: str = "", paid_cad: float = 0.0, on_sale: bool = False,
             why_selected: str = "", listing_promises: dict | None = None,
             purchased_on: str | None = None) -> int:
    """Write the manifest entry. Filenames and hashes only — never contents."""
    from sqlalchemy import select

    from ..core.models import BenchmarkProduct

    with db.session() as s:
        row = s.scalar(select(BenchmarkProduct).where(BenchmarkProduct.ref == result.ref))
        if row is None:
            row = BenchmarkProduct(ref=result.ref)
            s.add(row)
        row.seller = result.seller or row.seller
        row.category = category or row.category
        row.pod = pod or row.pod
        row.listing_ref = listing_ref or row.listing_ref
        row.paid_cad = paid_cad or row.paid_cad
        row.on_sale = on_sale
        row.why_selected = why_selected or row.why_selected
        row.listing_promises = dict(listing_promises or row.listing_promises or {})
        row.files = [f.to_dict() for f in result.files]
        row.purchased_on = purchased_on or row.purchased_on or date.today().isoformat()
        s.flush()
        return row.id


def manifest_markdown(db) -> str:
    """BENCHMARK_MANIFEST.md (#170), generated rather than maintained by hand."""
    from sqlalchemy import select

    from ..core.models import BenchmarkProduct

    with db.session() as s:
        rows = list(s.scalars(select(BenchmarkProduct).order_by(BenchmarkProduct.ref)))

    lines = [
        "# Benchmark library manifest",
        "",
        "Purchased competitor products, held for post-purchase customer-experience study.",
        "",
        "**These files are somebody else's copyrighted work.** They are never committed to "
        "this repository, never served to a customer, never quoted in a listing or a support "
        "reply, and never reachable by pattern generation. What this company keeps from them "
        "is the observations below: mechanisms and scores, never instructions or charts.",
        "",
    ]
    if not rows:
        lines += ["_No benchmark products have been purchased yet._", ""]
        return "\n".join(lines)

    lines += ["| ref | seller | category | purchased | paid CAD | files | state |",
              "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r.ref} | {r.seller} | {r.category or '—'} | {r.purchased_on} | "
                     f"{r.paid_cad:.2f} | {len(r.files or [])} | {r.teardown_state} |")
    lines.append("")
    for r in rows:
        lines += [f"## {r.ref}", ""]
        if r.why_selected:
            lines += [f"Selected because: {r.why_selected}", ""]
        lines += ["| file | role | bytes |", "|---|---|---|"]
        for f in (r.files or []):
            lines.append(f"| `{f['name']}` | {f['role']} | {f['bytes']:,} |")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The content boundary (#167)
#
# Same idea as the mechanism vocabulary in `intel/pods.py`, and the same reason: the rule has
# to be mechanical, because the moment somebody is mid-teardown with a genuinely useful
# paragraph in front of them is exactly when "store the abstraction, not the text" loses.

_LOOKS_LIKE_INSTRUCTIONS = (
    "row 1", "row 2", "rnd 1", "round 1", "ch 3", "ch. 3", "sc in each", "dc in each",
    "hdc in", "sl st in", "rep from", "repeat from *", "turn. ch",
)

_LOOKS_LIKE_TRANSCRIPTION = (
    "verbatim", "transcribed", "copied from", "their exact wording", "quote from the pdf",
    "excerpt:", "as written in",
)


def check_derived(text: str) -> None:
    """Refuse an observation that is really the competitor's product in a text field."""
    low = (text or "").lower()
    for phrase in _LOOKS_LIKE_INSTRUCTIONS:
        if phrase in low:
            raise ContentRefused(
                f"{phrase!r} reads as a competitor's instructions. Teardown findings record "
                f"mechanisms -- what makes instructions easy or hard to follow -- never the "
                f"instructions themselves (#167)")
    for phrase in _LOOKS_LIKE_TRANSCRIPTION:
        if phrase in low:
            raise ContentRefused(
                f"{phrase!r} describes reproducing the source rather than observing it")
