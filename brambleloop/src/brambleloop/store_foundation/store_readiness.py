"""Real-Etsy-store readiness: every planned store item, its status and its exact remaining gate.

Wave-4 lane STORE. One register over the store work already built in waves 1-3 (settings
checklist, taxonomy and attribute reads, policies, listing and image readiness, upload/read-back
verification, analytics intake, gated publication) plus the W4 live-state authority and drift
job, and the consolidated owner-action checklist for the store.

Statuses are the Wave-4 vocabulary only: PROVEN, OWNER-GATED, DATA-GATED, EXTERNAL-GATED,
NOT-APPLICABLE, OPEN-DEFECT. PROVEN means the code path is proven by the named tests; it never
means the real shop has been read (that is stated per item under `live`). Dynamic parts are
computed, not asserted: policy package problems, icon/banner gate findings, taxonomy-read gate,
credential presence (names only, never values) and the live drift report.

Run: PYTHONPATH=src python -m brambleloop.store_foundation.store_readiness --write
writes research/final_build/w4/STORE_READINESS.{json,md}. Nothing here contacts Etsy.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

PROVEN = "PROVEN"
OWNER_GATED = "OWNER-GATED"
DATA_GATED = "DATA-GATED"
EXTERNAL_GATED = "EXTERNAL-GATED"
NOT_APPLICABLE = "NOT-APPLICABLE"
OPEN_DEFECT = "OPEN-DEFECT"
STATUSES = (PROVEN, OWNER_GATED, DATA_GATED, EXTERNAL_GATED, NOT_APPLICABLE, OPEN_DEFECT)

REPO = Path(__file__).resolve().parents[3]
OUT_DIR = REPO / "research" / "final_build" / "w4"

#: Recorded 2026-10-07 from this lane's one read-only attempt: the public shop page answered
#: HTTP 403 with a DataDome CAPTCHA interstitial. Never bypassed (CLAUDE.md non-negotiable).
PUBLIC_PAGE_READ = {"url": "https://www.etsy.com/shop/BrambleloopStudio",
                    "attempted_at": "2026-10-07", "result": "HTTP 403 DataDome CAPTCHA",
                    "bypassed": False}

#: Env names whose presence (never value) decides whether a live read can run here.
CREDENTIAL_ENV = ("ETSY_KEYSTRING", "ETSY_API_KEY", "ETSY_SHARED_SECRET", "ETSY_SHOP_ID")


def _item(id_, area, item, status, *, evidence=(), gate="", live="", owner_action=None,
          note=""):
    assert status in STATUSES, status
    return {"id": id_, "area": area, "item": item, "status": status,
            "evidence": list(evidence), "remaining_gate": gate, "live": live,
            "owner_action": owner_action, "note": note}


def _env_presence(env) -> dict:
    e = env if env is not None else os.environ
    return {k: bool((e.get(k) or "").strip()) for k in CREDENTIAL_ENV}


# ---- the settings checklist (research/final_build/w3/ETSY_SETTINGS_CHECKLIST.md) -------------

#: (id, setting, owner_reported_done_2026_10_06, live readback route)
SETTINGS: tuple[tuple[str, str, bool, str], ...] = (
    ("A1", "Re-authorise the Etsy app with all scopes incl. transactions_r", False, "getMe/getShop"),
    ("A2", "Report whether the shop is 'open' (title/announcement fields visible)", False,
     "owner observation"),
    ("B1", "Account public profile picture = Brambleloop logo mark (not Laura)", False,
     "owner observation"),
    ("B2", "Account preferred name = a real person's name or removed", False,
     "owner observation"),
    ("B3", "Account bio blank or one honest line", False, "owner observation"),
    ("B4", "Two-factor authentication on", False, "owner observation"),
    ("C1", "Shop name kept as BrambleloopStudio", True, "getShop.shop_name"),
    ("C2", "Logo / shop icon", True, "getShop.icon_url_fullxfull"),
    ("C3", "Shop title (tagline) <= 55 chars", True, "getShop.title"),
    ("C4", "Banner (Big Banner) + phone-crop check in the Etsy app", True,
     "getShop.image_url_760x100 + owner phone screenshot"),
    ("C5", "Announcement", False, "getShop.announcement"),
    ("C6", "About your shop (headline + story, AI disclosure)", True, "owner observation"),
    ("C7", "Shop team: legal owner as Owner; Laura not Owner (owner added Laura as Designer)",
     True, "owner observation"),
    ("C8", "About featured photos (certified images only)", False, "owner observation"),
    ("C9", "Location = Canada (real province)", False, "owner observation"),
    ("C10", "Listing order = Custom", False, "owner observation"),
    ("C11", "Sold listings visibility off", False, "owner observation"),
    ("D1", "Sections: create only populated sections (D-FB-18 item 3)", False,
     "getShopSections"),
    ("D2", "Featured listings (4 hero listings, once active)", False, "owner observation"),
    ("E1", "Message to Buyers", False, "getShop.sale_message"),
    ("E2", "Message to Buyers for Digital Items", False, "getShop.digital_sale_message"),
    ("E3", "Order receipt banner (optional)", False, "owner observation"),
    ("F1", "Returns & exchanges (nothing to create for digital-only)", False, "-"),
    ("F2", "Cancellations setting", False, "owner observation"),
    ("F3", "Privacy policy", False, "getShop.policy_privacy"),
    ("F4", "Fixed policies (view only)", False, "-"),
    ("F5", "FAQ incl. pattern licence", False, "owner observation"),
    ("F6", "EU/Omnibus trader status (owner/legal)", False, "owner observation"),
    ("G1", "Options: 'Allow buyers to purchase digital prints' = Disabled", False,
     "owner observation (Options page)"),
    ("G2", "Offsite Ads enrolment (owner decision; fee on sale, not spend)", False,
     "owner observation"),
    ("G3", "Etsy Ads off (no budget)", False, "owner observation"),
)


def _settings_items(drift: dict) -> list[dict]:
    by_field = {r["field"]: r for r in drift["fields"]}
    live_map = {"C1": "shop_name", "C2": "shop_icon", "C3": "shop_title", "C4": "shop_banner",
                "C5": "announcement", "C6": "about_story", "C7": "laura_member_role",
                "E2": "digital_sale_message", "F3": "policy_privacy"}
    out = []
    for sid, what, done, route in SETTINGS:
        field = live_map.get(sid)
        live = by_field.get(field, {}).get("status", "UNKNOWN") if field else "UNKNOWN"
        if sid in ("F1", "F4"):
            out.append(_item(f"SET-{sid}", "settings", what, NOT_APPLICABLE,
                             evidence=["ETSY_SETTINGS_CHECKLIST.md Batch F"],
                             note="digital-only shop; nothing to configure"))
            continue
        if done:
            verified = live not in ("UNKNOWN", "LIVE_BLANK_OWNER_FIELD")
            status = PROVEN if verified else (
                EXTERNAL_GATED if route.startswith("getShop") else OWNER_GATED)
            if verified:
                gate = ""
            elif route.startswith("getShop"):
                gate = ("live read-back: etsy.shop_snapshot (getShop, shops_r) then "
                        "store.live_drift in production")
            else:
                gate = ("owner records a dated observation of the live field "
                        "(store_foundation.live_state.record_observation); no API returns it")
            out.append(_item(f"SET-{sid}", "settings", what, status,
                             evidence=["owner configured the live shop 2026-10-06 (statement)",
                                       f"readback route: {route}"],
                             gate=gate, live=live,
                             note="owner-configured: live is authoritative, never overwritten"))
        else:
            out.append(_item(f"SET-{sid}", "settings", what, OWNER_GATED,
                             evidence=["research/final_build/w3/ETSY_SETTINGS_CHECKLIST.md"],
                             gate="owner login to Etsy (no API writes this in Shadow Mode)",
                             live=live, owner_action=f"OA-{sid}"))
    return out


# ---- the capability items ----------------------------------------------------------------


def build(db=None, *, env: dict | None = None, now: datetime | None = None) -> dict:
    from ..commerce import shop_package
    from ..integrations import etsy_taxonomy
    from . import content, live_state, storefront_gate

    now = now or datetime.now(timezone.utc)
    creds = _env_presence(env)
    surfaces = content.build(db)
    drift = live_state.drift(db, now=now, surfaces=surfaces)
    pkg_problems = shop_package.check_package()
    icon_findings, icon_meta = storefront_gate.check_icon()
    banner_findings, _ = storefront_gate.check_banner()
    sections = surfaces["sections"].value
    populated = [s["name"] for s in sections if s.get("shown")]
    hidden = [s["name"] for s in sections if not s.get("shown")]
    try:
        tax_gate = etsy_taxonomy.gate(db, env=env) if db is not None else {
            "open": bool(etsy_taxonomy._api_key(env)[0]), "via": None,
            "missing": [] if etsy_taxonomy._api_key(env)[0] else
            ["no ETSY_KEYSTRING/ETSY_API_KEY in this environment"]}
    except Exception as exc:  # noqa: BLE001
        tax_gate = {"open": False, "missing": [f"gate unreadable: {type(exc).__name__}"]}
    tax_latest = etsy_taxonomy.latest(db) if db is not None else None
    no_live_read = "no Etsy credential in this environment; public page 403 (DataDome CAPTCHA, " \
                   "not bypassed)"

    items: list[dict] = []
    items += _settings_items(drift)
    items += [
        _item("LIVE-1", "live_state", "Live-state snapshot record (getShop + owner observation, "
              "per-field source/freshness; unread = UNKNOWN)", PROVEN,
              evidence=["store_foundation/live_state.py snapshot()",
                        "tests/test_w4_store_live_state.py"],
              live=f"{len(drift['unknown'])}/{len(drift['fields'])} fields UNKNOWN here "
                   f"({no_live_read})"),
        _item("LIVE-2", "live_state", "Drift report repo draft vs live; owner fields "
              "authoritative (ADOPT_LIVE_INTO_REPO), never auto-overwrite; proposals only",
              PROVEN, evidence=["live_state.drift()", "tests/test_w4_store_live_state.py"],
              live=json.dumps(drift["counts"])),
        _item("LIVE-3", "live_state", "Owner-field write protection (title removed from the "
              "updateShop field set; write_refusal/guard)", PROVEN,
              evidence=["commerce.shop_package.api_shop_fields",
                        "live_state.OWNER_CONFIGURED_API_FIELDS",
                        "tests/test_w4_store_live_state.py"]),
        _item("LIVE-4", "live_state", "Read-back/drift job on a cadence (store.live_drift)",
              EXTERNAL_GATED, evidence=["runtime/etsy_ops.py handle_store_live_drift",
                                        "tests/test_w4_store_live_state.py (runs via Worker)"],
              gate="WIRING REQUEST W4-AUTO: CADENCES entry + orchestrator permission; then "
                   "production getShop credential (A1)"),
        _item("LIVE-5", "live_state", "Storefront content model reports entered_on_etsy from "
              "live evidence", PROVEN,
              evidence=["store_foundation.content.build(db) -> live_state.annotate",
                        "tests/test_w4_store_live_state.py"]),
        _item("LIVE-6", "live_state", "Public shop page read", EXTERNAL_GATED,
              evidence=[json.dumps(PUBLIC_PAGE_READ)],
              gate="Etsy bot protection; only the API path is sanctioned (never bypass "
                   "CAPTCHA)"),
        _item("TAX-1", "taxonomy", "Seller taxonomy read (getSellerTaxonomyNodes) + crochet "
              "pattern subtree, daily listing.taxonomy_refresh", PROVEN if tax_latest else
              EXTERNAL_GATED,
              evidence=["integrations/etsy_taxonomy.py refresh()",
                        "tests/test_v11_seo_taxonomy.py", "tests/test_w3_k1_search.py",
                        "worker CADENCES etsy_taxonomy (24h)"],
              gate="" if tax_latest else
              "a real read needs ETSY_KEYSTRING (api-key only) or a recorded etsy.probe; "
              f"gate here: {tax_gate.get('missing')}",
              live="TAXONOMY_PATTERNS=66 UNVERIFIED until a real read"),
        _item("TAX-2", "attributes", "Required attributes per taxonomy "
              "(getPropertiesByTaxonomyId) and property contract", PROVEN if tax_latest else
              EXTERNAL_GATED,
              evidence=["EtsyClient.get_taxonomy_properties", "integrations/etsy_constraints.py",
                        "tests/test_etsy_property_contract.py",
                        "tests/test_w3_etsy_constraints.py"],
              gate="" if tax_latest else "same real read as TAX-1"),
        _item("POL-1", "policies", "Policy package (delivery, returns, privacy, licence FAQ, "
              "digital sale message) passes package checks",
              PROVEN if not pkg_problems else OPEN_DEFECT,
              evidence=["commerce.shop_package.check_package() -> "
                        f"{len(pkg_problems)} problems", "tests/test_shop_package.py"],
              gate="; ".join(pkg_problems[:3])),
        _item("POL-2", "policies", "Live policy text consistency vs canonical "
              "(policy_consistency in etsy.shop_snapshot)", EXTERNAL_GATED,
              evidence=["commerce/policy_consistency.py", "tests/test_k8_shop_cx.py"],
              gate="owner pastes Batch F; then getShop read-back"),
        _item("IMG-1", "images", "Shop icon at Etsy sizes (owner-approved micro-mark, D-FB-18 "
              "item 5)", PROVEN if not icon_findings else OPEN_DEFECT,
              evidence=["storefront_gate.check_icon() -> "
                        f"{len(icon_findings)} findings; asset "
                        f"{(icon_meta.get('choice') or {}).get('asset')}",
                        "tests/test_w3_store_ux_gate.py"],
              live=drift_status(drift, "shop_icon")),
        _item("IMG-2", "images", "Banner publication gates on the canonical owner banner "
              "(D-FB-17/18)", OWNER_GATED if banner_findings else PROVEN,
              evidence=[f"storefront_gate.check_banner() -> {len(banner_findings)} findings: "
                        + ", ".join(f["code"] for f in banner_findings)],
              gate="owner already put a banner live (2026-10-06): live is authoritative and is "
                   "not replaced. The repo gates still report the findings listed; they go to "
                   "the owner as findings (D-FB-17 item 2: never silently substitute)",
              live=drift_status(drift, "shop_banner"), owner_action="OA-BANNER"),
        _item("IMG-3", "images", "Listing image readiness: certified frames in certificate "
              "order, alt text, read-back", PROVEN,
              evidence=["runtime/etsy_ops.py certified_images/images_read_back",
                        "tests/test_etsy_readback_observe.py",
                        "tests/test_w3_etsy_upload_readback.py"],
              gate="real images need certified releases (DATA) and A1 for real upload"),
        _item("LST-1", "listings", "Listing readiness (release gates, search certificate, "
              "ranking readiness)", DATA_GATED,
              evidence=["publish/release_gates.py", "commerce/ranking_readiness.py",
                        "tests/test_ranking_readiness.py", "tests/test_listing_parity_gate.py"],
              gate="needs certified releases with listing-set + search certificates in the "
                   "production DB (none in this environment)"),
        _item("LST-2", "listings", "Sections: only populated categories exposed (D-FB-18 "
              "item 3)", PROVEN,
              evidence=[f"populated: {populated}", f"hidden (planned): {hidden}",
                        "store_foundation.navigation", "tests/test_w3_store_ux_structure.py"]),
        _item("UPL-1", "upload_readback", "Draft -> image upload -> file -> read back -> "
              "delete probe, field-by-field verification", PROVEN,
              evidence=["integrations/etsy_verify.py", "integrations/etsy_probe.py",
                        "tests/test_w3_etsy_upload_readback.py",
                        "tests/test_etsy_readback_observe.py (FakeEtsy contract)"],
              gate="real-Etsy confirmation needs A1 re-authorisation; stays LOCALLY_TESTED "
                   "until then", owner_action="OA-A1"),
        _item("UPL-2", "upload_readback", "Daily listing census + field drift (never "
              "overwrite)", PROVEN,
              evidence=["etsy.listing_census", "tests/test_etsy_readback_observe.py "
                        "test_a_listing_edited_on_etsy_is_field_drift_and_is_never_overwritten"],
              gate="real census needs the production credential"),
        _item("ANA-1", "analytics", "Etsy Stats CSV intake (listing-level) -> ListingOutcome, "
              "strict, blank != zero", PROVEN,
              evidence=["commerce/listing_outcomes.py submit_export/produce",
                        "commerce/attribution.py parse_stats_csv",
                        "tests/test_k3_listing_outcomes.py",
                        "tests/test_w3_spend_attribution.py"],
              gate="DATA: first owner export after listings are live", owner_action="OA-STATS"),
        _item("ANA-2", "analytics", "API read of views/favourites (impressions/carts stay "
              "UNKNOWN)", EXTERNAL_GATED,
              evidence=["commerce/listing_outcomes.py (getListingsByShop)"],
              gate="production credential + active listings"),
        _item("PUB-1", "publication", "Publication pipeline (store.publish drafts; "
              "store.activate only on read-back proof + owner authority at execution time)",
              OWNER_GATED,
              evidence=["runtime/pipeline.py handle_store_publish", "runtime/etsy_ops.py",
                        "tests/test_etsy.py", "tests/test_draft_creation_durability.py",
                        "tests/test_etsy_readback_observe.py"],
              gate="phase stays SHADOW; activation needs owner launch authorisation + "
                   "certified releases + A1", owner_action="OA-LAUNCH"),
    ]
    for f in drift["findings"]:
        items.append(_item(f"LIVE-FINDING-{f['field']}-{f['code']}", "live_state",
                           f"advisory on live owner field {f['field']}", OWNER_GATED,
                           evidence=[f["detail"]], gate="owner decides; software never edits"))
    counts: dict[str, int] = {}
    for it in items:
        counts[it["status"]] = counts.get(it["status"], 0) + 1
    return {"generated_at": now.isoformat(), "lane": "W4-STORE", "phase": "SHADOW",
            "credentials_present": creds, "public_page_read": PUBLIC_PAGE_READ,
            "counts": counts, "items": items, "drift": drift,
            "owner_actions": owner_actions(drift)}


def drift_status(drift: dict, field: str) -> str:
    for r in drift["fields"]:
        if r["field"] == field:
            return r["status"]
    return "UNKNOWN"


# ---- consolidated owner-action checklist -------------------------------------------------


def owner_actions(drift: dict) -> list[dict]:
    """One batched list: exact action, why, max cost, minutes, consequence of waiting."""
    def oa(id_, action, why, minutes, wait, cost="CA$0"):
        return {"id": id_, "action": action, "why": why, "max_cost": cost,
                "minutes": minutes, "if_you_wait": wait}

    rows = [
        oa("OA-A1", "Re-authorise the Etsy app: Command Center GET /api/etsy/oauth/start -> "
           "Allow all scopes incl. transactions_r", "the only route to a real read-back of "
           "the live shop (title, icon, banner), taxonomy, upload proof and orders", 5,
           "every live field stays UNKNOWN; nothing real can be verified"),
        oa("OA-OBS", "Record what the live shop shows for the fields no API returns: About "
           "headline, About story, Laura's member bio and role (paste text; one dated "
           "observation)", "lets the drift job treat your configuration as authoritative and "
           "check it (Laura disclosed as AI, not in the Owner role) without touching it", 5,
           "About/Laura fields stay UNKNOWN; previews may show stale repo drafts"),
        oa("OA-A2", "Report whether the shop is 'open' (title/announcement editable)",
           "decides whether announcement can be set now", 1, "C5 stays blocked"),
        oa("OA-B", "Account settings: profile picture = logo mark, real preferred name, short "
           "bio, 2FA on (Batch B)", "the account picture/name present the legal account "
           "holder; Laura must not appear as the account holder", 5,
           "a persona could read as the legal owner"),
        oa("OA-BANNER", "Phone check: open the shop in the Etsy app, screenshot the banner; "
           "and decide on the banner gate findings listed in IMG-2 (nav footer shows "
           "Wearables/Gifts/Seasonal, which have no products yet; Laura publication status)",
           "the live banner is yours and is not replaced; Etsy publishes no mobile crop, and "
           "the repo gates found items only you can rule on", 3,
           "crop/footer findings stay unresolved"),
        oa("OA-C", "Shop settings still open: announcement (C5), location (C9), listing order "
           "Custom (C10), sold visibility off (C11)", "trust surfaces and ordering", 5,
           "shop snapshot keeps reporting missing trust surfaces"),
        oa("OA-D1", "Create sections for populated categories only (today: Home, Baby)",
           "D-FB-18 item 3: never advertise empty categories", 3,
           "listings land unsectioned"),
        oa("OA-E", "Info & Appearance: Message to Buyers + Message for Digital Items (Batch E)",
           "the digital message is the only text every buyer receives at purchase", 3,
           "first buyers get no download guidance"),
        oa("OA-F", "Policy Settings: privacy policy, FAQ with licence, cancellations "
           "(Batch F)", "Etsy trust surfaces; licence belongs in the FAQ for a Canadian shop",
           10, "policy_consistency stays failing"),
        oa("OA-G1", "Settings > Options: 'Allow buyers to purchase digital prints' = Disabled",
           "a third party would sell printed copies of a pattern PDF", 1,
           "auto-enrolment may put a third-party product beside ours"),
        oa("OA-G2", "Offsite Ads: decide enrolment (15% fee on attributed sales, no fixed "
           "spend)", "a margin decision, recorded rather than defaulted", 1,
           "default enrolment stands", cost="15% of attributed orders (cap US$100/order)"),
        oa("OA-STATS", "After the first listings are live: export the listing-level Etsy "
           "Stats CSV and upload it (POST /api/attribution/stats)", "impressions/carts are not "
           "in the API; the CSV is the only measurement", 3, "funnel stays UNMEASURED"),
        oa("OA-LAUNCH", "Launch authorisation for the first listings (separate gated approval)",
           "no listing is activated without it", 5, "the shop stays without listings"),
    ]
    for f in drift.get("findings", []):
        rows.append(oa(f"OA-LIVE-{f['field']}", f"Review live {f['field']}: {f['detail']}",
                       "advisory from the drift report; software never edits a live owner "
                       "field", 2, "the finding stays open"))
    return rows


# ---- rendering ---------------------------------------------------------------------------


def render_md(report: dict) -> str:
    lines = [
        "# Store readiness — real Etsy shop (lane W4-STORE)", "",
        f"Generated {report['generated_at']} by `store_foundation.store_readiness` "
        "(regenerate: `PYTHONPATH=src python -m brambleloop.store_foundation.store_readiness "
        "--write`). Phase: **SHADOW** — no Etsy write, no publication.", "",
        "**Live state is authoritative.** The owner configured the real shop on 2026-10-06 "
        "(logo, banner, title/tagline, About headline/story, Laura's member profile and "
        "Designer role). Those fields are never overwritten; drift proposes "
        "ADOPT_LIVE_INTO_REPO only. In this environment no live value could be read: "
        f"no Etsy credential is present ({', '.join(k for k, v in report['credentials_present'].items() if v) or 'none of ' + ', '.join(CREDENTIAL_ENV)}), "
        f"and the public page returned {report['public_page_read']['result']} (not bypassed). "
        "Every live field is therefore **UNKNOWN** here; production performs the read-back "
        "(`etsy.shop_snapshot` → `store.live_drift`).", "",
        "Counts: " + ", ".join(f"{k} {v}" for k, v in sorted(report["counts"].items())), "",
        "| id | area | item | status | live | remaining gate | evidence |",
        "|---|---|---|---|---|---|---|",
    ]
    for it in report["items"]:
        ev = "; ".join(it["evidence"])[:260].replace("|", "/")
        lines.append(f"| {it['id']} | {it['area']} | {it['item'].replace('|', '/')} | "
                     f"**{it['status']}** | {it['live'] or '-'} | "
                     f"{(it['remaining_gate'] or '-').replace('|', '/')} | {ev} |")
    lines += ["", "## Live drift (repo draft vs live)", "",
              "| field | owner-configured | status | source | proposal |", "|---|---|---|---|---|"]
    for r in report["drift"]["fields"]:
        p = r["proposal"]["kind"] if r["proposal"] else "-"
        lines.append(f"| {r['field']} | {'yes' if r['owner_configured'] else 'no'} | "
                     f"{r['status']} | {r['live_source'] or '-'} | {p} |")
    lines += ["", "## Owner actions for the store (batched)", "",
              "| id | exact action | why | max cost | min | if you wait |",
              "|---|---|---|---|---|---|"]
    for a in report["owner_actions"]:
        lines.append(f"| {a['id']} | {a['action']} | {a['why']} | {a['max_cost']} | "
                     f"{a['minutes']} | {a['if_you_wait']} |")
    total = sum(a["minutes"] for a in report["owner_actions"])
    lines += ["", f"Total owner time: ~{total} minutes. OA-A1 and OA-OBS unblock the live "
              "read-back; the rest can follow in any order.", ""]
    return "\n".join(lines)


def write(report: dict, out_dir: Path = OUT_DIR) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    j = out_dir / "STORE_READINESS.json"
    m = out_dir / "STORE_READINESS.md"
    j.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n")
    m.write_text(render_md(report))
    return j, m


if __name__ == "__main__":  # pragma: no cover
    import sys

    rep = build()
    if "--write" in sys.argv:
        for p in write(rep):
            print(p)
    print(json.dumps(rep["counts"]))
