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
const consoleErrors = [];
page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });
page.on("pageerror", (e) => consoleErrors.push(`pageerror: ${e.message}`));
const postLog = async () => (await (await fetch(`${BASE}/__mock/log`)).json());

async function settle() {
  await page.waitForFunction(() => !document.querySelector("#main .loading"), null, { timeout: 10000 });
  await page.waitForTimeout(150);
}
async function noHScroll(name) {
  const r = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth,
    bw: document.body.scrollWidth }));
  check(r.sw <= r.cw && r.bw <= r.cw, `${name}: no horizontal scroll`, `scrollWidth ${r.sw}/${r.bw} > ${r.cw}`);
}
let shots = 0;
async function shot(name) {
  if (!SCREENS || shots >= 12) return;
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
  check(tabs.length === 5 && tabs.at(-1).id === "more", "tabbar: 4 primary tabs + More", JSON.stringify(tabs.map((t) => t.id)));
  check(tabs.length > 0 && tabs.every((t) => t.h >= 44 && t.w >= 44), "tabbar: tap targets >= 44px", JSON.stringify(tabs));

  // ---- every tab -------------------------------------------------------------------------
  const TABS = ["home", "approvals", "money", "store", "operations", "learn", "insights", "notifications", "timeline", "ask", "account", "emergency", "more"];
  const SHOT = new Set(["home", "approvals", "money", "store", "operations", "learn", "notifications", "ask", "account", "emergency"]);
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
  const rec = tiles.find((x) => x.label === "Recorded spend (not reconciled)");
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
