// ENG-CATALOGUE: full catalogue (GET /api/cc/catalogue); read-only; null = Unknown.
import { h } from "../dom.js";
import { api } from "../api.js";
import { card, statusPill, statTile } from "../components.js";
import { UNKNOWN_TEXT } from "../format.js";
import { pageMeta } from "./_shared.js";

const txt = (v) => (v === null || v === undefined || v === "" || v === "UNKNOWN" ? UNKNOWN_TEXT : String(v));
const HELD = [["", "Any hold state"], ["any", "Held (any reason)"], ["none", "Not held"],
  ["owner", "Held: owner"], ["physical", "Held: physical sample"],
  ["paid_approval", "Held: paid approval"], ["policy", "Held: policy"]];

function fact(label, text) {
  return h("div", { class: "fact" }, h("dt", null, label), h("dd", null, text));
}

function evidenceFacts(ev) {
  const e = ev || {};
  const cert = e.certificate;
  const etsy = e.etsy;
  return h("dl", { class: "facts" },
    fact("Certificate", cert ? `release ${String(cert.release_hash).slice(0, 12)}${cert.physical_test_required ? " · sample required" : ""}` : "none"),
    fact("Premium PDF", e.pdf ? h("a", { href: e.pdf.href }, Object.entries(e.pdf.sha256_by_terminology || {})
      .map(([t, sha]) => `${t.toUpperCase()} ${String(sha).slice(0, 12)}`).join(" · ") || "built") : "none"),
    fact("Gallery", e.gallery ? h("a", { href: e.gallery.href }, `verified (audit ${txt(e.gallery.audit_id)})`) : "none"),
    fact("Listing package", e.listing_package ? `listing ${txt(e.listing_package.listing_id)}` : "none"),
    fact("Etsy", etsy ? `${txt(etsy.etsy_listing_id)} · ${txt(etsy.state)} · read-back ${txt(etsy.read_back)}${etsy.draft_intent ? ` · intent ${etsy.draft_intent}` : ""}` : "none"));
}

function productRow(r) {
  const na = r.next_action || {};
  return h("li", { class: "row", data: { stage: r.stage } },
    h("div", { class: "row-head" },
      h("p", { class: "row-title" }, `${r.slug}${r.version ? `@${r.version}` : ""}`),
      statusPill(r.stage === "UNKNOWN" ? "UNKNOWN" : r.held && r.held.length ? "DEGRADED" : "OK",
        r.stage === "UNKNOWN" ? "Unknown" : r.stage_label)),
    r.title ? h("p", { class: "muted" }, r.title) : null,
    h("dl", { class: "facts" },
      fact("Family", `${txt(r.category)}${r.family ? ` · ${r.family}` : ""}`),
      fact("Held", r.held && r.held.length ? r.held.join(", ") : "not held"),
      fact("Next action", `${txt(na.action)} · owner ${txt(na.owner)}`),
      fact("Why", txt(r.why))),
    h("details", null, h("summary", null, "Evidence"), evidenceFacts(r.evidence)));
}

function options(pairs) {
  return pairs.map(([v, label]) => h("option", { value: v }, label));
}

export async function render() {
  const state = { q: "", stage: "", category: "", held: "", page: 1, page_size: 25 };
  const first = await api.catalogue(state);
  const data = first.data || {};
  const totals = data.totals || {};
  const stages = Array.isArray(data.stages) ? data.stages : [];
  const byStage = totals.by_stage || null;
  const byCat = totals.by_category || null;

  const list = h("div", { aria: { live: "polite" } });
  const search = h("input", { type: "search", id: "cat-q", placeholder: "Search slug or title", autocomplete: "off" });
  const stageSel = h("select", { id: "cat-stage" }, options([["", "All stages"], ...stages.map((s) => [s.key, s.label]), ["UNKNOWN", "Unknown"]]));
  const catSel = h("select", { id: "cat-category" }, options([["", "All families"], ...Object.keys(byCat || {}).sort().map((k) => [k, k === "UNKNOWN" ? "Unknown" : k])]));
  const heldSel = h("select", { id: "cat-held" }, options(HELD));

  function draw(result) {
    const d = result.data || {};
    const rows = Array.isArray(d.items) ? d.items : [];
    const matching = d.matching;
    const prev = h("button", { class: "btn", type: "button", disabled: !(d.page > 1),
      onclick: () => go(d.page - 1) }, "Previous");
    const next = h("button", { class: "btn", type: "button", disabled: !(d.pages && d.page < d.pages),
      onclick: () => go(d.page + 1) }, "Next");
    // replaceChildren() would print a null child as the text "null": drop the absent ones.
    list.replaceChildren(...[
      d.status === "UNKNOWN" ? h("p", { class: "callout callout-warn" }, `Unknown: ${txt(d.reason)}`) : null,
      h("p", { class: "muted", id: "cat-count" }, matching === null || matching === undefined
        ? "Matching products: Unknown"
        : `${matching} matching · page ${txt(d.page)} of ${txt(d.pages)}`),
      rows.length ? h("ul", { class: "rows", id: "cat-rows" }, ...rows.map(productRow))
        : h("p", { class: "muted" }, "No product matches."),
      h("div", { class: "pager" }, prev, next)].filter(Boolean));
  }

  async function go(page) {
    state.page = page;
    state.q = search.value.trim();
    state.stage = stageSel.value;
    state.category = catSel.value;
    state.held = heldSel.value;
    list.replaceChildren(h("p", { class: "muted" }, "Loading…"));
    try { draw(await api.catalogue(state)); }
    catch (e) { list.replaceChildren(h("p", { class: "callout callout-warn" }, "Unknown: the catalogue could not be loaded.")); }
  }

  const form = h("form", { class: "filters", role: "search", onsubmit: (e) => { e.preventDefault(); go(1); } },
    h("label", { class: "field", for: "cat-q" }, "Search"), search,
    h("label", { class: "field", for: "cat-stage" }, "Stage"), stageSel,
    h("label", { class: "field", for: "cat-category" }, "Family"), catSel,
    h("label", { class: "field", for: "cat-held" }, "Held"), heldSel,
    h("button", { class: "btn", type: "submit" }, "Apply"));
  draw(first);

  const stageTiles = byStage
    ? [...stages.map((s) => statTile(s.label, byStage[s.key])),
       statTile("Unknown", byStage.UNKNOWN ?? 0, { status: byStage.UNKNOWN ? "UNKNOWN" : null })]
    : [statTile("Every stage", null, { status: "UNKNOWN" })];
  return h("div", { class: "stack" }, ...pageMeta(first, data),
    h("p", { class: "callout" }, "Every product the company is making, one stage each (its current version), from the "
      + "production inventory. Totals are counted over all products, not this page; superseded versions and research concepts are counted apart; Unknown is never 0."),
    card({ title: "Totals", subtitle: `Products: ${txt(totals.products)} · versions: ${txt(totals.versions)} · concepts: ${txt(totals.concepts)} · superseded: ${txt(totals.superseded)}`,
      actions: statusPill(data.status || "UNKNOWN") },
      h("div", { class: "tiles", id: "cat-stage-tiles" }, ...stageTiles),
      byCat ? h("dl", { class: "facts" }, ...Object.entries(byCat).sort().map(([k, v]) => fact(k === "UNKNOWN" ? "Unknown family" : k, txt(v))))
        : h("p", { class: "callout callout-warn" }, "Families: Unknown")),
    card({ title: "Products", subtitle: "Filter, search, page" }, form, list));
}
