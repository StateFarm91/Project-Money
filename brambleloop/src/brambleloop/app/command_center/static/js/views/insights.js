// INSIGHTS: SEO (G), ads readiness (H), experiments, lessons, intelligence.
import { h } from "../dom.js";
import { api } from "../api.js";
import { pageMeta, renderAll } from "./_shared.js";

const ORDER = [["intel", "Market intelligence"], ["seo", "Search & keywords"], ["ads", "Ads readiness & economics"],
  ["experiments", "Experiments"], ["lessons", "Lessons"], ["improvements", "Improvements"]];

export async function render() {
  const result = await api.insights();
  const data = result.data || {};
  return h("div", { class: "stack" }, ...pageMeta(result, data),
    ...renderAll(data, ORDER, { result, required: ["seo", "ads"] }));
}
