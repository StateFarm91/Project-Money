// Lane A contact-sheet renderer: screenshots every *.html in <in_dir> into <out_dir>/<name>.png
// using the preinstalled Chromium (PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers); never installs.
//   node A_shoot.mjs <in_dir> <out_dir>
// Each page declares its viewport with <meta name="shoot" content="WIDTHxHEIGHT">.
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
const [inDir, outDir] = process.argv.slice(2);
fs.mkdirSync(outDir, { recursive: true });
const browser = await pw.chromium.launch();
try {
  for (const f of fs.readdirSync(inDir).filter((x) => x.endsWith(".html")).sort()) {
    const html = fs.readFileSync(path.join(inDir, f), "utf8");
    const m = html.match(/name="shoot" content="(\d+)x(\d+)"/);
    const [w, h] = m ? [Number(m[1]), Number(m[2])] : [1200, 800];
    const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
    await page.goto("file://" + path.resolve(inDir, f));
    await page.waitForTimeout(150);
    const out = path.join(outDir, f.replace(/\.html$/, ".png"));
    await page.screenshot({ path: out, fullPage: true });
    console.log("OK shot", out, fs.statSync(out).size);
    await page.close();
  }
} finally {
  await browser.close();
}
