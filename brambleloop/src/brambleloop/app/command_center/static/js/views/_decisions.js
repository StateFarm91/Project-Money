// W4-CCUX: "Decide first" -- the owner's open decisions ranked so the top ones lead, each with
// what it may cost and what happens if nothing is done. Read-only: it links to the full card
// (evidence, confirmation, step-up) and never acts by itself.
//
// Ranking is deterministic and explained on the card:
//   1. executable cards that carry evidence, soonest deadline first (no deadline last);
//   2. executable cards without evidence (they cannot be approved until evidence exists);
//   3. owner decisions from the batch queue, in the queue's own batch order;
//   4. cards that cannot be executed from here.
// A cost the source does not state is "Unknown", never CA$0.00.
import { h } from "../dom.js";
import { card, statusPill } from "../components.js";
import { formatMoney, relTime, utcStamp, UNKNOWN_TEXT } from "../format.js";

export const RANK_NOTE = "Ranked: decidable with evidence (soonest deadline first), then cards still missing evidence, then the batch queue in its own order, then items that cannot be executed here.";

function cardCost(v) {
  if (v === null || v === undefined || v === "") return UNKNOWN_TEXT;
  if (typeof v === "number") return formatMoney({ value_cad: v, state: "MEASURED" });
  return String(v);
}

function deadlineMs(iso) {
  const t = iso ? Date.parse(iso) : NaN;
  return Number.isFinite(t) ? t : Number.POSITIVE_INFINITY;
}

/** Normalise approval cards and batch decisions into one ranked list. */
export function rankDecisions(cards, batchesEnv) {
  const out = [];
  (Array.isArray(cards) ? cards : []).forEach((c, i) => {
    if (!c || typeof c !== "object") return;
    const evidence = Array.isArray(c.evidence) ? c.evidence.length : 0;
    const executable = c.executable !== false;
    out.push({
      kind: "card", id: c.card_id || null, order: i,
      tier: !executable ? 3 : evidence ? 0 : 1,
      title: c.title || c.card_id || "Untitled proposal",
      cost: cardCost(c.max_spend_cad),
      consequence: c.consequence_of_no_action || null,
      deadline: c.deadline || null,
      status: executable ? (evidence ? "AWAITING YOU" : "NEEDS EVIDENCE") : "NOT EXECUTABLE",
      pill: executable ? (evidence ? "PENDING" : "DEGRADED") : "BLOCKED",
    });
  });
  const batches = batchesEnv && Array.isArray(batchesEnv.items) ? batchesEnv.items : [];
  let n = 0;
  batches.forEach((b, bi) => (Array.isArray(b && b.items) ? b.items : []).forEach((d) => {
    if (!d || typeof d !== "object") return;
    out.push({
      kind: "batch", id: d.id || null, order: 1000 + n++, tier: 2,
      title: d.decision || d.id || "Decision",
      cost: d.max_cost ? String(d.max_cost) : UNKNOWN_TEXT,
      consequence: d.consequence_of_no || null,
      deadline: null, minutes: typeof d.minutes === "number" ? d.minutes : null,
      batch: `${bi + 1}. ${(b && (b.title || b.id)) || "Batch"}`,
      status: "OWNER ACTION", pill: "PENDING",
    });
  }));
  return out.sort((a, b) => a.tier - b.tier || deadlineMs(a.deadline) - deadlineMs(b.deadline) || a.order - b.order);
}

function decisionRow(d, { onBatch }) {
  const facts = [
    ["Max cost", d.cost],
    ["If you do nothing", d.consequence || "Not provided"],
    ["Deadline", d.deadline ? `${relTime(d.deadline)} (${utcStamp(d.deadline)})` : "No deadline"],
  ];
  if (d.kind === "batch") facts.push(["Minutes", d.minutes === null ? UNKNOWN_TEXT : String(d.minutes)], ["Batch", d.batch]);
  // The title is the tap target (>= 44 px): a card opens with its evidence, a batch decision
  // scrolls to the batch queue (Approvals) or opens Approvals (Home).
  const label = [h("span", { class: "decide-title" }, d.title), statusPill(d.pill, d.status)];
  const go = d.kind === "card" && d.id
    ? h("a", { class: "decide-go", href: `#/approvals/${encodeURIComponent(d.id)}`, aria: { label: `Review and decide: ${d.title}` } }, ...label)
    : d.kind === "batch" && onBatch
      ? h("button", { class: "decide-go", type: "button", onclick: onBatch, aria: { label: `Show in batches: ${d.title}` } }, ...label)
      : h("a", { class: "decide-go", href: "#/approvals" }, ...label);
  return h("li", { class: "row decide-row", data: { decision: d.kind, tier: String(d.tier) } },
    go,
    h("dl", { class: "decide-kv" }, facts.map(([k, v]) => h("div", { class: v === "Not provided" ? "missing" : null },
      h("dt", null, k), h("dd", null, v)))));
}

/**
 * The "Decide first" card. `limit` rows are shown; the remainder is counted, never hidden
 * silently. `onBatch` (optional) scrolls to the batch card on the Approvals page.
 */
export function decideFirstCard(ranked, { limit = 3, meta = null, onBatch = null, moreHref = null } = {}) {
  const list = Array.isArray(ranked) ? ranked : [];
  if (!list.length) {
    return card({ title: "Decide first", labelId: "decide-first", cls: "decide-first", actions: statusPill("OK", "NOTHING WAITING") },
      meta, h("p", { class: "muted" }, "No decision is waiting on you."));
  }
  const top = list.slice(0, limit);
  const rest = list.length - top.length;
  return card({ title: "Decide first", labelId: "decide-first", cls: "decide-first",
    subtitle: `${list.length} open · top ${top.length} by urgency, with cost and consequence`,
    actions: statusPill("PENDING", `${list.length} OPEN`) },
  meta,
  h("ol", { class: "rows decide-list" }, top.map((d) => decisionRow(d, { onBatch }))),
  rest > 0 ? h("p", { class: "muted small decide-rest" }, moreHref
    ? [`${rest} more open. `, h("a", { href: moreHref }, "See every decision")]
    : `${rest} more below, in the same order.`) : null,
  h("p", { class: "muted small decide-note" }, RANK_NOTE));
}
