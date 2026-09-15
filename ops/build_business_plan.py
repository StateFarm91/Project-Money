#!/usr/bin/env python3
"""Build the detailed business plan PDF from the repository state. Usage: .venv/bin/python ops/build_business_plan.py"""
import json, re, pathlib, datetime, csv
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, KeepTogether, ListFlowable, ListItem
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "BUSINESS_PLAN_2026-09-15.pdf"
pdfmetrics.registerFont(TTFont("DV", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DVB", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
NAVY = colors.HexColor("#1F3A5F"); LIGHT = colors.HexColor("#EEF3F8"); CREAM = colors.HexColor("#FFF8DC"); GREY = colors.HexColor("#555555")
ss = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=ss["BodyText"], fontName="DV", fontSize=9.5, leading=13.5, spaceAfter=5)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8, leading=10.5)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=7.8, leading=10, spaceAfter=0)
CELLB = ParagraphStyle("cellb", parent=CELL, fontName="DVB")
H1 = ParagraphStyle("h1", parent=ss["Heading1"], fontName="DVB", fontSize=16, leading=20, textColor=NAVY, spaceBefore=10, spaceAfter=8)
H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName="DVB", fontSize=12, leading=15, textColor=NAVY, spaceBefore=8, spaceAfter=4)
H3 = ParagraphStyle("h3", parent=ss["Heading3"], fontName="DVB", fontSize=10, leading=13, textColor=NAVY, spaceBefore=6, spaceAfter=3)
TITLE = ParagraphStyle("title", parent=ss["Title"], fontName="DVB", fontSize=24, leading=30, textColor=NAVY)
SUB = ParagraphStyle("sub", parent=BODY, fontSize=11, leading=15, textColor=GREY)
NOTE = ParagraphStyle("note", parent=BODY, fontSize=8.5, leading=11.5, textColor=GREY)

S = []
def h1(t): S.append(Paragraph(t, H1))
def h2(t): S.append(Paragraph(t, H2))
def h3(t): S.append(Paragraph(t, H3))
def p(t, st=BODY): S.append(Paragraph(t, st))
def bullets(items, st=BODY):
    S.append(ListFlowable([ListItem(Paragraph(i, st), leftIndent=12) for i in items], bulletType="bullet", leftIndent=14, bulletFontSize=7)); S.append(Spacer(1, 4))
def table(rows, widths=None, header=True, font=CELL, zebra=True):
    data = [[Paragraph(str(c), CELLB if (header and i == 0) else font) for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if header: style += [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
    if zebra:
        for i in range(1 if header else 0, len(rows)):
            if i % 2 == 0: style.append(("BACKGROUND", (0, i), (-1, i), LIGHT))
    t.setStyle(TableStyle(style)); S.append(t); S.append(Spacer(1, 6))
def header_cells_white(t): pass

def on_page(canvas, doc):
    canvas.saveState(); canvas.setFont("DV", 7.5); canvas.setFillColor(GREY)
    canvas.drawString(0.8 * inch, 0.55 * inch, "Project-Money · Claude's entry · Business plan v1 · 2026-09-15 (Day 1)")
    canvas.drawRightString(letter[0] - 0.8 * inch, 0.55 * inch, f"Page {doc.page}")
    canvas.restoreState()

# ---------------- Cover ----------------
S.append(Spacer(1, 1.6 * inch))
S.append(Paragraph("Claude's Entry", TITLE)); S.append(Paragraph("90-Day AI Business Competition", TITLE)); S.append(Spacer(1, 14))
S.append(Paragraph("Business plan, version 1 · Prepared on Day 1 (2026-09-15) by Claude, the autonomous operator", SUB))
S.append(Paragraph("Bankroll: up to CA$1,000 · Period: 2026-09-15 to 2026-12-13 · Owner: Jake (StateFarm91) · Repository: github.com/StateFarm91/Project-Money", SUB))
S.append(Spacer(1, 24))
p("This plan is the operator's own decision, made on the evidence gathered on Day 1 and recorded in the project repository. Every number in it is labelled as either a measured fact with a source, or an estimate. Projections are separated from actuals throughout. The plan changes only through the decision log; the repository is the live version and always wins over this document.", SUB)
S.append(Spacer(1, 30))
p("<b>Contents</b>", BODY)
for i, t in enumerate(["Executive summary", "Mandate, rules and constraints", "Market research: what was investigated and what it showed", "Strategy: two tracks, one setup, hard caps", "Track A: MapleSheets on Etsy", "Track B: Pine and Nook, a paid-social store", "Financial plan", "Milestones and targets", "Operations and automation", "Risks and mitigations", "Compliance and ethics", "What the owner does (and nothing else)", "Decision log", "Appendix A: full candidate ranking", "Appendix B: lessons learned on Day 1", "Appendix C: repository map", "Appendix D: key sources"], 1):
    p(f"{i}. {t}", SMALL)
S.append(PageBreak())

# ---------------- 1. Executive summary ----------------
h1("1. Executive summary")
p("The mission is to build and operate the strongest legitimate business outcome from a maximum of CA$1,000 over 90 days, with minimal owner involvement, against two competing AI entries. The scoreboard is real revenue from real strangers and net profit after fees, advertising and refunds. Nothing else counts.")
p("On Day 1 the operator researched 42 materially different opportunities across 12 market lenses with live web evidence, ranked them on the directive's criteria, deep-dived five finalists, and had an independent adversarial reviewer attack the leading plan. The decisive finding was about distribution: with no audience, no outreach (Canada's anti-spam law forbids cold contact) and no human posting daily, the only channels where buyers are already present and can be reached cheaply within 90 days are marketplaces with native search and paid social advertising. Everything else (software tools, directories, content, lead generation) needs months of search-engine or community presence that cannot be bought in this window.")
p("The plan therefore runs two tracks that share one owner setup:")
bullets(["<b>Track A, MapleSheets on Etsy (the floor).</b> A shop of Canadian small-business templates: a T2125-mapped bookkeeping system, a GST/HST quick-method calculator, home-office and vehicle workbooks, a tax planner, and a print-on-demand line of Canadian gifts. Two products are already built and validated. Etsy supplies the buyers; in-marketplace ads cost cents per click. Base case is modest (CA$300-450 revenue by Day 90) with near-zero downside and a catalogue that peaks in tax season after the competition.",
         "<b>Track B, Pine and Nook (the swing).</b> A Shopify store selling three research-selected physical products to Canada and the US through Meta ads during Q4, fulfilled by suppliers with 3-8 day US-warehouse shipping, with AI-generated creatives and an AI customer-support agent. It is run as a staged experiment: three products at CA$50 of ads each, kill fast; one survivor gets up to CA$250 more, scaled only while measured return holds. Roughly three in four first-time stores lose their test budget; if this one hits, CA$3,000-8,000 of revenue by Day 90 is realistic. The cap is about half the bankroll, so a miss leaves the floor intact and CA$290 in reserve."])
p("Money: Track A up to CA$190, Track B up to CA$520, reserve at least CA$290. Spent to date: CA$0.00. The caps are enforced in code before any budget can be created or raised, and every ad campaign carries a lifetime budget inside Meta so nothing can run away between operator runs.")
p("Owner involvement: one Etsy setup of about 45 minutes, and one store-stack setup of about two hours in three parts. After that the owner reads a weekly summary and answers only identity checks a platform may spring. Operations run unattended through a scheduled operator session three times a day.")
p("What would change the plan: only data. Fewer than 150 Etsy views in the first 14 days reworks the listings before ad spend. No product clearing stage 1 ends Track B. A product clearing it is scaled on measured return and nothing else.")

# ---------------- 2. Mandate ----------------
h1("2. Mandate, rules and constraints")
h2("2.1 The competition")
table([["Item", "Value"], ["Start (recorded)", "2026-09-15 11:00:07 UTC (Day 1)"], ["Official end (Day 90)", "2026-12-13"], ["Unofficial durability review (Day 180)", "2027-03-13"], ["Maximum starting bankroll", "CA$1,000"], ["Stretch target", "CA$25,000+ legitimate economic outcome (a stretch, not a licence for irrational risk)"], ["Competitors", "Claude vs ChatGPT vs Grok, each choosing its own strategy"], ["Scoreboard", "Gross revenue; net profit after platform, payment, advertising, refunds and operating costs; cash and capital deployed; recurring revenue; legitimate customers and unit economics; owner hours; conservative Day-180 asset value"]], [2.2 * inch, 4.6 * inch])
h2("2.2 What the operator can and cannot do")
p("The operator is Claude Code running in a cloud sandbox with web research, code, GitHub, and the ability to schedule itself. It can build and deploy software, generate images and (through paid APIs) video, call any API the owner authorizes, and run unattended on a schedule. It cannot create accounts that need identity verification, pass CAPTCHAs, spend money itself, make phone calls, handle physical goods, or post on social platforms from a personal account. It is not online in real time between scheduled runs, so anything customer-facing that must respond in minutes is built as a deployed service.")
h2("2.3 Owner constraints")
bullets(["The owner runs another business and has a family. Involvement is limited to identity verification, account creation, accepting terms, providing credentials, and authorizing spend. The owner confirmed on Day 1: no restrictions on setup, no operating role.",
         "Jurisdiction is Canada (CAD). CASL forbids unsolicited commercial email or messages, so cold outreach is excluded as a channel. Under CA$30,000 of taxable supplies the business is a GST/HST small supplier; the ledger tracks the threshold.",
         "The operator's compute is rate-limited on the owner's Claude plan (five-hour usage windows). Day 1 lost five hours to this and the operating cadence was redesigned around it."])
h2("2.4 Non-negotiables")
bullets(["Real customers and real revenue only. No circular transactions, fake reviews, fabricated scarcity, invented usage numbers or projections presented as earnings.",
         "An auditable ledger of actual events with evidence references; projections kept in a separate file.",
         "No platform-rule bypass, no secrets in the repository, no legal or financial commitments without the account holder.",
         "Everything customer-facing must be genuinely useful and honest, including delivery times and product claims."])

# ---------------- 3. Research ----------------
h1("3. Market research: what was investigated and what it showed")
h2("3.1 Method")
p("Twelve lens-specific researchers swept the opportunity space with live web search on 2026-09-15: vertical micro-SaaS; digital products on marketplaces; the AI-agent and developer-tool ecosystem; app-store distributed products; AI-fulfilled productized services; content, affiliate and data products; e-commerce and print-on-demand; Canada-specific and regulatory opportunities; first-hand revenue reports of what made money fast in 2025-26; arbitrage from 2026 shutdowns and rule changes; consumer micro-utilities with search intent; and niche marketplaces, directories and lead generation. They produced 42 materially different candidates, each with evidence URLs labelled as evidence or assumption, capital and time-to-revenue estimates, a first-10 and first-100 customer plan, and the single biggest failure reason. Sixteen verification searches then checked the facts that decided the ranking, five finalists were deep-dived, and an adversarial reviewer attacked the leading plan with its own searches.")
h2("3.2 Findings by lens (the parts that mattered)")
bullets(["<b>Marketplaces split into two kinds.</b> Etsy, Teachers Pay Teachers, Eloquens and the Notion Marketplace have built-in buyer search; Gumroad and Lemon Squeezy do not. Gumroad's own 2026 data: median creator earns US$72/month, 44% of products earn nothing, and its discovery feed is closed to products without prior sales. Etsy's digital downloads are not held in payment reserves and its seller API is approved in minutes for an owner's own shop.",
         "<b>Platform review queues decide 90-day feasibility.</b> Chrome Web Store 1-3 days; Stripe App Marketplace about 4 business days; WordPress.org 1-10 days; Shopify App Store 2-6 weeks; Atlassian 10-15 business days plus a required business entity and a mandatory 30-day trial; Google Workspace add-ons need OAuth verification that can take weeks.",
         "<b>The AI-agent tool ecosystem is supply-heavy and thin on paying demand.</b> Anthropic's plugin marketplaces have no payment layer, the biggest 'products' are free repositories with tens of thousands of stars, and fewer than 5% of MCP servers are monetized. Anything that is 'just configuration' competes with free.",
         "<b>Regulatory deadlines are the strongest 2026 demand drivers found.</b> The European Accessibility Act has been enforceable since June 2025; Ontario organizations with 20+ employees must file an AODA compliance report by 2026-12-31 (the website WCAG obligation applies to 50+ employees); Quebec's Bill 96 is complaint-driven with first-offence fines around CA$3,000 for English-only web content; Stripe Invoicing now has native late fees, which killed one candidate.",
         "<b>E-commerce realities.</b> TikTok Shop is not available in Canada. Redbubble takes 50% from standard-tier artists since September 2025. KDP publishers earn US$0-30/month in their first six months. Print-on-demand through Printify with Canadian providers yields 30-50% margins and 4-8 day domestic shipping. For paid-social dropshipping, a rigorous single-product test costs about CA$667 of ads, first-timers who sustain spend succeed about 18% of the time within 90 days, and profitable stores net 15-35%.",
         "<b>What made money fast in 2025-26 (first-hand reports).</b> Launch and listing platforms monetized by featured slots (one reached US$2,000 MRR in 19 days, with an existing audience), pay-once utilities with near-zero costs, and developer APIs sold by building in public. The median path to US$1,000 MRR is still 12-18 months.",
         "<b>Canada-specific.</b> Canadian fintech affiliate programs pay unusually well (up to CA$1,250 per funded client) but approvals and search ranking put first revenue past Day 45; Quebec's Bill 96 created demand for bilingual documents and French-content checks; Canadian bookkeeping templates already sell on Etsy with 4.8-star listings and few Canadian-specific competitors."])
h2("3.3 Ranking criteria")
p("Each candidate was scored 0-5 on eight criteria with weights reflecting the directive: demand evidence (3), distribution reachable without outreach and speed to the first ten customers (3), time to first revenue (2), Day-90 net-profit potential (3), executability by the operator with minimal owner time (3), platform, terms-of-service, approval and legal risk (2), competition and differentiation (2), and Day-180 asset value (1). Candidates whose first-customer plan depended on posting in communities were marked down, because the operator cannot do that and the owner should not have to. The full table is in Appendix A.")
h2("3.4 Finalists and what the adversarial review changed")
table([["Finalist", "Verdict", "Why"],
       ["Etsy shop of Canadian small-business templates", "Selected (Track A)", "Verified buyer search on Etsy, seller API approved in minutes, cheap in-marketplace ads; downgraded to a modest, roughly break-even base case because Sept-Dec is off-season for tax templates and a zero-review shop converts below average"],
       ["AODA/WCAG accessibility scanner (free scan, paid report, monitoring)", "Rejected as a track; backlog only", "The Dec-31 filing for 20-49 employee organizations is a self-attestation with no website check; automated reports are a commodity with free scanners from major vendors; a CA$100 search-ads test cannot signal at CA$3-5+ per click; a new domain will not rank inside 90 days"],
       ["Bill 96 French-content scan and translation pack", "Parked", "Shopify's free Translate & Adapt and CA$17/month apps make French cheap; no evidence of paid intent; services are excluded from merchant-of-record payment providers"],
       ["Chat export to court-ready PDF", "Screened out", "Proven paid intent but five active entrants in 18 months saturate the search results a new domain would need"],
       ["Express Entry draw alerts", "Screened out", "Huge audience and fully automatable, but every first-customer path runs through community posting the operator cannot do"],
       ["Paid-social dropshipping store", "Added as Track B after the owner removed setup restrictions", "Excluded at first for owner time, no video capability and no support capacity; re-evaluated once an AI support agent, AI video and unrestricted accounts were on the table; kept only with hard stage gates because of its base rate"]], [1.9 * inch, 1.3 * inch, 3.6 * inch])
h2("3.5 What was excluded and why")
bullets(["<b>Amazon:</b> its policy forbids the third-party-fulfilled dropshipping model; FBA needs inventory capital (a single product order would consume the bankroll) and 3-5 weeks of lead time before any sale.",
         "<b>TikTok Shop:</b> not launched in Canada; workarounds risk account termination. TikTok ads are deferred until Meta results exist.",
         "<b>Organic social (TikTok, Instagram, Reddit):</b> requires a human posting from personal accounts daily; the owner has no operating role and the operator cannot post.",
         "<b>Cold outreach of any kind:</b> CASL.",
         "<b>Software tools, directories, job boards, content sites:</b> first revenue past Day 45 or dependent on search ranking that takes months; several kept warm in the backlog for Day 180."])

# ---------------- 4. Strategy ----------------
h1("4. Strategy: two tracks, one setup, hard caps")
p("The strategy is a portfolio chosen for probability-weighted outcome with the bankroll protected: a high-probability, low-cost floor that compounds, and a capped swing with the only ceiling worth having inside 90 days. Both use the only two channels with present buyers and cheap access. Both are run by the operator end to end after a single owner setup.")
table([["", "Track A: MapleSheets (Etsy)", "Track B: Pine and Nook (Shopify + Meta ads)"],
       ["Role", "Floor and compounding asset", "Swing with stage gates"],
       ["Customers", "Canadian sole proprietors, freelancers, Etsy/Shopify sellers doing their own T2125 bookkeeping; gift buyers for the print-on-demand line", "Consumers in Canada and the US buying impulse-priced physical products in Q4"],
       ["Distribution", "Etsy search, Etsy Ads (US$0.20-0.60 per click), reviews compounding", "Meta Advantage+ shopping campaigns with lifetime-capped budgets; AI-generated video and image creatives"],
       ["Fulfilment", "Etsy delivers files; Printify prints and ships gifts", "CJ Dropshipping US warehouses (3-8 days) or Canadian suppliers; tracking synced to the store"],
       ["Support", "Etsy messages, replies drafted by the operator", "AI support agent (email) with order lookup; escalation to the operator within 8 hours"],
       ["Capital cap", "CA$190 (setup CA$40, ads up to CA$150)", "CA$520 (tools CA$90-120, stage 1 ads CA$150, stage 2 ads CA$250, one sample)"],
       ["P(first revenue within 30 days of launch)", "About 40%", "About 55% (sales come fast when ads work; profit is the hard part)"],
       ["Day-90 base case", "CA$300-450 revenue, about break-even to +150 net", "CA$400-900 revenue, about -150 to +150 net"],
       ["Day-90 upside", "CA$1,200-1,800 revenue", "CA$3,000-8,000 revenue, +600 to +2,000 net"],
       ["Downside", "About -CA$250", "About -CA$450"],
       ["Kill rule", "<150 views in 14 days: rework before ads; 100 ad clicks with no sale: stop ads", "Per product: CA$50 spent with no purchase, or 60 clicks with no add-to-cart; track: no product passes stage 1"]], [1.2 * inch, 2.75 * inch, 2.85 * inch])
p("Why not one track. The floor alone cannot produce a competitive outcome; the swing alone risks the bankroll on a bad base rate. Together, the worst case preserves the reserve and a compounding catalogue, and the best case is a real number. Why not other swings: nothing else in the 42 candidates combines present buyers, cheap access and a 90-day window.")

# ---------------- 5. Track A ----------------
h1("5. Track A: MapleSheets on Etsy")
h2("5.1 Products")
table([["#", "Product", "Price (CAD)", "Status"],
       ["1", "Canadian Sole Proprietor Bookkeeping System, T2125 edition 2026 (Excel + Google Sheets): income and expense ledgers mapped to every T2125 Part 4 line, sales tax by province (GST/HST/PST/RST/QST), home-office Part 7 with the loss cap and carry-forward, vehicle Chart A, regular-vs-quick-method GST/HST comparison with RC4058 rates and the 1% credit, $30,000 small-supplier tracker, dashboard; quick-start PDF and README", "29", "Built; validated (0 formula errors across 6,122 cells; key values verified); packaged with six listing images"],
       ["2", "GST/HST Quick Method vs Regular Method Calculator + Small-Supplier Tracker (standalone), including a voluntary-registration worksheet", "14", "Built; validated; packaged with three images"],
       ["3", "Home-office and vehicle expense workbook (Part 7 + Chart A) with printable logbook", "12", "Specified"],
       ["4", "Self-employed tax set-aside and instalment planner (2026 brackets verified before build)", "12", "Specified"],
       ["5", "Bundle of 1-4", "44", "After 1-2 are live"],
       ["6", "Print-on-demand line: personalized Canadian gifts (mugs, prints, totes) via Printify with Canadian print providers; automated personalization from the order field", "24-34", "Backlog; needs the owner's Printify connection"],
       ["7", "Line extensions chosen from Etsy API data: Shopify/Etsy-seller variant, therapist and allied-health practice templates", "29-49", "After the 14-day test"]], [0.3 * inch, 4.3 * inch, 0.8 * inch, 1.4 * inch])
p("Every rate and line number was checked against CRA pages on 2026-09-15 (RC4058 quick-method tables, T2125 Part 4 and Part 7, the small-supplier rule, provincial rates including Nova Scotia's 14% HST). Workbooks use only functions that behave identically in Excel and Google Sheets, carry a version stamp and a plain-language disclaimer, and are validated by an automated formula evaluator before release. AI assistance is disclosed per Etsy's Creativity Standards; the formulas and testing are the selling point.")
h2("5.2 Economics")
bullets(["Etsy fees for a Canadian seller: listing US$0.20, 6.5% transaction, 3% + CA$0.25 processing, GST/HST on Etsy's fees, one-time shop setup fee of US$15-29. Net on a CA$29 sale is about CA$25.70 before ads (about 89%).",
         "Etsy Ads: minimum US$1/day; new shops wait 15 days before ads; digital products convert at roughly 2-5% of clicks. Plan: CA$3/day on the single best listing from about Day 21; kill at 100 clicks with no sale; raise in CA$2/day steps only at ROAS above 2. Total ads capped at CA$150-200.",
         "Base case: 11-16 sales by Day 90 at about CA$28 average, revenue CA$300-450, net about break-even to +150 after fees, ads and setup. Upside: a listing that ranks plus Q4 'get ready for the 2026 tax year' demand, CA$1,200-1,800. Downside: about -250. Tax season (Feb-Apr 2027) is the peak for this catalogue and falls after Day 90; it is the Day-180 payoff."])
h2("5.3 Distribution and the 14-day test")
p("First ten customers come from Etsy search: titles, 13 tags and attributes built from competitor keyword neighbourhoods pulled through the Etsy API, six images per listing, honest descriptions. The most important test in the plan (EXP-001) asks whether Etsy search shows a zero-review Canadian listing to real buyers: by the 14th day the shop is live, at least 150 views and either a sale or five favourites. Pass: fund ads and the bundle. Fail: rewrite titles and tags from competitor data and swap products before any ad spend. First hundred customers: reviews compounding rank, the bundle, weekly title and tag rewrites from API view data, more products in the same shop (they inherit the shop's reviews), and the print-on-demand line for Q4 gifting.")
h2("5.4 Operations")
p("Workbooks are generated and tested by code; listings are created and updated through the Etsy API with a seller app the owner registers once; images are rendered programmatically; Etsy delivers files and receipts; a daily API pull writes views, favourites and orders to the dashboard; ledger rows come from Etsy Payments statements. The operator drafts replies to buyer messages for the owner to paste (Etsy has no messaging API); such messages are rare for digital products.")

# ---------------- 6. Track B ----------------
h1("6. Track B: Pine and Nook, a paid-social store")
h2("6.1 Model")
p("A single-brand Shopify store (brand name Pine and Nook, backup Wren Porch, both checked for conflicting businesses; a trademark search precedes the domain purchase) selling three tested physical products to consumers in Canada and the US, acquired through Meta ads, fulfilled without inventory by suppliers stocked in US warehouses or in Canada, supported by an AI agent. Q4 2026 (gifting, winter, Black Friday, holidays) falls inside the window and is the strongest season for this model.")
h2("6.2 Product selection")
p("Products are chosen from evidence rather than instinct: paid ads that have run 30+ days in consumer niches (someone is profiting), supplier availability with 3-8 day delivery, marketplace demand signals, and a legitimacy filter (no licensed characters or look-alikes, no health or beauty claims, no fragile or battery-certified electronics, no sizing-dependent apparel, honest delivery times). Retail CA$25-60, landed cost at most one third of retail, contribution margin after cost of goods at least 60% so ads can run at 40% of revenue or less. The Day-1 research shortlisted eight and recommended three across unrelated demand drivers:")
table([["Product", "Category", "Retail (CAD)", "Evidence", "Risk"],
       ["Cocktail smoker kit (wood-only, torch-free SKU from a US warehouse)", "Bar and gifting", "49", "Strongest: an Amazon US market report shows top-10 listings averaging about 1,480 units/month at US$33, the leader about 7,000/month; four independent 2026 buying guides; a CJ winning-products feature", "Competition from Amazon Prime; must avoid glass and torch SKUs"],
       ["Magnetic windshield snow and ice cover", "Auto and winter (Canada-specific)", "39", "Presence-based: a decade-old Amazon listing still active, '2026 New' listings, big-box retailers, and at least two single-product Shopify brands (the footprint of paid-social sellers); no sales counts found", "Seasonal timing; test reads better after first frost; geo-target Canada and the northern US"],
       ["Self-cleaning pet slicker brush + undercoat rake bundle", "Pets", "39", "Two independent 2026 supplier guides agree on cost (US$3-9) and retail (US$22-30); multiple supplier listings verified", "Saturation and low average order value, hence the bundle"],
       ["Alternate: oversized hooded wearable blanket", "Home comfort", "45-55", "Strong Q4 demand", "Likely fails the landed-cost rule on shipping weight unless a US-warehouse SKU lands at or below US$14"]], [1.7 * inch, 1.0 * inch, 0.6 * inch, 2.3 * inch, 1.2 * inch])
p("Supplier pages block automated fetches, so landed costs and warehouse stock are assumptions until the CJ API key exists; the three picks are re-confirmed or swapped at that point, and one sample of any product that scales is ordered (at most CA$30) to verify quality.", NOTE)
h2("6.3 Store, creatives, ads")
bullets(["<b>Store:</b> Shopify on the CA$1/month promotional plan (Basic is CA$68/month after three months), built through the Admin API: products, honest shipping profiles (supplier estimate plus two days), refund and privacy policies, markets for Canada (CAD) and the US (USD), pixel installed, a support address on the store's own domain.",
         "<b>Creatives:</b> image ads composed programmatically (1080x1080 and 1080x1350; product, benefit headline, price, trust line; four variants per product) and 5-10 second videos generated from supplier photos through fal.ai (Kling or Wan models at roughly US$0.03-0.08 per second) then cut, captioned and exported in 9:16 and 1:1 with ffmpeg; two to three variants per product at a target cost under US$2 per product. Honest claims only; delivery time stated on the landing page.",
         "<b>Ads:</b> Meta Advantage+ shopping campaigns through the Marketing API on the owner's own ad account (no app review needed; a non-expiring system-user token), one ad set per product with a lifetime budget and end date, purchase optimization on the pixel, insights pulled daily into the dashboard. TikTok ads are deferred until Meta results exist.",
         "<b>Support agent:</b> inbound email on the store domain routed to a Cloudflare Worker that stores the message, looks up the order in Shopify and tracking at the supplier, and answers with the Anthropic API (Haiku 4.5, about half a cent per reply) for tracking, delivery-time, address-change, cancellation and in-policy refund requests, issuing refunds through Shopify where policy allows. Anything else is escalated to the next operator run (within 8 hours). Chargebacks are handled through Shopify Payments disputes with tracking evidence."])
h2("6.4 Stage gates")
table([["Stage", "Budget", "Rule", "Pass", "Fail"],
       ["1 (about Days 10-24)", "Three products at CA$15/day, lifetime cap CA$50 each (CA$150)", "Kill a product at CA$50 spent with zero purchases, or at 60 clicks with zero add-to-carts", "Any product with at least two purchases and ROAS at or above 1.2", "All three killed: Track B stops, remaining budget returns to reserve, store stays up passively"],
       ["2", "Up to CA$250 more on the passing product", "Raise budget 30% every three days while ROAS stays at or above 1.6; retire the others", "ROAS at or above 1.6 sustained on 20+ purchases; refund rate under 8%; delivery complaints under 5%", "ROAS under 1.2 over any CA$80 of spend stops scaling; under 1.0 kills"],
       ["Scale", "Reinvested proceeds only", "Add creatives, a second country or product; raise operator cadence", "Measured return holds", "Any gate fails"]], [0.9 * inch, 1.5 * inch, 1.7 * inch, 1.4 * inch, 1.3 * inch])
h2("6.5 Economics")
table([["CAD", "Downside (~75%)", "Base", "Upside (~15%)"], ["Revenue by Day 90", "0-150", "400-900", "3,000-8,000"], ["Ads", "150", "300-400", "400 plus reinvested proceeds"], ["Tools (Shopify promo, domain, fal.ai, Anthropic credits)", "90", "90", "90-150"], ["Cost of goods (about 35% of revenue)", "0-50", "140-315", "1,050-2,800"], ["Net", "-450", "-150 to +150", "+600 to +2,000"]], [2.6 * inch, 1.4 * inch, 1.4 * inch, 1.4 * inch])
p("These are honest odds, not a pitch. The base rate for first-time paid-ads stores is poor; research-driven product selection, honest listings, fast iteration and Q4 seasonality improve it but do not remove it. The cap and the gates exist so that the likely miss costs a bounded amount while the floor keeps running.")

# ---------------- 7. Financial plan ----------------
h1("7. Financial plan")
h2("7.1 Capital allocation (CAD)")
table([["Bucket", "Cap", "Release condition"], ["Track A: Etsy setup, listing fees, Printify (free)", "40", "Owner Block 1"], ["Track A: Etsy Ads", "150 (hard guard 200)", "Only after the 14-day visibility test passes"], ["Track B: tools (Shopify promo, domain, fal.ai credits, Anthropic credits)", "90-120", "Owner Block 2"], ["Track B: stage 1 ads", "150", "Launch checklist complete"], ["Track B: stage 2 ads", "250", "A product passes stage 1"], ["Track B: one product sample", "30", "A product is scaling"], ["Reserve", "at least 290", "Never below this floor; growth capital only on measured return"], ["Total", "1,000", ""]], [3.4 * inch, 1.2 * inch, 2.2 * inch])
p("Caps are enforced by a module every budget change must pass; it reads actual spend from the ledger first and refuses any increase that would exceed a track's cap or breach the reserve floor. Meta campaigns are created only with lifetime budgets and end dates. Etsy Ads budgets are set by the owner once per instruction.")
h2("7.2 Combined projection (CAD, Day 90)")
table([["Scenario", "Track A net", "Track B net", "Combined", "Notes"], ["Downside (both fail)", "-250", "-450", "about -700", "Reserve and the Etsy catalogue preserved; Track B store stays up at CA$1/month"], ["Base", "0 to +150", "-150 to +150", "-100 to +300", "Etsy sells 11-16 units; one store product converts marginally or none does"], ["Upside", "+900 to +1,300", "+600 to +2,000", "+1,500 to +3,300", "A ranking Etsy listing plus a store product scaling on measured return; revenue CA$4,000-10,000"]], [1.2 * inch, 1.0 * inch, 1.0 * inch, 1.0 * inch, 2.6 * inch])
p("The stretch target of CA$25,000 is not the base case. It becomes reachable only in the upside path with reinvested proceeds and a second scaling product; the plan does not assume it and does not take irrational risk to chase it.")
h2("7.3 Unit economics")
bullets(["Etsy template at CA$29: net about CA$25.70 before ads; ad-driven customer acquisition cost of CA$5-15 in the base case; payback immediate.",
         "Store product at CA$40 with CA$13 landed cost and 2.9% + CA$0.30 processing: about CA$25 to cover ads and profit; break-even ROAS about 1.6; target ROAS 2.0 or better before scaling.",
         "Support agent: about CA$0.007 per reply; Meta creatives: under CA$3 per product for videos; Shopify: CA$3 for the whole window on the promotional plan."])
h2("7.4 Ledger discipline and tax")
p("The ledger records actual events only, one row per event with an evidence reference (receipt, payout report, statement) and running available cash. Projections live in a separate file and never mix with actuals. Revenue is recorded when the platform confirms the sale; fees and payouts when they post. Under CA$30,000 of worldwide taxable supplies the business is a GST/HST small supplier and need not register; the workbook line and the ledger track the threshold, and the operator alerts the owner at CA$25,000. Records are kept for six years as the CRA requires. Etsy and Shopify Payments handle card processing; merchant-of-record services were researched (Stripe Managed Payments recommended if an own-domain digital checkout is ever needed) but are not required for this plan.")

# ---------------- 8. Milestones ----------------
h1("8. Milestones and targets")
table([["Day", "Date", "Track A (Etsy)", "Track B (store)", "Owner"],
       ["1", "2026-09-15", "Two products built and validated; API client tested; heartbeat live", "Research done: 3 products, brand, spec, caps", "Read the plan; do Block 1 and Block 2 when convenient"],
       ["7", "2026-09-21", "Shop live, OAuth done, competitor data pulled, listing 1 published", "Store clients built; products verified against supplier data; creatives in production", "Blocks done"],
       ["14", "2026-09-28", "Listings 1-2 and bundle live; at least 50 views; 14-day test running", "Store live with policies, pixel, support agent tested; launch checklist passed; stage 1 ads live", "Nothing"],
       ["30", "2026-10-14", "14-day test evaluated; ads on; first sale; four listings; print-on-demand designs live", "Stage 1 decided (kill or pass); stage 2 started if a product passed", "Turn on Etsy Ads (5 min)"],
       ["60", "2026-11-13", "At least 8 sales (base); ads ROAS measured; line-extension decision", "Stage 2 decided; scaling on measured return or track closed; Black Friday creatives ready", "Nothing"],
       ["90", "2026-12-13", "At least 12 sales, 3 reviews, CA$300-450 revenue (base); Day-180 tax-season plan", "Final numbers; store kept or wound down on evidence", "Final report"]], [0.4 * inch, 0.8 * inch, 2.0 * inch, 2.1 * inch, 1.5 * inch])

# ---------------- 9. Operations ----------------
h1("9. Operations and automation")
h2("9.1 The operating loop")
p("Observe, analyze, prioritize, execute, test, measure, document, iterate. Every session starts by reading the current state, priorities, owner actions and experiments from the repository, and ends by updating them, so any future context resumes without chat memory. Phases are organizational only; nothing waits for the owner to say 'continue'.")
h2("9.2 Unattended operation")
bullets(["A scheduled Routine wakes a persistent operator session at 00:14, 08:14 and 16:14 UTC. Each run pulls the working branch, takes a lease lock so two sessions never edit at once, does the highest-value unblocked work (stats pulls, listing updates, creatives, ad-set gate rules, support escalations, ledger rows), persists state and pushes. The mechanism was verified on Day 1 by a real commit from the operator session.",
         "Hard caps live in Meta (lifetime budgets, end dates) and Etsy (daily budget set once), so spending cannot run away between runs. A kill switch pauses every ad set if return data is missing or the ledger is inconsistent.",
         "External writes record an idempotency key before execution, so reruns never duplicate a listing, an order or a campaign.",
         "The owner can pause or delete the Routine at any time from the Routines page; a failed run shows there and the next run continues from the repository.",
         "Compute is rate-limited (five-hour windows). Day 1's heavy research fan-out hit the limit and cost five idle hours; the plan now budgets research and build work per window and persists partial results early."])
h2("9.3 Monitoring and reporting")
p("The dashboard carries the directive's fields: day number, starting capital, available cash, capital deployed, gross revenue, expenses, realized net profit, customers and orders, recurring revenue, acquisition cost, conversion, average order value, best product, best channel, active experiments, biggest bottleneck, Day-90 projection with assumptions, and owner time this week. Values are measured or N/A, never invented. When the owner asks 'Status?', a script prints the operator report from committed state.")

# ---------------- 10. Risks ----------------
h1("10. Risks and mitigations")
table([["Risk", "Likelihood", "Mitigation"],
       ["Etsy search never surfaces a zero-review shop", "Medium", "14-day test before any ad spend; competitor keyword data from the API; bundle and images; product swaps; reviews compound"],
       ["Etsy account review or AI-content policy friction", "Low-medium", "AI assistance disclosed correctly; tested formulas as the selling point; owner answers any review request with drafted text"],
       ["A wrong tax rate produces a one-star review", "Low", "Every rate cross-checked against CRA pages with sources; automated evaluator; version stamp; no-argument refunds"],
       ["No store product converts (the base rate)", "High", "Capped stage 1 (CA$150); research-driven selection; kill fast; the floor keeps running"],
       ["Ad account or Business Manager restrictions from Meta", "Medium", "Honest creatives and landing pages; real policies; no prohibited claims; verification completed by the owner up front"],
       ["Supplier delays or stock-outs", "Medium", "US-warehouse or Canadian suppliers only; delivery times stated honestly; tracking synced; refunds issued within policy"],
       ["Refunds and chargebacks", "Medium", "Clear policies; support agent resolves fast; disputes answered with tracking evidence; refund rate is a stage-2 gate"],
       ["Compute rate limits stall operations", "Medium", "Three runs per day sized to the window; caps and kill rules live inside the platforms, not in sessions"],
       ["Credentials expire or break (Etsy refresh token 90 days, tokens rotated)", "Medium", "Expiry tracked; the operator asks the owner before expiry; no secrets in the repository"],
       ["Owner unavailable for days", "Expected", "Everything after setup runs without the owner; owner-only needs are batched and logged"]], [2.3 * inch, 0.8 * inch, 3.7 * inch])

# ---------------- 11. Compliance ----------------
h1("11. Compliance and ethics")
bullets(["No fake reviews, testimonials, customers or usage numbers; no fabricated scarcity; no misleading claims. Delivery times are stated from supplier data plus a buffer.",
         "No spam. CASL: no unsolicited commercial messages; the support agent answers only inbound messages and sends no marketing.",
         "Platform rules respected: Etsy Creativity Standards (AI disclosure), Meta advertising policies, Shopify and supplier terms, Amazon excluded because its policy forbids the model.",
         "No infringing assets: product selection rejects licensed characters, brand look-alikes and trademarked designs; brand names are conflict-checked; supplier photos are used within the rights suppliers grant for listings.",
         "Tax and records: small-supplier threshold tracked; six-year record retention; ledger with evidence.",
         "Privacy: only public pages are scanned by any tool; a privacy policy on the store; customer data stays in Shopify and the support database.",
         "Secrets: never in the repository; environment variables and GitHub Actions secrets only."])

# ---------------- 12. Owner actions ----------------
h1("12. What the owner does (and nothing else)")
p("Two setup blocks, then a weekly summary. Detailed click-by-click steps are in the repository file OWNER_ACTIONS.md; this section is the summary.")
h2("Block 1: Etsy (about 45 minutes; one-time fee of about CA$20-40)")
bullets(["Create the shop at etsy.com/sell: Canada, CAD, English. Name MapleSheets (then LoonieBooks, then TrueNorthSheets).", "Create one placeholder digital listing so Etsy lets the shop open (Claude replaces it via the API).", "Complete Etsy Payments: bank details, identity (photo ID and selfie), the setup fee, seller terms.", "Register a seller API app named MapleSheets Ops at etsy.com/developers/register; put the keystring in the Claude Code environment as ETSY_KEYSTRING.", "Say 'Etsy ready' in a session; open the authorization link Claude posts; paste back the URL you land on; add the ETSY_REFRESH_TOKEN Claude returns.", "Optional (10 minutes, free): Printify account connected to the Etsy shop, API token as PRINTIFY_TOKEN.", "Later, five minutes each when asked: turn on Etsy Ads at CA$3/day; paste drafted replies to any buyer message."])
h2("Block 2A: Shopify and supplier (about 40 minutes)")
bullets(["Shopify free trial at shopify.com/ca with a placeholder store name; choose Basic on the CA$1/month-for-three-months offer.", "Activate Shopify Payments (identity, bank).", "Create a custom app named Operator with the Admin API scopes listed in OWNER_ACTIONS.md; add SHOPIFY_ADMIN_TOKEN and SHOPIFY_STORE_DOMAIN.", "Free CJ Dropshipping account; API key as CJ_API_KEY; install the CJ app on the store."])
h2("Block 2B: domain, hosting, support agent (about 30 minutes)")
bullets(["Cloudflare account with your card; accept the domain registration agreement and set a registrant contact; API token with Workers, D1, DNS, Email Routing and Registrar permissions as CLOUDFLARE_API_TOKEN, plus CLOUDFLARE_ACCOUNT_ID. Claude then buys the .com (about CA$15) itself after a trademark check.", "Anthropic API: US$25 of credits, a US$40 monthly spend limit, auto-reload off, key as ANTHROPIC_API_KEY."])
h2("Block 2C: ads and video (about 45 minutes)")
bullets(["Meta Business Manager with a Page for the brand, an ad account in CAD with a payment method, any verification Meta asks for.", "A Meta developer app with the Marketing API, a system user with ads_management, ads_read, business_management, pages_read_engagement and pages_manage_ads, a never-expiring token as META_SYSTEM_TOKEN; plus META_AD_ACCOUNT_ID, META_PAGE_ID and a pixel as META_PIXEL_ID.", "fal.ai account with US$25 of credits; key as FAL_KEY."])
p("Money: no transfers. Etsy, Shopify, Meta and the two API providers bill the cards you put on file; Claude caps and logs every charge. Total setup cost now: about CA$20-40 (Etsy) plus CA$1 (Shopify) plus about CA$70 of API credits; everything else is spent only under the caps above.")

# ---------------- 13. Decision log ----------------
h1("13. Decision log (Day 1)")
dl = (ROOT / "DECISION_LOG.md").read_text()
rows = [["#", "Decision", "Why"]]
for line in dl.splitlines():
    if line.startswith("| D-"):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 4: rows.append([cells[0], re.sub(r"\*\*|`", "", cells[2])[:420], re.sub(r"\*\*|`", "", cells[3])[:420]])
table(rows, [0.5 * inch, 3.3 * inch, 3.0 * inch])

# ---------------- Appendix A ----------------
S.append(PageBreak()); h1("Appendix A: full candidate ranking (42)")
p("Criteria: D demand evidence (x3), R distribution reachable without outreach (x3), T time to first revenue (x2), P Day-90 net-profit potential (x3), X executability by the operator (x3), K platform and legal risk (x2), C competition and differentiation (x2), A Day-180 asset (x1). Maximum 95. Scores are the operator's judgement after verification searches; full notes are in research/OPPORTUNITY_RANKING.md.", NOTE)
rk = (ROOT / "research" / "OPPORTUNITY_RANKING.md").read_text()
rows = [["Rank", "Id", "Candidate", "Score", "Note"]]
for line in rk.splitlines():
    if re.match(r"^\| \d+ \| C\d\d \|", line):
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        rows.append([c[0], c[1], c[2], re.sub(r"\*\*", "", c[11]), c[12][:260]])
table(rows, [0.45 * inch, 0.45 * inch, 2.1 * inch, 0.5 * inch, 3.3 * inch])

# ---------------- Appendix B ----------------
h1("Appendix B: lessons learned on Day 1")
ll = (ROOT / "LESSONS_LEARNED.md").read_text()
for m in re.finditer(r"### (LL-\d+: .*?)\n(.*?)(?=\n### |\Z)", ll, re.S):
    h3(m.group(1)); p(re.sub(r"^- ", "", m.group(2).strip().replace("\n- ", " "), flags=re.M).replace("`", ""), SMALL)

# ---------------- Appendix C ----------------
h1("Appendix C: repository map")
table([["File or folder", "Purpose"], ["COMPETITION_RULES.md", "Immutable rules and the start timestamp"], ["MASTER_STRATEGY.md", "This is Claude's competition strategy (both tracks, gates, capital)"], ["CURRENT_STATE.md, CURRENT_PRIORITIES.md, BACKLOG.md", "Operational state and the self-directed work queue"], ["finance/FINANCIAL_LEDGER.csv, finance/PROJECTIONS.md", "Actual events only; projections kept separate"], ["KPI_DASHBOARD.md", "Measured metrics; N/A where no data exists"], ["EXPERIMENTS.md", "EXP-001 Etsy visibility test; EXP-002 Etsy Ads; EXP-003 deferred scanner pre-test; EXP-004/005 store stage gates"], ["DECISION_LOG.md, LESSONS_LEARNED.md", "Why things changed; reusable evidence"], ["OWNER_ACTIONS.md, CREDENTIALS_SETUP.md", "The only things the owner must do; integration status (never secrets)"], ["AUTOMATIONS.md, ops/", "Heartbeat Routine, lease lock, money caps, status and ledger scripts"], ["research/", "42 candidates with evidence, ranking, finalist deep-dives, adversarial review"], ["products/etsy-templates/", "Workbook generators, validators, Etsy API client, listing copy, packages and images"], ["products/store/", "Store product research and the store stack specification"], ["docs/", "Owner directive, infrastructure research, this plan"]], [2.6 * inch, 4.2 * inch])

# ---------------- Appendix D ----------------
h1("Appendix D: key sources")
p("All sources are listed with the claims they support in research/candidates/CANDIDATES.md, research/finalists/, research/ADVERSARIAL_REVIEW.md, products/etsy-templates/TAX_REFERENCE.md, products/store/PRODUCT_RESEARCH.md and docs/infra/. The most load-bearing ones:", SMALL)
bullets(["CRA: RC4058 Quick Method of Accounting for GST/HST; Form T2125 expenses section and business-use-of-home pages; GST/HST registration (small-supplier rule); business records retention.",
         "Etsy: seller fees for Canadian sellers, new-shop setup fee and verification, Etsy Ads minimums and the 15-day wait, Creativity Standards for AI-assisted digital downloads, Open API v3 (seller apps approved in minutes).",
         "Ontario AODA 2026 reporting deadline and thresholds (McCarthy Tetrault, Ogletree, Level Access); FTC order against accessiBe (no automated-compliance claims).",
         "Shopify Canada pricing (CA$1/month promotion, Basic CA$68/month); Meta Marketing API access for own ad accounts via system-user tokens; CJ Dropshipping warehouses and delivery times; Spocket and Syncee Canadian suppliers; fal.ai and Replicate video pricing; TikTok Shop Canada status.",
         "Dropshipping economics 2026 (testing budgets, 18% first-timer success at 90 days, 15-35% net margins); Gumroad 2026 creator data; Apify, Atlassian, Shopify App Store and Chrome Web Store review timelines and revenue-share terms.",
         "Amazon US market report for cocktail smoker kits (asinsight.com, July 2026) and 2026 buying guides; supplier cost guides for pet grooming tools."], SMALL)

doc = SimpleDocTemplate(str(OUT), pagesize=letter, leftMargin=0.8 * inch, rightMargin=0.8 * inch, topMargin=0.8 * inch, bottomMargin=0.85 * inch, title="Claude's Entry: 90-Day AI Business Competition, Business Plan v1", author="Claude (operator) for StateFarm91/Project-Money", subject="Business plan, Day 1")
doc.build(S, onFirstPage=on_page, onLaterPages=on_page)
print("wrote", OUT, OUT.stat().st_size // 1024, "KB")
