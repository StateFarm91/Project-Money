// Meta Ad Library keyword probe (public page, no login). Usage: node adlibrary_probe.mjs "<keyword>" [US|CA] [--json]
// TLS: the sandbox routes HTTPS through an egress proxy; every other tool trusts its CA bundle at /root/.ccr/ca-bundle.crt.
// Chromium does not read that bundle, so this script pins the bundle's certificate public-key hashes: the same trust, nothing more.
import { chromium } from 'playwright';
import { readFileSync, existsSync } from 'node:fs';
import { X509Certificate, createHash } from 'node:crypto';
const q = process.argv[2] || 'cocktail smoker kit', country = (process.argv[3] || 'US').toUpperCase(), asJson = process.argv.includes('--json');
const url = `https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=${country}&q=${encodeURIComponent(q)}&search_type=keyword_unordered&media_type=all`;
const bundle = process.env.CCR_CA_BUNDLE || '/root/.ccr/ca-bundle.crt';
const hashes = [...new Set((existsSync(bundle) ? readFileSync(bundle, 'utf8').match(/-----BEGIN CERTIFICATE-----[\s\S]*?-----END CERTIFICATE-----/g) || [] : []).flatMap(b => { try { return [createHash('sha256').update(new X509Certificate(b).publicKey.export({ type: 'spki', format: 'der' })).digest('base64')]; } catch { return []; } }))];
const args = ['--no-sandbox']; if (hashes.length) args.push(`--ignore-certificate-errors-spki-list=${hashes.join(',')}`);
const exe = existsSync('/opt/pw-browsers/chromium-1194/chrome-linux/chrome') ? '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' : undefined;
const browser = await chromium.launch({ executablePath: exe, headless: true, args });
const page = await browser.newPage({ locale: 'en-US', userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36' });
const out = { keyword: q, country, ok: false };
try {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 }); await page.waitForTimeout(7000);
  for (let i = 0; i < 3; i++) { await page.mouse.wheel(0, 2500); await page.waitForTimeout(1500); }
  const txt = await page.evaluate(() => document.body.innerText);
  const m = txt.match(/~?\s?([\d,]+)\s+results?/i);
  const dates = [...txt.matchAll(/Started running on ([A-Z][a-z]{2} \d{1,2}, \d{4})/g)].map(x => new Date(x[1])).filter(d => !isNaN(d)).sort((a, b) => a - b);
  Object.assign(out, { ok: true, results_count: m ? Number(m[1].replace(/,/g, '')) : null, ads_with_dates: dates.length, earliest: dates[0]?.toISOString().slice(0, 10) || null, latest: dates.at(-1)?.toISOString().slice(0, 10) || null, ads_older_than_28d: dates.filter(d => Date.now() - d > 28 * 864e5).length });
} catch (e) { out.error = e.message.split('\n')[0]; }
await browser.close();
console.log(asJson ? JSON.stringify(out) : Object.entries(out).map(([k, v]) => `${k}: ${v}`).join('\n'));
