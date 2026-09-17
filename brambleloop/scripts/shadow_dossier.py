"""Run the flagship product through the whole shadow chain and write the evidence down.

`reports/opportunity_pool.md` records which products should exist. This records what the
system actually produced for the top one: the real PDF, the real chart, the price net of
fees, the listing copy, the launch dates and a support transcript. It exists so the owner can
inspect the output rather than take a test count on trust.

    python scripts/shadow_dossier.py [YYYY-MM-DD]
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

REPORTS = ROOT / "reports"
ASSETS = REPORTS / "shadow_release"
ASSETS.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", str(ASSETS / "_store"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.artifacts import ArtifactStore  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, JobStatus  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: F401,E402
from brambleloop.runtime.worker import Worker  # noqa: E402

FLAGSHIP = "nordic-forest-mosaic-throw"


def run(today: date) -> dict:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/dossier.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    JobQueue(db).enqueue("orchestrator", "plan.cycle", {"as_of": today.isoformat()})
    w = Worker(db, "dossier-worker")
    for _ in range(1200):
        if not w.run_once():
            break

    q = JobQueue(db)
    with db.session() as s:
        jobs = list(s.scalars(select(Job)))
        audits = list(s.scalars(select(AuditLog)))
    out = {"db": db, "counts": q.counts(), "jobs": jobs, "audits": audits,
           "dead": q.dead_letters()}

    # A support transcript, from the released version, on the real product.
    support = JobQueue(db).enqueue("support", "support.reply", {
        "slug": FLAGSHIP, "version": "1.0.0",
        "question": "how many stitches should I have at the end of row 12?"})
    Worker(db, "support-worker").run_once()
    out["support"] = JobQueue(db).get(support.id).outputs
    return out


def _of(jobs, job_type: str, slug: str | None = None) -> dict | None:
    for j in jobs:
        if j.job_type == job_type and j.status == JobStatus.DONE and j.outputs:
            if slug is None or j.outputs.get("slug") == slug:
                return j.outputs
    return None


def main() -> int:
    today = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    r = run(today)
    jobs = r["jobs"]
    assets = _of(jobs, "assets.build", FLAGSHIP)
    price = _of(jobs, "pricing.position", FLAGSHIP)
    listing = _of(jobs, "listing.seo", FLAGSHIP)
    plan = _of(jobs, "launch.plan", FLAGSHIP)
    if not all((assets, price, listing, plan)):
        print("the chain did not complete for the flagship", file=sys.stderr)
        return 1

    store = ArtifactStore()
    (ASSETS / "nordic-forest-throw.pdf").write_bytes(store.get(assets["pdf_sha256"]))
    (ASSETS / "nordic-forest-chart.png").write_bytes(store.get(assets["chart_sha256"]))
    (ASSETS / "nordic-forest-legend.png").write_bytes(store.get(assets["legend_sha256"]))

    copy = listing["listing"]
    failed = [j for j in jobs if j.status in (JobStatus.FAILED, JobStatus.DEAD)]
    unexpected = [j for j in failed if j.job_type != "store.publish"]

    L: list[str] = []
    w = L.append
    w("# Shadow release dossier — Nordic Forest Overlay Mosaic Throw")
    w("")
    w(f"_Produced {today.isoformat()} by one unattended `plan.cycle`, from market scan to "
      f"finished assets. Regenerate with `python scripts/shadow_dossier.py`._")
    w("")
    w("Nothing here is published. The store operator refused, by design, because the system "
      "is in Shadow Mode and has no live Etsy connection. What follows is what it produced "
      "up to that refusal.")
    w("")
    w("## The run")
    w("")
    w(f"- Jobs completed: **{r['counts'].get('done', 0)}**")
    w(f"- Refused at the publish gate (expected): **{len(r['dead'])}**")
    w(f"- Unexpected failures: **{len(unexpected)}**")
    w(f"- Audit records written: **{len(r['audits'])}**")
    w("")
    w("## The product")
    w("")
    w(f"- Finished size: **{assets['size_label']}** at the stated gauge")
    w(f"- PDF: **{assets['pages']} pages**, sha256 `{assets['pdf_sha256'][:16]}…`")
    w(f"- Chart: sha256 `{assets['chart_sha256'][:16]}…`")
    w("- Yarn (estimate, ±{}%, uncalibrated):".format(int(assets["tolerance"] * 100)))
    for name, m in sorted(assets["yardage"].items()):
        lo, hi = m * (1 - assets["tolerance"]), m * (1 + assets["tolerance"])
        w(f"  - {name}: about {lo:.0f}–{hi:.0f} m")
    w("")
    w("Files: [`shadow_release/nordic-forest-throw.pdf`](shadow_release/nordic-forest-throw.pdf) · "
      "[`chart`](shadow_release/nordic-forest-chart.png) · "
      "[`legend`](shadow_release/nordic-forest-legend.png)")
    w("")
    w("## Price")
    w("")
    w(f"- List price: **CA${price['price_cad']:.2f}** (observed band "
      f"CA${price['floor_cad']:.2f}–{price['ceiling_cad']:.2f})")
    w(f"- Net after Etsy fees: **CA${price['net_cad']:.2f}** "
      f"(platform take {price['take_rate'] * 100:.1f}%)")
    for reason in price["reasons"]:
        w(f"- {reason}")
    for warn in price["warnings"]:
        w(f"- ⚠ {warn}")
    w("")
    w("No struck-through reference price. The category runs a near-universal permanent "
      "'50% off' against a price that is never charged; section 9 forbids it and the pricing "
      "code refuses to emit one.")
    w("")
    w("## Listing")
    w("")
    w(f"**Title** ({len(copy['title'])}/140)")
    w("")
    w(f"> {copy['title']}")
    w("")
    w(f"**Tags** ({len(copy['tags'])}/13)")
    w("")
    w("> " + " · ".join(f"`{t}`" for t in copy["tags"]))
    w("")
    w("**Description**")
    w("")
    w("```")
    w(copy["description"])
    w("```")
    w("")
    w("## Launch plan")
    w("")
    w(f"Buying window **{plan['window_opens']} → {plan['window_closes']}**, launch "
      f"**{plan['launch_on']}**.")
    w("")
    for warn in plan["warnings"]:
        w(f"> {warn}")
    w("")
    w("| Stage | Date | Must be true by then | |")
    w("|---|---|---|---|")
    for step in plan["steps"]:
        w(f"| {step['stage']} | {step['on']} | {step['requirement']} | "
          f"{'compressed' if step['late'] else ''} |")
    w("")
    w("## Support, answered from the released version")
    w("")
    sup = r["support"]
    w(f"> **Customer:** {sup['question']}")
    w(">")
    w(f"> **Brambleloop:** {sup['answer']}")
    w("")
    w(f"Cited version: `{sup['cited_version']}`, rows {sup['cited_rows']}. Support answers "
      f"from the exact version the customer bought and has no method that can change it; a "
      f"real defect becomes an incident and the pattern is fixed at source.")
    w("")
    (REPORTS / "shadow_release_nordic_forest.md").write_text("\n".join(L) + "\n")
    print(f"wrote reports/shadow_release_nordic_forest.md ({len(L)} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
