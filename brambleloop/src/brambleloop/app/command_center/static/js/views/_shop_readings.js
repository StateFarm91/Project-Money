// W4-LISTREADY (review F7): the owner's dated Shop Manager readings that first-sale readiness
// needs and no Etsy API can see -- where buyer messages reach (messages) and identity
// verification plus the tax position (legal_and_tax). Owner session + step-up only
// (POST /api/cc/etsy/shop-observation); the server validates every value and records the
// signed-in owner as the one who read it. Nothing is written to Etsy.
import { h } from "../dom.js";
import { api } from "../api.js";
import { card, guardedAction, toast } from "../components.js";

function field(label, input) {
  return h("div", null, h("label", { class: "field", for: input.id }, label), input);
}

function messagesForm(reload) {
  const inbox = h("input", { id: "sr-inbox", type: "text", maxLength: 200, placeholder: "the address Etsy message notifications go to" });
  const hours = h("input", { id: "sr-hours", type: "number", min: 1, max: 168, step: 1, placeholder: "24" });
  const statement = h("input", { id: "sr-msg-statement", type: "text", maxLength: 500, placeholder: "e.g. Shop Manager > Settings > Emails, read on my phone" });
  const btn = h("button", { class: "btn btn-primary", type: "button", onclick: async () => {
    if (!inbox.value.trim() || !hours.value || !statement.value.trim()) { toast("Fill in all three fields.", "bad"); return; }
    const r = await guardedAction({ title: "Record the Messages reading?",
      lines: ["Saved as your dated, audited reading. Nothing is written to Etsy."],
      confirmLabel: "Record", requiresStepUp: true,
      run: () => api.recordShopObservation({ page: "messages", observed_at: new Date().toISOString(), complete: true,
        values: { notifications_inbox: inbox.value.trim(), reply_window_hours: Number(hours.value) },
        statement: statement.value.trim() }),
      success: "Messages reading recorded." });
    if (r) reload();
  } }, "Record Messages reading");
  return h("div", { class: "stack" }, h("h3", { class: "section-title" }, "Messages"),
    field("Notification inbox", inbox), field("Reply window (hours)", hours), field("How you read it", statement), btn);
}

function legalForm(reload) {
  const verified = h("select", { id: "sr-identity" },
    h("option", { value: "" }, "Choose…"), h("option", { value: "true" }, "Verified"), h("option", { value: "false" }, "Not verified"));
  const tax = h("input", { id: "sr-tax", type: "text", maxLength: 200, placeholder: "e.g. small supplier, no GST/HST number given to Etsy" });
  const decided = h("input", { id: "sr-decided", type: "date" });
  const statement = h("input", { id: "sr-legal-statement", type: "text", maxLength: 500, placeholder: "e.g. Shop Manager > Settings > Legal and tax, read on my phone" });
  const btn = h("button", { class: "btn btn-primary", type: "button", onclick: async () => {
    if (!verified.value || !tax.value.trim() || !decided.value || !statement.value.trim()) { toast("Fill in every field.", "bad"); return; }
    const r = await guardedAction({ title: "Record the Legal and tax reading?",
      lines: ["Saved as your dated, audited reading. Nothing is written to Etsy.",
        "Only a reading with identity verified, a stated tax position and its date closes the item."],
      confirmLabel: "Record", requiresStepUp: true,
      run: () => api.recordShopObservation({ page: "legal_and_tax", observed_at: new Date().toISOString(), complete: true,
        values: { identity_verified: verified.value === "true", tax_position: tax.value.trim(), decided_on: decided.value },
        statement: statement.value.trim() }),
      success: "Legal and tax reading recorded." });
    if (r) reload();
  } }, "Record Legal and tax reading");
  return h("div", { class: "stack" }, h("h3", { class: "section-title" }, "Legal and tax"),
    field("Identity verification", verified), field("Tax position", tax), field("Decided on", decided),
    field("How you read it", statement), btn);
}

// LAUNCHPREP E2: whether Policy settings has an editable delivery text box for this
// digital-only shop. "No box" is what lets a blank delivery policy read not applicable.
function deliveryForm(reload) {
  const box = h("select", { id: "sr-delivery-box" },
    h("option", { value: "" }, "Choose…"),
    h("option", { value: "false" }, "No box: only Etsy's fixed 'Instant downloads' policy"),
    h("option", { value: "true" }, "There is a delivery text box I can type in"));
  const statement = h("input", { id: "sr-delivery-statement", type: "text", maxLength: 500, placeholder: "e.g. Shop Manager > Settings > Policy settings, read on my phone" });
  const btn = h("button", { class: "btn btn-primary", type: "button", onclick: async () => {
    if (!box.value || !statement.value.trim()) { toast("Fill in both fields.", "bad"); return; }
    const r = await guardedAction({ title: "Record the Delivery policy reading?",
      lines: ["Saved as your dated, audited reading. Nothing is written to Etsy."],
      confirmLabel: "Record", requiresStepUp: true,
      run: () => api.recordShopObservation({ page: "delivery_policy", observed_at: new Date().toISOString(), complete: true,
        values: { editable_delivery_box: box.value === "true" }, statement: statement.value.trim() }),
      success: "Delivery policy reading recorded." });
    if (r) reload();
  } }, "Record Delivery policy reading");
  return h("div", { class: "stack" }, h("h3", { class: "section-title" }, "Delivery policy"),
    field("What Policy settings shows", box), field("How you read it", statement), btn);
}

export function shopReadingsCard(rerender, { labelId = "completion-shop-readings" } = {}) {
  const reload = rerender || (() => {});
  return card({ title: "Shop Manager readings", labelId,
    subtitle: "First-sale items only you can read on Etsy. Step-up required; the server checks every value." },
    messagesForm(reload), legalForm(reload), deliveryForm(reload));
}
