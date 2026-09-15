// Meta Ad Library keyword probe (public transparency tool). NOTE: in the Claude Code sandbox the headless browser cannot complete TLS through the egress proxy and the safety classifier declined a certificate-pinning workaround (LL-007); run this from an environment with a normal trust store, or rely on the substitutes in SPEC section 8. Requires: npm install playwright.
import { chromium } from 'playwright';
const q = process.argv[2] || 'cocktail smoker kit';
const country = process.argv[3] || 'US';
const url = `https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=${country}&q=${encodeURIComponent(q)}&search_type=keyword_unordered&media_type=all`;
const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', headless: true, args: ['--no-sandbox'] }).catch(async e => { console.log('exePath launch failed:', e.message.split('\n')[0]); return chromium.launch({ headless: true, args: ['--no-sandbox'] }); });
const page = await browser.newPage({ locale: 'en-US', userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36' });
try {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(6000);
  const txt = await page.evaluate(() => document.body.innerText);
  const m = txt.match(/~?\s?([\d,]+)\s+results?/i);
  const started = [...txt.matchAll(/Started running on ([A-Z][a-z]{2} \d{1,2}, \d{4})/g)].map(x => x[1]);
  console.log('title:', await page.title());
  console.log('results count text:', m ? m[0] : 'not found');
  console.log('started dates found:', started.length, started.slice(0, 8));
  console.log('page text sample:', txt.replace(/\s+/g, ' ').slice(0, 400));
} catch (e) { console.log('error:', e.message.split('\n')[0]); }
await browser.close();
