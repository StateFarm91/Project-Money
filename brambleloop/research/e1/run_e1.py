"""E1: can a reference-capable provider turn a deterministic structural reference into a more
photoreal presentation WITHOUT changing the product?

Three arms, one prompt that names NO structure the reference carries (no stripe count, no
positions, no stitch family), so that anything the output gets right about those came from
the reference or from nowhere:

  A  reference + prompt, flux-2-pro   x3
  B  prompt only (control), flux-2-pro x2   -- what the prompt alone produces
  C  reference + prompt, gpt-image-2  x2   -- a second provider

Hard spend cap US$0.25. Every call's list price is recorded; the provider's own bill is the
authority and this file says so.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))
from brambleloop.gateway import images as G                              # noqa: E402

SCRATCH = Path("/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad")
CAP_USD = 0.25

PROMPT_REF = (
    "Product photograph for a handmade craft marketplace listing of the crocheted basket shown "
    "in the reference image. Keep the basket exactly as shown: the same shape, the same "
    "proportions, the same colours and where those colours sit. Render it as a real object in "
    "real yarn: natural fibre texture, soft window daylight, on a light wooden shelf. No text, "
    "nothing placed inside it, nothing else in frame.")
PROMPT_CONTROL = (
    "Product photograph for a handmade craft marketplace listing of a cream crocheted storage "
    "basket. Real yarn, natural fibre texture, soft window daylight, on a light wooden shelf. "
    "No text, nothing placed inside it, nothing else in frame.")

ARMS = [("A", "flux-2-pro", True, 3), ("B", "flux-2-pro", False, 2), ("C", "gpt-image-2", True, 2)]


def env_from_files() -> dict[str, str]:
    env: dict[str, str] = {}
    for account, fname in (("bfl", ".bflkey"), ("openai", ".oaikey"), ("google", ".gkey")):
        p = SCRATCH / fname
        if p.is_file():
            env[G.key_var(account)] = p.read_text().strip()
    return env


def main() -> None:
    ref = HERE / "out" / "basket_large_structural.png"
    assert ref.is_file(), ref
    out = HERE / "out" / "gen"
    out.mkdir(parents=True, exist_ok=True)
    env = env_from_files()
    planned = sum(G.BY_KEY[p].usd_per_image * n for _, p, _, n in ARMS)
    assert planned <= CAP_USD, f"planned US${planned:.2f} exceeds cap US${CAP_USD}"
    manifest = {"reference": str(ref), "planned_usd_list_price": round(planned, 3),
                "prompt_reference_arms": PROMPT_REF, "prompt_control_arm": PROMPT_CONTROL,
                "runs": []}
    spent = 0.0
    for arm, provider, with_ref, n in ARMS:
        for i in range(n):
            row = {"arm": arm, "provider": provider, "with_reference": with_ref, "index": i}
            t0 = time.time()
            try:
                r = G.generate(PROMPT_REF if with_ref else PROMPT_CONTROL,
                               reference_urls=[str(ref)] if with_ref else None,
                               env=env, provider_key=provider, work_dir=str(out), size="1024x1024",
                               timeout=180.0)
                src = Path(r["path"])
                dst = out / f"{arm}{i}_{provider}{src.suffix}"
                src.replace(dst)
                row.update(ok=True, path=str(dst), seconds=round(time.time() - t0, 1),
                           usd_list_price=G.BY_KEY[provider].usd_per_image)
                spent += G.BY_KEY[provider].usd_per_image
            except Exception as exc:  # noqa: BLE001 -- recorded, not hidden
                row.update(ok=False, error=f"{type(exc).__name__}: {str(exc)[:220]}",
                           seconds=round(time.time() - t0, 1))
            manifest["runs"].append(row)
            print(json.dumps({k: row[k] for k in row if k != "path"} | {"file": Path(row.get("path", "")).name}))
    manifest["spent_usd_list_price"] = round(spent, 3)
    (HERE / "out" / "e1_manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"\nspent (list price) US${spent:.2f} of cap US${CAP_USD}")


if __name__ == "__main__":
    main()
