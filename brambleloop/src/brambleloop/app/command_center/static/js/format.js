// Formatting rules that carry truth, not just style.
//
// Money: a value the backend could not measure is UNKNOWN and renders as the word "Unknown".
// It is never coerced to 0 and never printed as CA$0.00 -- CA$0.00 means a *measured* zero
// (F-902, §95 "Disconnect an accounting source"). Estimated and modelled amounts carry a visible
// basis label so a forecast cannot masquerade as booked money (F-905, F-913).

export const UNKNOWN_TEXT = "Unknown";

const BASIS_LABEL = {
  measured: "Actual", actual: "Actual", booked: "Actual", reconciled: "Reconciled",
  estimated: "Estimated", estimate: "Estimated", modelled: "Modelled", modeled: "Modelled",
  forecast: "Forecast", projected: "Forecast", recorded: "Recorded", unknown: "Unknown",
};

export function basisLabel(basis) {
  if (!basis) return "Unknown basis";
  return BASIS_LABEL[String(basis).toLowerCase()] || String(basis);
}

/** True when a basis is anything other than a measured/actual value. */
export function isNonActual(basis) {
  const b = String(basis || "").toLowerCase();
  return !(b === "measured" || b === "actual" || b === "booked" || b === "reconciled");
}

/**
 * Normalise every money shape the API may send into
 * {known: bool, amount: number|null, currency, basis, reason}.
 * Accepted: null, a number (treated as measured), {amount}, {amount_minor}, {cents},
 * {value}. status "UNKNOWN" or basis "unknown" always wins over any amount present.
 */
export function moneyValue(v, fallbackCurrency = "CAD") {
  if (v === null || v === undefined) return { known: false, amount: null, currency: fallbackCurrency, basis: "unknown", reason: "" };
  if (typeof v === "number") return Number.isFinite(v) ? { known: true, amount: v, currency: fallbackCurrency, basis: "measured", reason: "" } : moneyValue(null);
  if (typeof v !== "object") return moneyValue(null, fallbackCurrency);
  if ("value_cad" in v || "state" in v) {
    // Lane C contract (§0): {value_cad, state, basis, display, sources}. value_cad null, or a
    // state other than MEASURED/ESTIMATED/MODELLED, is UNKNOWN -- never coerced to 0.
    const state = String(v.state || "UNKNOWN").toUpperCase();
    const amount = typeof v.value_cad === "number" && Number.isFinite(v.value_cad) ? v.value_cad : null;
    // RECORDED = rows this system wrote: a real amount, but not reconciled, so labelled "Recorded".
    const known = amount !== null && (state === "MEASURED" || state === "ESTIMATED" || state === "MODELLED" || state === "RECORDED");
    return { known, amount: known ? amount : null, currency: "CAD",
      basis: known ? (state === "MEASURED" ? "measured" : state.toLowerCase()) : "unknown",
      reason: v.why || v.reason || (state === "UNMEASURED" ? "Not measured: source not connected" : "") };
  }
  const currency = v.currency || fallbackCurrency;
  const basis = v.basis || (v.estimated ? "estimated" : null);
  const status = String(v.status || "").toUpperCase();
  let amount = null;
  if (typeof v.amount_minor === "number") amount = v.amount_minor / 100;
  else if (typeof v.cents === "number") amount = v.cents / 100;
  else if (typeof v.amount === "number") amount = v.amount;
  else if (typeof v.amount === "string" && v.amount.trim() !== "" && Number.isFinite(Number(v.amount))) amount = Number(v.amount);
  else if (typeof v.value === "number") amount = v.value;
  const unknown = status === "UNKNOWN" || String(basis || "").toLowerCase() === "unknown"
    || amount === null || !Number.isFinite(amount);
  return {
    known: !unknown,
    amount: unknown ? null : amount,
    currency,
    basis: unknown ? "unknown" : (basis || "measured"),
    reason: v.reason || v.unknown_reason || "",
  };
}

export function formatMoney(v, fallbackCurrency = "CAD") {
  const m = moneyValue(v, fallbackCurrency);
  if (!m.known) return UNKNOWN_TEXT;
  const prefix = { CAD: "CA$", USD: "US$", EUR: "€", GBP: "£" }[m.currency] || `${m.currency} `;
  const abs = new Intl.NumberFormat("en-CA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    .format(Math.abs(m.amount));
  return `${m.amount < 0 ? "−" : ""}${prefix}${abs}`;
}

/** A count/percentage that may be unknown. Never turns null into 0. */
export function formatNumber(v, opts = {}) {
  if (v === null || v === undefined || (typeof v === "number" && !Number.isFinite(v))) return UNKNOWN_TEXT;
  if (typeof v === "object") {
    if (String(v.status || "").toUpperCase() === "UNKNOWN") return UNKNOWN_TEXT;
    return formatNumber(v.value ?? v.amount ?? null, opts);
  }
  if (typeof v !== "number") return String(v);
  if (opts.percent) return `${(v * (opts.ratio === false ? 1 : 100)).toFixed(opts.digits ?? 0)}%`;
  return new Intl.NumberFormat("en-CA", { maximumFractionDigits: opts.digits ?? 2 }).format(v);
}

export function parseTime(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** "3 min ago" plus the exact UTC timestamp for a title/datetime attribute. */
export function relTime(iso, now = Date.now()) {
  const d = parseTime(iso);
  if (!d) return "time unknown";
  const s = Math.round((now - d.getTime()) / 1000);
  const fut = s < 0;
  const a = Math.abs(s);
  let txt;
  if (a < 45) txt = "just now";
  else if (a < 3600) txt = `${Math.round(a / 60)} min`;
  else if (a < 86400) txt = `${Math.round(a / 3600)} h`;
  else txt = `${Math.round(a / 86400)} d`;
  if (txt === "just now") return txt;
  return fut ? `in ${txt}` : `${txt} ago`;
}

export function utcStamp(iso) {
  const d = parseTime(iso);
  if (!d) return "unknown";
  return d.toISOString().replace("T", " ").replace(/\.\d+Z$/, " UTC");
}

export const STATUS_CLASS = { OK: "ok", DEGRADED: "warn", BLOCKED: "bad", UNKNOWN: "unknown",
  CRITICAL: "bad", HIGH: "bad", MEDIUM: "warn", LOW: "info", INFO: "info", WARNING: "warn",
  PENDING: "warn", APPROVED: "ok", REJECTED: "bad", STALE: "warn", PAUSED: "warn",
  ACTIVE: "ok", RUNNING: "ok", FAILED: "bad", READY: "ok", GATED: "warn" };

export function statusClass(s) {
  return STATUS_CLASS[String(s || "UNKNOWN").toUpperCase()] || "unknown";
}

export function humanize(key) {
  return String(key).replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
