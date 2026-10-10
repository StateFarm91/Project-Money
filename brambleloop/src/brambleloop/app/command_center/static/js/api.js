// Typed client for the Owner Command Center API, per lane C's contract
// research/final_build/v1_1/COMMAND_CENTER_API.md. Every path and header name the frontend
// depends on is declared here, so adapting to a contract change is a one-file edit.
//
// Security properties this module guarantees for every caller:
//  - same-origin requests only; the HttpOnly session cookie travels with credentials:"same-origin";
//  - every non-GET call carries X-CSRF-Token, a fresh X-CC-Nonce and X-CC-Timestamp (§0);
//  - a 403 STEP_UP_REQUIRED is answered by asking the owner to re-authenticate, then retrying
//    once with a NEW nonce -- never by replaying the old request;
//  - responses are NEVER written to persistent storage (no Cache API, no localStorage). The
//    only cache is an in-memory Map that dies with the tab, used to show the last good view
//    *labelled as stale* when the network drops (F-883, F-898).

export const API_BASE = "/api/cc";
export const H_CSRF = "X-CSRF-Token";
export const H_NONCE = "X-CC-Nonce";
export const H_TS = "X-CC-Timestamp";

/** @typedef {"OK"|"DEGRADED"|"BLOCKED"|"UNKNOWN"} Status */
/**
 * @typedef {Object} Envelope   cross-lane provider envelope (§0)
 * @property {Status} status
 * @property {string|null} as_of
 * @property {"measured"|"estimated"|"modelled"|"unknown"} basis
 * @property {Array<Object>} items
 * @property {Array<string>} sources
 * @property {string=} reason
 * @property {string=} provider
 */
/**
 * @typedef {Object} TabResponse
 * @property {string} tab
 * @property {string} generated_at
 * @property {Object<string, Envelope>} sections
 */
/**
 * @typedef {Object} Money       (§0) render `display`; value_cad null is UNKNOWN, never 0
 * @property {number|null} value_cad
 * @property {"MEASURED"|"ESTIMATED"|"MODELLED"|"UNKNOWN"|"UNMEASURED"} state
 * @property {string} basis
 * @property {string} display
 * @property {Array<string>} sources
 */

const q = (params) => {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") s.set(k, String(v));
  const t = s.toString();
  return t ? `?${t}` : "";
};
const seg = encodeURIComponent;

export const ENDPOINTS = {
  status: () => `${API_BASE}/auth/status`,
  login: () => `${API_BASE}/auth/login`,
  logout: () => `${API_BASE}/auth/logout`,
  stepUp: () => `${API_BASE}/auth/step-up`,
  home: () => `${API_BASE}/home`,
  homeSeen: () => `${API_BASE}/home/seen`,
  morning: (hours = 12) => `${API_BASE}/brief/morning${q({ hours })}`,
  approvals: () => `${API_BASE}/approvals`,
  approval: (id) => `${API_BASE}/approvals/${seg(id)}`,
  action: (action) => `${API_BASE}/actions/${seg(action)}`,
  store: () => `${API_BASE}/store`,
  money: (period) => `${API_BASE}/money${q({ period })}`,
  moneyDrill: (metric, period) => `${API_BASE}/money/drill${q({ metric, period })}`,
  operations: () => `${API_BASE}/operations`,
  opsDrill: (kind, id) => `${API_BASE}/operations/drill${q({ kind, id })}`,
  autonomy: () => `${API_BASE}/autonomy`,
  company: () => `${API_BASE}/company`,
  completion: () => `${API_BASE}/completion`,
  launchPacket: () => `${API_BASE}/launch/packet`,
  // W4-STORE: owner-session gated (CSRF + nonce) although it is outside API_BASE.
  liveObservation: () => "/api/store/live_observation",
  insights: () => `${API_BASE}/insights`,
  timeline: (limit = 50) => `${API_BASE}/timeline${q({ limit })}`,
  notifications: () => `${API_BASE}/notifications`,
  notificationAck: (id) => `${API_BASE}/notifications/${seg(id)}/ack`,
  notificationsRefresh: () => `${API_BASE}/notifications/refresh`,
  notificationPolicy: () => `${API_BASE}/notifications/policy`,
  account: () => `${API_BASE}/account`,
  sessions: () => `${API_BASE}/account/sessions`,
  revokeSession: (id) => `${API_BASE}/account/sessions/${seg(id)}/revoke`,
  revokeOthers: () => `${API_BASE}/account/sessions/revoke-others`,
  emergency: () => `${API_BASE}/emergency`,
  emergencyPause: () => `${API_BASE}/emergency/pause`,
  emergencyKill: () => `${API_BASE}/emergency/kill`,
  emergencyResume: () => `${API_BASE}/emergency/resume`,
  ask: () => `${API_BASE}/ask`,
  laura: () => `${API_BASE}/laura`,
  lauraConversation: (limit = 20) => `${API_BASE}/laura/conversation${q({ limit })}`,
  lauraAsk: () => `${API_BASE}/laura/ask`,
  lauraFollowOn: () => `${API_BASE}/laura/follow-on`,
  lauraPortrait: () => `${API_BASE}/laura/portrait`,
  lauraPresence: () => `${API_BASE}/laura/presence`,
  lauraVoiceSpec: () => `${API_BASE}/laura/voice-spec`,
  privateStatus: () => `${API_BASE}/private/status`,
  privateOpen: () => `${API_BASE}/private/open`,
  privateClose: () => `${API_BASE}/private/close`,
  privateView: () => `${API_BASE}/private/view`,
  privateRemember: () => `${API_BASE}/private/remember`,
  privateTurn: () => `${API_BASE}/private/turn`,
  privateForget: () => `${API_BASE}/private/forget`,
};

export class ApiError extends Error {
  constructor(status, message, body) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = body && body.code ? String(body.code) : null;
    this.body = body;
  }
}
export class OfflineError extends Error {
  constructor(message) { super(message); this.name = "OfflineError"; }
}

const memory = new Map(); // path -> {data, fetchedAt}; in-memory only, never persisted
const auth = { csrf: null, stepupValidUntil: null, totpRequired: false, skewSec: 0 };
const authListeners = new Set();
let stepUpPrompt = null; // async () => {passphrase, totp} | null, installed by the shell

export function onAuthRequired(fn) { authListeners.add(fn); return () => authListeners.delete(fn); }
function emitAuthRequired(reason) { for (const fn of authListeners) fn(reason); }
export function setStepUpPrompt(fn) { stepUpPrompt = fn; }
export function authState() { return { ...auth }; }
export function forgetAll() { memory.clear(); auth.csrf = null; auth.stepupValidUntil = null; }

export function stepUpValid(now = Date.now()) {
  if (!auth.stepupValidUntil) return false;
  const t = Date.parse(auth.stepupValidUntil);
  return Number.isFinite(t) && t - 15000 > now; // 15 s margin so it does not expire mid-flight
}

function absorbAuth(body) {
  if (!body || typeof body !== "object") return;
  if ("csrf_token" in body && body.csrf_token) auth.csrf = body.csrf_token;
  if ("stepup_valid_until" in body) auth.stepupValidUntil = body.stepup_valid_until || null;
  if ("totp_required" in body) auth.totpRequired = !!body.totp_required;
  if (typeof body.server_time === "number") auth.skewSec = Math.round(body.server_time - Date.now() / 1000);
}

function nonce() {
  if (crypto.randomUUID) return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
}

async function parse(res) {
  const type = res.headers.get("content-type") || "";
  if (type.includes("application/json")) {
    try { return await res.json(); } catch (_) { return null; }
  }
  return null;
}

function errMessage(body, fallback) {
  return (body && (body.error || body.detail || body.reason)) || fallback;
}

/**
 * GET a JSON resource. Resolves {data, stale:false, fetchedAt} or, when the network is down
 * and this tab fetched it before, {data, stale:true, fetchedAt}. Rejects otherwise.
 */
export async function get(path) {
  let res;
  try {
    res = await fetch(path, { method: "GET", credentials: "same-origin", cache: "no-store",
      headers: { Accept: "application/json" } });
  } catch (_) {
    const prior = memory.get(path);
    if (prior) return { data: prior.data, stale: true, fetchedAt: prior.fetchedAt };
    throw new OfflineError("You appear to be offline, and this view has not been loaded in this session.");
  }
  const body = await parse(res);
  if (res.status === 401) { emitAuthRequired("session"); throw new ApiError(401, "Sign-in required", body); }
  if (!res.ok) throw new ApiError(res.status, errMessage(body, `Request failed (${res.status})`), body);
  const fetchedAt = new Date().toISOString();
  memory.set(path, { data: body, fetchedAt });
  return { data: body, stale: false, fetchedAt };
}

async function rawPost(path, payload, { withReplayGuard = true } = {}) {
  const headers = { "Content-Type": "application/json", Accept: "application/json" };
  if (withReplayGuard) {
    headers[H_CSRF] = auth.csrf || "";
    headers[H_NONCE] = nonce();
    headers[H_TS] = String(Math.floor(Date.now() / 1000) + auth.skewSec);
  }
  let res;
  try {
    res = await fetch(path, { method: "POST", credentials: "same-origin", cache: "no-store",
      headers, body: JSON.stringify(payload || {}) });
  } catch (_) {
    throw new OfflineError("Offline: the action was NOT sent. Nothing changed.");
  }
  return { res, body: await parse(res) };
}

/**
 * POST with CSRF + nonce + timestamp. On STEP_UP_REQUIRED, asks the owner to re-authenticate
 * (if a prompt is installed) and retries exactly once with a fresh nonce.
 */
export async function post(path, payload = {}) {
  if (!auth.csrf) {
    try { await loadStatus(); } catch (_) { /* handled below */ }
    if (!auth.csrf) { emitAuthRequired("csrf"); throw new ApiError(401, "Your session has no CSRF token. Please sign in again."); }
  }
  let { res, body } = await rawPost(path, payload);
  if (res.status === 403 && body && body.code === "STEP_UP_REQUIRED" && stepUpPrompt) {
    const cred = await stepUpPrompt();
    if (!cred) throw new ApiError(403, "Cancelled: re-authentication is required for this action. Nothing changed.", body);
    await stepUp(cred.passphrase, cred.totp);
    ({ res, body } = await rawPost(path, payload));
  }
  if (res.status === 401) { emitAuthRequired("session"); throw new ApiError(401, "Sign-in required", body); }
  if (!res.ok) throw new ApiError(res.status, errMessage(body, `Action refused (${res.status})`), body);
  memory.clear(); // a mutation can change anything this tab has seen
  absorbAuth(body);
  return body;
}

export async function loadStatus() {
  let res;
  try {
    res = await fetch(ENDPOINTS.status(), { credentials: "same-origin", cache: "no-store",
      headers: { Accept: "application/json" } });
  } catch (_) {
    throw new OfflineError("Offline: cannot reach the Command Center.");
  }
  const body = await parse(res);
  if (res.ok && body) { absorbAuth(body); return body; }
  throw new ApiError(res.status, errMessage(body, `Session check failed (${res.status})`), body);
}

export async function login(passphrase, totp, deviceLabel) {
  const payload = { passphrase };
  if (totp) payload.totp = totp;
  if (deviceLabel) payload.device_label = deviceLabel;
  const { res, body } = await rawPost(ENDPOINTS.login(), payload, { withReplayGuard: false });
  if (!res.ok) throw new ApiError(res.status, errMessage(body, "Sign-in refused"), body);
  absorbAuth(body);
  return body;
}

export async function stepUp(passphrase, totp) {
  const payload = { passphrase };
  if (totp) payload.totp = totp;
  const { res, body } = await rawPost(ENDPOINTS.stepUp(), payload);
  if (res.status === 401) { emitAuthRequired("session"); throw new ApiError(401, "Session ended during re-authentication.", body); }
  if (!res.ok) throw new ApiError(res.status, errMessage(body, "Re-authentication refused"), body);
  absorbAuth(body);
  return body;
}

export async function logout() {
  try { await post(ENDPOINTS.logout(), {}); } finally { forgetAll(); }
}

export const api = {
  home: () => get(ENDPOINTS.home()),
  homeSeen: () => post(ENDPOINTS.homeSeen(), {}),
  morning: (hours) => get(ENDPOINTS.morning(hours)),
  approvals: () => get(ENDPOINTS.approvals()),
  approval: (id) => get(ENDPOINTS.approval(id)),
  action: (action, params) => post(ENDPOINTS.action(action), params || {}),
  store: () => get(ENDPOINTS.store()),
  money: (period) => get(ENDPOINTS.money(period)),
  moneyDrill: (metric, period) => get(ENDPOINTS.moneyDrill(metric, period)),
  operations: () => get(ENDPOINTS.operations()),
  opsDrill: (kind, id) => get(ENDPOINTS.opsDrill(kind, id)),
  autonomy: () => get(ENDPOINTS.autonomy()),
  company: () => get(ENDPOINTS.company()),
  completion: () => get(ENDPOINTS.completion()),
  launchPacket: () => get(ENDPOINTS.launchPacket()),
  liveObservation: (observedAt, fields, statement) => post(ENDPOINTS.liveObservation(), { observed_at: observedAt, fields, statement }),
  insights: () => get(ENDPOINTS.insights()),
  timeline: (limit) => get(ENDPOINTS.timeline(limit)),
  notifications: () => get(ENDPOINTS.notifications()),
  ackNotification: (id) => post(ENDPOINTS.notificationAck(id), {}),
  refreshNotifications: () => post(ENDPOINTS.notificationsRefresh(), {}),
  setNotificationPolicy: (policy) => post(ENDPOINTS.notificationPolicy(), policy),
  account: () => get(ENDPOINTS.account()),
  sessions: () => get(ENDPOINTS.sessions()),
  revokeSession: (id) => post(ENDPOINTS.revokeSession(id), {}),
  revokeOthers: () => post(ENDPOINTS.revokeOthers(), {}),
  emergency: () => get(ENDPOINTS.emergency()),
  pause: (scope, reason, department) => post(ENDPOINTS.emergencyPause(), { scope, reason, ...(department ? { department } : {}) }),
  kill: (reason) => post(ENDPOINTS.emergencyKill(), { reason }),
  resume: (scope, reason, department) => post(ENDPOINTS.emergencyResume(), { scope, reason, ...(department ? { department } : {}) }),
  ask: (question) => post(ENDPOINTS.ask(), { question }),
  laura: () => get(ENDPOINTS.laura()),
  lauraConversation: (limit) => get(ENDPOINTS.lauraConversation(limit)),
  lauraAsk: (question) => post(ENDPOINTS.lauraAsk(), { question }),
  lauraPresence: () => get(ENDPOINTS.lauraPresence()),
  lauraVoiceSpec: () => get(ENDPOINTS.lauraVoiceSpec()),
  // Owner-private context: status is non-content; every content call is a POST, so nothing
  // private enters this tab's GET memory or any cache.
  privateStatus: () => get(ENDPOINTS.privateStatus()),
  privateOpen: () => post(ENDPOINTS.privateOpen(), {}),
  privateClose: () => post(ENDPOINTS.privateClose(), {}),
  privateView: () => post(ENDPOINTS.privateView(), {}),
  privateRemember: (key, text) => post(ENDPOINTS.privateRemember(), { key, text }),
  privateTurn: (text) => post(ENDPOINTS.privateTurn(), { text }),
  privateForget: (id) => post(ENDPOINTS.privateForget(), { id }),
  lauraFollowOn: (turnId, proposalKey) => post(ENDPOINTS.lauraFollowOn(), { turn_id: turnId, proposal_key: proposalKey, confirm: true }),
};
