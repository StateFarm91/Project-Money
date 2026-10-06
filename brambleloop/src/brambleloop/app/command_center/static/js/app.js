// Owner Command Center shell: auth gate, hash router, navigation, theme, connectivity.
import { h, icon, clear } from "./dom.js";
import { loadStatus, onAuthRequired, login, logout, ApiError, api, authState, setStepUpPrompt } from "./api.js";
import { loading, errorState, statusPill, toast, stepUpDialog } from "./components.js";
import { TABS, MORE_ROUTES } from "./routes.js";

const EXTRA_ROUTES = {
  more: { id: "more", label: "More" },
  drill: { id: "drill", label: "Source details" },
  emergency: { id: "emergency", label: "Emergency controls" },
};
const state = { session: null, route: null, renderSeq: 0 };
const root = document.getElementById("main");
const THEME_KEY = "cc-theme";

// ---- theme (per-viewer convenience only; storage may be unavailable) -----------------------
export function getTheme() {
  try { return localStorage.getItem(THEME_KEY) || "auto"; } catch (_) { return "auto"; }
}
export function setTheme(t) {
  try { localStorage.setItem(THEME_KEY, t); } catch (_) { /* private mode: still apply */ }
  applyTheme(t);
}
function applyTheme(t) {
  if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
  else delete document.documentElement.dataset.theme;
}
applyTheme(getTheme());

// ---- navigation -----------------------------------------------------------------------------
function navLink(tab, { compact }) {
  return h("a", { class: compact ? "tab" : "side-link", href: `#/${tab.id}`, data: { tab: tab.id } },
    icon(tab.icon, compact ? 22 : 20),
    h("span", { class: compact ? "tab-label" : "side-label" }, tab.label),
    h("span", { class: "badge", hidden: true, data: { badge: tab.id } }));
}

function buildNav() {
  const tabbar = document.getElementById("tabbar");
  const side = document.getElementById("sidenav");
  clear(tabbar);
  clear(side);
  for (const t of TABS.filter((t) => t.primary)) tabbar.append(navLink(t, { compact: true }));
  tabbar.append(navLink({ id: "more", label: "More", icon: "more" }, { compact: true }));
  for (const t of TABS) side.append(navLink(t, { compact: false }));
}

function markActive(tabId) {
  const moreIds = new Set([...MORE_ROUTES, "emergency"]);
  for (const a of document.querySelectorAll("[data-tab]")) {
    const id = a.dataset.tab;
    const active = id === tabId || (id === "more" && moreIds.has(tabId));
    if (active) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  }
}

export function setBadge(tabId, count) {
  if (tabId === "notifications") setBadge("more", count); // notifications live under More on phones
  for (const b of document.querySelectorAll(`[data-badge="${tabId}"]`)) {
    const n = Number(count);
    if (Number.isFinite(n) && n > 0) {
      b.hidden = false;
      b.textContent = n > 99 ? "99+" : String(n);
      b.setAttribute("aria-label", `${n} pending`);
    } else { b.hidden = true; b.textContent = ""; }
  }
}

function showPhase(phaseName) {
  const phase = document.getElementById("phase");
  clear(phase);
  if (!phaseName) return;
  const p = String(phaseName).toUpperCase();
  phase.append(statusPill(p === "PRODUCTION" ? "OK" : p === "SHADOW" ? "INFO" : "DEGRADED", p));
  phase.title = `Company phase: ${p}`;
}

/** Background refresh of chrome (phase pill, badges). Failures leave the chrome blank, never 0. */
export async function refreshChrome() {
  const [em, ap, no] = await Promise.allSettled([api.emergency(), api.approvals(), api.notifications()]);
  if (em.status === "fulfilled") {
    const ph = em.value.data && em.value.data.phase;
    showPhase(ph && typeof ph === "object" ? (ph.phase || ph.effective_phase) : ph);
  }
  if (ap.status === "fulfilled") {
    const cards = (ap.value.data && ap.value.data.cards) || [];
    setBadge("approvals", cards.filter((c) => c && c.executable !== false).length);
  }
  if (no.status === "fulfilled") {
    const list = (no.value.data && no.value.data.notifications) || [];
    setBadge("notifications", list.filter((n) => n && !n.acked_at).length);
  }
}

// ---- routing --------------------------------------------------------------------------------
function parseHash() {
  const raw = location.hash.replace(/^#\/?/, "");
  const [pathPart, queryPart] = raw.split("?");
  const parts = pathPart.split("/").filter(Boolean).map((p) => {
    try { return decodeURIComponent(p); } catch (_) { return p; }
  });
  const query = new URLSearchParams(queryPart || "");
  return { name: parts[0] || "home", params: parts.slice(1), query };
}

async function route() {
  if (!state.session || !state.session.authenticated) return showLogin();
  const r = parseHash();
  const def = TABS.find((t) => t.id === r.name) || (Object.hasOwn(EXTRA_ROUTES, r.name) ? EXTRA_ROUTES[r.name] : null);
  const seq = ++state.renderSeq;
  if (!def) { location.replace("#/home"); return; }
  markActive(def.id === "drill" ? "" : def.id);
  document.getElementById("view-title").textContent = def.label;
  document.title = `${def.label} · Brambleloop`;
  clear(root);
  root.append(loading(`Loading ${def.label}`));
  try {
    const mod = await import(`./views/${def.id}.js`);
    const node = await mod.render({ params: r.params, query: r.query, session: state.session,
      rerender: () => route(), setBadge });
    if (seq !== state.renderSeq) return; // a newer navigation won
    clear(root);
    root.append(node);
  } catch (err) {
    if (seq !== state.renderSeq) return;
    if (err instanceof ApiError && err.status === 401) return; // login takes over
    clear(root);
    root.append(errorState(err, () => route()));
  }
  if (state.route && state.route !== location.hash) {
    window.scrollTo(0, 0);
    root.focus({ preventScroll: true });
  }
  state.route = location.hash;
}

// ---- login ----------------------------------------------------------------------------------
function showLogin(message) {
  document.body.classList.add("is-signed-out");
  document.getElementById("view-title").textContent = "Sign in";
  document.title = "Sign in · Brambleloop";
  showPhase(null);
  clear(root);
  const st = state.session || {};
  const totpRequired = !!st.totp_required;
  const input = h("input", { id: "login-pass", type: "password", autocomplete: "current-password",
    required: true, name: "passphrase" });
  const totp = totpRequired ? h("input", { id: "login-totp", type: "text", inputMode: "numeric",
    autocomplete: "one-time-code", maxLength: 6, required: true, name: "totp" }) : null;
  const device = h("input", { id: "login-device", type: "text", autocomplete: "off", maxLength: 40,
    name: "device", placeholder: "e.g. My phone" });
  const err = h("p", { class: "form-error", role: "alert" }, message || "");
  const btn = h("button", { class: "btn btn-primary btn-block", type: "submit" }, "Sign in");
  const notConfigured = st.login_configured === false;
  const form = h("form", { class: "card login" },
    h("div", { class: "login-mark" }, icon("shield", 32)),
    h("h2", { class: "card-title" }, "Owner sign-in"),
    h("p", { class: "muted" }, "The Brambleloop Command Center is for the company owner only. Sessions expire automatically."),
    notConfigured ? h("p", { class: "callout callout-warn" }, "Owner sign-in is not configured on the server yet, so nobody can sign in. That is the safe default.") : null,
    h("label", { class: "field", for: "login-pass" }, "Owner passphrase"), input,
    totp ? h("label", { class: "field", for: "login-totp" }, "6-digit authenticator code") : null, totp,
    h("label", { class: "field", for: "login-device" }, "Name this device (optional)"), device,
    err, btn);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    btn.disabled = true;
    err.textContent = "";
    try {
      await login(input.value, totp ? totp.value.trim() : null, device.value.trim() || null);
      input.value = "";
      await boot();
    } catch (ex) {
      err.textContent = ex.message || "Sign-in refused";
    } finally { btn.disabled = false; }
  });
  root.append(form);
  input.focus();
}

export async function signOut() {
  try { await logout(); } catch (_) { /* session is cleared client-side regardless */ }
  state.session = { authenticated: false };
  showLogin("Signed out.");
}

// ---- connectivity ---------------------------------------------------------------------------
function updateOnline() {
  const el = document.getElementById("net");
  const on = navigator.onLine;
  el.hidden = on;
  document.body.classList.toggle("is-offline", !on);
}
window.addEventListener("online", () => { updateOnline(); toast("Back online. Refreshing."); route(); });
window.addEventListener("offline", () => { updateOnline(); toast("Offline. Nothing you tap will be sent until you reconnect.", "warn"); });

// ---- boot -----------------------------------------------------------------------------------
async function boot() {
  try {
    state.session = await loadStatus();
  } catch (err) {
    clear(root);
    root.append(errorState(err, () => boot()));
    return;
  }
  if (!state.session || !state.session.authenticated) return showLogin();
  document.body.classList.remove("is-signed-out");
  route();
  refreshChrome().catch(() => {});
}

setStepUpPrompt(() => stepUpDialog({ totpRequired: authState().totpRequired }));

onAuthRequired(() => {
  state.session = { authenticated: false };
  showLogin("Your session ended. Please sign in again.");
});

window.addEventListener("hashchange", () => route());
document.getElementById("skip").addEventListener("click", () => root.focus());
document.getElementById("refresh").addEventListener("click", () => route());

buildNav();
updateOnline();
boot();

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js", { scope: "./" }).catch(() => { /* PWA optional */ });
}
