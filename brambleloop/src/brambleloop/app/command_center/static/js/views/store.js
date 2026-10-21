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
import { shopReadingsCard } from "./_shop_readings.js";

const ORDER = [["store_foundation", "Store foundation"],
  ["live_drift", "Live shop vs repo drafts (drift)"], ["store_readiness", "Store readiness"],
  ["competitor_intel", "Competitor findings (provenance & confidence)"], ["products", "Products, releases & listings"],
  ["publication_candidates", "Ready for publication review"], ["launch_verdict", "Launch verdict"],
  ["visibility", "Launch visibility: storefront, search, funnel, traffic"], ["seo", "Search & SEO"],
  ["seo_w3", "Search: Etsy constraints & strategy"], ["search_evidence", "Search evidence per listing"],
  ["launch_packet", "Launch packet"]];

const CATALOGUE_WAIT_MS = 8000;
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
// Launch status of a collection product. CAP-1 (owner, 2026-10-11) changed the cap 5 -> 8 as
// configuration only: those products are in Launch-0 scope but not approved; gates pending.
const CAP1_LABEL = "In Launch-0 scope (CAP-1); not approved: gates pending";
function launchPill(p) {
  if (p.launch_status === "CAP1_SCOPE") return statusPill(p.on_customer_page ? "OK" : "DEGRADED", p.on_customer_page ? "CAP-1 · GATES PASS" : "CAP-1 · NOT APPROVED");
  if (p.launch_status === "PROPOSED") return statusPill("DEGRADED", "PROPOSED");
  return statusPill("OK", "LAUNCH-0");
}

// W4-SHOPSYNC: every live shop setting in one of three states. CONFIRMED-LIVE comes from a
// read-only Etsy API reading; OWNER-CONFIRMED from the owner's one-tap confirmation (for what
// the API cannot read), with the evidence already on file shown first; UNVERIFIED otherwise.
const STATE_CLASS = { "CONFIRMED-LIVE": "callout-info", "OWNER-CONFIRMED": "callout-info", UNVERIFIED: "callout-warn" };

function evidenceLines(ev) {
  const out = [];
  if (!ev) return out;
  for (const [k, v] of Object.entries(ev.api || {})) out.push(`Etsy API ${k}: ${JSON.stringify(v).slice(0, 160)}`);
  for (const [k, v] of Object.entries(ev.observations || {})) out.push(`Your observation ${k} (${v.observed_at || "?"}): ${JSON.stringify(v.value).slice(0, 160)}`);
  for (const a of ev.owner_actions || []) out.push(`Owner card ${a.key} (${a.done ? "done" : "open"}): ${a.action}`);
  return out;
}

function settingsCard(st, stale, rerender) {
  if (!st || !Array.isArray(st.settings)) return null;
  const counts = st.counts || {};
  const rows = st.settings.map((r) => {
    const meta = r.state === "UNVERIFIED" ? (r.why || "") : `${r.source || ""} · ${r.observed_at || ""}`;
    const kids = [h("strong", null, r.label), " ", h("span", { class: `callout ${STATE_CLASS[r.state] || ""}` }, r.state),
      h("div", { class: "muted" }, meta)];
    if (r.owner_confirmable && r.state !== "CONFIRMED-LIVE") {
      kids.push(h("button", { class: "btn", type: "button", disabled: stale, onclick: async () => {
        const lines = [r.prefilled_statement || "", ...evidenceLines(r.evidence), `Where: ${r.where}`];
        const done = await guardedAction({ title: `Confirm: ${r.label}?`, lines,
          confirmLabel: "Confirm", run: () => api.confirmStoreSetting(r.key, r.prefilled_statement || ""),
          success: "Recorded as OWNER-CONFIRMED." });
        if (done) rerender();
      } }, r.state === "OWNER-CONFIRMED" ? "Re-confirm" : "Confirm"));
    }
    return h("div", { class: "stack" }, ...kids);
  });
  const sync = h("button", { class: "btn", type: "button", disabled: stale, onclick: async () => {
    const r = await guardedAction({ title: "Re-read the shop from Etsy?",
      lines: ["Read-only. Nothing on Etsy is changed."], confirmLabel: "Re-read",
      run: () => api.storeSettingsSync(), success: "Re-read queued." });
    if (r) rerender();
  } }, "Re-read from Etsy");
  return card({ title: "Live shop settings",
    subtitle: `CONFIRMED-LIVE ${counts["CONFIRMED-LIVE"] || 0} · OWNER-CONFIRMED ${counts["OWNER-CONFIRMED"] || 0} · UNVERIFIED ${counts.UNVERIFIED || 0}` },
    ...rows, h("div", { class: "btn-row" }, sync));
}

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
      h("span", { class: "pimg-tag" }, img.pieces_finding ? "Rendering · incomplete hero" : "Rendering"));
  }
  const why = img.status === "NOT_CHECKED" ? "Image not checked" : img.status === "WITHHELD" ? "Image withheld (did not verify)" : `Image ${img.status || UNKNOWN_TEXT}`;
  return h("div", { class: [cls, "pimg-none"], data: { image: img.status || "UNKNOWN" } }, h("span", null, why));
}

function productTile(p) {
  return h("a", { class: "ptile", href: `#/store/product/${encodeURIComponent(p.slug)}`, data: { product: p.slug } },
    productImage(p),
    h("span", { class: "ptile-name" }, p.name),
    h("span", { class: "ptile-price" }, price(p.price_cad)),
    h("span", { class: "ptile-meta" }, launchPill(p),
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
    cat.preparing ? h("p", { class: "callout callout-info", data: { preparing: "1" } }, `Still checking: ${cat.preparing_note || "pictures and pattern checks are being computed"}`) : null,
    h("div", { class: "tiles" },
      h("div", { class: "tile" }, h("p", { class: "tile-label" }, "Launch collection"), h("p", { class: "tile-value" }, n(c.collection)),
        h("p", { class: "tile-meta" }, `${n(c.launch0)} Launch-0 · ${n(c.cap1)} CAP-1 (not approved)${c.proposed ? ` · ${n(c.proposed)} proposed` : ""}`)),
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
      h("li", { class: "row" }, h("div", { class: "row-head" }, h("p", { class: "row-title" }, `${d.key || "CAP-1"}: products in Launch-0 scope`),
        statusPill(d.approved ? "OK" : "PENDING", d.approved ? "APPROVED" : "NOT APPROVED: GATES PENDING")),
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

// ---- section: Etsy connection (W4-ETSYCOMM) ---------------------------------------------------
// The two Etsy-connection steps only the owner can take, from a phone. Re-check
// queues a read-only ping of the app key; Connect (step-up) starts the shop authorization and
// opens Etsy's own consent page. Neither changes scopes, credentials or the Etsy app.
const ETSY_CONSENT_HOST = "www.etsy.com";

function etsyCard(etsy, stale, rerender) {
  if (!etsy) return null;
  const probe = etsy.api_key_probe || {};
  const grant = etsy.grant || {};
  const auth = etsy.authorise || {};
  const lines = [];
  if (probe.state === "OK") lines.push(h("p", { class: "callout callout-info" }, `Etsy accepts the app key (last check ${probe.at || "?"}).`));
  else if (probe.state === "FAILING") lines.push(h("p", { class: "callout callout-bad" },
    `Etsy is refusing the app key (last check ${probe.at || "?"})${probe.etsy_error ? `: "${probe.etsy_error}"` : ""}. Check the app at etsy.com/developers/your-apps, then re-check.`));
  else lines.push(h("p", { class: "callout callout-warn" }, "The app key has not been checked yet."));
  lines.push(h("p", { class: "muted" }, grant.stored
    ? `Shop authorised for: ${(grant.scopes || []).join(", ") || "none"}.` + ((grant.missing_scopes || []).length ? ` Still needed: ${grant.missing_scopes.join(", ")}.` : "")
    : "The shop has not been authorised for this app yet."));
  for (const p of auth.problems || []) lines.push(h("p", { class: "callout callout-warn" }, p));
  const recheck = h("button", { class: "btn", type: "button", disabled: stale, onclick: async () => {
    const r = await guardedAction({ title: "Re-check the Etsy connection?",
      lines: ["Sends one read-only test request to Etsy. Nothing is written or published."],
      confirmLabel: "Re-check", run: () => api.etsyRecheck(), success: "Re-check queued." });
    if (r) rerender();
  } }, "Re-check Etsy connection");
  const connect = h("button", { class: "btn btn-primary", type: "button", disabled: stale || !etsy.can_connect, onclick: async () => {
    const r = await guardedAction({ title: "Connect the Etsy shop?",
      lines: ["Opens Etsy's own page asking you to approve this app's access to your shop, including reading orders (transactions_r).",
        "Sign in as the account that owns the shop and press Allow. Nothing is published."],
      confirmLabel: "Continue to Etsy", requiresStepUp: true,
      run: () => api.etsyConnect(), success: "Opening Etsy..." });
    // Navigate only to Etsy's own consent host: the URL is built server-side, but the phone
    // checks it anyway rather than following whatever a response says.
    const url = r && safeUrl(r.authorize_url);
    let host = "";
    try { host = url ? new URL(url).hostname : ""; } catch (_) { host = ""; }
    if (host === ETSY_CONSENT_HOST) window.location.assign(url);
  } }, "Connect Etsy shop");
  return card({ title: "Etsy connection", subtitle: "Only you can fix the app key or authorise the shop. These buttons are safe to press." },
    ...lines, h("div", { class: "btn-row" }, recheck, connect));
}

// ---- section: live-shop observation (W4-STORE) -------------------------------------------------
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
  return card({ title: "Catalogue", labelId: "store-catalogue-unavailable", actions: statusPill(err && err.preparing ? "PENDING" : "UNKNOWN", err && err.preparing ? "PREPARING" : "UNKNOWN") },
    h("p", { class: "muted" }, err && err.preparing ? `Not loaded yet: ${err.message}.`
      : `Unknown: the catalogue could not be loaded (${(err && err.message) || "error"}).`));
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
    card({ title: p.name, labelId: "product-head", cls: "product-head", actions: launchPill(p) },
      productImage(p, "pimg pimg-lg"),
      h("p", { class: "ptile-price big" }, price(p.price_cad)),
      h("p", { class: "dl-label" }, p.digital_label || "Digital download (PDF pattern)"),
      h("p", null, p.description || ""),
      h("dl", { class: "kv" }, (p.sizes || []).map((sz) => h("div", null, h("dt", null, (p.sizes || []).length > 1 ? `Size: ${String(sz.key).replace(/_/g, " ")}` : "Size"), h("dd", null, sz.label)))),
      p.launch_status !== "LAUNCH_0" ? h("p", { class: "callout callout-warn" }, p.launch_status_note) : null,
      h("p", { class: "muted small" }, p.on_customer_page ? "Shown on the customer preview." : "Not shown on the customer preview until every gate passes.")),
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
  const groups = [
    ["LAUNCH_0", "Launch-0"],
    ["CAP1_SCOPE", CAP1_LABEL],
    ["PROPOSED", "Proposed, awaiting your decision"],
  ].map(([st, label]) => [label, ps.filter((p) => p.launch_status === st)]).filter(([, list]) => list.length);
  return h("div", { class: "stack" },
    card({ title: `Launch collection · ${ps.length} patterns`, labelId: "store-collection", subtitle: "The 8-product launch collection and where each pattern stands" },
      h("p", { class: "card-meta" }, freshness(cat.generated_at || null)),
      groups.map(([label, list]) => [h("h3", { class: "section-title" }, `${label} (${list.length})`), catalogueGrid(list)])),
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
          h("p", { class: "muted small" }, `${l.title_chars ?? UNKNOWN_TEXT}/${l.title_max ?? UNKNOWN_TEXT} characters · ${p.launch_status === "CAP1_SCOPE" ? "CAP-1, not approved" : p.launch_status === "PROPOSED" ? "proposed" : "Launch-0"} · on Etsy: ${l.on_etsy || UNKNOWN_TEXT}`),
          h("details", { class: "review" }, h("summary", null, "Where title and price come from"),
            h("p", { class: "muted small" }, `Title: ${l.title_basis || UNKNOWN_TEXT}`), h("p", { class: "muted small" }, `Price: ${l.price_basis || UNKNOWN_TEXT}`)));
      }))));
}

export async function render({ params = [], rerender } = {}) {
  const sub = params[0] || "";
  // The first catalogue of a server process renders and checks eight pictures (tens of
  // seconds); later ones are cached. The page does not wait on that: past CATALOGUE_WAIT_MS it
  // renders with a "being prepared" card, and the request keeps warming the server cache.
  const catalogue = Promise.race([api.storeCatalogue(), new Promise((_, rej) => setTimeout(
    () => rej(Object.assign(new Error("the catalogue is still being prepared (pictures are rendered and checked on first load); refresh in a moment"), { preparing: true })),
    CATALOGUE_WAIT_MS))]);
  const [storeR, catR, etsyR] = await Promise.allSettled([api.store(), catalogue, api.etsy()]);
  if (storeR.status === "rejected" && catR.status === "rejected") throw storeR.reason;
  const result = storeR.status === "fulfilled" ? storeR.value : { data: {}, fetchedAt: null };
  const data = result.data || {};
  const s = sectionsOf(data);
  const cat = catR.status === "fulfilled" ? (catR.value.data || {}) : null;
  const preview = findPreview(data, s);
  const etsy = etsyR.status === "fulfilled" ? etsyR.value.data : null;
  let settings = null;
  try { settings = (await api.storeSettings()).data; } catch (_) { settings = null; }
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
    // Overview sections, each self-contained (a later lane adds its own card here):
    previewCard(preview, cat),
    settingsCard(settings, result.stale, rerender || (() => {})),
    etsyCard(etsy, result.stale, rerender || (() => {})),
    observationCard(s.live_drift, result.stale, rerender || (() => {})),
    // LAUNCHPREP E5: the owner's dated Shop Manager readings, from the phone (step-up).
    shopReadingsCard(rerender || (() => {}), { labelId: "store-shop-readings" }),
    evidenceGroup(data, result));
}
