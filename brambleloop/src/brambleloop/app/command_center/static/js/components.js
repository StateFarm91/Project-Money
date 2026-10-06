// Shared UI components. All text goes through h()/textContent (see dom.js).
import { h, icon, clear } from "./dom.js";
import { stepUpValid, stepUp, authState } from "./api.js";
import { formatMoney, moneyValue, basisLabel, isNonActual, relTime, utcStamp, statusClass,
  humanize, formatNumber, UNKNOWN_TEXT } from "./format.js";

export function statusPill(status, label) {
  const s = String(status || "UNKNOWN").toUpperCase();
  return h("span", { class: ["pill", `pill-${statusClass(s)}`] }, label || s);
}

export function basisTag(basis) {
  const label = basisLabel(basis);
  return h("span", { class: ["tag", isNonActual(basis) ? "tag-est" : "tag-actual"],
    title: `Basis: ${label}` }, label);
}

/** "Updated 3 min ago" with the exact UTC stamp; "STALE" when the view is from memory. */
export function freshness(asOf, { stale = false, fetchedAt = null } = {}) {
  const t = h("time", { datetime: asOf || "", title: utcStamp(asOf) },
    asOf ? `as of ${relTime(asOf)}` : "as of: unknown");
  return h("span", { class: ["fresh", stale ? "fresh-stale" : null] },
    stale ? h("strong", null, `STALE (offline, loaded ${relTime(fetchedAt)}) · `) : null, t);
}

/** Basis tag for an envelope, only when it says something: estimated/modelled/forecast, or an
 *  unknown basis on data that is otherwise presented as current. Measured is the default. */
export function basisNote(basis, status) {
  const b = String(basis || "unknown").toLowerCase();
  if (!isNonActual(b)) return [];
  if (b === "unknown" && String(status || "").toUpperCase() === "UNKNOWN") return [];
  return [" · ", basisTag(b)];
}

export function card(opts, ...children) {
  const { title, subtitle, actions, cls, tag = "section", labelId } = opts || {};
  const id = labelId || (title ? `c-${Math.random().toString(36).slice(2, 9)}` : null);
  return h(tag, { class: ["card", cls], aria: id ? { labelledby: id } : null },
    title || actions ? h("header", { class: "card-head" },
      h("div", null, title ? h("h2", { class: "card-title", id }, title) : null,
        subtitle ? h("p", { class: "card-sub" }, subtitle) : null),
      actions || null) : null,
    ...children);
}

export function sourcesList(sources, { label = "Sources" } = {}) {
  const list = Array.isArray(sources) ? sources.filter((s) => s !== null && s !== undefined && s !== "") : [];
  if (!list.length) return h("p", { class: "sources sources-none" }, "No sources reported, so treat this as unverified.");
  return h("details", { class: "sources" },
    h("summary", null, `${label} (${list.length})`),
    h("ul", null, list.map((s) => {
      const ref = typeof s === "string" ? s : (s.ref || s.id || s.path || s.table || JSON.stringify(s));
      const text = typeof s === "string" ? s : (s.label || s.title || ref);
      return h("li", null, h("a", { href: `#/drill/${encodeURIComponent(ref)}` }, text));
    })));
}

/** Money tile: label, amount (or "Unknown"), basis tag, optional drill link. */
export function moneyTile(label, value, { drillHref = null, currency = "CAD", hint = null } = {}) {
  const m = moneyValue(value, currency);
  const amount = h("p", { class: ["tile-value", m.known ? null : "is-unknown"], data: { money: m.known ? "known" : "unknown" } },
    formatMoney(value, currency));
  const body = [h("p", { class: "tile-label" }, label), amount,
    h("p", { class: "tile-meta" }, basisTag(m.known ? m.basis : "unknown"),
      !m.known && m.reason ? h("span", { class: "tile-reason", title: m.reason }, m.reason) : null,
      hint ? h("span", { class: "tile-reason" }, hint) : null)];
  if (drillHref) {
    return h("a", { class: "tile tile-link", href: drillHref,
      aria: { label: `${label}: ${formatMoney(value, currency)}, ${basisLabel(m.known ? m.basis : "unknown")}. Show source records` } },
    ...body, h("span", { class: "tile-chev" }, icon("chevron", 18)));
  }
  return h("div", { class: "tile" }, ...body);
}

export function statTile(label, value, { href = null, status = null } = {}) {
  const v = (value === null || value === undefined) ? UNKNOWN_TEXT : (typeof value === "number" ? formatNumber(value) : String(value));
  const kids = [h("p", { class: "tile-label" }, label),
    h("p", { class: ["tile-value", v === UNKNOWN_TEXT ? "is-unknown" : null] }, v),
    status ? h("p", { class: "tile-meta" }, statusPill(status)) : null];
  return href ? h("a", { class: "tile tile-link", href }, ...kids, h("span", { class: "tile-chev" }, icon("chevron", 18)))
    : h("div", { class: "tile" }, ...kids);
}

function isMoneyish(key, v) {
  return v && typeof v === "object" && !Array.isArray(v)
    && ("value_cad" in v || "currency" in v || "amount_minor" in v || "cents" in v || ("amount" in v && ("basis" in v || "status" in v)));
}

const TITLE_KEYS = ["title", "name", "label", "headline", "summary", "subject", "statement", "what", "action",
  "department", "provider", "scope", "job_type", "metric", "kind", "id"];
const DETAIL_KEYS = ["detail", "reason", "description", "message", "why", "explanation", "body"];
const SKIP_KEYS = new Set([...DETAIL_KEYS, "status", "severity", "sources", "source", "ref", "drill",
  "href", "items", "evidence", "as_of", "basis", "state", "provider", "card_id", "seal"]);

function titleOf(item) {
  for (const k of TITLE_KEYS) if (item[k] !== undefined && item[k] !== null && item[k] !== "") return [k, String(item[k])];
  return [null, "Item"];
}

export function itemTitle(item) {
  if (item === null || item === undefined) return "";
  if (typeof item !== "object") return String(item);
  return titleOf(item)[1];
}

/** Generic item row for an envelope's items[]: title, status, detail, key facts, drill link. */
export function itemRow(item, { drill = true } = {}) {
  if (item === null || typeof item !== "object") return h("li", { class: "row" }, h("p", { class: "row-title" }, String(item)));
  const [titleKey, title] = titleOf(item);
  let detailKey = null;
  for (const k of DETAIL_KEYS) if (item[k]) { detailKey = k; break; }
  const facts = [];
  for (const [k, v] of Object.entries(item)) {
    if (k === titleKey || SKIP_KEYS.has(k) || v === undefined) continue;
    if (facts.length >= 6) break;
    let text;
    if (isMoneyish(k, v)) {
      const m = moneyValue(v);
      text = m.known ? `${formatMoney(v)} · ${basisLabel(m.basis)}` : UNKNOWN_TEXT;
    }
    else if (v === null) text = UNKNOWN_TEXT;
    else if (typeof v === "number" && /_cad$/i.test(k)) text = formatMoney({ value_cad: v, state: "MEASURED" });
    else if (Array.isArray(v) && v.length && v.every((x) => typeof x !== "object")) text = v.join(", ");
    else if (typeof v === "object") continue;
    else if (typeof v === "boolean") text = v ? "Yes" : "No";
    else if (/(_at|_time|^at|^when|deadline)$/i.test(k) && typeof v === "string") text = `${relTime(v)} (${utcStamp(v)})`;
    else text = String(v);
    facts.push(h("div", { class: "fact" }, h("dt", null, humanize(k)), h("dd", null, text)));
  }
  const detail = detailKey ? String(item[detailKey]) : null;
  const ref = item.ref || item.drill || (typeof item.source === "string" ? item.source : null)
    || (Array.isArray(item.sources) && item.sources.length ? (typeof item.sources[0] === "string" ? item.sources[0] : null) : null);
  const href = item.href || (item.card_id ? `#/approvals/${encodeURIComponent(item.card_id)}` : null)
    || (drill && ref ? `#/drill/${encodeURIComponent(ref)}` : null);
  const status = item.status || item.severity || (typeof item.state === "string" ? item.state : null);
  const inner = [
    h("div", { class: "row-head" }, h("p", { class: "row-title" }, title), status ? statusPill(status) : null),
    detail ? h("p", { class: "row-detail" }, detail) : null,
    facts.length ? h("dl", { class: "facts" }, facts) : null,
    item.basis && isNonActual(item.basis) ? h("p", { class: "row-meta" }, basisTag(item.basis)) : null,
  ];
  if (href) return h("li", { class: "row" }, h("a", { class: "row-link", href }, ...inner, h("span", { class: "row-chev" }, icon("chevron", 18))));
  return h("li", { class: "row" }, ...inner);
}

/**
 * Render a provider envelope {status, as_of, basis, items, sources, reason} honestly. UNKNOWN
 * and BLOCKED statuses show their reason prominently instead of an empty list that looks fine.
 */
export function envelopeCard(title, env, { stale = false, fetchedAt = null, emptyText = "Nothing reported.", limit = 20 } = {}) {
  if (!env || typeof env !== "object") {
    return card({ title, actions: statusPill("UNKNOWN") },
      h("p", { class: "muted" }, "This department did not report. Status is Unknown."));
  }
  const items = Array.isArray(env.items) ? env.items : [];
  const shown = items.slice(0, limit);
  const status = String(env.status || "UNKNOWN").toUpperCase();
  return card({ title, actions: statusPill(status) },
    h("p", { class: "card-meta" }, freshness(env.as_of, { stale, fetchedAt }), ...basisNote(env.basis, status)),
    env.reason ? h("p", { class: ["callout", status === "OK" ? "callout-info" : "callout-warn"] }, env.reason) : null,
    shown.length ? h("ul", { class: "rows" }, shown.map((it) => itemRow(it))) : h("p", { class: "muted" }, status === "UNKNOWN" ? "Unknown: no data available yet." : emptyText),
    items.length > limit ? h("p", { class: "muted" }, `${items.length - limit} more not shown here.`) : null,
    sourcesList(env.sources));
}

export function loading(label = "Loading") {
  return h("div", { class: "loading", role: "status", aria: { live: "polite" } },
    h("span", { class: "spinner", aria: { hidden: "true" } }), `${label}…`);
}

export function errorState(err, retry) {
  const offline = err && err.name === "OfflineError";
  const msg = err && err.message ? err.message : "Something went wrong.";
  return card({ title: offline ? "Offline" : "Could not load", cls: "card-error" },
    h("p", { role: "alert" }, msg),
    h("p", { class: "muted" }, "Nothing on this screen is current. No data is shown rather than old or invented data."),
    retry ? h("button", { class: "btn", type: "button", onclick: retry }, icon("refresh", 18), "Try again") : null);
}

export function staleBanner(result) {
  if (!result || !result.stale) return null;
  return h("p", { class: "banner banner-stale", role: "status" },
    `Offline, so you are seeing this tab's last copy from ${relTime(result.fetchedAt)} (${utcStamp(result.fetchedAt)}). It may be out of date and actions are disabled.`);
}

let toastTimer = null;
export function toast(message, kind = "info") {
  const host = document.getElementById("toast");
  if (!host) return;
  clear(host);
  host.className = `toast toast-${kind} is-on`;
  host.append(document.createTextNode(message));
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { host.className = "toast"; }, 5000);
}

/**
 * Accessible confirmation dialog (native <dialog>, modal, focus-trapped by the browser).
 * Resolves {confirmed, reason, passphrase, totp}. With stepUp=true the owner must re-enter the
 * owner passphrase (and TOTP when the server requires it) before Confirm enables (F-887).
 * Credentials live only in the dialog's inputs and are wiped on close.
 */
export function confirmDialog({ title, lines = [], confirmLabel = "Confirm", danger = false,
  stepUp = false, totpRequired = false, reasonLabel = null, reasonRequired = false }) {
  return new Promise((resolve) => {
    const reason = reasonLabel ? h("textarea", { id: "dlg-reason", rows: 3, maxLength: 500, required: reasonRequired }) : null;
    const pass = stepUp ? h("input", { id: "dlg-pass", type: "password", autocomplete: "current-password", required: true }) : null;
    const totp = stepUp && totpRequired ? h("input", { id: "dlg-totp", type: "text", inputMode: "numeric", autocomplete: "one-time-code", maxLength: 6, required: true }) : null;
    const ok = h("button", { class: ["btn", danger ? "btn-danger" : "btn-primary"], type: "submit", data: { dlg: "confirm" } }, confirmLabel);
    const cancel = h("button", { class: "btn", type: "button", data: { dlg: "cancel" } }, "Cancel");
    const form = h("form", { class: "dlg-form" },
      h("h2", { class: "dlg-title", id: "dlg-title" }, title),
      ...lines.map((l) => (l instanceof Node ? l : h("p", null, l))),
      reason ? h("label", { class: "field", for: "dlg-reason" }, reasonLabel + (reasonRequired ? " (required)" : " (optional)")) : null,
      reason,
      stepUp ? h("p", { class: "callout callout-warn" }, "This is a consequential action. Re-enter your owner passphrase to confirm it is you.") : null,
      pass ? h("label", { class: "field", for: "dlg-pass" }, "Owner passphrase") : null, pass,
      totp ? h("label", { class: "field", for: "dlg-totp" }, "6-digit authenticator code") : null, totp,
      h("div", { class: "dlg-actions" }, cancel, ok));
    const dlg = h("dialog", { class: "dlg", aria: { labelledby: "dlg-title" } }, form);
    const sync = () => {
      ok.disabled = (pass && !pass.value) || (totp && !/^\d{6}$/.test(totp.value.trim()))
        || (reasonRequired && !reason.value.trim());
    };
    for (const el of [pass, totp, reason]) if (el) el.addEventListener("input", sync);
    sync();
    let done = false;
    const finish = (confirmed) => {
      if (done) return;
      done = true;
      const out = { confirmed, reason: reason ? reason.value.trim() : "",
        passphrase: pass ? pass.value : null, totp: totp ? totp.value.trim() : null };
      if (pass) pass.value = "";
      if (totp) totp.value = "";
      dlg.close();
      dlg.remove();
      resolve(out);
    };
    form.addEventListener("submit", (e) => { e.preventDefault(); if (!ok.disabled) finish(true); });
    cancel.addEventListener("click", () => finish(false));
    dlg.addEventListener("cancel", (e) => { e.preventDefault(); finish(false); });
    document.body.append(dlg);
    dlg.showModal();
    (pass || reason || cancel).focus();
  });
}

/** Re-authentication prompt used when the server answers STEP_UP_REQUIRED. */
export async function stepUpDialog({ totpRequired = false } = {}) {
  const r = await confirmDialog({ title: "Confirm it is you",
    lines: ["The server needs a fresh owner re-authentication before it will run this action."],
    confirmLabel: "Re-authenticate", stepUp: true, totpRequired });
  return r.confirmed ? { passphrase: r.passphrase, totp: r.totp } : null;
}

/**
 * Run a consequential call behind confirmation (+ step-up when needed). Shows the outcome in a
 * toast. Returns the response body or null when cancelled/refused.
 */
export async function guardedAction({ title, lines, confirmLabel, danger, requiresStepUp, reasonLabel,
  reasonRequired, run, success = "Done." }) {
  const needStepUp = !!requiresStepUp && !stepUpValid();
  const r = await confirmDialog({ title, lines, confirmLabel, danger, stepUp: needStepUp,
    totpRequired: authState().totpRequired, reasonLabel, reasonRequired });
  if (!r.confirmed) { toast("Cancelled. Nothing changed."); return null; }
  try {
    if (needStepUp) await stepUp(r.passphrase, r.totp);
    const body = await run(r.reason);
    toast(success, "info");
    return body;
  } catch (err) {
    toast(`${err.message || "Refused"}${err.code ? ` (${err.code})` : ""}`, "bad");
    return null;
  }
}

export { h, icon, clear };
