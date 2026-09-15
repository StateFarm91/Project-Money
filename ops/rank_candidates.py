#!/usr/bin/env python3
"""Score candidates on the directive's criteria and write research/OPPORTUNITY_RANKING.md.
Scores are the operator's judgement after the sweep and verification searches (Day 1); 0-5 each.
D demand evidence (x3) | R distribution reachable w/o outreach, speed to first 10 (x3) | T time to first revenue (x2; 5=<=14d,4=<=21,3=<=30,2=<=45,1=>45)
P Day-90 net profit potential (x3) | X executability by the AI operator + owner-minimal (x3) | K platform/ToS/approval/legal risk (x2; 5=low)
C competition/differentiation (x2) | A Day-180 asset (x1).  Max 95."""
import json, pathlib
root = pathlib.Path(__file__).resolve().parent.parent
cands = {c["id"]: c for c in json.load(open(root / "research/candidates/candidates.json"))}
W = dict(D=3, R=3, T=2, P=3, X=3, K=2, C=2, A=1)
S = {  # id: (D,R,T,P,X,K,C,A), note
 "C01": ((3,3,1,1,5,4,2,3), "Apify store discovery is real but free-plan runs pay $0; first payout ~Day 45+."),
 "C02": ((2,2,4,2,5,4,1,2), "Config packs compete with free 40k-star repos and with asking Claude to generate them."),
 "C03": ((3,3,2,2,5,4,3,4), "Instant GitHub Marketplace listing; Pro license via Polar; ~Day 35 first revenue; GitHub-native risk."),
 "C04": ((4,3,3,3,3,2,2,4), "Real demand, but probing third-party apps needs ownership verification; crowded free-first scanners."),
 "C05": ((2,2,4,2,5,4,1,2), "Skills are text files any Claude user can generate; no evidence packs sell."),
 "C06": ((4,4,3,2,4,4,3,3), "FINALIST F1. Etsy search demand verified (multiple Canadian T2125/bookkeeping listings, 4.8-star); seller-app API approved in minutes; Etsy Ads after 15-day wait."),
 "C07": ((3,2,2,3,4,4,2,3), "Gumroad supplies no organic traffic; launch-lottery dependence."),
 "C08": ((3,4,3,2,3,4,3,3), "Runner-up: Etsy line extension if F1 works; Notion build friction for the operator."),
 "C09": ((3,3,4,1,4,2,1,2), "TPT algorithmic demotion of AI stores; tens of dollars per month."),
 "C10": ((2,2,3,2,5,4,2,3), "Eloquens traffic unverified; credibility needs a named author."),
 "C11": ((4,3,3,3,4,4,2,5), "FINALIST F2. AODA Dec-31-2026 filing deadline + EAA verified; automated report undercuts $800-2,500 audits; competition confirmed (Decareto, Accessalyze, PageAudit)."),
 "C12": ((1,3,3,1,4,3,1,2), "KILLED by verification: Stripe Invoicing now has native late-fee rules (stripe.com resources, 2026)."),
 "C13": ((3,1,2,2,3,3,3,4), "Restaurant owners unreachable without outreach/Facebook groups."),
 "C14": ((3,2,1,1,2,2,3,4), "Needs a registered business entity; 30-day trial pushes cash past Day 60."),
 "C15": ((3,3,1,1,4,2,1,4), "Shopify review 2-6 weeks + trial => Day 50-60; 573-app category."),
 "C16": ((3,2,1,1,4,4,2,4), "Affiliate approval + SEO ramp beyond Day 45; good Day-180 asset only."),
 "C17": ((3,2,4,2,5,4,3,3), "FINALIST F5 (screened). Huge audience, automatable, but discovery depends on community posting the operator cannot do."),
 "C18": ((3,2,3,1,4,4,1,3), "Four indie clones already on the same free data."),
 "C19": ((3,3,3,2,4,3,1,2), "Extreme POD competition; Q4 timing helps but margins thin."),
 "C20": ((2,3,3,1,4,4,2,3), "KDP payouts 60 days in arrears; tiny velocity."),
 "C21": ((1,2,2,1,4,3,1,1), "50% platform fee; not recommended by its own researcher."),
 "C22": ((2,2,2,1,4,4,2,3), "Chicken-and-egg; 12-18 months to meaningful revenue."),
 "C23": ((3,2,2,2,3,3,3,3), "Homeowner demand needs ads/ranking first; owner-medium."),
 "C24": ((2,2,1,1,4,4,3,4), "Directory traffic takes >90 days."),
 "C25": ((3,2,3,3,4,4,2,3), "Runner-up: SoloPush anecdote relied on founder audience; cold start."),
 "C26": ((2,2,3,2,5,4,3,2), "Low urgency purchase."),
 "C27": ((2,4,3,2,5,3,1,3), "Downgraded by verification: eRank, EtsyHunt, Alura extensions are free/freemium."),
 "C28": ((3,2,3,3,4,4,2,4), "Runner-up: 2.5 months late; Thrilled $29/mo and a dozen vendors own the SERP."),
 "C29": ((2,3,3,2,4,2,3,3), "Obligations bind AI providers more than small deployers; WP.org review."),
 "C30": ((3,3,1,2,3,2,2,4), "Shopify review timeline; POS UI scope."),
 "C31": ((3,2,3,1,5,4,2,3), "Season (Jan-Mar 2027) falls after Day 90."),
 "C32": ((3,2,3,3,4,2,4,3), "Legal-adjacent accuracy risk; low Etsy volume for the term."),
 "C33": ((3,2,3,2,5,4,4,3), "FINALIST F3. Bill 96 enforcement verified (complaint-driven, $3k fines in 2026); fold into F2's scanner as a module rather than standalone."),
 "C34": ((3,3,3,2,4,3,2,4), "CookieYes/Complianz already cover Law 25; sub-1% conversion."),
 "C35": ((2,4,4,1,5,3,1,2), "Downgraded by verification: free 4.9-star competitors with 40k+ users."),
 "C36": ((3,3,1,2,4,2,3,3), "OAuth verification 1-8+ weeks."),
 "C37": ((3,2,4,3,2,3,2,2), "Downgraded by verification: Shopify Translate & Adapt (free) and Weglot ($17/mo) make French cheap; services excluded from MoR; Fiverr needs owner relay."),
 "C38": ((3,2,5,2,2,3,1,2), "Race to the bottom; Fiverr owner relay."),
 "C39": ((3,1,3,2,2,3,2,2), "No-review Upwork profile invisible; owner relay."),
 "C40": ((4,2,3,2,4,3,2,3), "Validated niche but SEO owned by incumbents; OCR/LLM cost."),
 "C41": ((4,2,3,2,5,4,2,3), "FINALIST F4 (screened). Proven paid intent but five paid entrants (ChatToPDF, PrintChat, ProofSnap, WaChat2PDF, whatsanalyze) saturate a new domain."),
 "C42": ((3,2,3,1,4,4,2,2), "Free alternatives good enough for casual users."),
}
rows = []
for cid, (sc, note) in S.items():
    d = dict(zip("DRTPXKCA", sc)); total = sum(d[k] * W[k] for k in W)
    rows.append((total, cid, d, note))
rows.sort(reverse=True)
L = ["# OPPORTUNITY_RANKING — all 42 candidates\n",
     "_Scored 2026-09-15 (Day 1) by the operator after the sweep (`research/candidates/CANDIDATES.md`) and 16 verification searches. Criteria and weights are in `ops/rank_candidates.py`; max score 95. These are judgements, not measurements; the finalist deep-dives in `research/finalists/` carry the labelled uncertainty._\n",
     "| rank | id | candidate | D | R | T | P | X | K | C | A | score | note |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
for i, (total, cid, d, note) in enumerate(rows, 1):
    L.append(f"| {i} | {cid} | {cands[cid]['name'][:60]} | {d['D']} | {d['R']} | {d['T']} | {d['P']} | {d['X']} | {d['K']} | {d['C']} | {d['A']} | **{total}** | {note} |")
L += ["", "## Finalists taken to deep-dive", "",
      "- **F1 = C06** Etsy Canadian small-business finance templates (marketplace-native, fastest credible first revenue).",
      "- **F2 = C11** AODA/WCAG compliance scanner: free scan -> paid readiness report -> monitoring (recurring asset with a dated regulatory driver).",
      "- **F3 = C33** Bill 96 French-content compliance scan (same engine as F2; module, not a standalone business).",
      "- **F4 = C41** Chat export to court-ready PDF (micro-utility; screened out on saturation).",
      "- **F5 = C17** Express Entry draw alerts (screened out on distribution the operator cannot run).",
      "", "Runner-ups kept warm in `BACKLOG.md`: C03 Agent-PR Guard, C08 therapist practice OS (Etsy line extension), C28 PulseNPS, C25 VibeLaunch.",
      "", "## Channel finding that drove the ranking", "",
      "The operator cannot post in communities, run social accounts, or send outreach itself (those need the owner's accounts, and CASL forbids cold contact). The channels it can run end-to-end are: marketplace listings with native buyer search that expose a publishing API (Etsy seller app: approved in minutes; Chrome Web Store API v2; WordPress.org SVN; Apify CLI; GitHub Marketplace), its own domain (SEO, free tools, paid search once the owner opens an ads account), and in-marketplace ads (Etsy Ads). Candidates whose first-10 plan depended on Reddit/Discord posting were marked down on R accordingly."]
(root / "research/OPPORTUNITY_RANKING.md").write_text("\n".join(L) + "\n")
print("\n".join(f"{t:>3} {c} {cands[c]['name'][:60]}" for t, c, _, _ in rows[:12]))
