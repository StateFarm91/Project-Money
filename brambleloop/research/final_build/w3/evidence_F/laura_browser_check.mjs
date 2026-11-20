// W3-F runtime proof: the Laura view against the REAL backend (bridge), phone + desktop.
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
let pw = null;
for (const id of ["playwright", "/opt/node22/lib/node_modules/playwright"]) { try { pw = require(id); break; } catch (_) {} }
if (!pw) { console.log("SKIP playwright module not found"); process.exit(3); }
process.env.PLAYWRIGHT_BROWSERS_PATH ||= "/opt/pw-browsers";
const BASE = process.env.CC_BASE, PASS = process.env.CC_PASSPHRASE, OUT = process.env.OUT;
let failures = 0;
const check = (c, name, why = "") => { if (c) console.log(`OK ${name}`); else { failures++; console.log(`FAIL ${name}: ${why}`); } };
const browser = await pw.chromium.launch({ headless: true });
for (const [label, vp, mobile] of [["phone", { width: 390, height: 844 }, true], ["desktop", { width: 1280, height: 860 }, false]]) {
  const context = await browser.newContext({ viewport: vp, isMobile: mobile, hasTouch: mobile });
  const page = await context.newPage();
  const errors = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  const settle = async () => { await page.waitForFunction(() => !document.querySelector("#main .loading"), null, { timeout: 20000 }); await page.waitForTimeout(200); };
  try {
    await page.goto(`${BASE}/cc/`);
    await page.waitForSelector("#login-pass");
    await page.fill("#login-pass", PASS);
    await page.click("form.login button[type=submit]");
    await page.waitForSelector(mobile ? "#tabbar .tab" : "#sidenav .side-link", { timeout: 15000 });
    await settle();
    check(await page.$(`${mobile ? "#tabbar" : "#sidenav"} [data-tab="laura"]`) !== null, `${label}: Laura is a primary nav entry`);
    await page.goto(`${BASE}/cc/#/laura`);
    await settle();
    check(!(await page.$(".card-error")), `${label}: Laura view renders without error state`);
    const portrait = await page.$eval(".laura-portrait img", (i) => ({ w: i.naturalWidth, src: i.getAttribute("src") })).catch(() => null);
    check(portrait && portrait.w > 0 && portrait.src === "/api/cc/laura/portrait", `${label}: canonical portrait loads from the owner-gated API`, JSON.stringify(portrait));
    const lab = await page.textContent(".laura-internal");
    check(/Internal/.test(lab) && /not publication-approved/.test(lab), `${label}: portrait visibly labelled internal`, lab);
    await page.click(".laura .chips .chip >> nth=0");            // "What did your company do overnight?"
    await page.waitForSelector(".laura-turn .laura-a", { timeout: 20000 });
    await settle();
    const ans = await page.textContent(".laura-turn:last-child .answer");
    console.log(`INFO ${label} answer: ${ans.slice(0, 160)}`);
    await page.click(".laura .chips .chip >> nth=7");            // "What genuinely needs me?"
    await page.waitForFunction(() => document.querySelectorAll(".laura-turn").length >= 2, null, { timeout: 20000 });
    await settle();
    const ev = await page.$$eval(".laura-turn:last-child .laura-evidence a", (a) => a.map((x) => x.getAttribute("href")));
    check(ev.length > 0 && ev.every((h) => h.startsWith("#/")), `${label}: answer has in-app evidence links`, JSON.stringify(ev.slice(0, 3)));
    const sw = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
    check(sw[0] <= sw[1], `${label}: no horizontal scroll`, String(sw));
    if (label === "phone") {
      // Follow-on from the first answer: confirmation dialog, then a mission.
      await page.click(".laura-turn:first-child .row-actions button");
      await page.waitForSelector("dialog.dlg[open]");
      check(/GREEN|orchestrator/.test(await page.textContent("dialog.dlg")), "phone: follow-on asks for confirmation and states its authority");
      await page.click("dialog.dlg [data-dlg=confirm]");
      await page.waitForSelector(".laura-turn:first-child .callout-info:not([hidden])", { timeout: 15000 });
      const done = await page.textContent(".laura-turn:first-child .callout-info:not([hidden])");
      check(/Mission recorded: jobs:\d+/.test(done), "phone: confirmed follow-on created a mission job", done);
      await page.evaluate(() => window.scrollTo(0, 0));
    }
    check(errors.length === 0, `${label}: no console errors (CSP included)`, errors.join(" | ").slice(0, 300));
    if (OUT) await page.screenshot({ path: `${OUT}/laura_${label}.jpg`, type: "jpeg", quality: 60, fullPage: false });
  } catch (e) {
    failures++;
    console.log(`FAIL ${label} aborted: ${String(e && e.message || e).split("\n")[0]}`);
  }
  await context.close();
}
await browser.close();
process.exit(failures ? 1 : 0);
