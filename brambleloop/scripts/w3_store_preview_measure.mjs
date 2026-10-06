// Wave 3 lane B: measure and screenshot the Owner Store Preview pages in Chromium.
//
// Usage: node scripts/w3_store_preview_measure.mjs <html-dir> <out-dir> [--shots]
// <html-dir> holds v1_mobile.html, v2_mobile.html, v1_desktop.html, v2_desktop.html (and
// optionally compare_desktop.html), written by
// `python -m brambleloop.store_foundation.preview_evidence`. Writes <out-dir>/B_metrics.json
// and, with --shots, small JPEG screenshots. Offline: pages are self-contained (data: URIs).
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { execSync } from "node:child_process";

// playwright is installed globally on this machine; resolve it without a local node_modules.
const require = createRequire(import.meta.url);
let pw;
try { pw = require("playwright"); } catch {
  const root = execSync("npm root -g").toString().trim();
  pw = require(path.join(root, "playwright"));
}
const { chromium } = pw;

const [dir, out, ...flags] = process.argv.slice(2);
const shots = flags.includes("--shots");
fs.mkdirSync(out, { recursive: true });

const JARGON = ["compiler", "compiled", "machine-readable", "machine readable", "machine",
  "row check", "row-check", "checked row by row", "row by row", "by code", "software",
  "algorithm", "verifier", "deterministic", "cir", "arithmetic", "program", "pipeline",
  "agent", "model", "formal", "validated", "validation", "automated", "release"];

function measureInPage(args) {
  const { H, JARGON } = args;
  // The shop starts below the preview bar; the first screen is the next H px of the shop.
  const bar = document.querySelector(".pbar, .ribbon");
  const chrome = document.querySelector(".chrome");
  let top0 = 0;
  for (const el of [bar, chrome]) if (el) top0 = Math.max(top0, el.getBoundingClientRect().bottom);
  const frame = document.querySelector(".frame");
  const fr = frame.getBoundingClientRect();
  const top = Math.max(top0, fr.top), bottom = top + H;
  const W = document.documentElement.clientWidth;
  const inScreen = (r) => r.bottom > top && r.top < bottom && r.width > 0 && r.height > 0;
  const clip = (r) => {
    const x0 = Math.max(r.left, fr.left), x1 = Math.min(r.right, fr.right);
    const y0 = Math.max(r.top, top), y1 = Math.min(r.bottom, bottom);
    return Math.max(0, x1 - x0) * Math.max(0, y1 - y0);
  };
  // image share: <img> and elements painting a raster background, union approximated by
  // painting a coarse 2px grid.
  const cell = 2, cols = Math.ceil(fr.width / cell), rows = Math.ceil(H / cell);
  const grid = new Uint8Array(cols * rows);
  const imgs = [...frame.querySelectorAll("*")].filter((el) => {
    if (el.tagName === "IMG") return !/svg\+xml/.test(el.src) || el.classList.contains("icon");
    const bg = getComputedStyle(el).backgroundImage;
    return bg && bg.startsWith("url(") && /image\/(png|jpeg)/.test(bg);
  });
  for (const el of imgs) {
    const r = el.getBoundingClientRect();
    if (!inScreen(r)) continue;
    const x0 = Math.max(0, Math.floor((r.left - fr.left) / cell)), x1 = Math.min(cols, Math.ceil((r.right - fr.left) / cell));
    const y0 = Math.max(0, Math.floor((r.top - top) / cell)), y1 = Math.min(rows, Math.ceil((r.bottom - top) / cell));
    for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) grid[y * cols + x] = 1;
  }
  const imageShare = grid.reduce((a, b) => a + b, 0) / grid.length;
  // text on the first screen
  const walker = document.createTreeWalker(frame, NodeFilter.SHOW_TEXT);
  const texts = [], sizes = new Map();
  const lum = (c) => { const m = c.match(/[\d.]+/g).map(Number); const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return [0.2126 * f(m[0]) + 0.7152 * f(m[1]) + 0.0722 * f(m[2]), m[3] === undefined ? 1 : m[3]]; };
  const bgOf = (el) => { for (let e = el; e; e = e.parentElement) { const cs = getComputedStyle(e); const b = cs.backgroundColor; if (b && !/rgba\(0, 0, 0, 0\)|transparent/.test(b)) { const a = b.match(/[\d.]+/g).map(Number); if (a.length < 4 || a[3] > 0.5) return b; } if (cs.backgroundImage.startsWith("url(")) return null; } return "rgb(255,255,255)"; };
  let minC = 99;
  while (walker.nextNode()) {
    const n = walker.currentNode; const t = n.textContent.replace(/\s+/g, " ").trim();
    if (!t) continue;
    const el = n.parentElement; const cs = getComputedStyle(el);
    if (el.closest(".pv, .pvs")) continue;   // preview labels are not shop content
    if (cs.visibility === "hidden" || cs.display === "none") continue;
    const range = document.createRange(); range.selectNodeContents(n);
    const r = range.getBoundingClientRect();
    if (!inScreen(r) || r.right <= fr.left || r.left >= fr.right) continue;
    texts.push(t);
    const fs = Math.round(parseFloat(cs.fontSize) * 2) / 2;
    sizes.set(fs, (sizes.get(fs) || 0) + t.length);
    const bg = bgOf(el);
    if (bg) { const [l1] = lum(cs.color), [l2] = lum(bg); const c = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05); if (fs < 24) minC = Math.min(minC, c); }
  }
  const text = texts.join(" ");
  const low = " " + text.toLowerCase() + " ";
  let jargon = 0; const terms = [];
  for (const j of JARGON) { const re = new RegExp("(?<![a-z])" + j.replace(/[-]/g, "\\-") + "(?![a-z])", "g"); const k = (low.match(re) || []).length; if (k) { jargon += k; terms.push(j); } }
  const words = (text.match(/[A-Za-z][A-Za-z'’-]*/g) || []).length;
  let body = 0, bodyN = -1; for (const [s, n] of sizes) if (n > bodyN) { body = s; bodyN = n; }
  const h1 = document.querySelector(".frame h1");
  // tap targets: things that look tappable on the shop page
  const taps = [...frame.querySelectorAll("a, summary, .btn, .secs li, .sections li, [aria-disabled]")]
    .filter((el) => el.getBoundingClientRect().width > 0);
  const small = taps.filter((el) => { const r = el.getBoundingClientRect(); return r.height < 44 || r.width < 44; });
  return {
    image_share_pct: Math.round(imageShare * 1000) / 10,
    words_first_screen: words, jargon_first_screen: jargon, jargon_terms: terms,
    distinct_font_sizes: sizes.size, body_px: body,
    headline_px: h1 ? parseFloat(getComputedStyle(h1).fontSize) : null,
    headline_to_body_ratio: h1 ? Math.round(parseFloat(getComputedStyle(h1).fontSize) / body * 100) / 100 : null,
    min_contrast_first_screen: Math.round(minC * 100) / 100,
    tap_targets: taps.length, tap_targets_under_44: small.length,
    horizontal_overflow_px: Math.max(0, document.documentElement.scrollWidth - W),
    first_screen_text: text.slice(0, 600),
  };
}

const browser = await chromium.launch();
const result = { as_of: new Date().toISOString(), basis: "Chromium (Playwright " +
  "headless), first screen = 844 px (phone) / 800 px (desktop) of the shop below the preview bar" };
const pages = [["v1_mobile", 390, 844], ["v2_mobile", 390, 844], ["v1_desktop", 1280, 800],
  ["v2_desktop", 1280, 800], ["compare_desktop", 1280, 800]];
for (const [name, w, h] of pages) {
  const file = path.join(dir, name + ".html");
  if (!fs.existsSync(file)) continue;
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  await page.goto("file://" + file);
  if (!name.startsWith("compare")) result[name] = await page.evaluate(measureInPage, { H: h, JARGON });
  if (shots) {
    if (name.startsWith("compare")) {
      await page.screenshot({ path: path.join(out, `B_${name}.jpg`), type: "jpeg", quality: 62, fullPage: false, clip: { x: 0, y: 0, width: w, height: 1100 } });
    } else {
      const y = await page.evaluate(() => { const f = document.querySelector(".frame"); return f.getBoundingClientRect().top + scrollY; });
      await page.screenshot({ path: path.join(out, `B_${name}_top.jpg`), type: "jpeg", quality: 62, fullPage: true, clip: { x: 0, y, width: w, height: h } });
      if (name.startsWith("v2")) {
        const full = await page.evaluate(() => document.documentElement.scrollHeight);
        // About/story and FAQ: the second and third screens of the shop
        const ab = await page.evaluate(() => { const a = document.querySelector(".about"); return a.getBoundingClientRect().top + scrollY; });
        await page.screenshot({ path: path.join(out, `B_${name}_about.jpg`), type: "jpeg", quality: 62, fullPage: true, clip: { x: 0, y: ab, width: w, height: Math.min(h * 1.6, full - ab) } });
        const bd = await page.evaluate(() => { const a = document.querySelector(".board"); return a.getBoundingClientRect().top + scrollY; });
        if (name === "v2_desktop") await page.screenshot({ path: path.join(out, `B_${name}_board.jpg`), type: "jpeg", quality: 60, fullPage: true, clip: { x: 0, y: bd, width: w, height: 1500 } });
      }
    }
  }
  await ctx.close();
}
await browser.close();
fs.writeFileSync(path.join(out, "B_metrics.json"), JSON.stringify(result, null, 1));
console.log(JSON.stringify(Object.fromEntries(Object.entries(result).filter(([k]) => k.includes("_")).map(([k, v]) => [k, Object.fromEntries(Object.entries(v).filter(([kk]) => kk !== "first_screen_text"))])), null, 1));
