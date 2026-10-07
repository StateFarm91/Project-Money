"""W4-CREATIVE2 runtime proof: catalogue creative audit on a scratch DB, before vs after.

Usage: cd brambleloop && PYTHONPATH=src python research/final_build/w4/creative_gate_r3_proof.py research/final_build/w4/creative_gate_r3.json
"before" is the parent commit's design process (5 HELD, their briefs absent),
re-measured live here by restoring that state in-process; "after" is this commit.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from types import SimpleNamespace

from brambleloop.app import dashboard_truth
from brambleloop.core.db import Database
from brambleloop.creative import audit
from brambleloop.creative import emotional_brief as EB
from brambleloop.products.builder import CATALOGUE

FORMERLY_HELD = ("winter-village-graphghan", "autumn-oak-mosaic-throw", "nordic-star-ornaments",
                 "pressed-flower-motifs", "cottage-wall-hanging")


def reading(label: str) -> dict:
    tmp = tempfile.mkdtemp(prefix="cg3-")
    db = Database(f"sqlite:///{tmp}/scratch.db", scratch=True)
    db.create_all()
    kept = audit.persist_catalogue_audit(db)
    s = dashboard_truth.creative_survivors(db)
    report = audit.audit_catalogue()
    db.engine.dispose()
    for f in os.listdir(tmp):
        os.remove(os.path.join(tmp, f))
    os.rmdir(tmp)
    return {
        "label": label,
        "audited": report["products_audited"],
        "survived": len(report["survivors"]),
        "survivors": sorted(report["survivors"]),
        "survivor_decisions": sorted(set(report["decisions"][k] for k in report["survivors"])),
        "deaths": report["autopsy"].get("deaths_by_critic") or {},
        "held": report["briefs"]["held"],
        "cadence_persist_catalogue_audit": {
            "deaths": kept["autopsy"].get("deaths_by_critic") or {},
            "lesson_kept": kept["lesson"].get("lesson") is not None,
            "lesson_why": kept["lesson"].get("why"),
        },
        "dashboard_truth.creative_survivors": {"count": s["count"], "audited": s["audited"]},
        "raw_generator": {"survived": len(report["raw_generator"]["survivors"]),
                          "deaths": report["raw_generator"]["autopsy"]["deaths_by_critic"]},
    }


def main() -> None:
    out_path = sys.argv[1]
    # BEFORE: the parent commit's design process -- these five briefs absent, HELD populated.
    saved_briefs = {k: EB.CATALOGUE_BRIEFS.pop(k) for k in FORMERLY_HELD}
    for k in FORMERLY_HELD:
        EB.HELD[k] = {"conflict": "r2 hold (parent commit)", "proposed_title": CATALOGUE[k].title}
    before = reading("before (parent commit 3219a13: 5 HELD, no briefs)")
    EB.HELD.clear()
    EB.CATALOGUE_BRIEFS.update(saved_briefs)
    after = reading("after (W4-CREATIVE2: HELD empty, 5 briefs validated)")
    per = {}
    for k in FORMERLY_HELD:
        d = CATALOGUE[k]
        b = EB.CATALOGUE_BRIEFS[k]
        per[k] = {"released_title": d.title, "motif": d.motif,
                  "title_conflicts": EB.title_conflicts(d.title, d.motif),
                  "validate_problems": EB.validate(b, motif=d.motif, title=d.title,
                                                   declared=EB.declared_by_slug(k)),
                  "recipient": b.recipient, "occasion": b.occasion, "feeling": b.feeling,
                  "decision_after": audit.audit_catalogue()["decisions"][k]}
    cat, _ = audit.briefed_catalogue_concepts()
    cands = EB.audit_candidates(cat)
    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "phase": "shadow",
        "producer": "W4-CREATIVE2 (research/final_build/w4/handoff_CREATIVE2.md)",
        "what": ("catalogue creative audit (cadence persist_catalogue_audit + "
                 "dashboard_truth.creative_survivors) on a scratch SQLite DB, before/after "
                 "releasing the 5 Product-Truth holds whose titles W4-PIPE/PIPE3 made truthful"),
        "catalogue": {"before": before, "after": after},
        "formerly_held": per,
        "stale_holds": EB.stale_holds(),
        "new_candidates_vs_briefed_catalogue": {
            "proposed": cands["proposed"], "survivors": len(cands["survivors"]),
            "refused_at_brief": cands["refused_at_brief"]},
        "not_claimed": ("needs_taste is not approval: thumbnail legibility and craft "
                        "impression still need a recorded vision judgement "
                        "(emotional_brief.NEEDS_TASTE_CLEARS); no listing, sale or buyer is "
                        "implied by any brief"),
    }
    with open(out_path, "w") as fh:
        json.dump(payload, fh, indent=1, sort_keys=False)
        fh.write("\n")
    print(json.dumps({"before": before["survived"], "after": after["survived"],
                      "before_deaths": before["deaths"], "after_deaths": after["deaths"],
                      "dash_before": before["dashboard_truth.creative_survivors"],
                      "dash_after": after["dashboard_truth.creative_survivors"]}))


if __name__ == "__main__":
    main()
