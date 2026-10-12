// Browser proof for the Owner Command Center PWA (lane D). Run:
//   node tests/fixtures/cc_mock/check.mjs [--screens <dir>]
// Uses the preinstalled Chromium (PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers); never installs.
// Prints "OK <name>" / "FAIL <name>: why" lines (suite harness convention) and exits non-zero on
// any failure.
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { createMock, PASSPHRASE } from "./server.mjs";

const require = createRequire(import.meta.url);
function loadPlaywright() {
  for (const id of ["playwright", "/opt/node22/lib/node_modules/playwright", "playwright-core"]) {
    try { return require(id); } catch (_) { /* next */ }
  }
  return null;
}
const pw = loadPlaywright();
if (!pw) { console.log("SKIP playwright module not found"); process.exit(3); }
process.env.PLAYWRIGHT_BROWSERS_PATH ||= "/opt/pw-browsers";

const argi = process.argv.indexOf("--screens");
const SCREENS = argi > 0 ? path.resolve(process.argv[argi + 1]) : null;
if (SCREENS) fs.mkdirSync(SCREENS, { recursive: true });

let failures = 0;
let passes = 0;
const ok = (name) => { passes++; console.log(`OK ${name}`); };
const fail = (name, why) => { failures++; console.log(`FAIL ${name}: ${why}`); };
const check = (cond, name, why = "assertion failed") => (cond ? ok(name) : fail(name, why));

const { server } = createMock();
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const BASE = `http://127.0.0.1:${server.address().port}`;

const browser = await pw.chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1,
  colorScheme: "light", isMobile: true, hasTouch: true, serviceWorkers: "allow" });
const page = await context.newPage();
// Opt-in fault injection (W4-CCUX): CC_HASHCHANGE_DELAY_MS=200 runs every hashchange handler
// late, as a busy event loop does under CPU contention. settle() must still wait for the new
// view (render-complete signal), so the whole check passes with or without it.
const HC_DELAY = Number(process.env.CC_HASHCHANGE_DELAY_MS || 0);
if (HC_DELAY > 0) {
  await page.addInitScript((d) => {
    const add = window.addEventListener.bind(window);
    window.addEventListener = (t, fn, o) => add(t, t === "hashchange" ? (e) => setTimeout(() => fn(e), d) : fn, o);
  }, HC_DELAY);
}
const consoleErrors = [];
page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });
page.on("pageerror", (e) => consoleErrors.push(`pageerror: ${e.message}`));
const postLog = async () => (await (await fetch(`${BASE}/__mock/log`)).json());

async function settle() {
  // Settled = the app's render-complete signal names the current URL (app.js route()) and
  // nothing is loading. "No spinner" alone was also true of the previous view in the gap
  // between a hash change and its hashchange handler, which made the deep-link check flaky.
  await page.waitForFunction(() => { const m = document.getElementById("main"); return m.dataset.rendered === location.hash && !m.querySelector(".loading"); }, null, { timeout: 10000 });
  await page.waitForTimeout(150);
}
async function noHScroll(name) {
  const r = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth,
    bw: document.body.scrollWidth }));
  check(r.sw <= r.cw && r.bw <= r.cw, `${name}: no horizontal scroll`, `scrollWidth ${r.sw}/${r.bw} > ${r.cw}`);
}
let shots = 0;
async function shot(name) {
  if (!SCREENS || shots >= 14) return;
  shots++;
  await page.screenshot({ path: path.join(SCREENS, `${String(shots).padStart(2, "0")}_${name}.png`), fullPage: false });
}

try {
  // ---- sign-in --------------------------------------------------------------------------
  await page.goto(`${BASE}/cc/`);
  await page.waitForSelector("#login-pass");
  check(await page.isVisible("label[for=login-pass]"), "login: labelled passphrase field");
  await page.fill("#login-pass", "wrong-passphrase");
  await page.click("form.login button[type=submit]");
  await page.waitForFunction(() => document.querySelector(".form-error")?.textContent.length > 0);
  check(/not accepted/i.test(await page.textContent(".form-error")), "login: wrong passphrase refused with message");
  consoleErrors.length = 0; // the 401 above is an expected network error in the console
  await page.fill("#login-pass", PASSPHRASE);
  await page.fill("#login-device", "Test phone");
  await page.click("form.login button[type=submit]");
  await page.waitForSelector(".hero");
  await settle();
  check(await page.evaluate(() => !document.cookie.includes("bl_cc_mock")), "login: session cookie is HttpOnly (invisible to JS)");

  const heroTiles = await page.$$eval(".hero .tile", (els) => els.map((e) => [e.querySelector(".tile-label").textContent, e.querySelector(".tile-value").textContent]));
  const heroMap = Object.fromEntries(heroTiles);
  check(heroMap.Revenue === "Unknown" && heroMap.Profit === "Unknown", "home: UNMEASURED/UNKNOWN revenue and profit render Unknown", JSON.stringify(heroTiles));
  check(heroMap["Decisions for you"] === "2" && heroMap["Open incidents"] === "0", "home: counts rendered (measured zero stays 0)", JSON.stringify(heroTiles));

  // ---- tab bar ---------------------------------------------------------------------------
  const tabs = await page.$$eval("#tabbar .tab", (els) => els.map((e) => ({ id: e.dataset.tab, h: e.getBoundingClientRect().height, w: e.getBoundingClientRect().width })));
  // W3 lane F / D-FB-16 item 6: Laura is the centre of the brand, so Talk to Laura is the first
  // primary tab (5 primary + More). The bar must still fit the phone width without overflow.
  check(tabs.length === 6 && tabs[0].id === "laura" && tabs.at(-1).id === "more", "tabbar: Laura + 4 primary tabs + More", JSON.stringify(tabs.map((t) => t.id)));
  const barFits = await page.$eval("#tabbar", (el) => el.scrollWidth <= el.clientWidth + 1 && el.getBoundingClientRect().right <= window.innerWidth + 1);
  check(barFits, "tabbar: fits the phone width without horizontal overflow", "");
  check(tabs.length > 0 && tabs.every((t) => t.h >= 44 && t.w >= 44), "tabbar: tap targets >= 44px", JSON.stringify(tabs));

  // ---- every tab -------------------------------------------------------------------------
  const TABS = ["home", "approvals", "money", "store", "operations", "learn", "insights", "notifications", "timeline", "ask", "account", "emergency", "more", "company", "completion"];
  const SHOT = new Set(["home", "approvals", "money", "store", "operations", "learn", "notifications", "ask", "account", "emergency", "company", "completion"]);
  for (const t of TABS) {
    consoleErrors.length = 0;
    await page.goto(`${BASE}/cc/#/${t}`);
    await settle();
    const err = await page.$(".card-error");
    check(!err, `${t}: renders without error state`, err ? await err.textContent() : "");
    await noHScroll(t);
    check(consoleErrors.length === 0, `${t}: no console errors`, consoleErrors.join(" | "));
    const small = await page.$$eval("#main button, #main a.btn, #main .chip", (els) => els
      .filter((e) => e.offsetParent !== null)
      .map((e) => ({ t: e.textContent.trim().slice(0, 20), h: Math.round(e.getBoundingClientRect().height) }))
      .filter((x) => x.h < 40));
    check(small.length === 0, `${t}: buttons meet tap-size floor`, JSON.stringify(small));
    if (SHOT.has(t)) await shot(t);
  }

  // ---- W4-CC company: department states, UNKNOWN never 0 ----------------------------------
  await page.goto(`${BASE}/cc/#/company`);
  await settle();
  const deptRows = await page.$$eval("section[aria-labelledby='company-departments'] li.row", (els) => els.map((e) => e.textContent));
  check(deptRows.length === 4, "company: every department listed", String(deptRows.length));
  check(deptRows.some((t) => /blocked/.test(t)) && deptRows.some((t) => /sleeping/.test(t)) && deptRows.some((t) => /active/.test(t)),
    "company: active/sleeping/blocked states shown", JSON.stringify(deptRows.map((t) => t.slice(0, 40))));
  const unk = deptRows.find((t) => /^Visual/.test(t)) || "";
  check(/UNKNOWN/.test(unk) && /Next wake\s*Unknown/.test(unk), "company: UNKNOWN department shows Unknown, not a time or 0", unk.slice(0, 160));
  const incTile = await page.$$eval(".tile", (els) => els.map((e) => [e.querySelector(".tile-label")?.textContent, e.querySelector(".tile-value")?.textContent]));
  const inc = incTile.find(([l]) => l === "Open incidents");
  check(!!inc && inc[1] === "Unknown", "company: null incidents count renders Unknown, never 0", JSON.stringify(inc));
  check(await page.isVisible("#main a[href='#/laura']"), "company: Talk to Laura link present");
  await page.goto(`${BASE}/cc/#/completion`);
  await settle();
  const laneRows = await page.$$eval("section:not([aria-labelledby='completion-launch-packet']) li.row", (els) => els.map((e) => e.textContent));
  check(laneRows.length === 2 && laneRows.some((t) => /Rows closed\s*Unknown/.test(t)), "completion: lanes listed, unknown rows-closed shown as Unknown", JSON.stringify(laneRows.map((t) => t.slice(0, 80))));

  // ---- RB-1 (CC_VERIFY_7421ef6): the Store tab renders the live-shop observation form ------
  await page.goto(`${BASE}/cc/#/store`);
  await settle();
  const storeErr = await page.$(".card-error");
  const form = await page.evaluate(() => {
    const v = document.getElementById("obs-value"), st = document.getElementById("obs-statement"), f = document.getElementById("obs-field");
    return { v: v ? v.maxLength : null, st: st ? st.maxLength : null, opts: f ? f.options.length : 0 };
  });
  check(!storeErr && form.v === 6000 && form.st === 500 && form.opts === 2,
    "store: live-drift observation form renders (field options, maxLength 6000/500)", storeErr ? await storeErr.textContent() : JSON.stringify(form));

  // ---- FU-2 (CC_VERIFY_7421ef6): all-time headline figures are labelled, Unknown never 0 ----
  await page.goto(`${BASE}/cc/#/money?period=last_month`);
  await settle();
  const head = await page.$$eval(".tile", (els) => els.map((e) => [e.querySelector(".tile-label")?.textContent, e.querySelector(".tile-value")?.textContent]));
  const spendT = head.find(([l]) => /^Recorded spend/.test(l || ""));
  const revT = head.find(([l]) => /^Revenue \(all time\)$/.test(l || ""));
  check(!!spendT && /\(all time\)$/.test(spendT[0]) && !!revT && revT[1] === "Unknown",
    "money: all-time headline tiles say 'all time' under a period filter; unknown revenue reads Unknown", JSON.stringify(head.slice(0, 4)));

  // ---- W4-CCFIN: estimate drift is a status card that keeps its detail; Unknown, never 0% ----
  await page.goto(`${BASE}/cc/#/money`);
  await settle();
  const drift = (await page.textContent("section[aria-labelledby='money-estimate-drift']").catch(() => "")) || "";
  check(/UNKNOWN/.test(drift) && /Calls with no reservation\s*Unknown/.test(drift) && /Settlement against provider billing\s*OWNER-GATED/.test(drift)
    && /Tolerance\s*±25%/.test(drift) && /Drift state\s*Unknown/.test(drift) && !/HEALTHY/.test(drift) && /as of/.test(drift) && !/\b0%/.test(drift), "money: estimate drift card shows status, detail and Unknown (never 0%)", drift.slice(0, 300));

  // ---- W4-CCFIN: Rule #1 state, per-agent status, authority (read-only, as-of shown) -------
  await page.goto(`${BASE}/cc/#/learn`);
  await settle();
  const r1 = (await page.textContent("section[aria-labelledby='autonomy-rule1']").catch(() => "")) || "";
  check(/Rule #1 defects\s*1/.test(r1) && /Departments evaluated\s*1 of 2/.test(r1), "learn: Rule #1 defects and evaluated counts shown", r1.slice(0, 200));
  const r1rows = await page.$$eval("section[aria-labelledby='autonomy-rule1'] li.row", (els) => els.map((e) => e.textContent));
  check(r1rows.length === 2 && /DEFECT/.test(r1rows[0]) && /Rule #1 defect\s*Unknown/.test(r1rows[1]) && /Eligible work not yet taken\s*Unknown/.test(r1rows[1]),
    "learn: unevaluated department reads Unknown, never 0", JSON.stringify(r1rows.map((t) => t.slice(0, 160))));
  check(/as of /.test(r1), "learn: Rule #1 card shows as-of", r1.slice(0, 120));
  const ag = await page.$$eval("section[aria-labelledby='autonomy-agents'] li.row", (els) => els.map((e) => e.textContent));
  check(ag.length === 2 && /Current work\s*autonomy\.orchestrate/.test(ag[0]) && /Last useful output\s*plan\.cycle/.test(ag[0])
    && /Etsy API access not granted/.test(ag[1]) && /BLOCKED/.test(ag[1]), "learn: agents show status, current work, useful output, blockers", JSON.stringify(ag.map((t) => t.slice(0, 200))));
  const cardsNoAsOf = await page.$$eval("#main section.card", (els) => els.filter((e) => !e.querySelector("time")).map((e) => e.querySelector(".card-title")?.textContent || "?"));
  check(cardsNoAsOf.length === 0, "learn: every section shows a freshness timestamp", JSON.stringify(cardsNoAsOf));
  await page.goto(`${BASE}/cc/#/account`);
  await settle();
  const pol = (await page.textContent("section[aria-labelledby='account-authority-policy']").catch(() => "")) || "";
  check(/AUTONOMOUS/.test(pol) && /Granted by\s*owner/.test(pol) && /as of /.test(pol), "account: authority grants rendered with as-of", pol.slice(0, 200));
  const dag = (await page.textContent("section[aria-labelledby='account-authority-dag']").catch(() => "")) || "";
  check(/UNKNOWN/.test(dag) && /no work items recorded yet/.test(dag), "account: empty DAG reads UNKNOWN with its reason", dag.slice(0, 200));
  const authBtns = await page.$$eval("section[aria-labelledby^='account-authority'] button", (els) => els.length);
  check(authBtns === 0, "account: authority views are read-only (no actions)", String(authBtns));

  // ---- W4-CCPACKET: launch packet on Completion, read-only, verdict + freshness ---------
  await page.goto(`${BASE}/cc/#/completion`);
  await settle();
  const pkt = (await page.textContent("section[aria-labelledby='completion-launch-packet']").catch(() => "")) || "";
  check(/BLOCKED/.test(pkt) && /as of /.test(pkt) && /Candidate commit\s*3a5700e01234/.test(pkt), "completion: launch packet shows verdict, commit and as-of", pkt.slice(0, 240));
  check(/harbour-throw/.test(pkt) && /parity: FAIL/.test(pkt), "completion: packet lists products with open gates", pkt.slice(0, 400));
  check(/Maximum cost\s*Unknown/.test(pkt) && /Minutes\s*240/.test(pkt), "completion: owner action with null cost reads Unknown, never CA$0.00", pkt.slice(0, 600));
  const pktBtns = await page.$$eval("section[aria-labelledby='completion-launch-packet'] button", (els) => els.length);
  check(pktBtns === 0, "completion: launch packet is read-only", String(pktBtns));

  // ---- money: UNKNOWN is "Unknown", never CA$0.00; basis labelled ------------------------
  await page.goto(`${BASE}/cc/#/money`);
  await settle();
  const tiles = await page.$$eval(".tile", (els) => els.map((e) => ({ label: e.querySelector(".tile-label")?.textContent,
    value: e.querySelector(".tile-value")?.textContent, money: e.querySelector(".tile-value")?.dataset.money,
    basis: e.querySelector(".tag")?.textContent })));
  const rev = tiles.find((x) => x.label === "Revenue");
  check(!!rev && rev.value === "Unknown" && rev.money === "unknown", "money: UNKNOWN revenue renders 'Unknown'", JSON.stringify(rev));
  const fees = tiles.find((x) => x.label === "Marketplace fees");
  check(!!fees && fees.value === "Unknown", "money: UNMEASURED fees render 'Unknown'", JSON.stringify(fees));
  const unknownTiles = tiles.filter((x) => x.money === "unknown");
  check(unknownTiles.length > 0 && unknownTiles.every((x) => !/\$|0\.00/.test(x.value)), "money: no unknown tile shows a dollar amount", JSON.stringify(unknownTiles));
  const tax = tiles.find((x) => x.label === "Tax reserve");
  check(!!tax && tax.value === "CA$0.00" && /actual/i.test(tax.basis), "money: measured zero renders CA$0.00 labelled Actual", JSON.stringify(tax));
  const contrib = tiles.find((x) => x.label === "Contribution");
  check(!!contrib && /estimated/i.test(contrib.basis), "money: estimated figure visibly labelled Estimated", JSON.stringify(contrib));
  const model = tiles.find((x) => x.label === "Safe discretionary budget");
  check(!!model && /modelled/i.test(model.basis), "money: modelled figure visibly labelled Modelled", JSON.stringify(model));
  const rec = tiles.find((x) => x.label === "Recorded spend (not reconciled) (all time)"); // FU-2: all-time scope shown
  check(!!rec && rec.value === "CA$14.20" && /recorded/i.test(rec.basis), "money: recorded (unreconciled) spend labelled Recorded", JSON.stringify(rec));
  check(await page.isVisible("text=revenue, fees and profit are UNKNOWN"), "money: source-health warning shown");
  // drill-through (F-915)
  await page.click("a.tile-link[href*='model_spend']");
  await settle();
  const rows = await page.$$eval("table tbody tr", (r) => r.length);
  check(rows === 2 && (await page.isVisible("text=Why this number exists")), "money: drill-through shows source rows", `rows=${rows}`);
  await noHScroll("money-drill");

  // ---- approvals: evidence + confirmation + step-up --------------------------------------
  await page.goto(`${BASE}/cc/#/approvals`);
  await settle();
  const cards = await page.$$eval("article.approval", (els) => els.map((e) => ({ id: e.dataset.card,
    evidence: Number(e.querySelector(".evidence")?.dataset.evidence), fields: e.querySelectorAll(".kv > div").length,
    approve: !!e.querySelector("button[data-action$='.approve']"), approveDisabled: e.querySelector("button[data-action$='.approve']")?.disabled })));
  check(cards.length === 2 && cards.every((c) => c.fields === 8), "approvals: every card shows all F-885 fields", JSON.stringify(cards));
  check(cards[0].evidence === 3, "approvals: evidence listed on card", JSON.stringify(cards[0]));
  await page.click("article.approval:nth-of-type(2) details.review > summary");
  check(!cards[1].approve && (await page.isVisible("article.approval:nth-of-type(2) >> text=No evidence attached")), "approvals: card without evidence cannot be approved");
  const maxSpend = await page.$eval("article.approval", (e) => [...e.querySelectorAll(".kv > div")].find((d) => d.querySelector("dt").textContent === "Max spend").querySelector("dd").textContent);
  check(maxSpend === "Unknown", "approvals: max_spend_cad null renders Unknown", maxSpend);

  const before = (await postLog()).length;
  await page.click("article.approval button[data-action='publication.approve']");
  await page.waitForSelector("dialog.dlg[open]");
  check((await postLog()).length === before, "approvals: nothing sent before confirmation");
  check(await page.isVisible("#dlg-pass"), "approvals: step-up passphrase requested for consequential action");
  check(await page.isDisabled("dialog.dlg button[data-dlg=confirm]"), "approvals: confirm disabled until step-up + reason entered");
  await shot("approval_confirm");
  await page.click("dialog.dlg button[data-dlg=cancel]");
  await page.waitForSelector("dialog.dlg", { state: "detached" });
  check((await postLog()).length === before, "approvals: cancel sends nothing");

  await page.click("article.approval button[data-action='publication.approve']");
  await page.waitForSelector("dialog.dlg[open]");
  await page.fill("#dlg-reason", "Gates pass; staging only.");
  await page.fill("#dlg-pass", PASSPHRASE);
  await page.click("dialog.dlg button[data-dlg=confirm]");
  // Wait for the action itself, not "a toast is on": the "Cancelled. Nothing changed." toast
  // from the cancel step above can still be visible, which raced this check under load.
  const actPath = "/api/cc/actions/publication.approve";
  for (let i = 0; i < 150 && !(await postLog()).slice(before).some((e) => e.path === actPath); i++) {
    await page.waitForTimeout(100);
  }
  await page.waitForSelector(".toast.is-on");
  const log = (await postLog()).slice(before);
  const stepUp = log.find((e) => e.path === "/api/cc/auth/step-up");
  const act = log.find((e) => e.path === "/api/cc/actions/publication.approve");
  check(!!stepUp && !stepUp.refused, "approvals: step-up performed before action", JSON.stringify(log));
  check(!!act && !act.refused && act.csrf && act.nonce && act.ts, "approvals: action sent with CSRF + nonce + timestamp", JSON.stringify(act));
  check(!!act && act.body && act.body.reason === "Gates pass; staging only." && act.body.expected_digest === "sha256:abc123", "approvals: action carries params + reason");
  const nonces = log.map((e) => e.nonce).filter(Boolean);
  check(nonces.length >= 2 && new Set(nonces).size === nonces.length, "approvals: nonce fresh per request");

  // ---- emergency: pause has no step-up; resume asks for it -------------------------------
  await page.goto(`${BASE}/cc/#/emergency`);
  await settle();
  await page.click("button[data-control='pause:department:growth']");
  await page.waitForSelector("dialog.dlg[open]");
  check(!(await page.$("#dlg-pass")), "emergency: pause needs confirmation but no step-up");
  await page.click("dialog.dlg button[data-dlg=cancel]");

  // ---- ask company: sources linked; unknown honest ---------------------------------------
  await page.goto(`${BASE}/cc/#/ask`);
  await settle();
  await page.fill("#ask-q", "What did Brambleloop do overnight?");
  await page.click("form.ask-form button[type=submit]");
  await page.waitForSelector(".answer-card");
  const srcLinks = await page.$$eval(".answer-card .sources a, .answer-card .rows a", (a) => a.map((x) => x.getAttribute("href")));
  check(srcLinks.some((h) => h.startsWith("#/drill/")), "ask: answer has source links", JSON.stringify(srcLinks));
  await page.fill("#ask-q", "Why is the sky blue?");
  await page.click("form.ask-form button[type=submit]");
  await page.waitForFunction(() => document.querySelectorAll(".answer-card").length === 2);
  check(await page.isVisible(".answer-card .answer[data-answer=UNKNOWN]"), "ask: unanswerable question shown as UNKNOWN");

  // ---- W4-CCUX: decide-first prioritisation, long-page sections, phone navigation ----------
  await page.goto(`${BASE}/cc/#/approvals`);
  await settle();
  const order = await page.$$eval("#main .stack > *", (els) => els.map((e) => e.matches("article.approval") ? "card"
    : e.matches(".decide-first") ? "decide" : e.matches("section[aria-labelledby='approvals-batches']") ? "batches" : "other"));
  const iDecide = order.indexOf("decide"), iCard = order.indexOf("card"), iBatch = order.indexOf("batches");
  check(iDecide >= 0 && iDecide < iCard && iCard < iBatch, "ccux approvals: Decide first leads, then the cards, then the batch queue", JSON.stringify(order));
  const dRows = await page.$$eval(".decide-first li.decide-row", (els) => els.map((e) => ({ kind: e.dataset.decision, text: e.textContent,
    href: e.querySelector("a.decide-go")?.getAttribute("href") || null, btn: e.querySelector("button.decide-go")?.textContent || null })));
  check(dRows.length === 3 && dRows[0].kind === "card" && /Harbour Throw/.test(dRows[0].text) && dRows[1].kind === "batch" && dRows[2].kind === "batch",
    "ccux approvals: top 3 = decidable card, then batch queue in order (non-executable card last)", JSON.stringify(dRows.map((d) => [d.kind, d.text.slice(0, 40)])));
  check(/Max cost\s*Unknown/.test(dRows[0]?.text || "") && /If you do nothing\s*Launch slips/.test(dRows[0]?.text || "") && /Deadline\s*in /.test(dRows[0]?.text || ""),
    "ccux approvals: each top decision shows cost (Unknown, never CA$0) and consequence", (dRows[0]?.text || "").slice(0, 300));
  check(/Max cost\s*CA\$25\.00/.test(dRows[1]?.text || "") && /Max cost\s*Unknown/.test(dRows[2]?.text || "") && !/CA\$0\.00/.test(dRows[2]?.text || "")
    && /If you do nothing\s*revenue stays Unknown/.test(dRows[2]?.text || ""), "ccux approvals: batch decision costs stated or Unknown", JSON.stringify(dRows.slice(1).map((d) => d.text.slice(0, 160))));
  check(dRows[0]?.href === "#/approvals/publication%3Aharbour-throw%401", "ccux approvals: top decision links to its evidence card", String(dRows[0]?.href));
  check(/1 more below/.test(await page.textContent(".decide-first")), "ccux approvals: the rest are counted, not hidden");
  const firstOpen = await page.$eval("article.approval", (e) => e.querySelector("details.review").open && /Harbour/.test(e.textContent));
  check(firstOpen, "ccux approvals: the most urgent card is first and open");
  await page.click(".decide-first li.decide-row:nth-child(2) button.decide-go");
  await page.waitForTimeout(200);
  const batchInView = await page.$eval("section[aria-labelledby='approvals-batches']", (e) => { const r = e.getBoundingClientRect(); return r.top < window.innerHeight && r.bottom > 0 && e.querySelector("details.review").open; });
  check(batchInView, "ccux approvals: 'Show in batches' scrolls to the open batch");
  await page.click(".decide-first li.decide-row:first-child a.decide-go");
  await settle();
  check(/#\/approvals\/publication/.test(page.url()) && (await page.$$("article.approval .evidence li")).length === 3, "ccux approvals: decide-first link opens the card with its evidence");

  // deterministic ranking (unit, in the page): deadline, evidence, executability, cost text
  const rank = await page.evaluate(async () => {
    const m = await import("/cc/js/views/_decisions.js");
    const d = (h) => new Date(Date.now() + h * 3600000).toISOString();
    const r = m.rankDecisions([
      { card_id: "late", executable: true, evidence: [1], deadline: d(48), max_spend_cad: 0 },
      { card_id: "noev", executable: true, evidence: [], deadline: d(1) },
      { card_id: "blocked", executable: false, evidence: [1], deadline: d(0.5) },
      { card_id: "soon", executable: true, evidence: [1], deadline: d(2), max_spend_cad: 12.5 },
      { card_id: "nodl", executable: true, evidence: [1], deadline: null },
    ], { items: [{ title: "B", items: [{ id: "b1", decision: "b1", max_cost: null }] }] });
    return r.map((x) => [x.id, x.cost]);
  });
  check(JSON.stringify(rank.map((x) => x[0])) === JSON.stringify(["soon", "late", "nodl", "noev", "b1", "blocked"]),
    "ccux ranking: evidence+soonest first, no-deadline after, missing evidence, batch, not-executable last", JSON.stringify(rank));
  check(rank.find((x) => x[0] === "late")[1] === "CA$0.00" && rank.find((x) => x[0] === "noev")[1] === "Unknown" && rank.find((x) => x[0] === "b1")[1] === "Unknown",
    "ccux ranking: a stated 0 stays CA$0.00, an unstated cost is Unknown", JSON.stringify(rank));

  // home: decide-first is the first card after the hero
  await page.goto(`${BASE}/cc/#/home`);
  await settle();
  const homeOrder = await page.$$eval("#main .stack > .card", (els) => els.slice(0, 2).map((e) => e.classList.contains("hero") ? "hero" : e.classList.contains("decide-first") ? "decide" : e.className));
  check(JSON.stringify(homeOrder) === JSON.stringify(["hero", "decide"]), "ccux home: Decide first directly after the brief", JSON.stringify(homeOrder));
  const homeDecide = await page.textContent(".decide-first");
  check(/Harbour Throw/.test(homeDecide) && /Max cost/.test(homeDecide) && /If you do nothing/.test(homeDecide) && /1 more open/.test(homeDecide)
    && (await page.isVisible(".decide-first .decide-rest a[href='#/approvals']")), "ccux home: top decisions with cost, consequence and a link to all", homeDecide.slice(0, 200));
  await noHScroll("ccux home");

  // ---- W4-OWNERHOME: six-block owner overview at 390 px ----------------------------------
  const ovTitles = await page.$$eval("#main .stack > .card", (els) => els.map((e) => e.classList.contains("hero") ? "hero"
    : e.classList.contains("decide-first") ? "decisions" : (e.className.match(/ov-(working|blocked|accomplished|ready|money)/) || [])[1] || null).filter(Boolean));
  check(JSON.stringify(ovTitles.slice(0, 7)) === JSON.stringify(["hero", "decisions", "working", "blocked", "accomplished", "ready", "money"]),
    "ownerhome: six blocks lead Home (decisions first after the brief)", JSON.stringify(ovTitles));
  const ovRows = await page.$$eval(".ov-block", (els) => els.map((e) => [e.className, e.querySelectorAll(":scope > .ov-rows > li").length,
    e.querySelector(":scope > .ov-evidence > summary")?.textContent || "", e.querySelector(":scope > details.ov-evidence")?.open]));
  check(ovRows.length === 5 && ovRows.every(([, n]) => n <= 5) && ovRows.every(([, , , open]) => open === false),
    "ownerhome: each block shows at most five rows, evidence folded", JSON.stringify(ovRows));
  check(ovRows.some(([c, n, sum]) => /ov-blocked/.test(c) && n === 5 && /Evidence \(7\)/.test(sum)), "ownerhome: evidence keeps every row the block summarises", JSON.stringify(ovRows));
  const blockedTop = await page.textContent(".ov-blocked .ov-rows li");
  check(/Etsy API credentials/.test(blockedTop) && /21 waiting/.test(blockedTop), "ownerhome: blocked ranks root causes by count", blockedTop);
  const moneyTxt = await page.textContent(".ov-money");
  check(/UNMEASURED/.test(moneyTxt) && !/Revenue\s*CA\$0\.00/.test(moneyTxt) && /Agent activity \(24 h\): 2 of 3/.test(moneyTxt),
    "ownerhome: money keeps UNKNOWN/UNMEASURED, agents measured by useful results", moneyTxt.slice(0, 240));
  const readyTxt = await page.textContent(".ov-ready .ov-rows");
  check(/PDF BUILT/.test(readyTxt) && /images UNKNOWN/.test(readyTxt) && /NOT READY/.test(readyTxt), "ownerhome: ready to sell shows certification, PDF and image status", readyTxt);
  check(/#4/.test(await page.textContent(".decide-first .ov-next-decisions")) && (await page.$$(".decide-first .decide-go")).length === 3,
    "ownerhome: decisions block reaches rank 5 without extra tap targets", "");
  check(!(await page.$eval("details.home-more", (d) => d.open)), "ownerhome: the previous Home detail is kept, folded", "");
  for (const sel of [".ov-blocked > .ov-evidence > summary", ".ov-ready > .ov-evidence > summary", ".ov-money > .ov-evidence > summary"]) await page.click(sel);
  await page.waitForTimeout(100);
  check((await page.$$eval(".ov-blocked .ov-ev", (e) => e.length)) === 7, "ownerhome: expanding evidence lists the rows with sources", "");
  await noHScroll("ownerhome expanded");
  const ovTap = await page.$$eval(".ov-evidence > summary", (els) => els.map((e) => Math.round(e.getBoundingClientRect().height)));
  check(ovTap.length >= 5 && ovTap.every((x) => x >= 44), "ownerhome: evidence toggles are >=44px tap targets", JSON.stringify(ovTap));
  if (SCREENS) {
    await page.screenshot({ path: path.join(SCREENS, "ownerhome_390_expanded_full.png"), fullPage: true });
    await page.reload();
    await settle();
    await page.screenshot({ path: path.join(SCREENS, "ownerhome_390_top.png"), fullPage: false });
    await page.screenshot({ path: path.join(SCREENS, "ownerhome_390_full.png"), fullPage: true });
  }
  const goH = await page.$$eval(".decide-first .decide-go", (els) => els.map((e) => Math.round(e.getBoundingClientRect().height)));
  check(goH.length === 3 && goH.every((x) => x >= 44), "ccux home: each top decision is a >=44px tap target", JSON.stringify(goH));

  // long page: sections index + collapse all, nothing dropped
  await page.goto(`${BASE}/cc/#/learn`);
  await settle();
  check(await page.isVisible(".page-tools"), "ccux learn: long page has a sections toolbar");
  const linksBefore = await page.$$eval("#main a[href]", (a) => a.map((x) => x.getAttribute("href")).sort());
  const hBefore = await page.evaluate(() => document.documentElement.scrollHeight);
  const nCards = await page.$$eval("#main .stack > .card:not(.hero) > .card-head .card-title", (e) => e.length);
  const nIndex = await page.$$eval(".page-index .index-link", (e) => e.length);
  check(nIndex === nCards && nCards >= 5, "ccux learn: index lists every titled section", `${nIndex} vs ${nCards}`);
  await page.click(".page-tools button[data-fold=all]");
  const folded = await page.$$eval("#main .stack > .card.is-collapsed", (e) => e.length);
  const hAfter = await page.evaluate(() => document.documentElement.scrollHeight);
  check(folded === nCards && hAfter < hBefore / 2, "ccux learn: Collapse all folds every section to its header", `${folded}/${nCards}, ${hBefore}->${hAfter}`);
  check(!(await page.isVisible("section[aria-labelledby='autonomy-rule1'] li.row >> nth=0")) && (await page.isVisible("section[aria-labelledby='autonomy-rule1'] .card-title")),
    "ccux learn: folded card hides its body, keeps its title");
  const linksFolded = await page.$$eval("#main a[href]", (a) => a.map((x) => x.getAttribute("href")).sort());
  check(JSON.stringify(linksFolded) === JSON.stringify(linksBefore), "ccux learn: folding keeps every link in the page (hidden, not removed)", `${linksBefore.length} vs ${linksFolded.length}`);
  await noHScroll("ccux learn folded");
  const smallFolded = await page.$$eval("#main button, #main a.btn", (els) => els.filter((e) => e.offsetParent !== null)
    .map((e) => Math.round(e.getBoundingClientRect().height)).filter((x) => x < 40));
  check(smallFolded.length === 0, "ccux learn: fold controls meet tap-size floor", JSON.stringify(smallFolded));
  await shot("ccux_learn_folded");
  await page.click("section[aria-labelledby='autonomy-rule1'] .card-expand");
  check(await page.isVisible("section[aria-labelledby='autonomy-rule1'] li.row >> nth=0"), "ccux learn: Show reopens one section");
  await page.click(".page-index > summary");
  await page.click(".page-index .index-link >> text=Agents: status");
  await page.waitForTimeout(150);
  const agentsOk = await page.$eval("section[aria-labelledby='autonomy-agents']", (e) => !e.classList.contains("is-collapsed") && e.getBoundingClientRect().top < 200 && e.getBoundingClientRect().top > -5);
  check(agentsOk, "ccux learn: index link opens the section and scrolls to it");
  await page.goto(`${BASE}/cc/#/home`);
  await settle();
  await page.goto(`${BASE}/cc/#/learn`);
  await settle();
  check((await page.getAttribute(".page-tools button[data-fold=all]", "aria-pressed")) === "true", "ccux learn: fold choice kept while navigating (memory only)");
  await page.click(".page-tools button[data-fold=all]");
  check((await page.$$("#main .card.is-collapsed")).length === 0, "ccux learn: Expand all restores every section");
  const lsKeys = await page.evaluate(() => Object.keys(localStorage));
  check(!lsKeys.some((k) => /collap|fold/i.test(k)), "ccux learn: fold state never written to browser storage", JSON.stringify(lsKeys));
  // approvals folded: evidence links and decision buttons survive, return on expand
  await page.goto(`${BASE}/cc/#/approvals`);
  await settle();
  const apTools = await page.$(".page-tools button[data-fold=all]");
  if (apTools) {
    const evBefore = await page.$$eval("article.approval .evidence a", (a) => a.length);
    await apTools.click();
    const evFolded = await page.$$eval("article.approval .evidence a", (a) => a.length);
    await page.click(".page-tools button[data-fold=all]");
    check(evBefore === 3 && evFolded === evBefore && (await page.isVisible("article.approval button[data-action='publication.approve']")),
      "ccux approvals: folding keeps evidence links and actions", `${evBefore}/${evFolded}`);
  } else ok("ccux approvals: page short enough that no folding is offered");
  // short page: no toolbar
  await page.goto(`${BASE}/cc/#/more`);
  await settle();
  check(!(await page.$(".page-tools")), "ccux more: short pages get no toolbar");

  // navigation: More menu hints + badges; breadcrumb on More sections (phone only)
  const menu = await page.$$eval(".menu a", (els) => els.map((e) => ({ id: e.dataset.more, hint: e.querySelector(".menu-hint")?.textContent || "",
    badge: e.querySelector(".badge") })));
  check(menu.length === 10 && menu.every((m) => m.hint.length > 5), "ccux more: every More item says what it holds", JSON.stringify(menu.map((m) => [m.id, m.hint])));
  const nb = await page.$eval(".menu a[data-more=notifications] .badge", (b) => ({ hidden: b.hidden, t: b.textContent }));
  const barBadge = await page.$eval("#tabbar [data-badge=more]", (b) => ({ hidden: b.hidden, t: b.textContent }));
  check(!nb.hidden && nb.t === barBadge.t && !barBadge.hidden, "ccux more: menu shows the same notifications badge as the bar", JSON.stringify([nb, barBadge]));
  await shot("ccux_more");
  await page.click(".menu a[data-more=company]");
  await settle();
  const crumb = await page.$eval("#main nav.crumb", (e) => ({ t: e.textContent, href: e.querySelector("a").getAttribute("href"), vis: e.offsetParent !== null })).catch(() => null);
  check(!!crumb && crumb.vis && crumb.href === "#/more" && /More\s*›\s*Company/.test(crumb.t), "ccux nav: More sections show 'More › Section' with a way back", JSON.stringify(crumb));
  await page.click("#main nav.crumb a");
  await settle();
  check(/#\/more$/.test(page.url()), "ccux nav: breadcrumb returns to More");
  await page.goto(`${BASE}/cc/#/home`);
  await settle();
  check(!(await page.$("#main nav.crumb")), "ccux nav: primary tabs carry no breadcrumb");
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(`${BASE}/cc/#/company`);
  await settle();
  check(!(await page.isVisible("#main nav.crumb")) && (await page.isVisible("#sidenav a[data-tab=company][aria-current=page]")), "ccux nav: desktop uses the sidebar, breadcrumb hidden");
  await page.setViewportSize({ width: 390, height: 844 });

  // ---- W4-STOREFRONT: owner Store area on a phone (390 px) ---------------------------------
  const reqs = [];
  const onReq = (r) => reqs.push(new URL(r.url()).pathname);
  page.on("request", onReq);
  await page.goto(`${BASE}/cc/#/store`);
  await settle();
  await page.waitForFunction(() => [...document.querySelectorAll(".pimg img")].every((i) => i.complete), null, { timeout: 10000 });
  const sov = await page.evaluate(() => ({
    nav: [...document.querySelectorAll(".store-nav a")].map((a) => a.textContent),
    readiness: document.querySelector("section[aria-labelledby='store-readiness']")?.textContent || "",
    decisions: document.querySelector("section[aria-labelledby='store-decisions']")?.textContent || "",
    tiles: [...document.querySelectorAll("section[aria-labelledby='store-catalogue'] .ptile")].map((t) => ({ slug: t.dataset.product,
      img: t.querySelector("img")?.getAttribute("src") || null, loaded: (t.querySelector("img")?.naturalWidth || 0) > 0,
      none: t.querySelector(".pimg-none")?.textContent || null })),
    preview: document.querySelector("section[aria-labelledby='store-preview'] a.btn-primary")?.getAttribute("href") || "",
    evidence: (() => { const d = document.querySelector("#store-evidence"); return d ? { open: d.open, sections: d.querySelectorAll(".card").length } : null; })(),
    obs: !!document.getElementById("obs-field"),
  }));
  check(JSON.stringify(sov.nav) === JSON.stringify(["Overview", "Collection", "Listings & prices", "Storefront"]), "storefront cc: store sub-navigation", JSON.stringify(sov.nav));
  check(/Launch collection\s*8/.test(sov.readiness) && /Pictures verified\s*7 \/ 8/.test(sov.readiness) && /Etsy connection\s*Not connected/.test(sov.readiness),
    "storefront cc: launch readiness shows collection, verified pictures and Etsy connection", sov.readiness.slice(0, 240));
  check(/CAP-1: products in Launch-0 scope/.test(sov.decisions) && /NOT APPROVED: GATES PENDING/.test(sov.decisions) && !/D-FB-9/.test(sov.decisions),
    "storefront cc: CAP-1 products shown as not approved (gates pending)", sov.decisions.slice(0, 200));
  const etsyCardText = await page.evaluate(() => [...document.querySelectorAll("#main section.card")].find((c) => c.querySelector(".card-title")?.textContent === "Etsy connection")?.textContent || "");
  check(/refusing the app key/.test(etsyCardText) && (await page.isDisabled("button:has-text('Connect Etsy shop')")), "storefront cc: Etsy connection card kept on the Store overview", etsyCardText.slice(0, 160));
  const verifiedTiles = sov.tiles.filter((t) => t.img);
  const withheld = sov.tiles.filter((t) => !t.img);
  check(sov.tiles.length === 5 && verifiedTiles.length === 4 && verifiedTiles.every((t) => t.img.startsWith("/api/cc/store/image/") && t.loaded),
    "storefront cc: visual catalogue loads verified pictures through the owner session", JSON.stringify(sov.tiles));
  check(withheld.length === 1 && /withheld/i.test(withheld[0].none || "") && !reqs.some((p) => p.endsWith("/store/image/nordic_star_ornaments")),
    "storefront cc: a withheld picture shows a placeholder and is never requested", JSON.stringify({ withheld, reqs: reqs.filter((p) => p.includes("/store/image/")) }));
  check(/variant=storefront/.test(sov.preview), "storefront cc: preview opens the customer storefront view", sov.preview);
  check(!!sov.evidence && sov.evidence.open === false && sov.evidence.sections >= 2 && sov.obs,
    "storefront cc: technical evidence folded; live-shop observation kept", JSON.stringify(sov.evidence));
  await noHScroll("storefront store overview");

  await page.goto(`${BASE}/cc/#/store/collection`);
  await settle();
  const coll = await page.$$eval(".pgrid", (gs) => gs.map((g) => g.querySelectorAll(".ptile").length));
  const collText = await page.textContent("section[aria-labelledby='store-collection']");
  check(JSON.stringify(coll) === JSON.stringify([5, 3]) && /In Launch-0 scope \(CAP-1\); not approved: gates pending \(3\)/.test(collText) && !/awaiting your decision/.test(collText),
    "storefront cc: 8-product launch collection, 5 Launch-0 + 3 CAP-1 not approved", JSON.stringify(coll));
  check(/Unknown/.test(collText) && !/CA\$0\.00/.test(collText), "storefront cc: an unknown price reads Unknown, never CA$0.00");
  await noHScroll("storefront collection");
  const smallC = await page.$$eval("#main button, #main a.btn", (els) => els.filter((e) => e.offsetParent !== null).map((e) => Math.round(e.getBoundingClientRect().height)).filter((x) => x < 40));
  check(smallC.length === 0, "storefront collection: tap-size floor", JSON.stringify(smallC));

  await page.click(".ptile[data-product='nursery-nesting-baskets']");
  await settle();
  const pd = await page.evaluate(() => ({ url: location.hash, title: document.querySelector(".product-head .card-title")?.textContent,
    img: document.querySelector(".product-head img")?.getAttribute("src"), dl: document.querySelector(".dl-label")?.textContent,
    pdf: [...document.querySelectorAll("a[data-pdf]")].map((a) => a.getAttribute("href")),
    readiness: document.querySelector("section[aria-labelledby='product-readiness']")?.textContent || "",
    listing: document.querySelector("section[aria-labelledby='product-listing']")?.textContent || "",
    evidenceOpen: document.querySelector("details.evidence-group")?.open }));
  check(/#\/store\/product\/nursery-nesting-baskets/.test(pd.url) && pd.title === "Nesting Baskets, three sizes" && pd.img === "/api/cc/store/image/nursery_nesting_baskets"
    && pd.dl === "Digital download (PDF pattern)", "storefront cc: product page with verified picture and digital-download label", JSON.stringify(pd).slice(0, 300));
  check(JSON.stringify(pd.pdf) === JSON.stringify(["/api/cc/store/pdf/nursery-nesting-baskets?terms=US", "/api/cc/store/pdf/nursery-nesting-baskets?terms=UK"]),
    "storefront cc: US and UK PDF previews linked", JSON.stringify(pd.pdf));
  const pdfRes = await page.evaluate(async (u) => { const r = await fetch(u, { credentials: "same-origin" }); return { s: r.status, t: r.headers.get("content-type") }; }, pd.pdf[0]);
  check(pdfRes.s === 200 && /application\/pdf/.test(pdfRes.t || ""), "storefront cc: PDF preview served as application/pdf", JSON.stringify(pdfRes));
  check(/OWNER/.test(pd.readiness) && /Listing title/.test(pd.listing) && /On Etsy\s*UNKNOWN/.test(pd.listing) && pd.evidenceOpen === false,
    "storefront cc: readiness, read-only listing (on Etsy UNKNOWN) and folded evidence", (pd.readiness + pd.listing).slice(0, 300));
  check((await page.$$("section[aria-labelledby='product-listing'] button")).length === 0, "storefront cc: listing view is read-only");
  await noHScroll("storefront product");
  await page.goto(`${BASE}/cc/#/store/product/housewarming-key-basket`);
  await settle();
  const pd2 = await page.textContent("#main");
  check(/CAP-1 · NOT APPROVED/.test(pd2) && /not approved: gates pending/.test(pd2) && /Not shown on the customer preview/.test(pd2)
    && /Price\s*Unknown/.test(pd2) && !/CA\$0\.00/.test(pd2), "storefront cc: CAP-1 product labelled not approved, off the customer page; unknown price Unknown", pd2.slice(0, 240));

  await page.goto(`${BASE}/cc/#/store/listings`);
  await settle();
  const lrows = await page.$$eval("li[data-listing]", (els) => els.length);
  check(lrows === 8 && (await page.$$("#main section[aria-labelledby='store-listings'] button")).length === 0, "storefront cc: listings & prices for all 8, read-only", String(lrows));
  await noHScroll("storefront listings");

  await page.goto(`${BASE}/cc/#/store/storefront`);
  await settle();
  const ctl = await page.textContent("section[aria-labelledby='store-etsy-controls']");
  check(/shop title/.test(ctl) && /Unknown · UNKNOWN/.test(ctl) && /Drawn by Etsy/.test(ctl), "storefront cc: what Etsy lets the shop control, UNKNOWN never a number", ctl.slice(0, 200));
  await noHScroll("storefront review");
  page.off("request", onReq);
  await page.goto(`${BASE}/cc/#/ask`);
  await settle();

  // ---- W4-CCREL: release approval card (candidate SHA, suite, security review, rollback) ----
  await page.goto(`${BASE}/cc/#/approvals`);
  await settle();
  const rel = await page.evaluate(() => { const c = document.querySelector("section[aria-labelledby='approvals-release']");
    return c ? { text: c.textContent, rows: [...c.querySelectorAll(".evidence li.row")].map((r) => r.textContent),
      links: [...c.querySelectorAll(".evidence a")].map((a) => a.getAttribute("href")), buttons: c.querySelectorAll("button").length } : null; });
  check(!!rel && /Candidate 5ad94dd0c0de/.test(rel.text) && /NOT READY/.test(rel.text) && rel.rows.length === 4,
    "ccrel approvals: release card names the candidate and is not ready", JSON.stringify(rel).slice(0, 300));
  check(!!rel && /Full release suite\s*PASS/.test(rel.rows[1] || "") && /7950 tests passing, 0 of 560 suites failing/.test(rel.rows[1] || "")
    && /Security review\s*UNKNOWN/.test(rel.rows[2] || "") && /not assumed passed/.test(rel.rows[2] || "") && /Rollback target 0417f3516f30/.test(rel.rows[3] || ""),
    "ccrel approvals: suite result, UNKNOWN security review (never a pass) and rollback target", JSON.stringify(rel && rel.rows).slice(0, 400));
  check(!!rel && rel.buttons === 0 && rel.links.length === 4 && rel.links.every((l) => l.startsWith("#/drill/")), "ccrel approvals: read-only, every row links to its evidence", JSON.stringify(rel && rel.links));
  await noHScroll("ccrel approvals");
  await page.goto(`${BASE}/cc/#/ask`);
  await settle();

  // ---- W4-CCREL: Etsy Connect end to end (re-check, step-up, Etsy-only navigation) ---------
  await fetch(`${BASE}/__mock/etsy?ready=1`);
  await page.goto(`${BASE}/cc/#/store`);
  await settle();
  check(!(await page.isDisabled("button:has-text('Connect Etsy shop')")), "etsy connect: Connect enabled once the key is accepted");
  let etsyBefore = (await postLog()).length;
  await page.click("button:has-text('Re-check Etsy connection')");
  await page.waitForSelector("dialog.dlg[open]");
  check((await postLog()).length === etsyBefore, "etsy connect: re-check sends nothing before confirmation");
  await page.click("dialog.dlg button[data-dlg=confirm]");
  for (let i = 0; i < 100 && !(await postLog()).slice(etsyBefore).some((e) => e.path === "/api/cc/etsy/recheck"); i++) await page.waitForTimeout(100);
  const rc = (await postLog()).slice(etsyBefore).find((e) => e.path === "/api/cc/etsy/recheck");
  check(!!rc && !rc.refused && rc.csrf && rc.nonce, "etsy connect: re-check POSTed with CSRF + nonce", JSON.stringify(rc));
  await settle();
  // Connect: confirmation + step-up, then navigation only to Etsy's own consent page.
  await page.route("https://www.etsy.com/**", (r) => r.fulfill({ status: 200, contentType: "text/html", body: "<!doctype html><title>Etsy consent (stub)</title><p>stub</p>" }));
  let evilHit = false;
  await page.route("https://evil.example/**", (r) => { evilHit = true; r.abort(); });
  etsyBefore = (await postLog()).length;
  await page.click("button:has-text('Connect Etsy shop')");
  await page.waitForSelector("dialog.dlg[open]");
  check((await postLog()).length === etsyBefore, "etsy connect: nothing sent before confirmation");
  if (await page.$("#dlg-pass")) await page.fill("#dlg-pass", PASSPHRASE);
  await Promise.all([page.waitForURL(/www\.etsy\.com\/oauth\/connect/, { timeout: 10000 }).catch(() => null),
    page.click("dialog.dlg button[data-dlg=confirm]")]);
  const conn = (await postLog()).slice(etsyBefore).find((e) => e.path === "/api/cc/etsy/connect");
  check(!!conn && !conn.refused && conn.csrf && conn.nonce, "etsy connect: connect POSTed with CSRF + nonce after step-up", JSON.stringify(conn));
  check(/^https:\/\/www\.etsy\.com\/oauth\/connect\?/.test(page.url()), "etsy connect: phone opens Etsy's own consent page", page.url());
  // A non-Etsy authorize URL is never followed.
  await fetch(`${BASE}/__mock/etsy?ready=1&evil=1`);
  await page.goto(`${BASE}/cc/#/store`);
  await settle();
  await page.click("button:has-text('Connect Etsy shop')");
  await page.waitForSelector("dialog.dlg[open]");
  if (await page.$("#dlg-pass")) await page.fill("#dlg-pass", PASSPHRASE);
  await page.click("dialog.dlg button[data-dlg=confirm]");
  await page.waitForTimeout(800);
  check(!evilHit && new URL(page.url()).hostname === "127.0.0.1", "etsy connect: a non-Etsy authorize URL is not followed", page.url());
  await page.unroute("https://www.etsy.com/**");
  await page.unroute("https://evil.example/**");
  await fetch(`${BASE}/__mock/etsy?ready=0`);
  await page.goto(`${BASE}/cc/#/ask`);
  await settle();

  // ---- W4-CCREL: Laura's CEO briefing on a phone (sections, cited records) -----------------
  consoleErrors.length = 0;
  await page.goto(`${BASE}/cc/#/laura`);
  await settle();
  await page.fill("#laura-q", "Give me a CEO briefing");
  await page.click("form.laura-form button[type=submit]");
  await page.waitForSelector(".briefing", { timeout: 10000 });
  const brief = await page.evaluate(() => { const b = document.querySelector(".briefing");
    const secs = [...b.querySelectorAll("details.briefing-sec")];
    return { n: secs.length, open: secs.map((d) => d.open), titles: secs.map((d) => d.querySelector(".briefing-title").textContent),
      lines: secs.map((d) => d.querySelectorAll(".briefing-lines li").length),
      cited: secs.map((d) => [...d.querySelectorAll(".briefing-cited li[data-record]")].map((li) => li.dataset.record)),
      links: [...b.querySelectorAll(".briefing-cited a")].map((a) => a.getAttribute("href")),
      intro: b.querySelector(".briefing-intro")?.textContent || "", text: b.textContent }; });
  check(brief.n === 3 && JSON.stringify(brief.open) === JSON.stringify([true, true, false])
    && JSON.stringify(brief.titles) === JSON.stringify(["The last 24 h", "Each department", "What blocks the first sale"]),
    "laura briefing: one block per section, first two open", JSON.stringify(brief).slice(0, 300));
  check(JSON.stringify(brief.lines) === JSON.stringify([2, 2, 1]) && JSON.stringify(brief.cited) === JSON.stringify([["E1", "E2"], ["E3", "E4", "E5"], ["E6"]]),
    "laura briefing: every line kept; each section lists the records it cites (incl. [E3, E4])", JSON.stringify([brief.lines, brief.cited]));
  check(/Here's where Brambleloop stands/.test(brief.intro) && /UNKNOWN: "Finance not evaluated"/.test(brief.text) && /expand decision 2/.test(brief.text)
    && brief.links.length === 6 && brief.links.every((l) => l.startsWith("#/drill/")), "laura briefing: header, UNKNOWN kept, follow-up hint and record links", brief.text.slice(0, 200));
  await noHScroll("laura briefing");
  check(consoleErrors.length === 0, "laura briefing: no console errors", consoleErrors.join(" | "));
  // ---- W4-CCFM1: departments (F-621), spend trend chart (F-652/F-670), customers (F-619) -----
  await page.goto(`${BASE}/cc/#/company`);
  await settle();
  const deptsF = await page.$$eval("section[aria-labelledby='company-departments'] li.row", (els) => els.map((e) => ({
    t: e.textContent, bars: e.querySelectorAll("svg.chart rect").length })));
  const exe = deptsF.find((d) => /^Executive/.test(d.t)) || {};
  const vis = deptsF.find((d) => /^Visual/.test(d.t)) || {};
  check(/Objective\s*Prioritise company work/.test(exe.t || "") && /Spend \(30 d, recorded\)\s*CA\$1\.25/.test(exe.t || "") && exe.bars === 7,
    "ccfm1 company: department objective, recorded spend and a 7-day completed-work chart", JSON.stringify(exe).slice(0, 300));
  check(/Spend \(30 d, recorded\)\s*Unknown/.test(vis.t || "") && /Completed work trend: Unknown/.test(vis.t || "") && vis.bars === 0,
    "ccfm1 company: unknown spend and trend read Unknown, no bars drawn", JSON.stringify(vis).slice(0, 300));
  await noHScroll("ccfm1 company");
  await page.goto(`${BASE}/cc/#/money`);
  await settle();
  const trend = await page.evaluate(() => { const c = document.querySelector("section[aria-labelledby='money-spend-trend']");
    return c ? { bars: c.querySelectorAll("svg.chart rect").length, zero: c.querySelectorAll("svg.chart rect.is-zero").length,
      label: c.querySelector("svg.chart")?.getAttribute("aria-label") || "", rows: c.querySelectorAll(".chart-data tr").length, text: c.textContent } : null; });
  check(!!trend && trend.bars === 30 && trend.zero === 6 && trend.rows === 30 && /Recorded spend per day: 30 points/.test(trend.label) && /Revenue is not charted while it is Unknown/.test(trend.text),
    "ccfm1 money: 30-day recorded spend chart with its values table; revenue not charted while Unknown", JSON.stringify(trend).slice(0, 300));
  await noHScroll("ccfm1 money");
  await page.goto(`${BASE}/cc/#/insights`);
  await settle();
  const custText = await page.textContent("#main");
  check(/Customers: orders/.test(custText) && /Customers: support/.test(custText) && /Customers: reviews/.test(custText) && !/Orders\s*0\b/.test(custText),
    "ccfm1 insights: customers shown as aggregates; unknown orders never 0", custText.slice(0, 200));
  const firstInsight = await page.$eval("#main .stack > .card .card-title", (e) => e.textContent).catch(() => "");
  check(firstInsight === "Marketing & customers" && /ROAS \(evidence-attributed Etsy Ads\)/.test(custText) && /Support cases \(owner-recorded\)/.test(custText),
    "ccall insights: combined marketing & customers view leads Insights (F-622)", firstInsight);
  await noHScroll("ccfm1 insights");
  await page.goto(`${BASE}/cc/#/ask`);
  await settle();

  // ---- deep link from a notification ----------------------------------------------------
  await page.goto(`${BASE}/cc/#/notifications`);
  await settle();
  await page.click("article.notif a.btn-primary");
  await settle();
  check(/#\/approvals\/publication/.test(page.url()) && (await page.$$("article.approval")).length === 1, "notifications: deep link opens the approval card");

  // ---- PWA: SW registered; never caches /api; offline is honest --------------------------
  await page.goto(`${BASE}/cc/#/home`);
  await settle();
  await page.evaluate(async () => { await navigator.serviceWorker.ready; });
  await page.reload();
  await settle();
  const cached = await page.evaluate(async () => {
    const out = [];
    for (const k of await caches.keys()) for (const r of await (await caches.open(k)).keys()) out.push(new URL(r.url).pathname);
    return out;
  });
  check(cached.length > 0 && cached.some((p) => p.endsWith("/cc/index.html")), "pwa: shell cached by service worker", JSON.stringify(cached));
  check(cached.length > 0 && !cached.some((p) => p.startsWith("/api/")), "pwa: no /api response in Cache Storage", JSON.stringify(cached));
  const ls = await page.evaluate(() => JSON.stringify(Object.keys(localStorage)));
  check(!/csrf|token|session|money/i.test(ls), "pwa: no session/money data in localStorage", ls);

  // in-session stale view: load a tab, go offline, re-render it -> stale banner
  await page.goto(`${BASE}/cc/#/money`);
  await settle();
  await context.setOffline(true);
  await page.click("#refresh");
  await settle();
  check(await page.isVisible(".banner-stale"), "offline: previously loaded view labelled stale");
  check(await page.isVisible(".net-off"), "offline: offline indicator shown");
  await shot("offline_stale");
  // fresh shell while offline: served from SW cache, no fabricated data
  await page.reload();
  await page.waitForSelector("#main .card");
  const txt = await page.textContent("#main");
  check(/offline/i.test(txt) && !/CA\$/.test(txt), "offline: reloaded shell says offline and shows no figures", txt.slice(0, 160));
  await context.setOffline(false);

  // dark theme renders without overflow
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto(`${BASE}/cc/#/home`);
  await settle();
  const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  check(bg === "rgb(15, 26, 22)", "theme: dark scheme applied", bg);
  await noHScroll("home-dark");
} catch (e) {
  fail("check aborted", e && e.stack ? e.stack.split("\n").slice(0, 3).join(" ") : String(e));
} finally {
  await browser.close();
  server.close();
}
console.log(`SUMMARY passes=${passes} failures=${failures} screenshots=${shots}`);
process.exit(failures ? 1 : 0);
