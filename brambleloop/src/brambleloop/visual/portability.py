"""F-747 Brand Asset Portability (W4-AGENTS cluster C2).

"Canonical identity must not depend on one vendor. Preserve provider-neutral references/
specification and sufficient evidence so Brambleloop can migrate to a better model/provider
without losing the established person."

`bundle()` is the provider-neutral migration bundle: the identity id, its owner decisions, the
three canonical reference frames as committed files verified by their bytes
(`visual.canonical.reference_file`), and the locked specification. `restore_check(dest)` copies
the frames out and re-verifies every hash, which is what a migration to another provider
would do first. Nothing here names or calls a provider. Read-only, CA$0.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

VENDOR_WORDS = ("flux", "bfl", "openai", "gpt", "gemini", "nano", "banana", "replicate",
                "fal", "midjourney", "stability", "anthropic", "claude")


def bundle() -> dict:
    from . import canonical

    frames = {}
    for frame, sha in canonical.CURRENT_REFERENCE_HASHES.items():
        path = canonical.reference_file(frame)
        frames[frame] = {"sha256": sha, "committed_file": path or None, "verified": bool(path)}
    spec = {"identity_name": canonical.IDENTITY_NAME, "identity_id": canonical.IDENTITY_ID,
            "revision": canonical.REVISION_NUMBER, "decisions": list(canonical.IDENTITY_DECISIONS),
            "locked": list(canonical.LOCKED), "rule": canonical.IDENTITY_RULE}
    blob = repr(spec).lower()
    vendor = sorted(w for w in VENDOR_WORDS if w in blob)
    return {"spec": spec, "frames": frames,
            "all_frames_committed": all(f["verified"] for f in frames.values()),
            "provider_neutral": not vendor, "vendor_terms_in_spec": vendor}


def restore_check(dest: str | Path) -> dict:
    """Copy each committed frame to `dest` and verify its bytes against the recorded hash."""
    b = bundle()
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    out = {}
    for frame, f in b["frames"].items():
        if not f["committed_file"]:
            out[frame] = False
            continue
        target = dest / Path(f["committed_file"]).name
        shutil.copyfile(f["committed_file"], target)
        out[frame] = hashlib.sha256(target.read_bytes()).hexdigest() == f["sha256"]
    return {"restored": out, "ok": bool(out) and all(out.values())}
