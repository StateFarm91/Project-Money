// Integration smoke of the PWA against a REAL lane C backend (not the mock), for the
// integrator. Usage:
//   CC_BASE=http://127.0.0.1:8899 CC_PASSPHRASE=... node tests/fixtures/cc_mock/real_backend_check.mjs
// The backend must serve this branch's static dir at /cc/ and the API at /api/cc/ with an empty
// (fresh) database. Prints OK/FAIL lines. Makes no mutating call except login/logout.
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
let pw = null;
for (const id of ["playwright", "/opt/node22/lib/node_modules/playwright"]) { try { pw = require(id); break; } catch (_) { /* next */ } }
if (!pw) { console.log("SKIP playwright module not found"); process.exit(3); }
process.env.PLAYWRIGHT_BROWSERS_PATH ||= "/opt/pw-browsers";
const BASE = process.env.CC_BASE;
const PASS = process.env.CC_PASSPHRASE;
if (!BASE || !PASS) { console.log("SKIP CC_BASE / CC_PASSPHRASE not set"); process.exit(3); }

let failures = 0;
const check = (c, name, why = "") => { if (c) console.log(`OK ${name}`); else { failures++; console.log(`FAIL ${name}: ${why}`); } };

const browser = await pw.chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
const page = await context.newPage();
const errors = [];
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
const settle = async () => { await page.waitForFunction(() => !document.querySelector("#main .loading"), null, { timeout: 15000 }); await page.waitForTimeout(150); };

try {
  const resp = await page.goto(`${BASE}/cc/`);
  const csp = resp.headers()["content-security-policy"] || "";
  check(/script-src 'self'/.test(csp) && !/unsafe-inline'[^;]*script|script-src[^;]*unsafe/.test(csp), "real: /cc/ served with strict CSP", csp);
  await page.waitForSelector("#login-pass");
  await page.fill("#login-pass", PASS);
  await page.fill("#login-device", "Integration phone");
  await page.click("form.login button[type=submit]");
  await page.waitForSelector("#tabbar .tab", { timeout: 15000 });
  await settle();
  check(await page.$(".hero") !== null, "real: signed in, home rendered");
  for (const t of ["home", "approvals", "money", "store", "operations", "learn", "insights", "notifications", "timeline", "ask", "account", "emergency", "more"]) {
    errors.length = 0;
    await page.goto(`${BASE}/cc/#/${t}`);
    await settle();
    const err = await page.$(".card-error");
    check(!err, `real ${t}: no error state`, err ? (await err.textContent()).slice(0, 200) : "");
    const sw = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
    check(sw[0] <= sw[1], `real ${t}: no horizontal scroll`, String(sw));
    check(errors.length === 0, `real ${t}: no console errors`, errors.join(" | ").slice(0, 300));
  }
  await page.goto(`${BASE}/cc/#/money`);
  await settle();
  const vals = await page.$$eval(".tile-value[data-money]", (e) => e.map((x) => [x.dataset.money, x.textContent]));
  check(vals.length > 0 && vals.filter(([k]) => k === "unknown").every(([, v]) => v === "Unknown"), "real money: unknown values render Unknown", JSON.stringify(vals));
  check(!vals.some(([k, v]) => k === "unknown" && /\$/.test(v)), "real money: no unknown value printed as dollars", JSON.stringify(vals));
  await page.goto(`${BASE}/cc/#/ask`);
  await settle();
  await page.fill("#ask-q", "What is blocking launch?");
  await page.click("form.ask-form button[type=submit]");
  await page.waitForSelector(".answer-card", { timeout: 15000 });
  check(true, "real ask: POST with CSRF+nonce accepted and answer rendered");
  const st = await page.textContent(".answer-card .pill");
  console.log(`INFO ask status=${st}`);
} catch (e) {
  failures++;
  console.log(`FAIL real check aborted: ${String(e && e.message || e).split("\n")[0]}`);
} finally {
  await browser.close();
}
process.exit(failures ? 1 : 0);
