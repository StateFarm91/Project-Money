// LISTING IMAGES (W-OWNERIMG). Autonomous gallery production status per product, and the
// optional owner upload fallback. The upload runs the same gates as autonomous production.
// Owner approval of the look is a separate field. It never counts as technical verification
// and never overrides a publication gate.
import { h, clear } from "../dom.js";
import { api } from "../api.js";
import { card, statusPill, toast } from "../components.js";

const ROLES = ["lifestyle", "detail", "size", "angle", "colour_context", "hero", "proof", "fit"];
const STATE_PILL = { ready_for_owner_review: "OK", approved_for_publication: "OK", blocked: "BAD" };

function field(label, input) {
  return h("div", null, h("label", { class: "field", for: input.id }, label), input);
}

function checksList(checks) {
  return h("ul", { class: "rows" }, Object.entries(checks || {})
    .filter(([k]) => !k.startsWith("_"))
    .map(([k, c]) => h("li", { class: "row" },
      h("p", { class: "row-title" }, statusPill(String(c.status || "UNKNOWN")), ` ${k}`),
      h("p", { class: "row-detail" }, String(c.why || "")))));
}

function resultCard(out) {
  const blockers = ((out.publication || {}).blockers || []);
  return card({ title: `Result: ${out.technical_status}`, subtitle: `sha256 ${String(out.sha256 || "").slice(0, 16)}… · not a photograph` },
    h("p", null, statusPill(out.publishable ? "OK" : "BAD", out.publishable ? "Publishable" : "Not publishable")),
    h("p", { class: "muted small" }, out.note || ""),
    checksList(out.checks),
    blockers.length ? h("div", null, h("h3", { class: "section-title" }, "Publication blockers"),
      h("ul", null, blockers.map((b) => h("li", null, b)))) : null);
}

function readFileB64(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result || "").split(",", 2)[1] || "");
    r.onerror = () => reject(new Error("Could not read the file"));
    r.readAsDataURL(file);
  });
}

function uploadForm(products, out) {
  const file = h("input", { id: "oi-file", type: "file", required: true });
  file.setAttribute("accept", "image/png,image/jpeg");
  const slug = h("select", { id: "oi-slug" }, products.map((p) => h("option", { value: p.listing }, p.listing)));
  const version = h("input", { id: "oi-version", placeholder: "1.2.0", required: true });
  const release = h("input", { id: "oi-release", placeholder: "release id (12+ hex)", required: true });
  const role = h("select", { id: "oi-role" }, ROLES.map((r) => h("option", { value: r }, r)));
  const provider = h("input", { id: "oi-provider", value: "bfl-dashboard" });
  const model = h("input", { id: "oi-model", value: "FLUX 3 Image" });
  const prompt = h("textarea", { id: "oi-prompt", rows: 3 });
  const refs = h("textarea", { id: "oi-refs", rows: 3, placeholder: "one per line: sha256 kind (laura_canonical, pattern_derived, physical_product_photo, prior_candidate, other)" });
  const cost = h("input", { id: "oi-cost", type: "number", step: "0.001", min: "0", placeholder: "optional" });
  const laura = h("input", { id: "oi-laura", type: "checkbox" });
  const outfit = h("input", { id: "oi-outfit", placeholder: "outfit id, required when Laura appears" });
  const liked = h("input", { id: "oi-liked", type: "checkbox" });
  const btn = h("button", { class: "btn btn-primary", type: "submit" }, "Submit image");
  const form = h("form", { class: "stack" },
    field("Image (original file, PNG or JPEG)", file), field("Product", slug), field("Version", version),
    field("Release", release), field("Gallery role", role), field("Provider", provider), field("Model", model),
    field("Prompt", prompt), field("Reference fingerprints", refs), field("Cost (USD, optional)", cost),
    field("Laura appears", laura), field("Outfit id", outfit), field("I approve the look (not a technical check)", liked), btn);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!file.files || !file.files[0]) { toast("Choose an image file", "bad"); return; }
    btn.disabled = true;
    try {
      const b64 = await readFileB64(file.files[0]);
      const res = await api.ownerImage({ image_b64: b64, slug: slug.value, version: version.value.trim(),
        release: release.value.trim(), role: role.value, provider: provider.value, model: model.value,
        prompt: prompt.value, references: refs.value, cost_usd: cost.value === "" ? null : cost.value,
        laura_present: laura.checked, outfit_id: outfit.value.trim(), owner_visual_approval: liked.checked });
      clear(out); out.append(resultCard(res));
    } catch (err) {
      toast(err.message, "bad");
    } finally {
      btn.disabled = false;
    }
  });
  return form;
}

function runRow(p, rerender) {
  const st = String(p.state || "awaiting_certified_pattern");
  const approve = st === "ready_for_owner_review" ? h("button", { class: "btn", type: "button", onclick: async () => {
    try {
      const r = await api.approveImages(p.run_key);
      toast(r.approved ? "Approved for publication" : `Not approved: ${(r.blockers || []).join("; ") || r.why}`, r.approved ? "ok" : "bad");
      rerender();
    } catch (err) { toast(err.message, "bad"); }
  } }, "Approve gallery") : null;
  return h("li", { class: "row" },
    h("p", { class: "row-title" }, statusPill(STATE_PILL[st] || "UNKNOWN", st), ` ${p.listing}`),
    p.blocked_reason ? h("p", { class: "row-detail" }, p.blocked_reason) : null,
    p.why ? h("p", { class: "row-detail" }, p.why) : null,
    approve);
}

export async function render({ rerender } = {}) {
  const board = await api.images();
  const products = Array.isArray(board.products) ? board.products : [];
  const out = h("div", { aria: { live: "polite" } });
  const learn = board.learning || {};
  return h("div", { class: "stack" },
    card({ title: "Gallery production", subtitle: "Autonomous image production per product. You are notified only when a gallery is ready for review or blocked after its permitted attempts." },
      h("ul", { class: "rows" }, products.map((p) => runRow(p, rerender || (() => {}))))),
    card({ title: "Learning", subtitle: "Per candidate outcomes. Cost per accepted image is Unknown until an image is accepted." },
      h("p", null, `Candidates: ${learn.candidates ?? "Unknown"} · accepted: ${learn.accepted ?? "Unknown"} · cost per accepted: ${learn.cost_per_accepted_cad == null ? "Unknown" : `CA$${learn.cost_per_accepted_cad}`}`)),
    card({ title: "Submit an owner-made image (fallback)", subtitle: "Stored unchanged by sha256, labelled AI-generated (never a photograph), and checked by the same gates as autonomous images. Missing evidence stays Unknown." },
      uploadForm(products, out)),
    out);
}
