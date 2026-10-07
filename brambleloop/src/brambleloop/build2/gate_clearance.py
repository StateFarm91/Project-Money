"""Business-gate clearance packets: what exactly clears each parked business gate (W4-GATESB).

Owner authorisation 2026-10-07: the eight business gates in the console's "waiting on the
owner" table are to be *cleared* rather than left parked. Clearing a gate is not opening it in
code -- every gate in `executor.GATES` opens only on the evidence its check counts, and that
does not change here. What changes is that each gate now carries the exact clearance: the
action, the links, the cost ceiling, the minutes, how the result reaches the system, and --
the part a parked card never said -- whether the owner can usefully act yet, or whether
company work or another gate has to land first.

Three classifications are corrected by this module and its callers, each against a specific
way the old table misled:

* **customers is DATA/EXTERNAL, never an owner card.** Buyers create orders. The old table
  rendered "grant real orders" as an owner action. `closure.DATA_GATES` already classed it;
  `approval_inbox` lists it under `waiting_on_data`, and `prerequisite` below never offers it.
* **A gate whose precondition is unmet is not askable yet.** An ad budget asked for before a
  listing can sell, a physical make asked for before anybody agreed to make it, and a listing
  publication asked for before a product cleared the final publication gate are all requests
  the owner cannot usefully answer. They are listed with the precondition instead
  (`not_yet_askable`), and return to the queue by themselves the day it is met.
* **owned_surfaces recognises the Etsy shop.** The shop exists and is owner-configured
  (`etsy_shop` gate open). It is the paid destination every owned funnel leads to, so that
  portion is satisfied; what stays missing is a surface *of the company's own* to publish free
  content, pins, video and email to -- and each missing one is named with why it is required.

Nothing here spends, publishes, contacts anybody or writes to Etsy.
"""
from __future__ import annotations

import html

# The gates this lane owns the clearance of (the business half of the owner table).
BUSINESS_GATES: tuple[str, ...] = (
    "benchmark_purchases", "physical_proof", "tester_roster", "second_market_benchmark",
    "owned_surfaces", "customers", "ad_authority", "live_listings",
)

CLEARED = "CLEARED"                       # the gate's evidence exists (gate open)
OWNER_ACTION = "OWNER-ACTION"             # askable now: one exact owner step clears it
NOT_YET_ASKABLE = "NOT-YET-ASKABLE"       # company work / another gate must land first
DATA_GATED = "DATA-GATED"                 # only buyers/traffic open it
COMPANY_SELECTED = "COMPANY-SELECTED"     # the company made the choice; observation pending

PRODUCTION = "https://brambleloop-os-production.up.railway.app"
INTAKE_PAGE = PRODUCTION + "/ops/teardown"
INTAKE_API = PRODUCTION + "/api/teardown/intake"
PHYSICAL_TEST_API = PRODUCTION + "/api/physical-test"
PHYSICAL_PHOTO_API = PRODUCTION + "/api/physical-photo"


# ---- 1. benchmark_purchases --------------------------------------------------------------

def benchmark_purchase_list(db) -> dict:
    """The approved benchmark set, exactly as intake will expect it, with links and cost.

    The set size and the ceiling are the owner's 2026-09-20 decision (B-501/B-512), enforced
    in `teardown.intake` as SET_SIZE/SET_BUDGET_CAD; the picks are `purchase_selection`'s
    deterministic coverage selection over the observed catalogue -- the same call the upload
    page makes, so the list the owner buys from and the list intake ticks off cannot differ.
    """
    from ..intel import benchmarks
    from ..intel.purchase_selection import SelectionRefused, select
    from ..teardown import intake

    try:
        chosen = select(db, benchmarks.MJS_KEY, target=intake.SET_SIZE,
                        budget_cad=intake.SET_BUDGET_CAD)
    except SelectionRefused as exc:
        return {"status": "UNKNOWN", "picks": [], "why": str(exc)}
    picks = [{"n": i, "listing_ref": str(p.get("listing_ref")),
              "title": html.unescape(str(p.get("title") or "")),
              "department": p.get("pod"), "price_cad": p.get("price_cad"),
              "url": p.get("url"), "answers": p.get("answers")}
             for i, p in enumerate(chosen.get("selected") or [], start=1)]
    return {
        "status": "LISTED" if picks else "UNKNOWN",
        "benchmark": benchmarks.MJS_KEY,
        "set_size_approved": intake.SET_SIZE,
        "budget_cad_approved": intake.SET_BUDGET_CAD,
        "picks": picks,
        "total_cad": chosen.get("total_cad"),
        "within_budget": chosen.get("within_budget"),
        "price_basis": ("observed Etsy listing price in CAD at observation time; taxes and any "
                        "sale price on the day are not included -- an expected cost, not a "
                        "quote"),
        "delivery": benchmark_delivery(),
        "never": ("no competitor text, chart, photograph or instruction is copied into any "
                  "Brambleloop product; the files live in the quarantined library and only "
                  "analysts read them (teardown/library.py)"),
    }


def benchmark_delivery() -> dict:
    """How purchased files reach the system: the existing intake, nothing new."""
    return {
        "page": INTAKE_PAGE,
        "api": INTAKE_API,
        "steps": [
            "Buy each listing on Etsy (signed in as the owner; any payment method).",
            "Open Etsy > You > Purchases and reviews > Download files for that order.",
            f"Open {INTAKE_PAGE} on the same phone or computer, paste the operator token "
            "(BRAMBLELOOP_OPS_TOKEN; kept in page memory only).",
            "Tap the pick (rows are the approved set in the same order), choose the downloaded "
            "file(s) -- zips are accepted and expanded -- optionally type the price paid.",
            "Repeat per purchase. The page shows received/outstanding; nothing needs renaming.",
        ],
        "api_form": {"listing_ref": "the Etsy listing id of the pick (required)",
                     "files": "one or more downloaded files (pdf/zip/images/video)",
                     "paid_cad": "optional: what was actually paid, in CAD",
                     "licence_terms": "optional JSON: the shop's stated licence terms"},
        "durability": ("files are mirrored to the off-provider archive when offsite storage "
                       "is configured; until then the reply says durable:false and the files "
                       "should be re-uploaded after offsite storage exists"),
        "gate_opens_when": "the first BenchmarkProduct row exists (first intake)",
    }


# ---- 5. owned_surfaces ---------------------------------------------------------------------

# Each requirement parked on owned_surfaces, the surface(s) its remaining work publishes to,
# and the portion the Etsy shop already satisfies. Read from the rows' own bodies/notes.
OWNED_SURFACE_NEEDS: dict[int, dict] = {
    4: {"needs": ("pinterest", "site"),
        "etsy_satisfies": "nothing: concept tests must never use Etsy listings (fake-listing "
                          "ban); they need a surface of our own"},
    10: {"needs": ("site", "pinterest", "email"),
         "etsy_satisfies": "the paid destination (premium singles/collections are sold on the "
                           "Etsy shop); the free-content top of the funnel needs a site"},
    246: {"needs": ("pinterest",),
          "etsy_satisfies": "the pin landing destination (an Etsy listing URL once a listing "
                            "is live); posting pins needs a Pinterest business account"},
    247: {"needs": ("site",),
          "etsy_satisfies": "the paid product each cluster ends on; the cluster pages need a "
                            "site (Etsy shop pages cannot host informational content)"},
    248: {"needs": ("video",),
          "etsy_satisfies": "listing video slots (per listing, once live); a canonical "
                            "tutorial and Shorts need a video channel"},
    251: {"needs": ("email",),
          "etsy_satisfies": "nothing: Etsy forbids marketing email to buyers from order "
                            "data; a consented list needs our own signup + sending provider"},
    255: {"needs": ("site",),
          "etsy_satisfies": "the product each tool links to; the tools need a site to run on"},
}

MISSING_SURFACES: dict[str, dict] = {
    "site": {"what": "a Brambleloop website on a domain the company controls",
             "why": "hosts free motifs/tutorials/tools, SEO topic clusters and the consented "
                    "email signup (#4 #10 #247 #251 #255); Etsy shop pages cannot",
             "owner_step": "buy brambleloop domain (registrar of choice) and point it at a "
                           "static host; the company builds and publishes the pages",
             "max_cost_cad": 25.0, "cost_basis": "ESTIMATED: one .com/.ca domain-year; "
                                                 "static hosting on a free tier",
             "minutes": 20},
    "pinterest": {"what": "a Pinterest business account for Brambleloop",
                  "why": "pins with seasonal lead time and attribution (#246), concept "
                         "interest tests (#4), free-to-paid funnel entry (#10)",
                  "owner_step": "create a free Pinterest business account (accepts "
                                "Pinterest's terms; person-only), then authorise the app",
                  "max_cost_cad": 0.0, "cost_basis": "free account", "minutes": 15},
    "email": {"what": "an email sending provider with a CASL-compliant signup form",
              "why": "welcome/launch/seasonal lifecycle flows to consented subscribers (#251) "
                     "and the funnel's consented-email step (#10)",
              "owner_step": "open a free-tier sending account (accepts its terms, verifies the "
                            "sender domain and a physical mailing address for CASL)",
              "max_cost_cad": 0.0, "cost_basis": "free tier up to its subscriber cap",
              "minutes": 20},
    "video": {"what": "a YouTube channel for Brambleloop",
              "why": "canonical technique tutorials and Shorts reused from flagship video "
                     "modules (#248)",
              "owner_step": "create a YouTube brand channel (Google account terms; "
                            "person-only)", "max_cost_cad": 0.0,
              "cost_basis": "free", "minutes": 10},
}


def owned_surfaces_inventory(db, env: dict | None = None) -> dict:
    """Which owned surfaces exist, which portion the Etsy shop satisfies, what is missing."""
    from . import executor

    shop_open = None
    try:
        shop_open = bool(executor.GATE_BY_KEY["etsy_shop"].open(db, env))
    except Exception:  # noqa: BLE001 - unreadable is UNKNOWN, never "absent"
        shop_open = None
    shop_reading = None
    try:
        from ..store_foundation import live_state

        shop_reading = live_state._shop_reading(db)
    except Exception:  # noqa: BLE001
        shop_reading = None
    publish_probe = None
    try:
        publish_probe = bool(executor._owned_surface_probed(db, env))
    except Exception:  # noqa: BLE001
        publish_probe = None
    present = {
        "etsy_shop": {
            "state": ("PRESENT" if shop_open else "UNKNOWN" if shop_open is None
                      else "NOT-VERIFIED-HERE"),
            "evidence": ("executor gate etsy_shop open: shop identifier set AND a recorded "
                         "etsy.probe succeeded (production /api/build gates.etsy_shop.open="
                         "true at fcb982d, read 2026-10-07); owner configured the live shop "
                         "by hand 2026-10-06 (store_foundation.live_state.OWNER_CONFIGURED_ON)"),
            "shop_snapshot_on_file": shop_reading is not None,
            "role": ("the marketplace and paid destination. It is not an owned publishing "
                     "surface: it cannot host free content, pins, video or an email list"),
        },
    }
    needed = sorted({s for v in OWNED_SURFACE_NEEDS.values() for s in v["needs"]})
    return {
        "present": present,
        "owned_publish_surface_probed": publish_probe,
        "etsy_shop_satisfies": {rid: v["etsy_satisfies"]
                                for rid, v in OWNED_SURFACE_NEEDS.items()},
        "missing": {k: MISSING_SURFACES[k] for k in needed},
        "requirements": {rid: list(v["needs"]) for rid, v in OWNED_SURFACE_NEEDS.items()},
        "minimum_to_open_gate": ("one owned surface whose publish path passes the "
                                 "owned_surface.probe (site or Pinterest); each further "
                                 "surface un-parks the rows that name it"),
        "max_cost_cad_all": round(sum(MISSING_SURFACES[k]["max_cost_cad"] for k in needed), 2),
        "minutes_all": sum(MISSING_SURFACES[k]["minutes"] for k in needed),
    }


# ---- 7. ad_authority -----------------------------------------------------------------------

# What "ready to sell" means for an ad recommendation. Each is checked from rows.
AD_READY_DEFINITION: tuple[str, ...] = (
    "the listing exists on Etsy (Listing.etsy_listing_id set) and its state is active",
    "its release is certified (Listing.release_hash set) -- the same release the listing "
    "was published from",
    "orders can be read (transactions_r gate open), so CAC and contribution are measured "
    "rather than guessed; without it ads would run blind and are not recommended",
)
# Etsy Ads' own floor is a daily budget per shop; the conservative caps already in code start
# at it. The recommendation never exceeds `paid_media.CONSERVATIVE_CAPS`.
MAX_ADVERTISED_LISTINGS = 4


def ad_readiness(db, env: dict | None = None) -> dict:
    """Whether an initial ad budget may be recommended yet, and what it would be."""
    from sqlalchemy import select

    from ..commerce.paid_media import CONSERVATIVE_CAPS
    from ..core.models import Listing
    from . import executor

    with db.session() as s:
        rows = [(r.product_slug, r.version, float(r.price_cad or 0.0), r.state or "",
                 r.release_hash or "", r.etsy_listing_id or "")
                for r in s.scalars(select(Listing))]
    live = [r for r in rows if r[5]]
    ready = [r for r in live if r[3] == "active" and r[4]]
    try:
        measured = bool(executor.GATE_BY_KEY["transactions_r"].open(db, env))
    except Exception:  # noqa: BLE001
        measured = False
    reasons = []
    if not live:
        reasons.append("no listing exists on Etsy yet (live_listings gate closed)")
    elif not ready:
        reasons.append(f"{len(live)} listing(s) on Etsy but none is active with a certified "
                       f"release")
    if not measured:
        reasons.append("orders cannot be read yet (transactions_r gate closed), so CAC would "
                       "be unmeasured")
    structure = {
        "platform": "Etsy Ads (on-platform only); Offsite Ads is a fee-on-sale setting, not "
                    "spend, and is decided separately",
        "campaign": "one campaign: the ready listings, highest net-after-fees first, at most "
                    f"{MAX_ADVERTISED_LISTINGS}",
        "targeting": ("Etsy Ads exposes no keyword/audience targeting to sellers: the levers "
                      "are which listings advertise and the daily budget. Search relevance "
                      "comes from the listing's own title/tags (seo certificate)"),
        "measurement": ("ads.adjust (daily) reads ListingOutcome traffic split paid/organic, "
                        "Orders via transactions_r, contribution after fees; organic-first "
                        "proof (#242) gates any scaling"),
        "guardrails_in_code": {
            "caps": {"daily_cad": CONSERVATIVE_CAPS.daily_cad,
                     "campaign_cad": CONSERVATIVE_CAPS.campaign_cad,
                     "monthly_cad": CONSERVATIVE_CAPS.monthly_cad,
                     "max_test_loss_cad": CONSERVATIVE_CAPS.max_test_loss_cad,
                     "max_cac_cad": CONSERVATIVE_CAPS.max_cac_cad},
            "enforced_by": ["commerce.paid_media.authorise_spend (refuses in shadow and above "
                            "any cap)", "commerce.paid_media.should_pause (tracking failure, "
                            "unavailable listing, CAC breach, refund anomaly, test-loss cap)",
                            "runtime.growth_ops ads.campaign (hard-refused while the "
                            "ad_authority gate is closed)",
                            "executor gate ad_authority: SpendLimit('ads') positive, unpaused"],
        },
    }
    if reasons:
        return {"ready": False, "ready_listings": [], "why_not": reasons,
                "definition_of_ready": list(AD_READY_DEFINITION),
                "recommended": None,
                "when": "recommended automatically the day every condition holds",
                "structure": structure}
    ready.sort(key=lambda r: -r[2])
    chosen = ready[:MAX_ADVERTISED_LISTINGS]
    return {
        "ready": True,
        "ready_listings": [{"slug": r[0], "version": r[1], "price_cad": r[2],
                            "etsy_listing_id": r[5]} for r in chosen],
        "definition_of_ready": list(AD_READY_DEFINITION),
        "recommended": {
            "daily_cad": CONSERVATIVE_CAPS.daily_cad,
            "campaign_cad": CONSERVATIVE_CAPS.campaign_cad,
            "monthly_cad": CONSERVATIVE_CAPS.monthly_cad,
            "why": ("the conservative caps already enforced in code (Master Plan s.11: start "
                    "small, scale only on profitable evidence); a test, not a scale budget"),
            "owner_step": ("set SpendLimit scope 'ads' daily_cap_cad="
                           f"{CONSERVATIVE_CAPS.daily_cad:.2f} lifetime_cap_cad="
                           f"{CONSERVATIVE_CAPS.campaign_cad:.2f} (owner credential), and "
                           "turn on Etsy Ads in Shop Manager > Marketing at the same daily "
                           "budget"),
        },
        "structure": structure,
    }


# ---- live_listings ------------------------------------------------------------------------

def live_listing_readiness(db) -> dict:
    """Company work first: has any product cleared the final publication gate?"""
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        approved = s.scalar(select(AuditLog.id).where(
            AuditLog.action == "owner.publication.approved").limit(1))
    return {
        "company_work": ("lane PIPE / product pipeline moves the strongest products through "
                         "the final publication gate (ops.publication_authority.evidence: "
                         "certification, parity, listing set, disclosure, policy, search, "
                         "economics, rollback)"),
        "owner_step": ("per product that shows complete publication evidence: approve its "
                       "sealed 24h publication grant (D-FB-10) and authorise leaving shadow "
                       "for that listing"),
        "grant_ever_approved": approved is not None,
    }


# ---- prerequisites: when a card is not yet askable -------------------------------------------

def prerequisite(db, gate: str, env: dict | None = None) -> str | None:
    """Why an owner card for `gate` cannot usefully be answered yet, or None when it can.

    Only preconditions that are evidence-checked here. A gate with no entry is askable.
    """
    from . import executor

    def is_open(key: str) -> bool:
        try:
            return bool(executor.GATE_BY_KEY[key].open(db, env))
        except Exception:  # noqa: BLE001 - unreadable reads closed
            return False

    if gate == "ad_authority":
        state = ad_readiness(db, env)
        if not state["ready"]:
            return ("no listing is ready to sell yet: " + "; ".join(state["why_not"])
                    + ". The initial budget is recommended (paid_media.CONSERVATIVE_CAPS) "
                    "the day it is")
    if gate == "physical_proof" and not is_open("tester_roster"):
        return ("no tester has agreed yet (tester_roster gate closed); the physical make is "
                "commissioned from the first agreed tester, so answer the tester_roster card "
                "first. Kit and protocol: research/final_build/w4/tester_kit/")
    if gate == "live_listings":
        state = live_listing_readiness(db)
        if not state["grant_ever_approved"] and not is_open("live_listings"):
            return ("company work first: no product has yet cleared the final publication "
                    "gate (" + state["company_work"] + "). The owner is asked per product "
                    "once its publication evidence is complete")
    return None


# ---- per-gate owner card fields ----------------------------------------------------------

def card_fields(db, gate: str, env: dict | None = None) -> dict:
    """The exact action/cost/minutes/links an owner card for this business gate carries."""
    if gate == "benchmark_purchases":
        plan = benchmark_purchase_list(db)
        total = plan.get("total_cad")
        n = len(plan.get("picks") or [])
        return {
            "action": (f"Buy the {n} approved MJs benchmark patterns (list with links: "
                       "research/final_build/w4/GATE_CLEARANCE_BUSINESS.md) and upload each "
                       f"download at {INTAKE_PAGE}"),
            "steps": "; ".join(plan["delivery"]["steps"]),
            "max_cost_cad": float(total) if total else None,
            "max_spend_cad": float(total) if total else None,
            "minutes": 5 * max(n, 1) + 10,
            "consequence_of_waiting": ("the benchmark challenge (#168/#315) cannot measure our "
                                       "deliverables against purchased ones, so it stays a "
                                       "release blocker; the teardown lab (#317) has nothing "
                                       "to analyse"),
            "links": [p["url"] for p in plan.get("picks") or []] + [INTAKE_PAGE],
        }
    if gate == "tester_roster":
        from ..quality import tester_programme as tp

        return {
            "action": ("Confirm the tester outreach: post the prepared call for testers "
                       f"({tp.CHANNEL['primary']}) -- text in "
                       "research/final_build/w4/tester_kit/OUTREACH.md. Nothing is sent "
                       "until you confirm"),
            "steps": tp.OWNER_STEPS,
            "max_cost_cad": tp.MAX_COST_CAD, "max_spend_cad": tp.MAX_COST_CAD,
            "minutes": tp.OWNER_MINUTES,
            "consequence_of_waiting": ("no physical proof can exist (#64), the tester "
                                       "roster (#9/#43/#250) stays empty, and every Class B/C "
                                       "product stays blocked from live sale"),
        }
    if gate == "physical_proof":
        from ..quality import tester_kit

        kit = tester_kit.KIT
        return {
            "action": ("Approve commissioning the first agreed independent tester to make "
                       f"{kit['slug']}@{kit['version']} from the printable kit; you are not "
                       "being asked to crochet"),
            "steps": "; ".join(tester_kit.PROTOCOL_STEPS),
            "max_cost_cad": kit["max_cost_cad"], "max_spend_cad": kit["max_cost_cad"],
            "minutes": 5,
            "consequence_of_waiting": (f"{kit['slug']} and its sibling sizes stay blocked "
                                       "from live sale; yardage stays uncalibrated; #64 has "
                                       "no finished-object photograph to upgrade to"),
        }
    if gate == "owned_surfaces":
        inv = owned_surfaces_inventory(db, env)
        return {
            "action": ("The Etsy shop exists (recognised). Still missing, each a person-only "
                       "account opening: " + ", ".join(
                           f"{k} ({v['what']})" for k, v in inv["missing"].items())),
            "steps": "; ".join(f"{k}: {v['owner_step']}" for k, v in inv["missing"].items()),
            "max_cost_cad": inv["max_cost_cad_all"], "max_spend_cad": inv["max_cost_cad_all"],
            "minutes": inv["minutes_all"],
            "consequence_of_waiting": ("free content, pins, video and the email list have "
                                       "nowhere to publish; acquisition is Etsy search only"),
        }
    return {}


def clearance(db, env: dict | None = None) -> dict:
    """Every business gate's clearance state, evidence-read. The GATE_CLEARANCE report body."""
    from . import closure, executor

    out = {}
    for gate in BUSINESS_GATES:
        g = executor.GATE_BY_KEY[gate]
        try:
            opened = bool(g.open(db, env))
        except Exception:  # noqa: BLE001
            opened = None
        kind = closure.kind_of(gate)
        if opened:
            state = CLEARED
        elif kind == closure.DATA_GATED:
            state = DATA_GATED
        elif gate == "second_market_benchmark":
            state = COMPANY_SELECTED
        else:
            state = NOT_YET_ASKABLE if prerequisite(db, gate, env) else OWNER_ACTION
        out[gate] = {"state": state, "kind": kind, "open": opened, "what": g.what,
                     "how_it_is_checked": g.how,
                     "prerequisite": None if opened else prerequisite(db, gate, env),
                     **({} if opened else card_fields(db, gate, env))}
    return out
