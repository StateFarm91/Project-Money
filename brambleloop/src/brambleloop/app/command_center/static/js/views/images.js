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

// ---- gallery approval card (W-VISNEXT) ---------------------------------------------------
// The images themselves, and three decisions that stay apart: your look (recorded, read by no
// gate), technical certification (automated; your look cannot change it) and publication
// authorization (step-up; every gate is re-checked when you press it).

const DECISION_PILL = { approved: "OK", available: "OK", PASS: "OK", rejected: "BAD", FAIL: "BAD", not_available: "BAD" };

function frameFigure(f) {
  const alt = `${f.role} (position ${f.position}): ${f.label || "no generated image"}`;
  return h("figure", { class: "gallery-frame" },
    f.image_url ? h("img", { src: f.image_url, alt, loading: "lazy", width: 240, height: 240 })
      : h("div", { class: "muted small" }, f.source === "disclosed_render" ? "Disclosed rendering (certified set)" : "No generated image"),
    h("figcaption", null,
      h("p", { class: "row-title" }, statusPill(f.technical_status === "PASS" ? "OK" : f.technical_status ? (f.technical_status === "FAIL" ? "BAD" : "UNKNOWN") : "UNKNOWN", f.technical_status || "—"), ` ${f.position}. ${f.role}`),
      h("p", { class: "row-detail" }, String(f.status || "")),
      Object.keys(f.failed || {}).length ? h("p", { class: "row-detail" }, `Failed: ${Object.keys(f.failed).join(", ")}`) : null,
      (f.unknown || []).length ? h("p", { class: "row-detail" }, `Unknown: ${f.unknown.join(", ")}`) : null));
}

function decisionBlock(title, d, ...extra) {
  return h("div", { class: "stack" },
    h("h3", { class: "section-title" }, title),
    h("p", null, statusPill(DECISION_PILL[d.state] || "UNKNOWN", String(d.state || "UNKNOWN"))),
    h("p", { class: "muted small" }, String(d.what || "")), ...extra);
}

// Stage A (W-VISNEXT2): the Laura identity anchor. Confirming lets it be used as identity
// context for this listing; it never turns any check into a pass.
function anchorBlock(c, reload) {
  const a = c.identity_anchor;
  const decide = async (decision) => {
    try {
      const r = await api.identityReview(c.run_key, decision, "");
      toast(r.resolved ? `Recorded: ${decision}` : r.why, r.resolved ? "ok" : "bad");
      reload();
    } catch (err) { toast(err.message, "bad"); }
  };
  return h("div", { class: "stack" },
    h("h3", { class: "section-title" }, "Laura identity anchor"),
    a.image_url ? h("img", { src: a.image_url, alt: a.label, loading: "lazy", width: 240, height: 240 }) : null,
    h("p", { class: "row-detail" }, `${a.technical_status} · attempts ${a.attempts} · unknown ${(a.unknown || []).join(", ") || "none"}`),
    a.review_needed ? h("div", { class: "row" },
      h("button", { class: "btn", type: "button", onclick: () => decide("confirmed_same_person") }, "This is Laura"),
      h("button", { class: "btn", type: "button", onclick: () => decide("not_laura") }, "Not Laura"),
      h("button", { class: "btn", type: "button", onclick: () => decide("inconclusive") }, "Can't tell")) :
      h("p", { class: "muted small" }, a.review ? `Review: ${a.review.decision || a.review.state}` : ""));
}

export function galleryCard(c, reload) {
  const d = c.decisions || {};
  const vis = d.visual_approval || {}, tech = d.technical_certification || {}, pub = d.publication_authorization || {};
  const note = h("input", { id: `va-note-${c.run_key}`, placeholder: "note (optional)" });
  const look = async (approved) => {
    try {
      const r = await api.visualApproval(c.run_key, approved, note.value);
      toast(r.recorded ? "Your look is recorded (not a technical or publication decision)" : r.why, r.recorded ? "ok" : "bad");
      reload();
    } catch (err) { toast(err.message, "bad"); }
  };
  const authorize = pub.state === "available" ? h("button", { class: "btn btn-primary", type: "button", onclick: async () => {
    try {
      const r = await api.approveImages(c.run_key);
      toast(r.approved ? "Publication authorized" : `Not authorized: ${(r.blockers || []).join("; ") || r.why}`, r.approved ? "ok" : "bad");
      reload();
    } catch (err) { toast(err.message, "bad"); }
  } }, "Authorize publication") : null;
  const rs = c.restartable || {};
  const restart = rs.restartable ? h("button", { class: "btn", type: "button", onclick: async () => {
    try {
      const r = await api.restartImages(c.run_key, "owner restart from the gallery card");
      toast(r.restarted ? `Restarted (epoch ${r.epoch}) at ${r.resume_at}` : r.why, r.restarted ? "ok" : "bad");
      reload();
    } catch (err) { toast(err.message, "bad"); }
  } }, `Restart at ${rs.resume_at}`) : null;
  return card({ title: `${c.experiment ? (c.label || "EXPERIMENT") + ": " : ""}Gallery: ${c.listing}`,
    subtitle: `${c.status} · spent CA$${c.spent_cad} · ${c.generation_calls} generation call(s) · restarts ${c.restarts}` },
    h("div", { class: "gallery-grid" }, (c.frames || []).map(frameFigure)),
    c.identity_anchor ? anchorBlock(c, reload) : null,
    decisionBlock("1. Visual approval (your look only)", vis,
      vis.record ? h("p", { class: "row-detail" }, `${vis.record.approved_look ? "Liked" : "Not liked"} by ${vis.record.by} at ${vis.record.at}`) : null,
      note,
      h("div", { class: "row" },
        h("button", { class: "btn", type: "button", onclick: () => look(true) }, "I like the look"),
        h("button", { class: "btn", type: "button", onclick: () => look(false) }, "Not this look"))),
    decisionBlock("2. Technical certification (automated)", tech,
      tech.certification ? h("p", { class: "row-detail" }, `Pattern certification: ${(tech.certification || {}).granted ? "granted" : "REFUSED"}`) : null,
      h("p", { class: "row-detail" }, `Set check: ${(tech.set_check || {}).ok ? "ok" : "not ok"} · campaign consistency: ${(tech.campaign_consistency || {}).status || "—"}`)),
    decisionBlock("3. Publication authorization", pub,
      (pub.blockers || []).length ? h("ul", null, pub.blockers.map((b) => h("li", null, b))) : null,
      h("p", { class: "muted small" }, String(pub.requires || "")), authorize),
    (c.recommended_fix || []).length ? h("div", null, h("h3", { class: "section-title" }, "Recommended fix"),
      h("ul", null, c.recommended_fix.map((x) => h("li", null, x)))) : null,
    rs.restartable === false && c.state === "blocked" ? h("p", { class: "muted small" }, `Restart: ${rs.why}`) : restart);
}

function runRow(p, rerender, slot) {
  const st = String(p.state || "awaiting_certified_pattern");
  const open = p.run_key ? h("button", { class: "btn", type: "button", onclick: async () => {
    const load = async () => {
      try {
        const c = await api.imagesCard(p.run_key);
        clear(slot); slot.append(galleryCard(c, load));
        slot.scrollIntoView({ behavior: "smooth", block: "start" });
      } catch (err) { toast(err.message, "bad"); }
    };
    load();
  } }, "Open gallery") : null;
  return h("li", { class: "row" },
    h("p", { class: "row-title" }, statusPill(STATE_PILL[st] || "UNKNOWN", st), ` ${p.listing}`),
    p.blocked_reason ? h("p", { class: "row-detail" }, p.blocked_reason) : null,
    p.why ? h("p", { class: "row-detail" }, p.why) : null,
    open);
}

// ---- wardrobe editor (W-VISNEXT) -----------------------------------------------------------

function outfitRow(o, listings, reload) {
  const act = async (payload, ok) => {
    try { await api.outfitAction({ outfit_id: o.outfit_id, ...payload }); toast(ok, "ok"); reload(); }
    catch (err) { toast(err.message, "bad"); }
  };
  const listingSel = h("select", { id: `wr-l-${o.outfit_id}` }, listings.map((l) => h("option", { value: l }, l)));
  const refInput = h("input", { id: `wr-r-${o.outfit_id}`, placeholder: "sha256 of an image of this outfit" });
  const g = o.garments || {};
  return h("li", { class: "row" },
    h("p", { class: "row-title" }, statusPill(o.approval_state === "approved" ? "OK" : o.approval_state === "retired" ? "BAD" : "UNKNOWN", o.approval_state), ` ${o.outfit_id}`,
      o.listing ? ` · ${o.listing}` : " · unreserved"),
    h("p", { class: "row-detail" }, ["top_or_dress", "lower", "shoes", "outerwear", "accessories"].map((k) => `${k}: ${g[k] || "—"}`).join(" · ")),
    h("p", { class: "row-detail" }, `Distinct: ${(o.distinctness || {}).status || "UNKNOWN"} ${(o.distinctness || {}).why || ""}`),
    h("p", { class: "row-detail" }, `Outfit reference: ${o.approved_reference ? o.approved_reference.slice(0, 16) + "…" : "none"}`),
    h("div", { class: "row" },
      o.approval_state === "proposed" ? h("button", { class: "btn", type: "button", onclick: () => act({ action: "approve" }, "Approved") }, "Approve") : null,
      !o.listing && o.approval_state === "approved" ? h("span", null, listingSel,
        h("button", { class: "btn", type: "button", onclick: () => act({ action: "reserve", listing: listingSel.value }, "Reserved") }, "Reserve for listing")) : null,
      o.listing && !(o.uses || []).length ? h("button", { class: "btn", type: "button", onclick: () => act({ action: "release", listing: o.listing }, "Released") }, "Release") : null,
      o.approval_state === "approved" ? h("span", null, refInput,
        h("button", { class: "btn", type: "button", onclick: () => act({ action: "set_reference", image_sha256: refInput.value.trim() }, "Outfit reference set") }, "Set outfit reference")) : null));
}

function newOutfitForm(w, reload) {
  const slots = w.slots || [];
  const id = h("input", { id: "wr-new-id", placeholder: "outfit id, e.g. rust-turtleneck-07", required: true });
  const inputs = Object.fromEntries(slots.map((s) => {
    const dl = h("datalist", { id: `wr-dl-${s}` }, ((w.catalogue || {})[s] || []).map((g) => h("option", { value: g })));
    const inp = h("input", { id: `wr-new-${s}`, placeholder: s });
    inp.setAttribute("list", `wr-dl-${s}`);
    return [s, [inp, dl]];
  }));
  const approve = h("input", { id: "wr-new-approve", type: "checkbox" });
  const btn = h("button", { class: "btn btn-primary", type: "submit" }, "Add outfit");
  const form = h("form", { class: "stack" }, field("Outfit id", id),
    ...slots.map((s) => h("div", null, field(s, inputs[s][0]), inputs[s][1])),
    field("Approve now", approve), btn);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    btn.disabled = true;
    try {
      const garments = Object.fromEntries(slots.map((s) => [s, inputs[s][0].value.trim()]));
      await api.registerOutfit({ outfit_id: id.value.trim(), garments, approve: approve.checked });
      toast("Outfit added", "ok"); reload();
    } catch (err) { toast(err.message, "bad"); } finally { btn.disabled = false; }
  });
  return form;
}

export function wardrobeEditor(w, listings, reload) {
  return card({ title: "Wardrobe", subtitle: `One complete outfit per listing, never reused. Outfits are distinct below ${w.max_similarity} similarity. The canonical references' clothing (${Object.values(w.reference_clothing || {}).filter((v) => v && v !== "none").join(", ")}) is never an outfit.` },
    h("ul", { class: "rows" }, (w.outfits || []).map((o) => outfitRow(o, listings, reload))),
    h("h3", { class: "section-title" }, "Add an outfit"),
    newOutfitForm(w, reload));
}

// ---- controlled experiments (W-VISNEXT) ----------------------------------------------------
// Owner-only. Authorize and Run both need step-up. The output is an EXPERIMENT: shown in the
// same gallery card, never publishable.

function experimentDetails(c) {
  const costs = c.costs || {};
  const ver = c.verification || {};
  return card({ title: c.banner || "EXPERIMENT", subtitle: `Authorization ${(c.authorization || {}).auth_id || "—"} · definition ${String(c.definition_sha256 || "").slice(0, 12)}…` },
    h("p", { class: "row-detail" }, `Generation CA$${costs.generation_spent_cad ?? "—"} of CA$${costs.generation_cap_cad ?? "—"} · vision CA$${costs.vision_spent_cad ?? "—"} of CA$${costs.vision_cap_cad ?? "—"}`),
    h("h3", { class: "section-title" }, "References sent, in order"),
    h("ol", null, (c.references_in_order || []).map((r) => h("li", null, `${r.role}: ${String(r.sha256 || "").slice(0, 16)}…`))),
    h("h3", { class: "section-title" }, `Verification: ${ver.summary || "UNKNOWN"}`),
    h("ul", { class: "rows" }, Object.entries(ver.checks || {}).map(([k, v]) => h("li", { class: "row" },
      h("p", { class: "row-title" }, statusPill(v.status === "PASS" ? "OK" : v.status === "FAIL" ? "BAD" : "UNKNOWN", v.status || "UNKNOWN"), ` ${k}`),
      h("p", { class: "row-detail" }, String(v.why || ""))))),
    (ver.unknown || []).length ? h("p", { class: "muted small" }, `Unknown (never treated as pass): ${ver.unknown.join(", ")}`) : null,
    h("h3", { class: "section-title" }, "Provider receipt"),
    h("p", { class: "row-detail" }, `model ${(c.receipt || {}).model || "—"} · cost CA$${(c.receipt || {}).cad ?? "—"} · task ${((c.receipt || {}).provider_receipt || {}).id || "—"}`));
}

function experimentsCard(list, slot, reload) {
  return card({ title: "Controlled experiments", subtitle: "Frozen, owner-authorized experiments. Authorize and Run need step-up. Outputs are EXPERIMENT images and never publish." },
    h("ul", { class: "rows" }, (list || []).map((e) => h("li", { class: "row" },
      h("p", { class: "row-title" }, statusPill(e.inputs_verified ? "OK" : "BAD", e.inputs_verified ? "inputs verified" : "inputs drifted"), ` ${e.id}`),
      h("p", { class: "row-detail" }, `${e.model} ${e.size} · caps: generation CA$${e.generation_cap_cad}, vision CA$${e.vision_cap_cad} · retries ${e.max_retries}`),
      h("p", { class: "row-detail" }, e.authorization ? `Authorized ${e.authorization.auth_id} by ${e.authorization.authorized_by}` : "Not authorized"),
      h("div", { class: "row" },
        h("button", { class: "btn", type: "button", onclick: async () => {
          try { const r = await api.authorizeExperiment(e.id, {}); toast(`Authorized ${r.auth_id}`, "ok"); reload(); }
          catch (err) { toast(err.message, "bad"); }
        } }, "Authorize"),
        e.authorization ? h("button", { class: "btn btn-primary", type: "button", onclick: async () => {
          try { const r = await api.runExperiment(e.id); toast(r.duplicate ? `Already queued (run ${r.run_id})` : `Queued run ${r.run_id}`, "ok"); reload(); }
          catch (err) { toast(err.message, "bad"); }
        } }, "Run") : null),
      h("ul", null, (e.runs || []).map((r) => h("li", null, `run ${r.run_id} · ${r.status} `,
        h("button", { class: "btn", type: "button", onclick: async () => {
          try {
            const c = await api.experimentCard(r.run_id);
            clear(slot); slot.append(galleryCard(c, reload), experimentDetails(c));
          } catch (err) { toast(err.message, "bad"); }
        } }, "Open"))))))));
}

export async function render({ rerender } = {}) {
  const [board, wardrobe, exps] = await Promise.all([api.images(), api.wardrobe().catch(() => null),
    api.experiments().catch(() => null)]);
  const products = Array.isArray(board.products) ? board.products : [];
  const out = h("div", { aria: { live: "polite" } });
  const gallery = h("div", { aria: { live: "polite" } });
  const learn = board.learning || {};
  const listings = products.map((p) => p.listing);
  return h("div", { class: "stack" },
    card({ title: "Gallery production", subtitle: "Autonomous image production per product. You are notified only when a gallery is ready for review or blocked after its permitted attempts." },
      h("ul", { class: "rows" }, products.map((p) => runRow(p, rerender || (() => {}), gallery)))),
    gallery,
    exps ? experimentsCard(exps.experiments, gallery, rerender || (() => {})) : null,
    card({ title: "Learning", subtitle: "Per candidate outcomes. Cost per accepted image is Unknown until an image is accepted." },
      h("p", null, `Candidates: ${learn.candidates ?? "Unknown"} · accepted: ${learn.accepted ?? "Unknown"} · cost per accepted: ${learn.cost_per_accepted_cad == null ? "Unknown" : `CA$${learn.cost_per_accepted_cad}`}`),
      h("p", { class: "row-detail" }, Object.entries(learn.failure_categories || {}).map(([k, v]) => `${k}: ${v}`).join(" · ") || "No failures recorded.")),
    wardrobe ? wardrobeEditor(wardrobe, listings, rerender || (() => {})) : null,
    card({ title: "Submit an owner-made image (fallback)", subtitle: "Stored unchanged by sha256, labelled AI-generated (never a photograph), and checked by the same gates as autonomous images. Missing evidence stays Unknown." },
      uploadForm(products, out)),
    out);
}
