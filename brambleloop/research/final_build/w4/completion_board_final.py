"""W4-BOARD: the one finish-line board for Build 2 (320) and the Final Master (917; 490
launch-critical), generated -- never typed -- from the canonical ledgers and production.

Inputs (all read-only):
  * research/final_build/w4/BUILD2_LEDGER.json  -- build2.closure.ledger (build2_ledger.py),
    regenerated with the production gate readings below;
  * research/final_build/closure_matrix.json    -- aggregate.py adjudication of all 917 rows;
  * research/final_build/w4/OWNER_ACTIONS.json  -- the owner's exact actions, keyed by gate;
  * production GETs saved under w4/evidence_BOARD/ (/health, /api/status, /api/verify,
    /api/build, /api/build2, /api/queue/dead) -- which commit runs and which gates are open;
  * git: which modules are in the deployed tree (0417f35) and unchanged on this branch, and which
    unmerged worker branches (claude/w4-*) name a row in a commit message.

Every row lands in exactly one class:
  verified_complete      the ledger proves it AND every module it names is in the deployed
                         production tree, unchanged since (production runs that commit)
  implemented_unverified the ledger proves it, or its code is written, but the code differs
                         from or is absent in production (release not deployed / no evidence)
  in_progress            unfinished, and an active unmerged worker branch names it
  blocked_engineering    unfinished, and the next step is company engineering (incl. a gate
                         production now reports OPEN: the work is unparked)
  blocked_owner          unfinished, parked on an owner gate (exact action attached)
  blocked_external       unfinished, parked on an outside party or provider (named)
NOT-APPLICABLE rows (process directives) are counted separately, never as complete.
No row is closed here: the class of a finished row comes from the ledgers' own acceptance
evidence; this script only reads it.

  cd brambleloop && python3 research/final_build/w4/completion_board_final.py
"""
from __future__ import annotations

import json
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
FB = HERE.parent
BL = FB.parents[1]
REPO = BL.parent
EV = HERE / "evidence_BOARD"
OUT_JSON = HERE / "COMPLETION_BOARD_FINAL.json"
OUT_MD = HERE / "COMPLETION_BOARD_FINAL.md"
OUT_CARD = HERE / "COMPLETION_BOARD_FINAL_CARD.json"
CLASSES = ("verified_complete", "implemented_unverified", "in_progress", "blocked_engineering",
           "blocked_owner", "blocked_external")
ACTIVE_BRANCH_HOURS = 24

# Root causes: gate key -> (root cause id, class when the gate is closed, who/what blocks).
ROOT = {
    "etsy_api": ("etsy_credential_403", "blocked_owner", "owner: Etsy API credential"),
    "etsy_shop": ("etsy_credential_403", "blocked_owner", "owner: Etsy API credential"),
    "transactions_r": ("oauth_transactions_r", "blocked_owner", "owner: Etsy OAuth scope"),
    "model_provider": ("model_credits", "blocked_owner", "owner: model provider credit"),
    "model_provider_fallback": ("model_credits", "blocked_owner", "owner: model provider credit"),
    "image_vision": ("model_credits", "blocked_owner", "owner: model provider credit"),
    "insights_access": ("insights_paste", "blocked_owner", "owner: Marketplace Insights paste"),
    "stats_export": ("insights_paste", "blocked_owner", "owner: Etsy Stats export"),
    "live_listings": ("live_listings", "blocked_owner", "owner: go-live / publication grant"),
    "publication_authority": ("live_listings", "blocked_owner", "owner: publication grant"),
    "customers": ("real_customers", "blocked_external", "external: real buyers"),
    "listing_traffic": ("real_customers", "blocked_external", "external: real buyers/traffic"),
    "seasonal_orders": ("real_customers", "blocked_external", "external: real buyers"),
    "market_outcomes": ("real_customers", "blocked_external", "external: market outcomes"),
    "concept_outcomes": ("real_customers", "blocked_external", "external: market outcomes"),
    "style_outcomes": ("real_customers", "blocked_external", "external: market outcomes"),
    "learning_sources": ("data_accrual", "blocked_external",
                         "external: data accrues with operating time"),
    "lead_lag_series": ("data_accrual", "blocked_external",
                        "external: data accrues with operating time"),
    "season_harvest": ("data_accrual", "blocked_external",
                       "external: a season has to pass"),
    "etsy_ads": ("real_customers", "blocked_external", "external: Etsy Ads data"),
    "production_window": ("release_not_deployed", "blocked_engineering",
                          "engineering: deploy successor + 24h unattended window"),
    "hosted_operating_history": ("release_not_deployed", "blocked_engineering",
                                 "engineering: deployed release + hosted history"),
    # Tracked requirement outside the FM/Build 2 ledgers (PRIVATE_LAURA_TRACE G-12).
    "laura_private_register": ("private_laura_owner_gates", "blocked_owner",
                               "owner: OA-PL-1/2/4 (private key, D-W4-PL-1 acknowledgement, "
                               "spend authorisation + register switch; no consent "
                               "prerequisite, D-W4-PL-3), then the class-B production soak"),
    "model_bearing_render": ("image_provider_capability", "blocked_external",
                             "external: image provider capability"),
    "visual_v1_provider_capability": ("image_provider_capability", "blocked_external",
                                      "external: image provider capability"),
    "image_vision@external": ("image_provider_capability", "blocked_external",
                              "external: vision provider capability"),
    "rendered_pages": ("etsy_no_api_or_403", "blocked_external",
                       "external: Etsy pages 403 to automation / no API"),
    "etsy_policy_pages_403": ("etsy_no_api_or_403", "blocked_external", "external: Etsy 403"),
    "no_messages_api": ("etsy_no_api_or_403", "blocked_external", "external: Etsy has no API"),
    "no_dashboard_api": ("etsy_no_api_or_403", "blocked_external", "external: Etsy has no API"),
    "no_search_visibility_api": ("etsy_no_api_or_403", "blocked_external",
                                 "external: Etsy has no API"),
    "customer_service_stats": ("etsy_no_api_or_403", "blocked_external",
                               "external: Etsy has no API"),
    "advertising_rules": ("etsy_no_api_or_403", "blocked_external", "external: Etsy 403"),
    "session_environment_signing": ("session_environment", "blocked_external",
                                    "external: session environment signing"),
    "ad_authority": ("paid_media_authority", "blocked_owner", "owner: ad budget authority"),
    "benchmark_purchases": ("benchmark_purchases", "blocked_owner", "owner: buy benchmark set"),
    "owned_surfaces": ("owned_surfaces", "blocked_owner", "owner: open owned channels"),
    "tester_roster": ("testers_physical_proof", "blocked_owner", "owner: testers / sample"),
    "physical_proof": ("testers_physical_proof", "blocked_owner", "owner: testers / sample"),
    "offsite_storage": ("offsite_storage", "blocked_owner", "owner: offsite bucket"),
    "acceptance_ruling": ("owner_rulings", "blocked_owner", "owner: ruling"),
    "visual_paid_generation": ("visual_paid_generation", "blocked_owner",
                               "owner: paid image calls"),
    "live_restart_drill": ("owner_rulings", "blocked_owner", "owner: authorise a live drill"),
    "bank_and_payment_ledger_feed": ("banking_feeds", "blocked_owner", "owner: banking export"),
    "monthly_statement": ("banking_feeds", "blocked_owner", "owner: banking export"),
    "payout": ("etsy_shop_settings", "blocked_owner", "owner: Etsy shop settings"),
    "provider_usage_api": ("provider_admin_keys", "blocked_owner", "owner: provider admin keys"),
}
ETSY_SETTINGS = {"etsy_plus_subscription", "etsy_plus_status", "share_and_save_enrolment",
                 "apps_confirmation", "shared_access_confirmation", "info_and_appearance",
                 "policy_settings", "store_preview_v2_review", "etsy_ai_partner_guidance"}
ROOT_TITLES = {
    "etsy_credential_403": "Etsy API credential refused (HTTP 403)",
    "oauth_transactions_r": "Etsy OAuth missing transactions_r",
    "model_credits": "Model / vision provider credit",
    "insights_paste": "Marketplace Insights / Stats paste",
    "launch0_cap_CAP1": "Launch-0 catalogue cap (CAP-1)",
    "live_listings": "No live listings (go-live not authorised)",
    "real_customers": "No real customers / market outcomes yet",
    "release_not_deployed": "Release not deployed (successor + 24h window)",
    "image_provider_capability": "Image/vision provider capability",
    "etsy_no_api_or_403": "Etsy surface has no API or is 403 to automation",
    "paid_media_authority": "Paid-media authority",
    "benchmark_purchases": "Benchmark purchases",
    "owned_surfaces": "Owned channels (site / Pinterest)",
    "testers_physical_proof": "Testers and physical samples",
    "offsite_storage": "Offsite storage bucket",
    "owner_rulings": "Owner rulings",
    "visual_paid_generation": "Paid image generation approval",
    "banking_feeds": "Banking / payment-ledger feeds",
    "etsy_shop_settings": "Etsy Shop Manager settings",
    "provider_admin_keys": "Provider admin usage keys",
    "owner_other": "Other owner decisions (credential rotation, tax, CASL, spend numbers, "
                   "deploy settings)",
    "data_accrual": "Data that only accrues with time / seasons",
    "session_environment": "Session environment",
    "gate_open_reverify": "Gate now OPEN in production: unparked, re-verify",
    "audit_criterion_not_demonstrated": "Spot audit: the evidence does not demonstrate the "
                                        "criterion (BOARD_AUDIT.json)",
    "private_laura_owner_gates": "Private Laura register: owner gates, then production soak",
    "engineering_open": "Open engineering work",
    "release_undeployed_code": "Proven only on the integration branch (release + production "
                               "evidence needed)",
}
ETSY_CRED_ACTION = ("Fix the Etsy API credential so etsy.probe succeeds: production gets HTTP 403 "
                    "('Etsy v3 requires x-api-key as keystring:shared_secret; check "
                    "ETSY_SHARED_SECRET'); then use the Command Center Etsy re-check")


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True,
                          text=True).stdout


def _latest(pattern: str) -> Path:
    return sorted(EV.glob(pattern))[-1]


def _prod() -> dict:
    health = json.loads(_latest("prod_health_*.json").read_text())
    build = json.loads(_latest("prod_api_build_*.json").read_text())
    verify = json.loads(_latest("prod_api_verify_2*.json").read_text())
    status = json.loads(_latest("prod_api_status_*.json").read_text())
    dead = json.loads(_latest("prod_api_queue_dead_*.json").read_text())
    read_at = _latest("prod_health_*.json").stem.rsplit("_", 1)[-1]
    return {"commit": health["build"]["commit"], "known": health["build"].get("known"),
            "read_at": read_at, "gates": {k: bool(v.get("open")) for k, v in
                                          (build.get("gates") or {}).items()},
            "final_master": build.get("final_master"),
            "off_device_proof": {k: (build.get("off_device_proof") or {}).get(k)
                                 for k in ("window_hours", "passed", "unmet")},
            "verify_ok": verify.get("ok"),
            "verify_failing": [c["check"] for c in verify.get("checks", []) if not c["ok"]],
            "boot_guard": {k: (status.get("boot_guard") or {}).get(k)
                           for k in ("enforced", "ok")},
            "dead_letter_groups": [{k: g.get(k) for k in ("job_type", "count", "last_seen")}
                                   for g in dead.get("groups", [])]}


def _deployed_index(prod_commit: str) -> tuple[set, set]:
    in_prod = set(_git("ls-tree", "-r", "--name-only", prod_commit, "--",
                       "brambleloop/src/brambleloop").split())
    # against the working tree, not HEAD: an uncommitted edit is no more deployed than a
    # committed one
    changed = set(_git("diff", "--name-only", prod_commit, "--",
                       "brambleloop/src/brambleloop").split())
    return in_prod, changed


def _active_branches() -> dict[str, dict]:
    """Unmerged claude/w4-* branches with a commit in the last ACTIVE_BRANCH_HOURS: the rows
    their commit messages name."""
    out = {}
    now = datetime.now(timezone.utc)
    for ref in _git("for-each-ref", "--format=%(refname:short)",
                    "refs/remotes/origin/claude/").split():
        if "/w4-" not in ref or ref.endswith(("w4-INTEG2", "w4-BOARD")):
            continue
        # --cherry-pick: a commit already integrated by cherry-pick is not outstanding work
        ahead = _git("rev-list", "--count", "--right-only", "--cherry-pick",
                     f"HEAD...{ref}").strip()
        if not ahead or int(ahead) == 0:
            continue
        when = _git("log", "-1", "--format=%cI", ref).strip()
        try:
            ts = datetime.fromisoformat(when)
        except ValueError:
            continue
        if now - ts > timedelta(hours=ACTIVE_BRANCH_HOURS):
            continue
        msgs = _git("log", "--format=%B", "--right-only", "--cherry-pick", f"HEAD...{ref}")
        fm = set(re.findall(r"\bF-\d{3}(?:@v[\d.]+)?\b", msgs))
        b2 = {int(n) for n in re.findall(r"(?:Build 2|B2)[^\n#]{0,40}#(\d{1,3})\b", msgs)}
        out[ref.replace("origin/", "")] = {"head": _git("rev-parse", "--short", ref).strip(),
                                           "last_commit": when, "commits_ahead": int(ahead),
                                           "fm": sorted(fm), "b2": sorted(b2)}
    return out


def _owner_actions() -> dict[str, dict]:
    oa = json.loads((HERE / "OWNER_ACTIONS.json").read_text())
    by_gate = {}
    for b in oa.get("batches", []):
        for it in b.get("items", []):
            for g in it.get("gates") or []:
                by_gate.setdefault(g, {"id": it["id"], "batch": b["id"],
                                       "action": it["decision"],
                                       "max_cost_cad": it.get("max_cost_cad"),
                                       "minutes": it.get("minutes")})
    return by_gate


def _modules_fm(row) -> list[str]:
    text = " ".join(str(row.get(k) or "") for k in ("producer",))
    mods = re.findall(r"(?:src/brambleloop/)?((?:[a-z_0-9]+/)+[a-z_0-9]+\.py)", text)
    # runtime modules only: repo-root operator tooling (ops/deploy_guard.py, scripts/) never
    # ships, so it can neither be deployed nor evidenced by production
    return sorted({m for m in mods if (BL / "src" / "brambleloop" / m).exists()})


def _deploy_state(mods, in_prod, changed):
    """(code exists on this branch, every named module is in the deployed tree UNCHANGED).

    W4-BOARD recount (2026-10-19): a module present in production but edited on this branch
    since is not the code production runs, so it no longer counts as deployed (the `changed`
    set was computed and ignored before)."""
    if not mods:
        return None, None
    src = [f"brambleloop/src/brambleloop/{m}" for m in mods]
    exists = all((REPO / p).exists() for p in src)
    deployed = all(p in in_prod and p not in changed for p in src)
    return exists, deployed


def _root_for(key, kind, text):
    if key and kind == "external" and key == "image_vision":
        key = "image_vision@external"
    if key in ROOT:
        return ROOT[key]
    if key in ETSY_SETTINGS:
        return ("etsy_shop_settings", "blocked_owner", "owner: Etsy Shop Manager setting")
    if kind == "external":
        return ("etsy_no_api_or_403", "blocked_external", f"external: {key}")
    if kind in ("owner", "data"):
        return ("owner_other", "blocked_owner", f"owner: {key}")
    return None


def classify(rows_in, prod, in_prod, changed, branches, owner_by_gate):
    fm_branch = defaultdict(list)
    b2_branch = defaultdict(list)
    for name, b in branches.items():
        for u in b["fm"]:
            fm_branch[u].append(name)
        for n in b["b2"]:
            b2_branch[n].append(name)
    out = []
    for r in rows_in:
        rid, src = r["id"], r["source"]
        mods = r["modules"]
        exists, deployed = _deploy_state(mods, in_prod, changed)
        text = r["text"]
        cap1 = "catalogue_depth" in text or "CAP-1" in text
        rec = {"id": rid, "source": src, "scope": r["scope"], "title": r["title"][:90],
               "ledger_state": r["ledger_state"], "modules": mods[:6],
               "code_exists": exists, "deployed": deployed}
        if r["state"] == "NA":
            rec.update(cls="not_applicable", root="not_applicable")
            out.append(rec)
            continue
        if r["state"] == "done":
            if r["done_at_deployed"] and deployed is not False:
                rec.update(cls="verified_complete", root=None,
                           evidence=(f"ledger {r['ledger_state']}, and already so in the "
                                     f"ledger committed at the deployed {prod['commit'][:7]} "
                                     "(or closed on committed production evidence of it); "
                                     f"named module(s) in the deployed tree; production "
                                     f"build.commit {prod['commit'][:7]} known={prod['known']}"))
            else:
                rec.update(cls="implemented_unverified", root="release_undeployed_code",
                           missing_evidence=("proven only on the integration branch: not "
                                             "complete in the ledger at the deployed commit, "
                                             "or a named module is absent from production"),
                           blocked_by="engineering: release + deploy",
                           responsible="integrator (release)")
            out.append(rec)
            continue
        # unfinished
        rec["remaining"] = r["remaining"][:300]
        gate_key, gate_kind = r["gate_key"], r["gate_kind"]
        on_branch = (fm_branch.get(rid) if src == "final_master" else b2_branch.get(rid)) or []
        root = _root_for(gate_key, gate_kind, text) if gate_key else None
        if on_branch:
            rec.update(cls="in_progress", root=(root[0] if root else "engineering_open"),
                       blocked_by="in progress", responsible=", ".join(sorted(on_branch)))
        elif root and gate_key in prod["gates"] and prod["gates"][gate_key] and \
                root[1] != "blocked_external":
            rec.update(cls="blocked_engineering", root="gate_open_reverify",
                       blocked_by=(f"engineering: gate {gate_key} is OPEN in production "
                                   f"({prod['read_at']}); the row is unparked and must be "
                                   "re-verified, not assumed done"),
                       responsible="next engineering lane")
        elif root:
            rid_root, cls, who = root
            if cap1 and cls == "blocked_owner":
                rid_root = "launch0_cap_CAP1"
            rec.update(cls=cls, root=rid_root, blocked_by=who,
                       responsible=("owner" if cls == "blocked_owner" else
                                    "integrator (release)" if cls == "blocked_engineering"
                                    else who.split(": ", 1)[-1]))
            if cls == "blocked_owner":
                oa = owner_by_gate.get(gate_key)
                if gate_key in ("etsy_api", "etsy_shop"):
                    oa = {"id": "etsy_credential", "action": ETSY_CRED_ACTION,
                          "max_cost_cad": 0.0, "minutes": None}
                if rid_root == "launch0_cap_CAP1":
                    oa = {"id": "CAP-1", "action": ("decide whether Launch-0 opens with 8 "
                                                     "products (research/final_build/w4/"
                                                     "PRODUCT_FIX.md, CAP-1)"),
                          "max_cost_cad": 0.0, "minutes": 5}
                rec["owner_action"] = oa or r.get("owner_action") or {
                    "id": gate_key, "action": r["gate_detail"][:240], "max_cost_cad": None,
                    "minutes": None}
        elif cap1:
            rec.update(cls="blocked_owner", root="launch0_cap_CAP1",
                       blocked_by="owner: CAP-1 decision", responsible="owner",
                       owner_action={"id": "CAP-1", "action": "decide the Launch-0 depth "
                                     "(PRODUCT_FIX.md CAP-1)", "max_cost_cad": 0.0,
                                     "minutes": 5})
        elif exists and deployed is False and any(
                f"brambleloop/src/brambleloop/{m}" not in in_prod for m in mods):
            # W4-INTEG3: an UNFINISHED row counts as implemented-awaiting-release only when
            # its code is new (absent from production). BOARD's deploy rule makes a module
            # edited since the deploy "not deployed"; an unrelated edit to an open row's module
            # (REL2's main.py, INTEG3's core/db.py) must not promote OPEN F-144/F-718 to
            # implemented -- the ledger still says OPEN (test_w4_board lc_done == COMPLETE).
            rec.update(cls="implemented_unverified", root="release_undeployed_code",
                       blocked_by="engineering: release + deploy, then production evidence",
                       responsible="integrator (release)")
        else:
            area = (mods[0].split("/")[0] if mods else "unknown")
            rec.update(cls="blocked_engineering", root="engineering_open",
                       blocked_by="engineering", responsible=f"next engineering lane ({area})")
        rec["missing_evidence"] = r["missing"][:240] or None
        rec["code_exists"] = exists
        out.append(rec)
    return out


def _at_deployed(rel: str, commit: str):
    raw = _git("show", f"{commit}:brambleloop/research/final_build/{rel}")
    return json.loads(raw) if raw.strip() else None


def _rows_b2(commit):
    led = json.loads((HERE / "BUILD2_LEDGER.json").read_text())
    old = _at_deployed("w4/BUILD2_LEDGER.json", commit) or {"rows": []}
    old_done = {r["id"] for r in old["rows"] if r["state"] == "PROVEN"}
    raw = _git("show", "HEAD:brambleloop/research/final_build/w4/BUILD2_LEDGER.json")
    committed = {r["id"]: r for r in (json.loads(raw)["rows"] if raw.strip() else [])}
    rows = []
    for r in led["rows"]:
        st = r["state"]
        g = r.get("gate") or {}
        prev = (committed.get(r["id"]) or {}).get("gate") or {}
        if not g and st == "OPEN-DEFECT" and prev.get("key"):
            g = dict(prev)          # unparked since the committed ledger: keep its gate key
        kind = {"OWNER-GATED": "owner", "DATA-GATED": "data",
                "EXTERNAL-GATED": "external"}.get(g.get("kind"))
        mods = sorted({m for m in (r.get("evidence") or {}).get("artefacts") or []
                       if m.endswith(".py")})
        rows.append({"id": r["id"], "source": "build2", "scope": "build2", "title": r["title"],
                     "ledger_state": st, "done_at_deployed": r["id"] in old_done,
                     "state": "done" if st == "PROVEN" else "NA" if st == "NOT-APPLICABLE"
                     else "open",
                     "modules": mods, "gate_key": g.get("key"), "gate_kind": kind,
                     "gate_detail": str(g.get("opens_when") or g.get("what") or ""),
                     "remaining": str(r.get("why") or ""),
                     "missing": str(g.get("remaining_note") or r.get("why") or "")[:240],
                     "text": json.dumps(r)[:4000]})
    return rows, led


def _rows_fm(commit):
    m = json.loads((FB / "closure_matrix.json").read_text())
    old = _at_deployed("closure_matrix.json", commit) or {"matrix": []}
    old_done = {r["uid"] for r in old["matrix"] if r["completion"] == "COMPLETE"}
    old_rows = {r["uid"]: r for r in old["matrix"]}
    v_old: dict[str, str] = {}
    rows = []
    for r in m["matrix"]:
        lc = r["launch_class"] == "LAUNCH-CRITICAL"
        if r["completion"] == "NOT-APPLICABLE":
            st = "NA"
        elif lc:
            st = "done" if r["completion"] == "COMPLETE" else "open"
        else:
            # post-launch rows: the same completion rule, read for the board (not a verdict
            # change: aggregate still reports them POST-LAUNCH)
            import sys
            sys.path.insert(0, str(FB))
            import aggregate as agg
            v, _ = agg.completion(dict(r, launch_class="LAUNCH-CRITICAL"))
            st = "done" if v == "COMPLETE" else "open"
            o = old_rows.get(r["uid"])
            if o is not None:
                ov, _ = agg.completion(dict(o, launch_class="LAUNCH-CRITICAL"))
                v_old[r["uid"]] = "done" if ov == "COMPLETE" else "open"
        g = r.get("gate") or {}
        kind = g.get("kind") if g.get("kind") in ("owner", "data", "external") else None
        key = g.get("key") if kind else None
        # evidence produced on/against the deployed 0417f35 (production GETs, or audits run on
        # a clean worktree of that exact commit)
        prod_ev = any("evidence_FMGATE_0417f35/" in str(e) for e in r.get("evidence") or [])
        if st == "done" and not lc:
            done_dep = v_old.get(r["uid"]) == "done"
        else:
            done_dep = r["uid"] in old_done or prod_ev
        rows.append({"id": r["uid"], "source": "final_master", "done_at_deployed": done_dep,
                     "scope": "launch_critical" if lc else (
                         "not_applicable" if st == "NA" else "post_launch"),
                     "title": r["title"], "ledger_state": r["completion"], "state": st,
                     "modules": _modules_fm(r), "gate_key": key, "gate_kind": kind,
                     "gate_detail": str(g.get("detail") or ""),
                     "remaining": str(r.get("next_action") or r.get("missing_part") or ""),
                     "missing": str(r.get("missing_part") or ""),
                     "text": " ".join(str(r.get(k) or "") for k in
                                      ("missing_part", "next_action", "gate"))})
    return rows, m


# Required components tracked by no FM / Build 2 row (PRIVATE_LAURA_TRACE §1.1, G-12). The
# criterion is quoted verbatim from its source; it is not a new acceptance criterion.
TRACKED_ROWS = (
    {"id": "LAURA-PRIVATE-REGISTER",
     "title": "Private Laura: owner-private conversational register (text; voice on "
              "LAURA-VOICE-P2)",
     "criterion": ("PL-11 (DECISION_LOG.md D-FB-15; D-FB-16 item 11): \"Private Laura layer: "
                   "remains a required Final Master component; completion of business "
                   "memory/Talk-to-Laura does not close it; the private conversation register "
                   "stays GATED until implementable within execution constraints.\" / \"11. "
                   "PRIVATE LAURA remains required (PRIV infrastructure accepted); unsupported "
                   "private behaviour stays OPEN/GATED.\""),
     "verifiability": ("A", "B"),
     "modules": ["gateway/laura_register.py", "app/command_center/private_context.py",
                 "laura/private/store.py"],
     "gate_key": "laura_private_register", "gate_kind": "owner",
     "gate_detail": ("code + tests built (W4-PRIVLAURA); enablement is owner-only: "
                     "BRAMBLELOOP_PRIVATE_MEMORY_KEY, D-W4-PL-1 acknowledgement, "
                     "BRAMBLELOOP_LAURA_PRIVATE_REGISTER=1 and "
                     "BRAMBLELOOP_LAURA_PRIVATE_DAILY_CAD (agent laura_private); no consent "
                     "prerequisite (D-W4-PL-3); then an approved deploy and the "
                     "class-B soak (one turn, a reply, persistence across a redeploy)"),
     "owner_action": {"id": "OA-PL-1/2/4",
                      "action": ("PRIVATE_LAURA_TRACE §5 owner actions (OA-PL-3 removed by "
                                 "D-W4-PL-3): OA-PL-1 set BRAMBLELOOP_PRIVATE_MEMORY_KEY; "
                                 "OA-PL-2 acknowledge D-W4-PL-1; OA-PL-4 authorise "
                                 "BRAMBLELOOP_LAURA_PRIVATE_DAILY_CAD (at most the "
                                 "laura_private CA$0.50/day) and set "
                                 "BRAMBLELOOP_LAURA_PRIVATE_REGISTER=1"),
                      "max_cost_cad": None, "minutes": 9},
     "source_ref": "research/final_build/w4/PRIVATE_LAURA_TRACE.md; spec/07 Ruling 2"},
)


def _rows_tracked():
    """The tracked rows in the board's row shape: always open until their own evidence (the
    production soak) exists -- never closed by this board."""
    return [{"id": t["id"], "source": "tracked", "scope": "required_component",
             "title": t["title"], "ledger_state": "TRACKED-OPEN", "done_at_deployed": False,
             "state": "open", "modules": list(t["modules"]), "gate_key": t["gate_key"],
             "gate_kind": t["gate_kind"], "gate_detail": t["gate_detail"],
             "remaining": t["gate_detail"], "missing": t["gate_detail"][:240],
             "criterion": t["criterion"], "verifiability": list(t["verifiability"]),
             "owner_action": t["owner_action"], "text": json.dumps(t)[:4000]}
            for t in TRACKED_ROWS]


AUDIT_FILE = HERE / "BOARD_AUDIT.json"
CLOSURES_FILE = HERE / "BOARD_CLOSURES.json"


def _audit() -> dict:
    """The hand spot-audit of verified rows (BOARD_AUDIT.json): (source, id) -> entry."""
    if not AUDIT_FILE.exists():
        return {}
    return {(r["source"], r["id"]): r for r in json.loads(AUDIT_FILE.read_text())["rows"]}


def _test_exists(ref: str) -> bool:
    f, _, fn = ref.partition("::")
    path = BL / f
    if not path.is_file():
        return False
    return not fn or re.search(r"^def " + re.escape(fn) + r"\(", path.read_text(), re.M) is not None


def apply_audit(rows: list[dict], audit: dict) -> None:
    """Downgrade, never upgrade. A sampled verified_complete row whose evidence does not
    demonstrate its criterion leaves verified_complete with the reason, unless `reclosed`
    names tests (present in tests/) that now assert the missing part. A row the ledgers do not
    prove is never moved by the audit."""
    for x in rows:
        a = audit.get((x["source"], x["id"]))
        if not a:
            continue
        x["audit"] = {k: a.get(k) for k in ("verdict", "basis", "production_reading",
                                               "downgrade_reason", "reclosed")}
        if a["verdict"] != "DOWNGRADE" or x["cls"] != "verified_complete":
            continue
        rc = a.get("reclosed") or {}
        if rc.get("tests") and all(_test_exists(t) for t in rc["tests"]):
            x["audit"]["reclosed_verified"] = True
            continue
        x.update(cls="implemented_unverified", root="audit_criterion_not_demonstrated",
                 blocked_by="engineering: the evidence does not demonstrate the criterion",
                 responsible="next engineering lane",
                 missing_evidence=a.get("downgrade_reason"))


def _closures(prod: dict) -> dict:
    """Rows closed on committed production evidence of the DEPLOYED commit (BOARD_CLOSURES.json).
    Accepted only when every named evidence file exists and the production /health read with
    the same timestamp names the deployed commit; the ledger must still say done."""
    if not CLOSURES_FILE.exists():
        return {}
    data = json.loads(CLOSURES_FILE.read_text())
    ok = {}
    for c in data.get("rows", []):
        files = [BL / f for f in c.get("evidence_files", [])]
        health = BL / c.get("health_file", "")
        if not files or not all(f.is_file() for f in files) or not health.is_file():
            continue
        commit = json.loads(health.read_text()).get("build", {}).get("commit", "")
        if not commit or commit != prod["commit"]:
            continue
        if any(not _test_exists(t) for t in c.get("tests", [])):
            continue
        ok[(c["source"], c["id"])] = c
    return ok


RECOUNT = ("production_verified", "dev_proven_not_deployed", "implemented_unverified",
           "in_progress", "engineering_blocked", "owner_blocked", "external_blocked",
           "live_customer_C", "not_applicable")
EMPIRICAL_ROOTS = {"real_customers", "data_accrual"}


def recount(rows: list[dict], crit: dict) -> list[dict]:
    """The nine categories the owner asked for, one per row. Class C (criterion words demand
    live customers / post-launch history, prelaunch_scope.classify) is carved out of whatever
    blocked/unverified class the row is in; verified and n/a rows keep their class."""
    import prelaunch_scope as ps
    for x in rows:
        if x["cls"] == "not_applicable":
            cat = "not_applicable"
        elif x["cls"] == "verified_complete":
            cat = "production_verified"
        else:
            v = ps.classify(x, crit.get((x["source"], x["id"]), ""), (x["source"], x["id"]))
            x["verifiability"] = v["class"]
            if v["class"] == "C":
                x["c_quote"] = v["quote"]
                cat = "live_customer_C"
            elif x["cls"] == "implemented_unverified":
                cat = ("dev_proven_not_deployed" if x.get("root") == "release_undeployed_code"
                       else "implemented_unverified")
            else:
                cat = {"in_progress": "in_progress", "blocked_engineering": "engineering_blocked",
                       "blocked_owner": "owner_blocked",
                       "blocked_external": "external_blocked"}[x["cls"]]
        x["recount"] = cat
        x["empirical"] = (cat == "live_customer_C" or (cat not in ("production_verified",
                          "not_applicable") and x.get("root") in EMPIRICAL_ROOTS))
    return rows


def recount_counts(rows: list[dict]) -> dict:
    c = {k: sum(1 for x in rows if x["recount"] == k) for k in RECOUNT}
    unfinished = [x for x in rows if x["recount"] not in ("production_verified",
                                                           "not_applicable")]
    c["total"] = len(rows)
    c["unfinished"] = len(unfinished)
    c["post_launch_empirical"] = sum(1 for x in unfinished if x["empirical"])
    c["executable_engineering"] = sum(
        1 for x in unfinished if not x["empirical"] and x["recount"] in (
            "dev_proven_not_deployed", "implemented_unverified", "in_progress",
            "engineering_blocked"))
    c["owner_or_external_non_empirical"] = sum(
        1 for x in unfinished if not x["empirical"] and x["recount"] in (
            "owner_blocked", "external_blocked"))
    return c


ESTIMATES = {
    "release_not_deployed": ("release cycle + 24h", "suite 4693 s (RELEASE_5dfd1ac run "
                             "20261011T083839Z-21062); record 09:56Z -> deployed worker "
                             "13:59Z = ~4 h observed; then off_device_proof window_hours 24"),
    "release_undeployed_code": ("one release cycle", "same release evidence: ~78 min suite + "
                                "~4 h observed record-to-deploy"),
    "etsy_credential_403": ("owner minutes, then 1 daily cadence", "listing.taxonomy_refresh "
                            "cadence 24 h (runtime/worker.py); etsy.probe 6-hourly"),
    "model_credits": ("already OPEN for model_provider/image_vision in production", "gates read "
                      "at the board's production GET"),
    "gate_open_reverify": ("one engineering pass over the unparked rows", "gates read OPEN "
                           "at the board's production GET; each row's own tests/evidence decide"),
    "real_customers": ("unbounded (market)", "no buyer exists; cannot be scheduled"),
    "live_listings": ("owner go-live sitting (OWNER_ACTIONS go_live minutes_total)", ""),
}


def main() -> int:
    prod = _prod()
    in_prod, changed = _deployed_index(prod["commit"])
    branches = _active_branches()
    owner_by_gate = _owner_actions()
    b2_rows, led = _rows_b2(prod["commit"])
    fm_rows, matrix = _rows_fm(prod["commit"])
    closed = _closures(prod)
    for r in b2_rows + fm_rows:
        if (r["source"], r["id"]) in closed and r["state"] == "done":
            r["done_at_deployed"] = True
            r["closed_on"] = closed[(r["source"], r["id"])]
    b2 = classify(b2_rows, prod, in_prod, changed, branches, owner_by_gate)
    fm = classify(fm_rows, prod, in_prod, changed, branches, owner_by_gate)
    for rec, src in zip(b2 + fm, b2_rows + fm_rows):
        if src.get("closed_on") and rec["cls"] == "verified_complete":
            rec["closed_on_production_evidence"] = {
                k: src["closed_on"].get(k) for k in ("evidence_files", "health_file", "reading",
                                                     "tests", "worker")}
    audit = _audit()
    apply_audit(b2 + fm, audit)
    tr_in = _rows_tracked()
    tracked = classify(tr_in, prod, in_prod, changed, branches, owner_by_gate)
    for rec, src in zip(tracked, tr_in):
        rec.update(criterion=src["criterion"], verifiability=src["verifiability"])
    import sys
    sys.path.insert(0, str(HERE))
    import prelaunch_scope as ps
    crit = ps._criteria()
    recount(b2 + fm, crit)
    for x in tracked:
        x["recount"] = "owner_blocked" if x["cls"] == "blocked_owner" else x["cls"]
        x["empirical"] = False

    def counts(rows):
        return {c: sum(1 for x in rows if x["cls"] == c) for c in CLASSES + ("not_applicable",)}

    fm_lc = [x for x in fm if x["scope"] == "launch_critical"]
    unfinished = [x for x in b2 + fm + tracked
                  if x["cls"] not in ("verified_complete", "not_applicable")]
    groups: dict[str, dict] = {}
    for x in unfinished:
        g = groups.setdefault(x["root"], {"root": x["root"],
                                          "title": ROOT_TITLES.get(x["root"], x["root"]),
                                          "rows": 0, "build2": 0, "fm_launch_critical": 0,
                                          "fm_post_launch": 0, "tracked": 0,
                                          "classes": Counter(),
                                          "owner_actions": {}, "ids": []})
        g["rows"] += 1
        g["build2" if x["source"] == "build2" else
          "tracked" if x["source"] == "tracked" else
          "fm_launch_critical" if x["scope"] == "launch_critical" else "fm_post_launch"] += 1
        g["classes"][x["cls"]] += 1
        g["ids"].append(f"{'B2#' if x['source'] == 'build2' else ''}{x['id']}")
        oa = x.get("owner_action")
        if oa:
            g["owner_actions"][oa["id"]] = oa
    for g in groups.values():
        g["classes"] = dict(g["classes"])
        g["owner_actions"] = list(g["owner_actions"].values())
        est = ESTIMATES.get(g["root"])
        mins = [a.get("minutes") for a in g["owner_actions"] if isinstance(a.get("minutes"), int)]
        if est:
            g["estimate"] = {"figure": est[0], "basis": est[1]}
        elif mins:
            g["estimate"] = {"figure": f"owner ~{sum(mins)} min, then the gate's own reading",
                             "basis": "minutes stated per action in OWNER_ACTIONS.json / "
                                      "PRODUCT_FIX.md; no date is promised"}
        else:
            g["estimate"] = None
    ranked = sorted(groups.values(), key=lambda g: (-g["fm_launch_critical"] - g["build2"],
                                                    -g["rows"]))
    path = [r for r in ("release_not_deployed", "release_undeployed_code",
                        "gate_open_reverify", "etsy_credential_403", "launch0_cap_CAP1",
                        "oauth_transactions_r", "live_listings", "real_customers")
            if r in groups]
    critical = [{"step": i + 1, "root": r, "title": groups[r]["title"],
                 "unblocks_rows": groups[r]["rows"],
                 "unblocks_fm_launch_critical": groups[r]["fm_launch_critical"],
                 "unblocks_build2": groups[r]["build2"],
                 "who": ("owner" if groups[r]["classes"].get("blocked_owner") else
                         "external" if groups[r]["classes"].get("blocked_external") else
                         "engineering"),
                 "estimate": groups[r]["estimate"]} for i, r in enumerate(path)]
    board = {
        "kind": "brambleloop.completion_board_final", "schema": 1,
        "generated_by": "research/final_build/w4/completion_board_final.py (do not edit by hand)",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "branch_head": _git("rev-parse", "--short", "HEAD").strip(),
        "production": prod,
        "sources": ["research/final_build/w4/BUILD2_LEDGER.json (build2.closure.ledger, gates "
                    "from production)", "research/final_build/closure_matrix.json "
                    "(aggregate.py)", "research/final_build/w4/OWNER_ACTIONS.json",
                    "research/final_build/w4/evidence_BOARD/ (production GETs)"],
        "rule": ("verified_complete = the ledger's own acceptance evidence, already complete in "
                 "the ledger committed at the deployed commit (or closed on committed evidence "
                 "taken from it), with every named runtime module in the deployed tree; no row "
                 "is closed by this board"),
        "headline": {
            "build2": {"total": len(b2), **counts(b2)},
            "final_master_launch_critical": {"total": len(fm_lc), **counts(fm_lc)},
            "final_master_total": {"total": len(fm), **counts(fm)},
            "tracked_requirements": {"total": len(tracked), **counts(tracked)},
            "recount": {"build2": recount_counts(b2),
                        "final_master_total": recount_counts(fm),
                        "final_master_launch_critical": recount_counts(fm_lc),
                        "categories": list(RECOUNT),
                        "rule": ("production_verified = verified_complete after the spot "
                                 "audit (BOARD_AUDIT.json); dev_proven_not_deployed = proven "
                                 "on the branch only; live_customer_C = the criterion's own "
                                 "words demand live customers / post-launch history "
                                 "(prelaunch_scope C_PATTERNS, quoted); post_launch_empirical "
                                 "= live_customer_C plus rows parked on real customers / data "
                                 "accrual; executable_engineering = the rest of the unfinished "
                                 "rows the company itself can move")},
            "audit": {"sampled": len(audit),
                      "verdicts": dict(Counter(a["verdict"] for a in audit.values())),
                      "downgraded": sorted(
                          f"{'B2#' if x['source'] == 'build2' else ''}{x['id']}"
                          for x in b2 + fm if x.get("root") == "audit_criterion_not_demonstrated"),
                      "reclosed": sorted(
                          f"{'B2#' if x['source'] == 'build2' else ''}{x['id']}"
                          for x in b2 + fm if (x.get("audit") or {}).get("reclosed_verified"))},
            "closed_on_production_evidence": sorted(
                f"{'B2#' if x['source'] == 'build2' else ''}{x['id']}"
                for x in b2 + fm if x.get("closed_on_production_evidence")),
            "ledger_native": {"build2": led["counts"],
                              "final_master_launch_critical":
                                  matrix["summary"]["launch_critical_completion"]}},
        "root_causes": ranked,
        "critical_path": critical,
        "active_worker_branches": branches,
        "rows": {"build2": b2, "final_master": fm, "tracked": tracked},
    }
    OUT_JSON.write_text(json.dumps(board, indent=1, default=str) + "\n")
    card = {"kind": "brambleloop.completion_board_final_card", "schema": 1,
            "generated_at": board["generated_at"], "branch_head": board["branch_head"],
            "production_commit": prod["commit"][:12], "production_read_at": prod["read_at"],
            "headline": board["headline"],
            "top_root_causes": [{k: g[k] for k in ("root", "title", "rows", "build2",
                                                   "fm_launch_critical", "fm_post_launch",
                                                   "classes")}
                                | {"owner_action": (g["owner_actions"][0]["action"][:200]
                                                    if g["owner_actions"] else None)}
                                for g in (ranked[:10] + [g for g in ranked[10:]
                                                         if g["root"] == "engineering_open"])],
            "critical_path": critical,
            "source": "research/final_build/w4/COMPLETION_BOARD_FINAL.json"}
    OUT_CARD.write_text(json.dumps(card, indent=1, default=str) + "\n")
    _markdown(board)
    print(json.dumps(board["headline"], indent=1))
    return 0


def _markdown(b):
    h = b["headline"]
    L = ["# Completion board (final): Build 2 + Final Master", "",
         f"Generated {b['generated_at']} by `{b['generated_by'].split(' ')[0]}` on branch head "
         f"{b['branch_head']}. Production runs `{b['production']['commit'][:12]}` (read "
         f"{b['production']['read_at']}; /api/verify ok={b['production']['verify_ok']}, failing "
         f"{b['production']['verify_failing']}). Rule: {b['rule']}.", "",
         "| scope | total | verified complete | implemented, unverified | in progress | "
         "blocked: engineering | blocked: owner | blocked: external | n/a |",
         "|---|---|---|---|---|---|---|---|---|"]
    for name, c in (("Build 2", h["build2"]),
                    ("Final Master launch-critical", h["final_master_launch_critical"]),
                    ("Final Master total", h["final_master_total"]),
                    ("Tracked requirements", h.get("tracked_requirements") or
                     {"total": 0, "not_applicable": 0, **{k: 0 for k in CLASSES}})):
        L.append(f"| {name} | {c['total']} | " + " | ".join(str(c[k]) for k in CLASSES)
                 + f" | {c['not_applicable']} |")
    rc = h.get("recount")
    if rc:
        L += ["", "## Recount (nine categories, after the spot audit)", "",
              "| scope | " + " | ".join(rc["categories"]) + " | executable engineering | "
              "post-launch empirical | owner/external (non-empirical) |",
              "|---|" + "---|" * (len(rc["categories"]) + 3)]
        for name, key in (("Build 2", "build2"), ("Final Master launch-critical",
                                                   "final_master_launch_critical"),
                          ("Final Master total", "final_master_total")):
            c = rc[key]
            L.append(f"| {name} | " + " | ".join(str(c[k]) for k in rc["categories"])
                     + f" | {c['executable_engineering']} | {c['post_launch_empirical']} | "
                     f"{c['owner_or_external_non_empirical']} |")
        L += ["", f"Rule: {rc['rule']}.", "",
              f"Spot audit: {h['audit']['sampled']} rows, verdicts {h['audit']['verdicts']}; "
              f"downgraded {h['audit']['downgraded']}; re-closed with new tests "
              f"{h['audit']['reclosed']}. Closed on production evidence of the deployed "
              f"commit: {h['closed_on_production_evidence']}."]
    L += ["", f"Ledger-native counts: Build 2 {h['ledger_native']['build2']}; Final Master "
          f"launch-critical {h['ledger_native']['final_master_launch_critical']}.", "",
          "## Critical path", ""]
    for s in b["critical_path"]:
        est = s["estimate"] or {}
        L.append(f"{s['step']}. **{s['title']}** ({s['who']}): unblocks {s['unblocks_rows']} rows "
                 f"({s['unblocks_fm_launch_critical']} FM launch-critical, "
                 f"{s['unblocks_build2']} Build 2). Estimate: {est.get('figure', 'UNKNOWN')}"
                 + (f" -- {est['basis']}" if est.get("basis") else ""))
    L += ["", "## Root causes (unfinished rows)", "",
          "| root cause | rows | B2 | FM LC | FM post-launch | classes | owner action |",
          "|---|---|---|---|---|---|---|"]
    for g in b["root_causes"]:
        oa = g["owner_actions"][0]["action"][:110] if g["owner_actions"] else ""
        L.append(f"| {g['title']} | {g['rows']} | {g['build2']} | {g['fm_launch_critical']} | "
                 f"{g['fm_post_launch']} | {g['classes']} | {oa} |")
    L += ["", "## Active worker branches (unmerged, last 24 h)", ""]
    for n, br in b["active_worker_branches"].items():
        L.append(f"- `{n}` @ {br['head']} ({br['commits_ahead']} ahead, {br['last_commit']}): "
                 f"rows named {br['fm'] + [f'B2#{x}' for x in br['b2']] or 'none'}")
    L += ["", "## Unfinished launch-critical / Build 2 rows", "",
          "| row | class | blocked by | code | deployed | remaining |", "|---|---|---|---|---|---|"]
    for x in b["rows"]["build2"] + b["rows"]["final_master"] + b["rows"].get("tracked", []):
        if x["cls"] in ("verified_complete", "not_applicable") or x["scope"] == "post_launch":
            continue
        rid = f"B2#{x['id']}" if x["source"] == "build2" else x["id"]
        L.append(f"| {rid} | {x['cls']} | {x.get('blocked_by', '')} | {x['code_exists']} | "
                 f"{x['deployed']} | {str(x.get('remaining', '')).replace('|', '/')[:120]} |")
    OUT_MD.write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
