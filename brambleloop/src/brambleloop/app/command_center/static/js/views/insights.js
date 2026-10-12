// INSIGHTS: SEO (G), ads readiness (H), experiments, lessons, intelligence.
import { h } from "../dom.js";
import { api } from "../api.js";
import { pageMeta, renderAll } from "./_shared.js";

const ORDER = [["marketing_customers", "Marketing & customers"],
  // W4-CCMKTLAB (F-684): each channel and experiment with hypothesis, baseline, budget,
  // attribution and stop/scale rules.
  ["marketing_lab_channels", "Marketing lab: channels"], ["marketing_lab_experiments", "Marketing lab: experiments"],
  ["intel", "Market intelligence"], ["seo", "Search & keywords"], ["ads", "Ads readiness & economics"],
  ["experiments", "Experiments"], ["lessons", "Lessons"], ["improvements", "Improvements"],
  // W4-CCFM1 (F-619): customers, aggregates only (no buyer names or messages).
  ["customer_orders", "Customers: orders"], ["customer_support", "Customers: support"], ["customer_reviews", "Customers: reviews"]];

export async function render() {
  const result = await api.insights();
  const data = result.data || {};
  return h("div", { class: "stack" }, ...pageMeta(result, data),
    ...renderAll(data, ORDER, { result, required: ["seo", "ads"] }));
}
