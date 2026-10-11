// STORE (F-926; reorganised W4-STOREFRONT for the phone). Routes:
//   #/store                    overview: launch readiness, owner decisions, visual catalogue,
//                              storefront review, live-shop observation, technical evidence
//   #/store/collection         the 8-product launch collection (Launch-0 + proposal)
//   #/store/product/<slug>     one product: image, PDF previews, quality, listing, readiness
//   #/store/listings           listing titles and prices with their basis (read-only)
//   #/store/storefront         customer preview and what Etsy lets the shop control
// Read-only everywhere except the existing live-shop observation (CSRF + nonce via api.js).
// Images and PDFs are owner-session URLs; an unverified image is never requested or shown.
// The preview opens as its own page: the edge sends frame-ancestors 'none', so no iframe.
import { h, icon, safeUrl } from "../dom.js";
import { api } from "../api.js";
import { card, guardedAction, statusPill, freshness } from "../components.js";
import { formatMoney, UNKNOWN_TEXT } from "../format.js";
import { sectionsOf, pageMeta, renderAll, backLink } from "./_shared.js";

const ORDER = [["store_foundation", "Store foundation"],
  ["live_drift", "Live shop vs repo drafts (drift)"], ["store_readiness", "Store readiness"],
  ["competitor_intel", "Competitor findings (provenance & confidence)"], ["products", "Products, releases & listings"],
  ["publication_candidates", "Ready for publication review"], ["launch_verdict", "Launch verdict"],
  ["visibility", "Launch visibility: storefront, search, funnel, traffic"], ["seo", "Search & SEO"],
  ["seo_w3", "Search: Etsy constraints & strategy"], ["search_evidence", "Search evidence per listing"],
  ["launch_packet", "Launch packet"]];

const SUBNAV = [["", "Overview"], ["collection", "Collection"], ["listings", "Listings & prices"], ["storefront", "Storefront"]];

function findPreview(data, s) {
  const cands = [data.preview_url, data.preview_path];
  const sf = s.store_foundation;
  if (sf) {
    cands.push(sf.preview_url, sf.preview_path);
    for (const it of Array.isArray(sf.items) ? sf.items : []) if (it && typeof it === "object") cands.push(it.preview_url, it.preview_path);
  }
  for (const c of cands) {
    const u = safeUrl(c);
    if (u && u.startsWith("/")) return u; // same-origin only
  }
  return null;
}

const ETSY_LABEL = { CONNECTED: "Connected", NOT_CONNECTED: "Not connected", UNKNOWN: UNKNOWN_TEXT };
const price = (v) => (typeof v === "number" ? formatMoney({ value_cad: v, state: "MEASURED" }) : UNKNOWN_TEXT);
const pill = (st, label) => statusPill(st === "OWNER_GATED" ? "PENDING" : st, label || st);

function subnav(current) {
  return h("nav", { class: "seg store-nav", aria: { label: "Store sections" } },
    SUBNAV.map(([id, label]) => h("a", { class: "btn", href: id ? `#/store/${id}` : "#/store",
      aria: { current: id === current ? "true" : null } }, label)));
}

/** Product image: the verified rendering through the owner-session URL, else a placeholder. */
function productImage(p, cls = "pimg") {
  const img = p.image || {};
  if (img.status === "VERIFIED" && img.path) {
    return h("div", { class: cls }, h("img", { src: img.path, alt: img.alt_text || `${p.name}: digital rendering`, loading: "lazy", width: 400, height: 400 }),
      h("span", { class: "pimg-tag" }, "Rendering"));
  }
  const why = img.status === "NOT_CHECKED" ? "Image not checked" : img.status === "WITHHELD" ? "Image withheld (did not verify)" : `Image ${img.status || UNKNOWN_TEXT}`;
  return h("div", { class: [cls, "pimg-none"], data: { image: img.status || "UNKNOWN" } }, h("span", null, why));
}

function productTile(p) {
  return h("a", { class: "ptile", href: `#/store/product/${encodeURIComponent(p.slug)}`, data: { product: p.slug } },
    productImage(p),
    h("span", { class: "ptile-name" }, p.name),
    h("span", { class: "ptile-price" }, price(p.price_cad)),
    h("span", { class: "ptile-meta" }, p.launch_status === "PROPOSED" ? statusPill("DEGRADED", "PROPOSED") : statusPill("OK", "LAUNCH-0"),
      " ", pill((p.readiness || {}).status || "UNKNOWN", (p.readiness || {}).status === "OWNER_GATED" ? "OWNER-GATED" : null)));
}

function catalogueGrid(products) {
  return h("div", { class: "pgrid" }, products.map(productTile));
}

function readinessCard(cat, data, s) {
  const c = cat.counts || {};
  const verdict = s.launch_verdict;
  const etsy = cat.etsy || {};
  const n = (v) => (typeof v === "number" ? String(v) : UNKNOWN_TEXT);
  return card({ title: "Launch readiness", labelId: "store-readiness", actions: statusPill(verdict && verdict.status ? verdict.status : "UNKNOWN") },
    h("p", { class: "card-meta" }, freshness(cat.generated_at || null)),
    h("div", { class: "tiles" },
      h("div", { class: "tile" }, h("p", { class: "tile-label" }, "Launch collection"), h("p", { class: "tile-value" }, n(c.collection)),
        h("p", { class: "tile-meta" }, `${n(c.launch0)} Launch-0 · ${n(c.proposed)} proposed`)),
      h("div", { class: "tile" }, h("p", { class: "tile-label" }, "Pictures verified"), h("p", { class: "tile-value" }, `${n(c.images_verified)} / ${n(c.collection)}`)),
      h("div", { class: "tile" }, h("p", { class: "tile-label" }, "Pattern quality OK"), h("p", { class: "tile-value" }, `${n(c.quality_ok)} / ${n(c.collection)}`)),
      h("div", { class: "tile", data: { etsy: etsy.status || "UNKNOWN" } }, h("p", { class: "tile-label" }, "Etsy connection"),
        h("p", { class: ["tile-value", !etsy.status || etsy.status === "UNKNOWN" ? "is-unknown" : null] }, ETSY_LABEL[etsy.status] || UNKNOWN_TEXT),
        etsy.reason ? h("p", { class: "tile-meta" }, etsy.reason) : null)),
    verdict && verdict.reason ? h("p", { class: "callout callout-warn" }, `Launch verdict: ${verdict.reason}`) : null,
    h("p", { class: "muted small" }, "Nothing is published from this screen. Publication is your authorisation, on the Approvals tab."));
}

function decisionsCard(cat, s) {
  const d = cat.decision || {};
  const pubs = s.publication_candidates && Array.isArray(s.publication_candidates.items) ? s.publication_candidates.items.length : null;
  return card({ title: "Your store decisions", labelId: "store-decisions" },
    h("ul", { class: "rows" },
      h("li", { class: "row" }, h("div", { class: "row-head" }, h("p", { class: "row-title" }, `${d.key || "D-FB-9"}: catalogue floor`),
        statusPill(d.approved ? "OK" : "PENDING", d.approved ? "DECIDED" : "AWAITING YOU")),
        h("p", { class: "row-detail" }, d.question || UNKNOWN_TEXT), d.how ? h("p", { class: "muted small" }, d.how) : null),
      h("li", { class: "row" }, h("div", { class: "row-head" }, h("p", { class: "row-title" }, "Publication approvals"),
        statusPill(pubs ? "PENDING" : pubs === 0 ? "OK" : "UNKNOWN", pubs === null ? "UNKNOWN" : `${pubs} READY FOR REVIEW`)),
        h("a", { class: "btn", href: "#/approvals" }, "Open approvals"))));
}

function previewCard(preview, cat) {
  const pv = (cat && cat.preview) || {};
  const base = preview || pv.path || null;
  const link = (variant, label, primary) => h("a", { class: ["btn", primary ? "btn-primary btn-block" : null], href: `${base}?variant=${encodeURIComponent(variant)}&viewport=mobile`, target: "_blank", rel: "noopener noreferrer" },
    primary ? icon("external", 18) : null, label);
  return card({ title: "Storefront review", labelId: "store-preview", subtitle: "The shop the way a buyer would meet it, before anything goes live." },
    base ? link(pv.default_variant || "storefront", "Open customer storefront preview", true)
      : h("p", { class: "callout callout-warn" }, "Store preview is not available yet: the store foundation has not reported a preview page."),
    base ? h("details", { class: "review" }, h("summary", null, "Earlier designs and comparisons"),
      h("div", { class: "btn-row" }, link("v2", "v2 proposal"), link("compare", "v2 vs v1"), link("standard", "v1 standard"), link("brand_face", "v1 with Laura"))) : null,
    h("p", { class: "muted" }, "Preview only. Nothing is published or activated from this screen. Internal checks sit in a folded owner panel at the foot of the preview."));
}

function controlsCard(cat) {
  const ctl = cat.etsy_controls;
  if (!ctl) return null;
  const surfaces = ctl.surfaces || {};
  return card({ title: "What Etsy lets the shop control", labelId: "store-etsy-controls", subtitle: `From Etsy's own help and API documents, read ${ctl.retrieved_on || "on an unknown date"}` },
    h("p", { class: "muted small" }, ctl.note || ""),
    Object.entries(surfaces).map(([surface, items]) => h("details", { class: "review" },
      h("summary", null, `${surface.replace(/_/g, " ")} (${items.length})`),
      h("dl", { class: "kv" }, items.map((it) => h("div", { class: it.value === null ? "missing" : null },
        h("dt", null, it.what), h("dd", null, `${it.value === null ? UNKNOWN_TEXT : Array.isArray(it.value) ? it.value.join(", ") : String(it.value)} · ${it.basis}`)))))),
    h("details", { class: "review" }, h("summary", null, "Drawn by Etsy, approximated by the preview"),
      h("ul", { class: "rows" }, (ctl.not_controlled || []).map((x) => h("li", { class: "row" }, h("p", { class: "row-title" }, x.element), h("p", { class: "row-detail" }, x.why))))));
}

// The owner records what the live Etsy page shows, one field at a time. Nothing is written to
// Etsy: the reading only feeds the drift check, whose repo proposals are ADOPT_LIVE_INTO_REPO.
function observationCard(drift, stale, rerender) {
  const rows = drift && Array.isArray(drift.items) ? drift.items : [];
  if (!rows.length) return null;
  const field = h("select", { id: "obs-field" }, rows.map((r) => h("option", { value: r.field }, r.title || r.field)));
  const value = h("textarea", { id: "obs-value", rows: 3, maxLength: 6000 });
  const statement = h("input", { id: "obs-statement", type: "text", maxLength: 500, placeholder: "e.g. read from the live shop page on my phone" });
  const btn = h("button", { class: "btn btn-primary", type: "button", disabled: stale, onclick: async () => {
    const statementText = statement.value.trim();
    if (!statementText) { statement.focus(); return; }
    const r = await guardedAction({ title: "Record this live-shop reading?",
      lines: ["It is saved as a dated, audited observation. Nothing is written to Etsy."],
      confirmLabel: "Record",
      run: () => api.liveObservation(new Date().toISOString(), { [field.value]: value.value }, statementText),
      success: "Observation recorded." });
    if (r) rerender();
  } }, "Record observation");
  return card({ title: "Record what the live shop shows", subtitle: "The live shop is authoritative for fields you set yourself. Software never edits them." },
    h("label", { class: "field", for: "obs-field" }, "Field"), field,
    h("label", { class: "field", for: "obs-value" }, "What the live page shows (leave empty if blank)"), value,
    h("label", { class: "field", for: "obs-statement" }, "How you read it"), statement, btn);
}

function catalogueError(err) {
  return card({ title: "Catalogue", actions: statusPill("UNKNOWN") },
    h("p", { class: "muted" }, `Unknown: the catalogue could not be loaded (${(err && err.message) || "error"}).`));
}

function evidenceGroup(data, result) {
  const cards = renderAll(data, ORDER, { result, required: ["store_foundation", "products"], skip: ["preview_url", "preview_path"] });
  return h("details", { class: "card evidence-group", id: "store-evidence" },
    h("summary", null, h("strong", null, `Technical evidence (${cards.length} sections)`),
      h("span", { class: "muted small" }, " · readiness checks, sources, search, launch packet")),
    h("div", { class: "stack" }, cards));
}

// ---- pages ------------------------------------------------------------------------------------

function productPage(p, cat) {
  if (!p) return card({ title: "No such product", actions: statusPill("UNKNOWN") }, h("p", { class: "muted" }, "This product is not in the launch collection."));
  const q = p.quality || {};
  const l = p.listing || {};
  const r = p.readiness || {};
  const img = p.image || {};
  const pdf = p.pdf || {};
  return h("div", { class: "stack" },
    card({ title: p.name, labelId: "product-head", cls: "product-head", actions: p.launch_status === "PROPOSED" ? statusPill("DEGRADED", "PROPOSED") : statusPill("OK", "LAUNCH-0") },
      productImage(p, "pimg pimg-lg"),
      h("p", { class: "ptile-price big" }, price(p.price_cad)),
      h("p", { class: "dl-label" }, p.digital_label || "Digital download (PDF pattern)"),
      h("p", null, p.description || ""),
      h("dl", { class: "kv" }, (p.sizes || []).map((sz) => h("div", null, h("dt", null, (p.sizes || []).length > 1 ? `Size: ${String(sz.key).replace(/_/g, " ")}` : "Size"), h("dd", null, sz.label)))),
      p.launch_status === "PROPOSED" ? h("p", { class: "callout callout-warn" }, p.launch_status_note) : null),
    card({ title: "Pattern PDF", labelId: "product-pdf", subtitle: "Your review copy, rendered now from the pattern file" },
      h("div", { class: "btn-row" }, (pdf.terms || []).map((t) => h("a", { class: "btn", href: (pdf.paths || {})[t], target: "_blank", rel: "noopener noreferrer", data: { pdf: t } }, icon("external", 18), `${t} terms PDF`))),
      h("p", { class: "muted small" }, pdf.note || "")),
    card({ title: "Readiness", labelId: "product-readiness", actions: pill(r.status || "UNKNOWN") },
      h("ul", { class: "rows" }, (r.blockers || []).map((b) => h("li", { class: "row" }, h("div", { class: "row-head" }, h("p", { class: "row-title" }, b.what), statusPill(b.clearer === "OWNER" ? "PENDING" : "BLOCKED", b.clearer))))),
      r.note ? h("p", { class: "muted small" }, r.note) : null),
    card({ title: "Listing & price", labelId: "product-listing", subtitle: "Read-only. Nothing is entered on Etsy from here." },
      h("dl", { class: "kv" },
        h("div", null, h("dt", null, "Listing title"), h("dd", null, l.title || UNKNOWN_TEXT)),
        h("div", { class: l.title_ok === false ? "missing" : null }, h("dt", null, "Title length"), h("dd", null, `${l.title_chars ?? UNKNOWN_TEXT} of ${l.title_max ?? UNKNOWN_TEXT} characters`)),
        h("div", null, h("dt", null, "Price"), h("dd", null, price(l.price_cad))),
        h("div", null, h("dt", null, "On Etsy"), h("dd", null, `${l.on_etsy || UNKNOWN_TEXT}: ${l.on_etsy_note || ""}`)))),
    h("details", { class: "card evidence-group" },
      h("summary", null, h("strong", null, "Technical evidence"), h("span", { class: "muted small" }, " · quality, image check, sources")),
      h("dl", { class: "kv" },
        h("div", null, h("dt", null, "Pattern quality"), h("dd", null, `${q.status || UNKNOWN_TEXT}${q.reason ? `: ${q.reason}` : ""}`)),
        h("div", null, h("dt", null, "Compiles / certified"), h("dd", null, `${q.compiles === undefined ? UNKNOWN_TEXT : q.compiles ? "yes" : "no"} / ${q.certified === undefined ? UNKNOWN_TEXT : q.certified ? "yes" : "no"}`)),
        h("div", null, h("dt", null, "Release hash"), h("dd", { class: "mono" }, q.release_hash || UNKNOWN_TEXT)),
        h("div", null, h("dt", null, "Picture check"), h("dd", null, `${img.status || UNKNOWN_TEXT} (verifier ${img.verifier_status || UNKNOWN_TEXT}, caption ${img.caption_status || UNKNOWN_TEXT})`)),
        h("div", null, h("dt", null, "Picture sha256"), h("dd", { class: "mono" }, img.sha256 || UNKNOWN_TEXT)),
        h("div", null, h("dt", null, "Title source"), h("dd", null, l.title_basis || UNKNOWN_TEXT)),
        h("div", null, h("dt", null, "Price source"), h("dd", null, l.price_basis || UNKNOWN_TEXT)),
        h("div", null, h("dt", null, "Design"), h("dd", { class: "mono" }, `${(p.representative || {}).cir_slug || UNKNOWN_TEXT} @ ${(p.representative || {}).cir_fingerprint || UNKNOWN_TEXT}`))),
      (q.certificate_errors || []).length ? h("ul", null, q.certificate_errors.map((e) => h("li", null, e))) : null),
    h("p", { class: "card-meta" }, freshness((cat && cat.generated_at) || null)));
}

function collectionPage(cat) {
  const ps = cat.products || [];
  const l0 = ps.filter((p) => p.launch_status === "LAUNCH_0");
  const prop = ps.filter((p) => p.launch_status === "PROPOSED");
  return h("div", { class: "stack" },
    card({ title: `Launch collection · ${ps.length} patterns`, labelId: "store-collection", subtitle: "5 Launch-0 patterns plus 3 prepared for the 8-product floor" },
      h("p", { class: "card-meta" }, freshness(cat.generated_at || null)),
      h("h3", { class: "section-title" }, `Launch-0 (${l0.length})`), catalogueGrid(l0),
      h("h3", { class: "section-title" }, `Proposed, awaiting your decision (${prop.length})`),
      prop.length ? catalogueGrid(prop) : h("p", { class: "muted" }, "None: the catalogue-floor decision has been made.")),
    decisionsCard(cat, {}));
}

function listingsPage(cat) {
  const ps = cat.products || [];
  return h("div", { class: "stack" },
    card({ title: "Listings & prices", labelId: "store-listings", subtitle: "Read-only: titles and prices with where each comes from. Nothing is entered on Etsy here." },
      h("p", { class: "card-meta" }, freshness(cat.generated_at || null)),
      h("ul", { class: "rows" }, ps.map((p) => {
        const l = p.listing || {};
        return h("li", { class: "row", data: { listing: p.slug } },
          h("div", { class: "row-head" }, h("a", { class: "row-title", href: `#/store/product/${encodeURIComponent(p.slug)}` }, p.name),
            h("span", { class: "ptile-price" }, price(l.price_cad))),
          h("p", { class: "row-detail" }, l.title || UNKNOWN_TEXT),
          h("p", { class: "muted small" }, `${l.title_chars ?? UNKNOWN_TEXT}/${l.title_max ?? UNKNOWN_TEXT} characters · ${p.launch_status === "PROPOSED" ? "proposed" : "Launch-0"} · on Etsy: ${l.on_etsy || UNKNOWN_TEXT}`),
          h("details", { class: "review" }, h("summary", null, "Where title and price come from"),
            h("p", { class: "muted small" }, `Title: ${l.title_basis || UNKNOWN_TEXT}`), h("p", { class: "muted small" }, `Price: ${l.price_basis || UNKNOWN_TEXT}`)));
      }))));
}

export async function render({ params = [], rerender } = {}) {
  const sub = params[0] || "";
  const [storeR, catR] = await Promise.allSettled([api.store(), api.storeCatalogue()]);
  if (storeR.status === "rejected" && catR.status === "rejected") throw storeR.reason;
  const result = storeR.status === "fulfilled" ? storeR.value : { data: {}, fetchedAt: null };
  const data = result.data || {};
  const s = sectionsOf(data);
  const cat = catR.status === "fulfilled" ? (catR.value.data || {}) : null;
  const preview = findPreview(data, s);
  const head = [...pageMeta(result, data), subnav(sub === "product" ? "collection" : sub)];

  if (sub === "product") {
    const p = cat ? (cat.products || []).find((x) => x.slug === params[1]) : null;
    return h("div", { class: "stack" }, backLink("#/store/collection", "Launch collection"),
      cat ? productPage(p, cat) : catalogueError(catR.reason));
  }
  if (sub === "collection") return h("div", { class: "stack" }, ...head, cat ? collectionPage(cat) : catalogueError(catR.reason));
  if (sub === "listings") return h("div", { class: "stack" }, ...head, cat ? listingsPage(cat) : catalogueError(catR.reason));
  if (sub === "storefront") return h("div", { class: "stack" }, ...head, previewCard(preview, cat), cat ? controlsCard(cat) : catalogueError(catR.reason));

  return h("div", { class: "stack" },
    ...head,
    cat ? readinessCard(cat, data, s) : catalogueError(catR.reason),
    cat ? decisionsCard(cat, s) : null,
    cat ? card({ title: "Catalogue", labelId: "store-catalogue", subtitle: "Tap a pattern for its pictures, PDFs, quality and listing", actions: h("a", { class: "btn", href: "#/store/collection" }, "All 8") },
      catalogueGrid((cat.products || []).filter((p) => p.launch_status === "LAUNCH_0"))) : null,
    previewCard(preview, cat),
    observationCard(s.live_drift, result.stale, rerender || (() => {})),
    evidenceGroup(data, result));
}
