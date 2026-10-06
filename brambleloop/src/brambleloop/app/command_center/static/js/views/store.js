// STORE (F-926 store preview tab): readiness from lane F/G, products/releases/listings, and the
// customer-view preview link. The preview opens as its own page: the edge sends
// frame-ancestors 'none' / X-Frame-Options DENY, so it is deliberately not embedded in an iframe.
import { h, icon, safeUrl } from "../dom.js";
import { api } from "../api.js";
import { card } from "../components.js";
import { sectionsOf, pageMeta, renderAll } from "./_shared.js";

const ORDER = [["store_foundation", "Store foundation"], ["products", "Products, releases & listings"],
  ["publication_candidates", "Ready for publication review"], ["launch_verdict", "Launch verdict"],
  ["visibility", "Launch visibility: storefront, search, funnel, traffic"], ["seo", "Search & SEO"],
  ["seo_w3", "Search: Etsy constraints & strategy"], ["search_evidence", "Search evidence per listing"],
  ["launch_packet", "Launch packet"]];

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

export async function render() {
  const result = await api.store();
  const data = result.data || {};
  const s = sectionsOf(data);
  const preview = findPreview(data, s);
  return h("div", { class: "stack" },
    ...pageMeta(result, data),
    card({ title: "Customer-view preview", subtitle: "See the shop the way a buyer would, before anything goes live." },
      preview ? h("a", { class: "btn btn-primary btn-block", href: preview, target: "_blank", rel: "noopener noreferrer" },
        icon("external", 18), "Open store preview")
        : h("p", { class: "callout callout-warn" }, "Store preview is not available yet: the store foundation has not reported a preview page."),
      h("p", { class: "muted" }, "Preview only. Nothing is published or activated from this screen.")),
    ...renderAll(data, ORDER, { result, required: ["store_foundation", "products"], skip: ["preview_url", "preview_path"] }));
}
