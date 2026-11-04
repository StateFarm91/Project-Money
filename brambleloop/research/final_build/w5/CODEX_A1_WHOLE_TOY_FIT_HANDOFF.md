# A1 whole-toy fit hold

Based on `codex/a1-detachable-part-aliases` at `7e54c33`; preserve its preceding safety changes when integrating. `CHILDRENS_CATEGORY.md` §2.2 explicitly includes whole toys in the small-parts assessment for products intended for children under three. The previous gate inspected cross-component assembly only, allowing a single-piece toy through without any whole-object assessment.

An assigned `amigurumi_toy` for `UNDER_3` now receives a small-parts hold even without cross-component assembly. The existing part holds are unchanged. No approved content-bound physical-fit authority exists, so the hold intentionally includes large and otherwise legitimate single-piece toys. It must not be interpreted as a physical test, clearance, or owner approval. This narrow change does not address other toy subcategories, missing/wrong audience assignments, other delivery paths, authority fencing or PostgreSQL concurrency. Adult and non-toy audience classification is unchanged. Compose with the newer version/digest-bound ChildrensDecisionRequired handling before integration.

The focused test uses a synthetic assignment and exact digest solely to reach the actual PDF/worker gate, verifies durable hold and no PDF, and checks the direct gate for other audience/category combinations. No production purchase, publication or deployment took place.
