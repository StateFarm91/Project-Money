// W4-CCVERIFY: drive every Command Center page of a locally served real app with Playwright.
// Usage (test credentials only; the secret file is local, never committed, never printed):
//   PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers CC_BASE=http://localhost:8899 \
//   CC_SECRET_FILE=<file: line1 passphrase, line2 base32 TOTP secret> OUT=<dir> node cc_verify_drive.mjs
// Writes <OUT>/screens/*.png, <OUT>/api/*.json (every /api/cc response the page made) and
// <OUT>/dom/<page>.json (what the page rendered), plus <OUT>/drive_result.json.
import { createRequire } from "node:module";
import { createHmac } from "node:crypto";
import fs from "node:fs";
import path from "node:path";

const require = createRequire(import.meta.url);
let pw = null;
for (const id of ["playwright", "/opt/node22/lib/node_modules/playwright"]) { try { pw = require(id); break; } catch (_) { /* next */ } }
if (!pw) { console.log("SKIP playwright module not found"); process.exit(3); }
process.env.PLAYWRIGHT_BROWSERS_PATH ||= "/opt/pw-browsers";
const BASE = process.env.CC_BASE;
const OUT = process.env.OUT;
const [PASS, TOTP_SECRET] = fs.readFileSync(process.env.CC_SECRET_FILE, "utf8").trim().split(/\s+/);
for (const d of ["screens", "api", "dom"]) fs.mkdirSync(path.join(OUT, d), { recursive: true });

function b32(s) {
  const a = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"; let bits = ""; const out = [];
  for (const c of s.replace(/=+$/, "").toUpperCase()) bits += a.indexOf(c).toString(2).padStart(5, "0");
  for (let i = 0; i + 8 <= bits.length; i += 8) out.push(parseInt(bits.slice(i, i + 8), 2));
  return Buffer.from(out);
}
function totp(at = Date.now() / 1000) {
  const ctr = Buffer.alloc(8); ctr.writeBigUInt64BE(BigInt(Math.floor(at / 30)));
  const mac = createHmac("sha1", b32(TOTP_SECRET)).update(ctr).digest();
  const off = mac[mac.length - 1] & 0xf;
  return String((mac.readUInt32BE(off) & 0x7fffffff) % 1e6).padStart(6, "0");
}

const result = { base: BASE, started_at: new Date().toISOString(), login: {}, pages: [] };
const browser = await pw.chromium.launch({ headless: true, executablePath: process.env.CHROME_EXE || undefined });
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await context.newPage();
let errors = [];
let apiFails = [];
let apiSeq = 0;
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
page.on("response", async (r) => {
  const u = new URL(r.url());
  if (!u.pathname.startsWith("/api/cc/")) return;
  if (r.status() >= 400 && !u.pathname.startsWith("/api/cc/auth/")) apiFails.push(`${r.status()} ${u.pathname}${u.search}`);
  try {
    const body = await r.json();
    const name = `${String(++apiSeq).padStart(3, "0")}_${(u.pathname.slice(8) + u.search).replace(/[^A-Za-z0-9]+/g, "_")}.json`;
    if (!u.pathname.startsWith("/api/cc/auth/login")) fs.writeFileSync(path.join(OUT, "api", name), JSON.stringify({ status: r.status(), url: u.pathname + u.search, body }, null, 1));
  } catch (_) { /* not json */ }
});
const settle = async (ms = 180000) => {
  await page.waitForFunction(() => !document.querySelector("#main .loading"), null, { timeout: ms });
  await page.waitForTimeout(400);
};

async function capture(id) {
  return page.evaluate(() => {
    const txt = (e) => (e ? e.textContent.replace(/\s+/g, " ").trim() : null);
    const cards = [...document.querySelectorAll("#main .card")].map((c) => ({
      title: txt(c.querySelector(":scope > .card-head .card-title")),
      pill: txt(c.querySelector(":scope > .card-head .pill")),
      has_time: !!c.querySelector(".fresh, time"),
      time_text: txt(c.querySelector(".fresh, time")),
      reason: txt(c.querySelector(":scope > .callout")),
      tiles: [...c.querySelectorAll(".tile")].map((t) => ({ label: txt(t.querySelector(".tile-label")), value: txt(t.querySelector(".tile-value")), money: t.querySelector(".tile-value") ? t.querySelector(".tile-value").dataset.money || null : null, pill: txt(t.querySelector(".pill")) })),
      text: txt(c).slice(0, 4000),
    }));
    const body = txt(document.querySelector("#main")) || "";
    const bad = ["NaN", "undefined", "[object Object]", "Invalid Date", "null"].filter((w) => new RegExp(`(^|[^A-Za-z])${w.replace(/[[\]]/g, "\\$&")}([^A-Za-z]|$)`).test(body));
    return { title: document.title, view_title: txt(document.getElementById("view-title")), page_meta: txt(document.querySelector("#main .page-meta")),
      error_state: !!document.querySelector("#main .card-error, #main .error-state"), error_text: txt(document.querySelector("#main .card-error, #main .error-state")),
      cards, bad_tokens: bad, text_len: body.length, body: body.slice(0, 60000),
      scroll: [document.documentElement.scrollWidth, document.documentElement.clientWidth] };
  });
}

async function visit(id, hash, { action = null, wait = 180000 } = {}) {
  errors = []; apiFails = [];
  const t0 = Date.now();
  let dom = null; let fail = null;
  try {
    await page.goto(`${BASE}/cc/${hash}`);
    await settle(wait);
    if (action) await action();
    dom = await capture(id);
  } catch (e) { fail = String(e && e.message || e).split("\n")[0]; }
  await page.screenshot({ path: path.join(OUT, "screens", `${id}.png`), fullPage: true }).catch(() => {});
  const rec = { id, hash, seconds: Math.round((Date.now() - t0) / 100) / 10, fail, js_errors: [...errors], api_failures: [...apiFails],
    error_state: dom && dom.error_state, error_text: dom && dom.error_text, bad_tokens: dom && dom.bad_tokens,
    cards: dom ? dom.cards.length : 0, cards_without_time: dom ? dom.cards.filter((c) => !c.has_time).map((c) => c.title) : [],
    page_meta: dom && dom.page_meta };
  if (dom) fs.writeFileSync(path.join(OUT, "dom", `${id}.json`), JSON.stringify(dom, null, 1));
  result.pages.push(rec);
  console.log(`${fail || rec.js_errors.length || rec.error_state ? "FAIL" : "OK  "} ${id} ${rec.seconds}s cards=${rec.cards} js=${rec.js_errors.length} api_fail=${rec.api_failures.length} ${fail || ""}`);
  return rec;
}

try {
  // ---- login: TOTP is required; a wrong code is refused; the right one signs in ----
  const resp = await page.goto(`${BASE}/cc/`);
  result.login.csp = resp.headers()["content-security-policy"] || "";
  await page.waitForSelector("#login-pass", { timeout: 60000 });
  result.login.totp_field = !!(await page.$("#login-totp"));
  await page.screenshot({ path: path.join(OUT, "screens", "00_login.png"), fullPage: true });
  await page.fill("#login-pass", PASS);
  if (process.env.WRONG_TOTP === "1") {
    const good = totp();
    await page.fill("#login-totp", good === "000000" ? "111111" : "000000");
    await page.click("form.login button[type=submit]");
    await page.waitForTimeout(2500);
    result.login.wrong_totp_still_on_login = !!(await page.$("#login-pass")) && !(await page.$("#main .card"));
    result.login.wrong_totp_message = await page.evaluate(() => (document.querySelector("form.login .callout, form.login [role=alert], .login .error, form.login .err") || {}).textContent || null);
    await page.screenshot({ path: path.join(OUT, "screens", "00_login_wrong_totp.png"), fullPage: true });
  }
  await page.fill("#login-pass", PASS);
  await page.fill("#login-totp", totp());
  await page.fill("#login-device", "CCVERIFY test browser");
  await page.click("form.login button[type=submit]");
  await page.waitForFunction(() => !document.querySelector("#login-pass") && document.querySelector("#main .card"), null, { timeout: 120000 });
  result.login.signed_in = true;
  await settle();
  const cookies = await context.cookies();
  result.login.cookies = cookies.map((c) => ({ name: c.name, httpOnly: c.httpOnly, secure: c.secure, sameSite: c.sameSite }));
  result.login.js_errors = [...errors];

  // ---- every tab and view ----
  await visit("01_home", "#/home");
  await visit("02_laura", "#/laura");
  await visit("03_approvals", "#/approvals");
  await visit("04_money_default", "#/money");
  for (const p of ["month", "last_month", "ytd", "all"]) await visit(`04_money_${p}`, `#/money?period=${p}`);
  await visit("04_money_drill_recorded_spend", "#/money/drill/recorded_spend?period=month");
  await visit("04_money_bad_period_7d", "#/money?period=7d");
  await visit("05_store", "#/store");
  await visit("06_company", "#/company");
  // Build 2 closure computes in the background on a cold process: re-read once it has had time.
  await page.waitForTimeout(90000);
  await visit("06_company_warm", "#/company");
  await visit("06_company_departments", "#/company/departments");
  await visit("07_completion", "#/completion");
  await page.waitForTimeout(30000);
  await visit("07_completion_warm", "#/completion");
  await visit("08_operations", "#/operations");
  await visit("09_learn", "#/learn");
  await visit("10_insights", "#/insights");
  await visit("11_notifications", "#/notifications");
  await visit("12_timeline", "#/timeline");
  await visit("13_ask", "#/ask", { action: async () => {
    await page.fill("#ask-q", "What is blocking launch?");
    await page.click("form.ask-form button[type=submit]");
    await page.waitForSelector(".answer-card", { timeout: 120000 });
  } });
  await visit("14_account", "#/account");
  await visit("15_emergency", "#/emergency");
  await visit("16_more", "#/more");
  await visit("17_drill", "#/drill?provider=autonomy&index=0");
  // Talk to Laura Phase 1: ask a question in the Laura tab.
  await visit("02_laura_talk", "#/laura", { action: async () => {
    const box = await page.$("#laura-q");
    if (!box) throw new Error("no Laura input found");
    await box.fill("What should I do first today?");
    const before = await page.$$eval("#main .laura-turn", (e) => e.length);
    await page.click("form.laura-form button[type=submit]");
    await page.waitForFunction((n) => document.querySelectorAll("#main .laura-turn").length > n, before, { timeout: 120000 });
    await page.waitForTimeout(500);
  } });
  // Phone width: no horizontal scroll on the core pages.
  await page.setViewportSize({ width: 390, height: 844 });
  for (const t of ["home", "company", "money", "learn", "completion", "store", "operations", "approvals", "insights", "laura", "more"]) await visit(`20_phone_${t}`, `#/${t}`);
  // Logout ends the session: an API read afterwards is 401.
  await page.setViewportSize({ width: 1280, height: 900 });
  const st = await page.evaluate(async () => (await fetch("/api/cc/company")).status);
  result.logout = { before_status: st };
} catch (e) {
  result.aborted = String(e && e.message || e).split("\n")[0];
  console.log(`ABORT ${result.aborted}`);
  await page.screenshot({ path: path.join(OUT, "screens", "99_abort.png"), fullPage: true }).catch(() => {});
} finally {
  result.finished_at = new Date().toISOString();
  fs.writeFileSync(path.join(OUT, "drive_result.json"), JSON.stringify(result, null, 1));
  await browser.close();
}
