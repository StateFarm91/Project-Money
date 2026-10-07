// Tiny local mock of the Owner Command Center API (lane C contract), for browser checks only.
// Serves the real static PWA directory at /cc/ with the contract's strict CSP, and fixture JSON
// at /api/cc/*. It enforces the contract's CSRF + nonce + timestamp + step-up rules so the
// check proves the client sends them. NOT shipped; lives under tests/fixtures.
//
// Fixture deviation (documented): login does NOT count as step-up here (the real server's
// does), so the browser check can exercise the step-up prompt on the first approval.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";
import { DATA } from "./data.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const STATIC_DIR = path.resolve(HERE, "../../../src/brambleloop/app/command_center/static");
export const PASSPHRASE = "fixture-owner-passphrase";
const CSP = "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
  + "font-src 'self'; manifest-src 'self'; worker-src 'self'; form-action 'self'; base-uri 'none'; "
  + "frame-ancestors 'none'; object-src 'none'";
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".json": "application/json", ".webmanifest": "application/manifest+json", ".png": "image/png", ".svg": "image/svg+xml" };

export function createMock() {
  const st = { sid: null, csrf: null, stepupUntil: 0, nonces: new Set(), log: [] };

  const send = (res, code, body, headers = {}) => {
    const buf = Buffer.from(JSON.stringify(body));
    res.writeHead(code, { "Content-Type": "application/json", "Cache-Control": "no-store", "Content-Security-Policy": CSP,
      "X-Content-Type-Options": "nosniff", ...headers });
    res.end(buf);
  };
  const readBody = (req) => new Promise((resolve) => {
    let b = "";
    req.on("data", (c) => { b += c; });
    req.on("end", () => { try { resolve(b ? JSON.parse(b) : {}); } catch (_) { resolve(null); } });
  });
  const authed = (req) => !!st.sid && (req.headers.cookie || "").split(/;\s*/).includes(`bl_cc_mock=${st.sid}`);
  const status = (req) => ({ authenticated: authed(req), login_configured: true, totp_required: false,
    csrf_token: authed(req) ? st.csrf : null, session: authed(req) ? { session_id: "s_current", device_label: "Test phone" } : null,
    stepup_valid_until: authed(req) && st.stepupUntil > Date.now() ? new Date(st.stepupUntil).toISOString() : null,
    stepup_window_seconds: 300, server_time: Math.floor(Date.now() / 1000) });

  function guard(req) {
    const h = req.headers;
    const entry = { path: req.url, csrf: h["x-csrf-token"] === st.csrf, nonce: h["x-cc-nonce"] || null, ts: h["x-cc-timestamp"] || null };
    if (!authed(req)) return [401, { error: "not authenticated", code: "NOT_AUTHENTICATED" }, entry];
    if (!entry.csrf) return [403, { error: "bad CSRF token", code: "CSRF" }, entry];
    if (!/^[A-Za-z0-9_-]{16,128}$/.test(entry.nonce || "")) return [400, { error: "missing nonce", code: "STALE_REQUEST" }, entry];
    if (st.nonces.has(entry.nonce)) return [409, { error: "replayed", code: "REPLAY" }, entry];
    if (!entry.ts || Math.abs(Number(entry.ts) - Date.now() / 1000) > 120) return [400, { error: "stale", code: "STALE_REQUEST" }, entry];
    st.nonces.add(entry.nonce);
    return [0, null, entry];
  }

  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, "http://localhost");
    const p = url.pathname;
    if (p === "/__mock/log") return send(res, 200, st.log);
    if (p === "/" ) { res.writeHead(302, { Location: "/cc/" }); return res.end(); }
    if (p.startsWith("/cc/") || p === "/cc") {
      let rel = p === "/cc" || p === "/cc/" ? "index.html" : decodeURIComponent(p.slice(4));
      const file = path.resolve(STATIC_DIR, rel);
      if (!file.startsWith(STATIC_DIR + path.sep) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
        res.writeHead(404, { "Content-Type": "text/plain" }); return res.end("not found");
      }
      res.writeHead(200, { "Content-Type": TYPES[path.extname(file)] || "application/octet-stream", "Content-Security-Policy": CSP,
        "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer", "Cache-Control": "no-cache" });
      return res.end(fs.readFileSync(file));
    }
    if (!p.startsWith("/api/cc/")) { res.writeHead(404); return res.end(); }
    const route = p.slice("/api/cc/".length);

    if (req.method === "GET") {
      if (route === "auth/status") return send(res, 200, status(req));
      if (!authed(req)) return send(res, 401, { error: "not authenticated", code: "NOT_AUTHENTICATED" });
      const simple = { home: "home", "brief/morning": "morning", approvals: "approvals", store: "store", operations: "operations",
        autonomy: "autonomy", learn: "autonomy", insights: "insights", timeline: "timeline", notifications: "notifications",
        account: "account", "account/sessions": "sessions", emergency: "emergency",
        company: "company", completion: "completion" };
      if (Object.hasOwn(simple, route)) return send(res, 200, DATA[simple[route]]());
      if (route === "money") return send(res, 200, DATA.money(url.searchParams.get("period")));
      if (route === "money/drill") return send(res, 200, DATA.moneyDrill(url.searchParams.get("metric") || ""));
      if (route.startsWith("approvals/")) {
        const id = decodeURIComponent(route.slice("approvals/".length));
        const card = DATA.approvals().cards.find((c) => c.card_id === id);
        return card ? send(res, 200, card) : send(res, 404, { error: "no such card", code: "NOT_FOUND" });
      }
      if (route === "operations/drill") return send(res, 200, { kind: url.searchParams.get("kind"), id: url.searchParams.get("id"),
        created_at: new Date().toISOString(), responsible_agent: "visual", detail: "Fixture row", audit: [{ title: "created", at: new Date().toISOString() }] });
      return send(res, 404, { error: "unknown route", code: "NOT_FOUND" });
    }

    if (req.method !== "POST") return send(res, 405, { error: "method" });
    const body = await readBody(req);
    if (route === "auth/login") {
      if (!body || body.passphrase !== PASSPHRASE) return send(res, 401, { error: "Passphrase not accepted.", code: "BAD_CREDENTIALS" });
      st.sid = crypto.randomBytes(16).toString("hex");
      st.csrf = crypto.randomBytes(16).toString("hex");
      st.stepupUntil = 0; // fixture deviation: see header
      st.log.push({ path: "/api/cc/auth/login", ok: true });
      return send(res, 200, { authenticated: true, csrf_token: st.csrf, session: { session_id: "s_current" }, stepup_valid_until: null },
        { "Set-Cookie": `bl_cc_mock=${st.sid}; HttpOnly; SameSite=Strict; Path=/` });
    }
    const [code, err, entry] = guard(req);
    st.log.push({ ...entry, body, refused: code || null });
    if (code) return send(res, code, err);
    if (route === "auth/logout") { st.sid = null; return send(res, 200, { logged_out: true }); }
    if (route === "auth/step-up") {
      if (!body || body.passphrase !== PASSPHRASE) return send(res, 401, { error: "Passphrase not accepted.", code: "BAD_CREDENTIALS" });
      st.stepupUntil = Date.now() + 300000;
      return send(res, 200, { stepup_valid_until: new Date(st.stepupUntil).toISOString() });
    }
    if (route.startsWith("actions/")) {
      const action = decodeURIComponent(route.slice("actions/".length));
      const needsStepUp = /\.approve$/.test(action);
      if (needsStepUp && st.stepupUntil <= Date.now()) return send(res, 403, { error: "step-up required", code: "STEP_UP_REQUIRED" });
      if (action.endsWith(".preview")) return send(res, 200, { ok: true, action, result: { display: "Harbour Throw v1 · CA$9.50 · 7 images · PDF 12 pages", digest: "sha256:abc123" }, audit_id: 1 });
      return send(res, 200, { ok: true, action, result: { granted: true }, audit_id: 2 });
    }
    if (route === "emergency/resume" && st.stepupUntil <= Date.now()) return send(res, 403, { error: "step-up required", code: "STEP_UP_REQUIRED" });
    if (route.startsWith("emergency/")) return send(res, 200, { ok: true });
    if (route === "ask") return send(res, 200, DATA.ask(String((body && body.question) || "")));
    if (route === "home/seen") return send(res, 200, { seen_at: new Date().toISOString() });
    if (/^notifications\/[^/]+\/ack$/.test(route)) return send(res, 200, { acked: route.split("/")[1] });
    if (route === "notifications/refresh") return send(res, 200, { created: 0, deduplicated: 2, suppressed: 37 });
    if (route === "notifications/policy") return send(res, 200, body);
    if (route.startsWith("account/sessions")) return send(res, 200, { revoked: 1 });
    return send(res, 404, { error: "unknown route", code: "NOT_FOUND" });
  });
  return { server, state: st };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  const port = Number(process.env.PORT || 8765);
  createMock().server.listen(port, "127.0.0.1", () => console.log(`mock on http://localhost:${port}/cc/`));
}
