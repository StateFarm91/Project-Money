# Operating-cost truth handoff
Base a4c79ed (AB included), implementation c9e038c. Root integrator reviews/cherry-picks.
Modelled listing exposure is persisted before effect and deduplicated by listing under local DB
accounting locks. Actual payment listing rows persist by external ID and replace model in Books.
Books emits explicit basis and UNKNOWN cash for modelled/unknown inputs. No thresholds changed.
Tests5+21+18+1 pass; no production or provider spend. See report.json for exact proof and limits.
Next root: integrate after AB, inspect dashboard nullable cash handling, run affected broad suites;
audit other cost consumers separately. Postgres concurrency and real Etsy feed remain unverified.
H blocked WIP unchanged; frozen Visual V2 untouched. No certification/status changes.

Follow-up: post-reservation authority/gates revalidated; adversarial suite now6/6.
Downstream cost-label audit proposed to coordinator; no consumer edits yet.
