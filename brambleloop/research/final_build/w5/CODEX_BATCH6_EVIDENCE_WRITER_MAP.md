# Batch 6 evidence writer and action map

Audit aid for an isolated integration candidate, not evidence that a fence exists.
The successful safety preview is `6cb70e3a90ab4cc84f3ecd73f4fca570e48c1859`.
Additional paths below were inspected on A3 `c888769bb0a0003f97701c589a751052f90fb630`,
A6 `77d2d415e27f401e75a09e3704ca8f5138daa84f`, and A9
`e1974a6dae46e49099a8b56d32b3b8c2c8a3198f`. This is a minimum inventory,
not a claim that every writer has been found.

| Evidence / authority | Known producers and mutators | Consequential readers / actions | Unclosed boundary |
| --- | --- | --- | --- |
| Approved learning rule, scope, review and evaluation; frozen pin audit (`design_rules`, `design_evaluation_runs`, `audit_log`) | `improve/design_knowledge.py`: proposal, `freeze_pins`, `repin_revalidated_cir`, and review/retire/replace paths. Review uses SQLAlchemy Core `update(DesignRule)`, not just ORM flush. | `runtime/pipeline.py` `handle_certify`; `improve/knowledge_gate.py`; `runtime/quality_ops.py`; `visual/image_production.py`. | Certify checks authority in a separate session before persisting its release. The duplicate-certification early return also needs current authority. Same-version freeze history does not authenticate arbitrary new-version lineage. Mutable audit and provenance cannot authenticate themselves against an actor with authority to rewrite them. |
| Physical test and photo rights (`physical_tests`, `physical_photos`) | `quality/physical.py` records tests; `publish/physical_upgrade.py` ingests physical photos and changes frames. Existing rows may also be edited or deleted through SQL. | `publish/photo_asset_review.py`; `publish/release_gates.py`; `runtime/etsy_ops.py` `certified_frames`; `runtime/pipeline.py` certification and downstream consumption. | Locking existing rows alone misses insert phantoms, dependencies read in separate sessions, changes after commit, and external artifact bytes. |
| Gallery and listing certification (`listing_assets`, `listing_set_certificates`, `artefact_provenance`) | `publish/photo_asset_review.py`, `publish/physical_upgrade.py`, `publish/release_gates.py`, and `runtime/release.py` create, reorder, hold or approve records; `ops/artefacts.py` records provenance. | `runtime/etsy_ops.py` `certified_frames`; `commerce/deliverables.py`; PDF/visual/listing release consumers. | Sibling/order and provenance insertions must invalidate or be included in the current evidence snapshot. A database hash is not proof that external bytes still match it. |
| Product, CIR release, certificate and listing (`products`, `pattern_versions`, `listings`) | `runtime/pipeline.py`, `runtime/release.py`, `publish` and other producers. A9's `publish/listing_package_fence.py` listens to ORM `before_flush`; it expressly does not cover bulk/Core/raw SQL. | `publish/listing_package.py` and `runtime/listing_package_ops.py` build and record owner-review packages. | Any mutation must cover old and new identities, including deferred attributes, reassignment, deletes and inserts. Record-time validation does not protect an owner action after the transaction commits. |
| Owner authority and package state (`owner_actions`, `operating_readings`) | `publish/listing_package.py` records and invalidates package requests; queue and command-center code also maintain owner actions. | `build2.executor.approval_inbox` and `app/command_center/approvals.py`; downstream owner and publication actions. | Each consequential action must bind the actual authenticated owner decision to the current complete evidence, rather than treating an old request or `done` flag as current authority. |

## Contract and tests required before integration

* Transactionally bind the evidence identities, versions, content digests, authority and
  decision to an immutable protected audit record. Verify actor authority and separation;
  a caller-supplied hash or actor name alone is not authentication.
* Cover insert/update/delete through ORM, Core, bulk and raw SQL, including changes to both
  old and new scopes. PostgreSQL triggers with appropriately restricted roles are one
  possible enforcement point; privilege, trigger/migration integrity and legacy binaries
  must be addressed. Advisory locks or ORM callbacks alone do not cover uncooperative writers.
* Serialize the actual authorization recheck and consequential database write in the same
  transaction. Include missing rows and collection phantoms. Establish a global lock order
  or bounded retry on an entire fresh transaction; never silently accept exhausted retries.
* Revalidate at owner approval and at later consequential use. Invalidate stale outstanding
  and completed approvals as appropriate; fail closed on missing, revoked, unauthenticated or
  changed inputs. Irreversible remote side effects cannot be rolled back by a database lock:
  their in-flight revocation and recovery policy needs explicit design and authorization.
* Use real PostgreSQL interleavings for both lock orders, rollback, retries, source deletion,
  new phantom provenance, old/new identity changes, rule retirement during certification,
  stale-owner action, and SQLAlchemy Core/raw SQL. Verify no duplicate action after retry.
  Repeat required real-handler regressions on Python 3.11; SQLite alone is not concurrency
  evidence for PostgreSQL.

Until coverage and independent review are complete, A3, A6 and A9 continuation checkpoints
remain **do not integrate**. No owner approval, physical evidence, provider authority,
budget, publication or deployment permission is created by this map.
