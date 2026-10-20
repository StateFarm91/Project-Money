// COMPLETION EFFORT (W4-CC): the parallel completion lanes, read from the committed
// research/final_build/w4/COMPLETION_BOARD.json. A null is Unknown, never 0.
import { h } from "../dom.js";
import { api } from "../api.js";
import { card, statusPill, freshness, sourcesList, statTile, itemRow, basisNote, releaseNote, envelopeCard } from "../components.js";
import { relTime, utcStamp, UNKNOWN_TEXT, formatMoney } from "../format.js";
import { sectionsOf, pageMeta } from "./_shared.js";

const ORDER = ["BLOCKED", "RUNNING", "REVIEW", "QUEUED", "UNKNOWN", "MERGED", "DONE", "ABANDONED"];
const when = (iso) => (iso ? `${relTime(iso)} (${utcStamp(iso)})` : UNKNOWN_TEXT);
const txt = (v) => (v === null || v === undefined || v === "" ? UNKNOWN_TEXT : String(v));

function fact(label, text) {
  return h("div", { class: "fact" }, h("dt", null, label), h("dd", null, text));
}

// W4-CCGAP: the operating company's own work, live from the jobs table (not the dev board).
function liveWorkCard(env, result) {
  if (env === undefined) return null;
  const title = "Company work now (live, from jobs)";
  if (!env || typeof env !== "object") return envelopeCard(title, null);
  const n = (v) => (typeof v === "number" ? v : null);
  const c = envelopeCard(title, env, { stale: result.stale, fetchedAt: result.fetchedAt, emptyText: "No job is running right now." });
  if (env.status === "OK") {
    c.append(h("div", { class: "tiles" },
      statTile("Running", n(env.running)), statTile("Queued", n(env.pending)),
      statTile("Completed (24 h)", n(env.completed_24h)), statTile("Failed (24 h)", n(env.failed_24h), { status: n(env.failed_24h) ? "DEGRADED" : null })));
  }
  return c;
}

function laneRow(it) {
  const rc = it.rows_closed;
  const ids = rc && Array.isArray(rc.ids) ? rc.ids : [];
  return h("li", { class: "row" },
    h("div", { class: "row-head" }, h("p", { class: "row-title" }, `${it.lane}: ${txt(it.task)}`),
      statusPill(it.stale ? "STALE" : it.status, it.stale ? `${it.status} · STALE` : it.status)),
    it.blocker ? h("p", { class: "callout callout-warn" }, `Blocker: ${it.blocker}`) : null,
    h("dl", { class: "facts" },
      fact("Worker", txt(it.worker)),
      fact("Started", when(it.started_at)),
      fact("Last update", when(it.last_update_at)),
      fact("Useful output", txt(it.useful_output)),
      fact("Next action", txt(it.next_action)),
      fact("Rows closed", typeof it.rows_closed_count === "number" ? `${it.rows_closed_count}${ids.length ? ` (${ids.slice(0, 12).join(", ")}${ids.length > 12 ? ", …" : ""})` : ""}` : UNKNOWN_TEXT),
      it.branch ? fact("Branch", `${it.branch}${it.head_sha ? ` @ ${String(it.head_sha).slice(0, 7)}` : ""}`) : null));
}

// W4-CCPACKET (F-878): the Launch-0 launch packet, generated from state. Read-only; the
// verdict is the packet's own (READY / BLOCKED / UNKNOWN), UNKNOWN never shown as passing.
export function packetCard(settled) {
  const title = "Launch-0 launch packet";
  if (!settled || settled.status === "rejected") {
    const msg = settled && settled.reason && settled.reason.message ? settled.reason.message : "not loaded";
    return card({ title, labelId: "completion-launch-packet", actions: statusPill("UNKNOWN") },
      h("p", { class: "callout callout-warn" }, `Unknown: the launch packet could not be loaded (${msg}).`));
  }
  const r = settled.value;
  const env = sectionsOf(r.data || {}).packet || {};
  const status = String(env.status || "UNKNOWN").toUpperCase();
  const items = Array.isArray(env.items) ? env.items : [];
  const q = env.owner_queue || {};
  const actions = Array.isArray(q.owner_actions) ? q.owner_actions : [];
  const ph = env.phase || {};
  const suite = env.recorded_suite || {};
  const steps = Array.isArray(env.activation_steps) ? env.activation_steps : [];
  const cache = env.cache || {};
  return card({ title, labelId: "completion-launch-packet", subtitle: "What has to be true before launch, read from state", actions: statusPill(status, env.verdict ? String(env.verdict) : status) },
    h("p", { class: "card-meta" }, freshness(env.as_of, { stale: r.stale, fetchedAt: r.fetchedAt }), ...basisNote(env.basis, status),
      cache.ttl_seconds ? ` · regenerated at most every ${Math.round(cache.ttl_seconds / 60)} min` : ""),
    env.reason ? h("p", { class: ["callout", status === "OK" ? "callout-info" : "callout-warn"] }, env.reason) : null,
    h("dl", { class: "facts" },
      fact("Candidate commit", txt(env.candidate_sha && env.candidate_sha !== "unknown" ? String(env.candidate_sha).slice(0, 12) : null)),
      fact("Phase (effective)", txt(ph.phase)),
      fact("Phase recorded / environment", `${txt(ph.recorded_phase)} / ${txt(ph.env)}${ph.agree === false ? " (DISAGREE)" : ""}`),
      fact("Launch readiness", q.state ? String(q.state) : UNKNOWN_TEXT),
      fact("Recorded suite", suite.suite ? `${txt(suite.suite.passed)} passed, ${txt(suite.suite.failed)} failed (${txt(suite.suite.commit || suite.suite.sha)})` : txt(suite.why)),
      fact("Verdict rule", txt(env.verdict_rule))),
    h("h3", { class: "section-title" }, "Products"),
    items.length ? h("ul", { class: "rows" }, items.map((it) => itemRow(it, { drill: false })))
      : h("p", { class: "muted" }, "Unknown: the packet listed no product."),
    h("h3", { class: "section-title" }, "Open owner actions"),
    actions.length ? h("ul", { class: "rows" }, actions.map((a) => h("li", { class: "row" },
      h("div", { class: "row-head" }, h("p", { class: "row-title" }, txt(a.action || a.key)), statusPill("PENDING", "OWNER")),
      a.why ? h("p", { class: "row-detail" }, a.why) : null,
      h("dl", { class: "facts" },
        fact("Maximum cost", typeof a.max_cost_cad === "number" ? formatMoney({ value_cad: a.max_cost_cad, state: "ESTIMATED" }) : UNKNOWN_TEXT),
        fact("Minutes", txt(a.minutes)),
        fact("If it waits", txt(a.consequence_of_delay))))))
      : h("p", { class: "muted" }, q.state === "UNKNOWN" || !q.state ? "Unknown: the owner queue was not read." : "No open owner action."),
    steps.length ? h("details", { class: "sources" }, h("summary", null, `Activation steps (${steps.length})`),
      h("ol", null, steps.map((s) => h("li", null, s)))) : null,
    sourcesList(env.sources));
}

// W4-BOARD: the one finish-line board (Build 2 + Final Master), generated from the ledgers and
// production GETs; compact on a phone: the counts, then the root causes behind a <details>.
const CLASS_LABELS = [["verified_complete", "Verified complete"], ["implemented_unverified", "Built, unverified"],
  ["in_progress", "In progress"], ["blocked_engineering", "Blocked: engineering"],
  ["blocked_owner", "Blocked: owner"], ["blocked_external", "Blocked: external"]];
export function finishLineCard(env, result) {
  const title = "Finish line: Build 2 + Final Master";
  if (!env || typeof env !== "object") return envelopeCard(title, null);
  const scopes = env.scopes || {};
  const n = (v) => (typeof v === "number" ? v : null);
  const scopeBlock = (label, sc) => {
    if (!sc) return h("p", { class: "muted" }, `${label}: ${UNKNOWN_TEXT}`);
    return h("div", null, h("h3", { class: "section-title" }, `${label} (${sc.total})`),
      h("div", { class: "tiles" }, ...CLASS_LABELS.map(([k, lab]) =>
        statTile(lab, n(sc[k]), { status: k.startsWith("blocked") && n(sc[k]) ? "BLOCKED" : null }))));
  };
  const roots = Array.isArray(env.items) ? env.items : [];
  const path = Array.isArray(env.critical_path) ? env.critical_path : [];
  return card({ title, labelId: "completion-finish-line", subtitle: "Every requirement in exactly one class; generated, never typed", actions: statusPill(env.status) },
    h("p", { class: "card-meta" }, freshness(env.as_of, result),
      env.production_commit ? ` · production ${String(env.production_commit).slice(0, 7)}` : ""),
    env.reason ? h("p", { class: "callout callout-warn" }, env.reason) : null,
    scopeBlock("Final Master launch-critical", scopes.final_master_launch_critical),
    scopeBlock("Build 2", scopes.build2),
    scopeBlock("Final Master total", scopes.final_master_total),
    h("details", { class: "sources" }, h("summary", null, `Top root causes (${roots.length})`),
      h("ul", { class: "rows" }, roots.map((r) => h("li", { class: "root-cause" },
        h("div", { class: "row-head" }, h("p", { class: "row-title" }, txt(r.title)), statusPill("BLOCKED", `${txt(r.rows)} rows`)),
        h("p", { class: "row-detail" }, `Final Master launch-critical ${txt(r.fm_launch_critical)} · Build 2 ${txt(r.build2)}`),
        r.owner_action ? h("p", { class: "row-detail" }, `Owner action: ${r.owner_action}`) : null)))),
    path.length ? h("details", { class: "sources" }, h("summary", null, `Critical path (${path.length} steps)`),
      h("ol", null, path.map((s) => h("li", null, `${txt(s.title)} (${txt(s.who)}): unblocks ${txt(s.unblocks_rows)} rows${s.estimate && s.estimate.figure ? ` · estimate: ${s.estimate.figure}` : ""}`)))) : null,
    sourcesList(env.sources));
}

// W4-FIRSTSALE: every gate between a Launch-0 product and its first paid download, per product
// and shop-wide, with evidence and who acts. Read-only; UNKNOWN is never shown as passing.
export function firstSaleCard(settled) {
  const title = "First-sale readiness";
  if (!settled || settled.status === "rejected") {
    const msg = settled && settled.reason && settled.reason.message ? settled.reason.message : "not loaded";
    return card({ title, labelId: "completion-first-sale", actions: statusPill("UNKNOWN") },
      h("p", { class: "callout callout-warn" }, `Unknown: the first-sale view could not be loaded (${msg}).`));
  }
  const r = settled.value;
  const env = sectionsOf(r.data || {}).first_sale || {};
  const status = String(env.status || "UNKNOWN").toUpperCase();
  const items = Array.isArray(env.items) ? env.items : [];
  const shop = Array.isArray(env.shop) ? env.shop : [];
  const owner = Array.isArray(env.owner_actions) ? env.owner_actions : [];
  const gateLi = (g) => h("li", { class: "row" },
    h("div", { class: "row-head" }, h("p", { class: "row-title" }, `${txt(g.gate)}${g.blocker ? ` (${g.blocker})` : ""}`),
      statusPill(g.status || "UNKNOWN", txt(g.state))),
    h("p", { class: "row-detail" }, txt(g.why)),
    h("dl", { class: "facts" }, fact("Evidence", txt(g.evidence)),
      fact("Who acts", g.state === "PASS" ? "nobody" : txt(g.who_acts)),
      g.action ? fact("Next", g.action) : null));
  return card({ title, labelId: "completion-first-sale", subtitle: "Every gate to a first paid download, read from state", actions: statusPill(status) },
    h("p", { class: "card-meta" }, freshness(env.as_of, { stale: r.stale, fetchedAt: r.fetchedAt }), ...basisNote(env.basis, status)),
    env.reason ? h("p", { class: ["callout", status === "OK" ? "callout-info" : "callout-warn"] }, env.reason) : null,
    h("h3", { class: "section-title" }, "Shop-wide"),
    shop.length ? h("ul", { class: "rows" }, shop.map(gateLi)) : h("p", { class: "muted" }, "Unknown: no shop-wide gate was read."),
    h("h3", { class: "section-title" }, "Per product"),
    items.length ? h("ul", { class: "rows" }, items.map((it) => h("li", { class: "row" },
      h("details", null, h("summary", null, `${txt(it.title)} `, statusPill(it.status || "UNKNOWN"),
        ` who acts: ${(it.who_acts || []).join(", ") || "nobody"}`),
        h("ul", { class: "rows" }, (it.gates || []).map(gateLi))))))
      : h("p", { class: "muted" }, "Unknown: no product was listed."),
    h("h3", { class: "section-title" }, "Owner actions"),
    owner.length ? h("ul", null, owner.map((a) => h("li", null, a))) : h("p", { class: "muted" }, "None read."),
    sourcesList(env.sources));
}

export async function render() {
  const [res, pk, fs] = await Promise.allSettled([api.completion(), api.launchPacket(), api.firstSale()]);
  if (res.status === "rejected") throw res.reason;
  const result = res.value;
  const data = result.data || {};
  const env = sectionsOf(data).board || {};
  const items = Array.isArray(env.items) ? [...env.items] : [];
  items.sort((a, b) => ORDER.indexOf(a.status) - ORDER.indexOf(b.status));
  const c = env.counts || {};
  const n = (v) => (typeof v === "number" ? v : null);
  return h("div", { class: "stack" }, ...pageMeta(result, data),
    card({ title: "Completion effort", subtitle: "Parallel Claude development lanes finishing the build (not company agents; agents are on Company and Autonomy & Learn)", actions: statusPill(env.status) },
      h("p", { class: "card-meta" }, freshness(env.as_of, result), env.updated_by ? ` · updated by ${env.updated_by}` : ""),
      releaseNote(env),
      env.reason ? h("p", { class: "callout callout-warn" }, env.reason) : null,
      h("div", { class: "tiles" },
        statTile("Running", n(c.RUNNING)), statTile("Blocked", n(c.BLOCKED), { status: n(c.BLOCKED) ? "BLOCKED" : null }),
        statTile("In review", n(c.REVIEW)), statTile("Merged / done", n(c.MERGED) === null || n(c.DONE) === null ? null : c.MERGED + c.DONE),
        statTile("Unknown", n(c.UNKNOWN)),
        statTile("Rows closed (known lanes)", n(env.rows_closed_total))),
      typeof env.rows_closed_lanes_unknown === "number" && env.rows_closed_lanes_unknown
        ? h("p", { class: "muted small" }, `${env.rows_closed_lanes_unknown} lane(s) have not reported rows closed; they are not counted as 0.`) : null,
      Array.isArray(env.stale) && env.stale.length ? h("p", { class: "callout callout-warn" }, `Stale (running, no update for 3 h): ${env.stale.join(", ")}`) : null,
      Array.isArray(env.schema_errors) && env.schema_errors.length ? h("p", { class: "callout callout-warn" }, `Board problems: ${env.schema_errors.slice(0, 5).join("; ")}`) : null,
      env.note ? h("p", { class: "muted small" }, env.note) : null),
    finishLineCard(sectionsOf(data).finish_line, result),
    liveWorkCard(sectionsOf(data).live_work, result),
    packetCard(pk),
    firstSaleCard(fs),
    card({ title: "Claude development lanes" }, h("p", { class: "card-meta" }, freshness(env.as_of || null, result)),
      items.length ? h("ul", { class: "rows" }, items.map(laneRow)) : h("p", { class: "muted" }, "Unknown: the board did not report any lane."),
      sourcesList(env.sources)));
}
