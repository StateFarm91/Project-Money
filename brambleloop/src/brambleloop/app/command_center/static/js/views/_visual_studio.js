// WIRE1 (F-748, F-680): Visual Studio. Read-only owner panel over GET /api/cc/visual/studio and
// GET /api/cc/visual/evidence/{slug}. It shows the canonical model version, the best demonstrated
// provider, recent identity/realism yield, rejected drift examples, active improvement work and
// whether each listing image passed BOTH Model Identity and Product Truth. Nothing here writes.
import { h } from "../dom.js";
import { api } from "../api.js";
import { card, statusPill } from "../components.js";

function rate(y) {
  if (!y || y.state === "ABSENT") return "Unknown";
  return `${Math.round((y.rate || 0) * 100)}% of ${y.judged}`;
}

function absent(part) {
  return part && !Array.isArray(part) && part.state === "ABSENT";
}

function evidenceBlock(p) {
  const line = (label, part, show) => h("li", { class: "row" },
    h("p", { class: "row-title" }, statusPill(absent(part) ? "UNKNOWN" : "OK"), ` ${label}`),
    h("p", { class: "row-detail" }, absent(part) ? String(part.why || "absent") : show(part)));
  const rejected = p.rejected_candidates || [];
  return h("ul", { class: "rows" },
    line("Real benchmark reference", p.real_benchmark_reference, (x) => `${x.length} reference photo(s)`),
    line("Brambleloop 3D", p.brambleloop_3d, (x) => `version ${x.version || "?"} · ${(x.gallery_frames || []).length} gallery frame(s)`),
    line("Conditioning passes", p.conditioning_passes, (x) => Object.keys(x.references_by_kind || {}).join(", ") || "receipts only"),
    line("Generated candidates", p.generated_candidates, (x) => `${x.length} candidate(s)`),
    h("li", { class: "row" }, h("p", { class: "row-title" }, `Rejected: ${rejected.length}`),
      h("p", { class: "row-detail" }, rejected.slice(0, 5).map((r) =>
        `${r.role}: ${Object.entries(r.reasons || {}).map(([k, v]) => `${k} (${v})`).join("; ") || (r.failure_categories || []).join(", ")}`).join(" · ") || "None.")),
    line("Final approved asset", p.final_approved_asset, (x) => x.map((a) => `${a.role} ${String(a.sha256).slice(0, 12)}`).join(", ")));
}

export async function visualStudioCard(slugs) {
  let v;
  try { v = await api.visualStudio(); } catch (e) {
    return card({ title: "Visual Studio", actions: statusPill("UNKNOWN") }, h("p", { class: "muted" }, "Could not load the Visual Studio view."));
  }
  const c = v.canonical || {};
  const best = v.best_provider_mode || {};
  const y = v.recent_yield || {};
  const drift = Array.isArray(v.rejected_drift_examples) ? v.rejected_drift_examples : [];
  const exps = (v.active_improvement_experiments || {}).proposals || [];
  const imgs = v.listing_images || [];
  const out = h("div", { aria: { live: "polite" } });
  const pick = h("select", { id: "vs-slug", onchange: async () => {
    out.replaceChildren(h("p", { class: "muted" }, "Loading…"));
    try { out.replaceChildren(evidenceBlock(await api.visualEvidence(pick.value))); }
    catch (e) { out.replaceChildren(h("p", { class: "muted" }, "Could not load the evidence panel.")); }
  } }, h("option", { value: "" }, "Choose a product…"), (slugs || []).map((s) => h("option", { value: s }, s)));
  return card({ title: "Visual Studio", subtitle: "Canonical model, provider evidence and per-image gates. Read-only.",
    actions: statusPill(c.verified ? "OK" : "BAD", c.verified ? "Registry verified" : "Registry not verified") },
    h("p", null, `Canonical model: ${c.identity_id || "Unknown"} (revision ${c.revision ?? "?"})`),
    h("p", null, `Best provider/mode: ${best.provider || "none demonstrated"} (${best.basis || "?"})`),
    h("p", null, `Recent yield: identity ${rate(y.identity)} · realism ${rate(y.realism)}`),
    h("p", null, `Rejected drift examples: ${drift.length} · active improvement proposals: ${exps.length}`),
    h("p", null, `Listing images passing both Model Identity and Product Truth: ${v.listing_images_passing_both ?? 0} of ${imgs.length}`),
    h("div", null, h("label", { class: "field", for: "vs-slug" }, "Visual evidence for"), pick),
    out);
}
