# W-AGENTS: the Storefront Director, as an operational agent

Branch `claude/w4-AGENTS`, cut from `origin/claude/final-candidate-b997efd` (f19b264e line). Date 2026-10-21 (UTC).
No deploys, no Etsy calls or writes, no spend. Audit input: `AGENT_AUDIT.md` (3546be8).

## 1. Requirement trace

Sources:
- the Master Plan v1.2 (`spec/01_*.pdf`, extracted with pdftotext);
- the FINAL Master v1.0 F-rows (`research/final_build/master_registry.json`) and the v1.1 rows (`master_registry_v1_1.json`);
- the Build 2 ledger (`src/brambleloop/build2/requirements.json`).

The board status is taken from `build2/final_master_closure.json` (completion/maturity).

### Rows that name the roles

| Row | Acceptance criterion (abridged) | Board | What the audit found exists |
|---|---|---|---|
| MP v1.2 §6 | "Storefront Director owns banner, icon, About, policies, sections, announcement, thumbnails and grid coherence." | (spec, no F-id) | No agent. `brand/storefront.py` is a static copy library. |
| MP v1.2 §16 | Org: Creative (Creative Director, Collection Architect, category specialists); Brand/Publishing (**Storefront Director**, Brand Model Consistency, PDF/Charts, Visual Director, Asset Truth, Listing, Thumbnail Warfare, Etsy SEO); Commercial/Growth (Promotion, Pinterest, Social, Email, SEO, Video, Attribution…) | (spec) | Creative: `creative_director`, `crochet_engineer`. Storefront Director, Branding and Marketing: none. Growth: `growth` and `ads`. |
| F-454 | Department agents, including SEO/Marketing | POST-LAUNCH / DEPLOYED | registry only |
| F-890 (v1.1) | 24/7 department agents, including Store/Commerce and Growth/Marketing | COMPLETE / INTEGRATED | charters exist; no storefront agent |
| F-892 (v1.1) | Role charters: no silent authority expansion | COMPLETE / INTEGRATED | `autonomy/charters.py` |
| F-601 | Permanent AI company, with Visual/Creative and Marketing/Growth departments | POST-LAUNCH / INTEGRATED | charters |
| F-613 | Marketing & Growth Department | POST-LAUNCH / INTEGRATED | growth agent; `content.draft` has no handler |
| F-737, F-745 | "Visual/Brand agents" improve the canonical model | POST-LAUNCH / DEPLOYED | under `creative_director` / `publishing` |
| F-799, F-828 | Learn/Content department; Marketing/SEO packages discovery | COMPLETE / POST-LAUNCH | learn agent |
| B2 #76 | The Creative Director maintains the benchmark set | covered | `intel/benchmark_set.py` |

### Storefront surface rows (owned by the Storefront Director per §6)

| Row | Criterion | Board | Exists |
|---|---|---|---|
| F-233 | Storefront Completion Gate: icon, banner, title, announcement, About, policies/FAQ, identity, sections, featured | COMPLETE / INTEGRATED | the check exists (`brand/storefront.check_storefront`); no agent fills the gaps |
| F-239 | Mobile Storefront QA | GATED / MISSING | none (no browser worker) |
| F-241 / B2 #131 | Seasonal Storefront Takeover, with start/revert | COMPLETE / INTEGRATED | planner only; there is no write path |
| F-279 | Storefront-to-listing continuity | COMPLETE / INTEGRATED | seasonal/daily.py |
| F-293 | Storefront Visual Inspection | GATED / MISSING | none |
| F-515 | Shop Completeness Gate, checked continuously | GATED / DEPLOYED | check only |
| F-502 | Storefront Continuous Optimization | POST-LAUNCH / INTEGRATED | growth_ops (listings) |
| F-526 | Shop Home Merchandising (sections, featured) | POST-LAUNCH / INTEGRATED | static SECTIONS; no section writes |
| F-527 | Brand Asset Health, routing fixes to Brand/Visual | POST-LAUNCH / DEPLOYED | static |
| F-584 | Shop Appearance Optimizer: announcement, title, About… | POST-LAUNCH / INTEGRATED | static |
| F-597 | Storefront Change Budget | POST-LAUNCH / none | none |
| F-814 | Content Constellation | POST-LAUNCH / INTEGRATED | `growth/content.py` via `marketing.schedule` |

**Conclusion.** The authorised work in priority order is:
1. Implement the §6/§16 Storefront Director as a registered agent, inside the existing `store_commerce` charter (no new department: the charters fix eleven).
2. Make it read, evaluate and draft continuously (F-233/F-515/F-584/F-526), as proposals.
3. Give its proposals a gated write path, which is the only change to Etsy authority. It is refused in SHADOW and without an owner grant.
4. Let Laura delegate to it.

Branding and Marketing as *separate* agents are **not** authorised by any row: §16 puts storefront and brand under Brand/Publishing, and F-613 puts marketing under the existing Growth department. Inventing them would be a new workforce architecture, which the owner directive forbids.
