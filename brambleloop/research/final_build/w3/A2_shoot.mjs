// Lane A2 screenshot helper: takes a JSON job list and screenshots each local HTML file with the
// preinstalled Chromium (PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers). Never installs browsers.
// Network is blocked for every page: anything that is not file:// or data: is aborted and
// reported, so a page that needed the network fails visibly.
//   node A2_shoot.mjs jobs.json
// job: {"html": path, "out": png, "w": int, "h": int, "selector"?: CSS selector, "pad_top"?: px}
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

const require = createRequire(import.meta.url);
let pw = null;
for (const id of ["playwright", "/opt/node22/lib/node_modules/playwright"]) {
  try { pw = require(id); break; } catch (_) { /* next */ }
}
if (!pw) { console.log("SKIP playwright module not found"); process.exit(3); }
process.env.PLAYWRIGHT_BROWSERS_PATH ||= "/opt/pw-browsers";
const jobs = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const browser = await pw.chromium.launch();
let blocked = 0;
try {
  for (const j of jobs) {
    const page = await browser.newPage({ viewport: { width: j.w, height: j.h }, deviceScaleFactor: 1 });
    await page.route("**/*", (r) => {
      const u = r.request().url();
      if (u.startsWith("file://") || u.startsWith("data:")) return r.continue();
      blocked += 1; console.log("BLOCKED", u); return r.abort();
    });
    await page.goto("file://" + path.resolve(j.html));
    await page.waitForTimeout(200);
    if (j.selector) {
      // element box, extended upward by pad_top so an icon that overlaps the banner is whole
      const b = await page.locator(j.selector).first().boundingBox();
      const pad = Math.min(j.pad_top || 0, b.y);
      await page.screenshot({ path: j.out, clip: { x: b.x, y: b.y - pad, width: b.width, height: b.height + pad } });
    }
    else await page.screenshot({ path: j.out, fullPage: false });
    console.log("OK shot", j.out, fs.statSync(j.out).size);
    await page.close();
  }
} finally {
  await browser.close();
}
console.log("BLOCKED_TOTAL", blocked);
