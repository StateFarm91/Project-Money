# SOURCE INVENTORY AND SHARED-FILE MAP

Authoritative reviewed checkpoint: `0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56` on `claude/visual-investigation`. These source URLs are pinned, not live branch references. Local Codex application checkout remains the older `8877f054c6a031e0cb991873e9ecdd575f2d8da4`; it was not updated or used as the repair-wave truth. Six candidate series start at `9d6eed2`; current checkpoint includes `b90e7e1` C-73 fixes. All six agent snapshots were still unfinished with no final per-row reports.

## Authority and audit inputs

- [brambleloop/research/b2_resume/RESUME_MANIFEST.md](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/RESUME_MANIFEST.md)
- [brambleloop/research/b2_resume/closure_state.json](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/closure_state.json)
- [brambleloop/research/BUILD2_CERTIFICATION.md](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/BUILD2_CERTIFICATION.md)
- [brambleloop/src/brambleloop/build2/requirements.json](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/build2/requirements.json)
- [brambleloop/research/b2_resume/final_audit_9434c53.json](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/final_audit_9434c53.json)
- [brambleloop/research/b2_resume/reopen_prev.json](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/reopen_prev.json)
- [brambleloop/research/b2_resume/wave_brief.md](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/wave_brief.md)

## platform

[Patch series](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox); [brief](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/wave_platform.md); [saved status](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.status.txt).

```text
d06928893f4615623023f1708c208e708cb686cb
02cc3a15bb42c3e6f2b2768f0db6162890e27e85
2c20df59235125da31950c110bb1b170b2b1e236
81ece066a2ceb921ecff921c42aa0be1c0c14960
0006b991ceabf3978e33483e67a2e047ad9b506b
253e71701c2c06a5ddd3db53419fd115768d53d5
```

Changed paths:

- `brambleloop/src/brambleloop/build2/closure.py`
- `brambleloop/src/brambleloop/build2/reachability.py`
- `brambleloop/tests/test_closure.py`
- `brambleloop/tests/test_reachability.py`
- `brambleloop/src/brambleloop/app/runner.py`
- `brambleloop/src/brambleloop/commerce/lanes.py`
- `brambleloop/src/brambleloop/finance/governor.py`
- `brambleloop/src/brambleloop/runtime/release.py`
- `brambleloop/src/brambleloop/swarm/capacity.py`
- `brambleloop/src/brambleloop/swarm/orchestrate.py`
- `brambleloop/tests/test_cert_lanes_capacity.py`
- `brambleloop/src/brambleloop/runtime/pipeline.py`
- `brambleloop/tests/test_cert_rebuild_chain.py`
- `brambleloop/src/brambleloop/teardown/lab.py`
- `brambleloop/src/brambleloop/teardown/scorecard.py`
- `brambleloop/tests/test_cert_culture_teardown.py`
- `brambleloop/tests/test_cert_unique_value.py`
- `brambleloop/src/brambleloop/visual/gallery.py`
- `brambleloop/src/brambleloop/visual/parity.py`
- `brambleloop/tests/test_gallery_escalation.py`
- `brambleloop/src/brambleloop/launch/readiness.py`
- `brambleloop/src/brambleloop/publish/layout_qa.py`
- `brambleloop/src/brambleloop/publish/listing_assets.py`
- `brambleloop/src/brambleloop/queue/durable.py`
- `brambleloop/src/brambleloop/runtime/worker.py`
- `brambleloop/src/brambleloop/visual/inspect.py`
- `brambleloop/tests/test_cert_listing_frames.py`

platform.uncommitted.diff changes orchestrate; platform_untracked/test_cert_thrash.py is separately preserved and currently endorses increasing backoff on a sweep without a new poll.

## orders

[Patch series](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox); [brief](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/wave_orders.md); [saved status](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.status.txt).

```text
0f50457f2e0f3019714f44bd59d8375dd5d7b1f6
8837c2fb864c8f4c4e03ea924f7841d1ca53ff7a
```

Changed paths:

- `brambleloop/src/brambleloop/agents/registry.py`
- `brambleloop/src/brambleloop/app/main.py`
- `brambleloop/src/brambleloop/commerce/buyer_trust.py`
- `brambleloop/src/brambleloop/commerce/cohorts.py`
- `brambleloop/src/brambleloop/commerce/order_readings.py`
- `brambleloop/src/brambleloop/commerce/orders_ingest.py`
- `brambleloop/src/brambleloop/commerce/pricing.py`
- `brambleloop/src/brambleloop/commerce/referral.py`
- `brambleloop/src/brambleloop/core/models.py`
- `brambleloop/src/brambleloop/creative/ideation.py`
- `brambleloop/src/brambleloop/creative/standard.py`
- `brambleloop/src/brambleloop/growth/loops.py`
- `brambleloop/src/brambleloop/integrations/etsy.py`
- `brambleloop/src/brambleloop/runtime/commerce_readings.py`
- `brambleloop/src/brambleloop/runtime/orders.py`
- `brambleloop/src/brambleloop/runtime/pipeline.py`
- `brambleloop/src/brambleloop/runtime/release.py`
- `brambleloop/src/brambleloop/runtime/worker.py`
- `brambleloop/src/brambleloop/scale/trajectory.py`
- `brambleloop/src/brambleloop/swarm/orchestrate.py`
- `brambleloop/tests/test_cert_orders.py`

No saved uncommitted changes.

## growth

[Patch series](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox); [brief](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/wave_growth.md); [saved status](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.status.txt).

```text
120813c17a5c609d0dff44e7bcbf539f834659f3
c211c919a5c4ac161fff12491ba36abb33043c9b
b2726239ba1866cf86d596b1004831f468db883f
2d3d6857dde7170795c7e38b0129d8ea2681df6b
175633f7c97f33562590ffd79df5ad3839be3b9d
072e8e574d6ef6cd1b60d7fdabbedc3c03d06c08
```

Changed paths:

- `brambleloop/src/brambleloop/app/main.py`
- `brambleloop/src/brambleloop/growth/weekly.py`
- `brambleloop/src/brambleloop/runtime/release.py`
- `brambleloop/src/brambleloop/scale/confidence.py`
- `brambleloop/src/brambleloop/scale/evidence.py`
- `brambleloop/src/brambleloop/runtime/commerce_readings.py`
- `brambleloop/src/brambleloop/support/service.py`
- `brambleloop/src/brambleloop/agents/registry.py`
- `brambleloop/src/brambleloop/ops/retention.py`
- `brambleloop/src/brambleloop/runtime/growth_ops.py`
- `brambleloop/src/brambleloop/runtime/pipeline.py`
- `brambleloop/src/brambleloop/runtime/worker.py`
- `brambleloop/src/brambleloop/swarm/orchestrate.py`
- `brambleloop/src/brambleloop/scale/war_room.py`
- `brambleloop/tests/test_cert_growth_ops.py`
- `brambleloop/tests/test_roles.py`

No saved uncommitted changes. Removing ads types from missing-handler tests is legitimate registration repair, not evidence of campaign execution.

## design

[Patch series](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/design.mbox); [brief](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/wave_design.md); [saved status](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/design.status.txt).

```text
7c3ad9d5f900e4e5019e88141b507c19c4eadd00
6df21318e9bcae5d1ec937a29e15480d194d53b1
7195d265da682396682973a6d2ac6e315424f826
```

Changed paths:

- `brambleloop/src/brambleloop/creative/ideation.py`
- `brambleloop/src/brambleloop/creative/intake.py`
- `brambleloop/src/brambleloop/creative/preengineering.py`
- `brambleloop/src/brambleloop/creative/prospecting.py`
- `brambleloop/src/brambleloop/runtime/pipeline.py`
- `brambleloop/src/brambleloop/runtime/release.py`
- `brambleloop/tests/test_cert_ideation.py`
- `brambleloop/tests/test_cert_preengineering.py`
- `brambleloop/src/brambleloop/app/main.py`
- `brambleloop/src/brambleloop/commerce/intent.py`
- `brambleloop/src/brambleloop/improve/roi.py`
- `brambleloop/src/brambleloop/intel/mission.py`
- `brambleloop/src/brambleloop/intel/mission_runtime.py`
- `brambleloop/src/brambleloop/intel/observe.py`
- `brambleloop/src/brambleloop/publish/release_gates.py`
- `brambleloop/src/brambleloop/seasonal/leadtime.py`
- `brambleloop/src/brambleloop/ops/retention.py`
- `brambleloop/tests/test_cert_design_pipeline.py`

No saved uncommitted changes. Intel supplies some prerequisites later; rerun complete Design trace after Intel without substituting its swatch/rarity proxies.

## improve

[Patch series](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox); [brief](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/wave_improve.md); [saved status](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.status.txt).

```text
0f76cf247383e9308cb48c1d469227136496ce4e
3682e969254fa15ebdb4d9e1b9995773499b30ba
d06802e745e245eccdbe2ac88b50ea26a97cf50d
9a2ee67c405dbf9d9b56407c02512ba1f6b20652
```

Changed paths:

- `brambleloop/src/brambleloop/agents/registry.py`
- `brambleloop/src/brambleloop/app/main.py`
- `brambleloop/src/brambleloop/core/models.py`
- `brambleloop/src/brambleloop/improve/cells.py`
- `brambleloop/src/brambleloop/improve/league.py`
- `brambleloop/src/brambleloop/improve/replay.py`
- `brambleloop/src/brambleloop/improve/roi.py`
- `brambleloop/src/brambleloop/improve/runner.py`
- `brambleloop/src/brambleloop/intel/mission_runtime.py`
- `brambleloop/src/brambleloop/publish/release_gates.py`
- `brambleloop/src/brambleloop/queue/durable.py`
- `brambleloop/src/brambleloop/runtime/pipeline.py`
- `brambleloop/src/brambleloop/runtime/release.py`
- `brambleloop/src/brambleloop/runtime/worker.py`
- `brambleloop/src/brambleloop/swarm/orchestrate.py`
- `brambleloop/src/brambleloop/teardown/audits.py`
- `brambleloop/src/brambleloop/teardown/enforce.py`
- `brambleloop/src/brambleloop/teardown/lab.py`
- `brambleloop/src/brambleloop/teardown/pipeline.py`
- `brambleloop/src/brambleloop/teardown/scorecard.py`
- `brambleloop/tests/test_cert_improve_wave.py`
- `brambleloop/src/brambleloop/creative/ideation.py`
- `brambleloop/src/brambleloop/creative/standard.py`
- `brambleloop/src/brambleloop/culture/radar.py`
- `brambleloop/src/brambleloop/growth/mix.py`
- `brambleloop/src/brambleloop/improve/consume.py`
- `brambleloop/src/brambleloop/improve/evolution.py`
- `brambleloop/src/brambleloop/improve/roles.py`
- `brambleloop/src/brambleloop/improve/bootstrap.py`
- `brambleloop/src/brambleloop/ops/retention.py`
- `brambleloop/tests/test_swarm_runtime.py`

improve.uncommitted.diff edits test_cert_wiring. Preserve C-73 no-spin/disclosure semantics; do not reintroduce obsolete waiting-priority behavior.

## intel

[Patch series](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox); [brief](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/wave_intel.md); [saved status](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.status.txt).

```text
78ef13457b4bf05b535cc65678046ac57171e374
1d454356b093e6c92bd56af5dd2b14564d312503
cd8af208cc468cc1b1d837ad93e9ee87c884515e
abd473b62d2bba30077c8eee101dee0a9d42757d
ac5c10ab8cc8505cadb5ccc4cc8e74fe8a781056
fc8f8ba83008d7729d3a72a365bd480dde1ee7ac
e71882b31a67e03b746a34f2ce6b9d658ec20a51
3e42d6b11769af54a4d498d082257389659ad02a
883697edb928ffe0b96b54346435737f2adc7c33
```

Changed paths:

- `brambleloop/src/brambleloop/intel/mission_runtime.py`
- `brambleloop/src/brambleloop/runtime/release.py`
- `brambleloop/src/brambleloop/agents/registry.py`
- `brambleloop/src/brambleloop/build2/executor.py`
- `brambleloop/src/brambleloop/commerce/markets.py`
- `brambleloop/src/brambleloop/core/models.py`
- `brambleloop/src/brambleloop/creative/prospecting.py`
- `brambleloop/src/brambleloop/intel/benchmarks.py`
- `brambleloop/src/brambleloop/intel/etsy_public.py`
- `brambleloop/src/brambleloop/intel/observe.py`
- `brambleloop/src/brambleloop/intel/panel_discovery.py`
- `brambleloop/src/brambleloop/intel/serp.py`
- `brambleloop/src/brambleloop/radar/arbitrage.py`
- `brambleloop/src/brambleloop/runtime/pipeline.py`
- `brambleloop/src/brambleloop/runtime/worker.py`
- `brambleloop/src/brambleloop/swarm/orchestrate.py`
- `brambleloop/src/brambleloop/intel/benchmark_refresh.py`
- `brambleloop/tests/test_cert_intel_wave.py`
- `brambleloop/src/brambleloop/gates/platform_policy.py`
- `brambleloop/src/brambleloop/publish/release_gates.py`
- `brambleloop/tests/test_executor.py`
- `brambleloop/src/brambleloop/app/main.py`
- `brambleloop/src/brambleloop/creative/board.py`
- `brambleloop/src/brambleloop/creative/preengineering.py`
- `brambleloop/src/brambleloop/creative/strength.py`
- `brambleloop/src/brambleloop/publish/physical_upgrade.py`
- `brambleloop/src/brambleloop/culture/engine.py`
- `brambleloop/src/brambleloop/seasonal/benchmark_matrix.py`
- `brambleloop/src/brambleloop/seasonal/daily.py`
- `brambleloop/tests/test_cert_growth_seasonal.py`
- `brambleloop/src/brambleloop/ops/retention.py`
- `brambleloop/src/brambleloop/publish/model_photography.py`
- `brambleloop/src/brambleloop/visual/drift_series.py`
- `brambleloop/src/brambleloop/creative/ideation.py`
- `brambleloop/src/brambleloop/creative/reference.py`
- `brambleloop/src/brambleloop/launch/access.py`
- `brambleloop/tests/test_cert_intel_wave2.py`

No saved uncommitted changes. Keep genuine image_vision/model_bearing_render/owner/data boundaries; no physical/visual evidence can be fabricated to close them.

## Shared files (exact preserved overlap)

| Path | Clusters |
|---|---|
| `brambleloop/src/brambleloop/runtime/release.py` | platform, orders, growth, design, improve, intel |
| `brambleloop/src/brambleloop/swarm/orchestrate.py` | platform, orders, growth, improve, intel |
| `brambleloop/src/brambleloop/runtime/pipeline.py` | platform, orders, growth, design, improve, intel |
| `brambleloop/src/brambleloop/teardown/lab.py` | platform, improve |
| `brambleloop/src/brambleloop/teardown/scorecard.py` | platform, improve |
| `brambleloop/src/brambleloop/queue/durable.py` | platform, improve |
| `brambleloop/src/brambleloop/runtime/worker.py` | platform, orders, growth, improve, intel |
| `brambleloop/src/brambleloop/agents/registry.py` | orders, growth, improve, intel |
| `brambleloop/src/brambleloop/app/main.py` | orders, growth, design, improve, intel |
| `brambleloop/src/brambleloop/core/models.py` | orders, improve, intel |
| `brambleloop/src/brambleloop/creative/ideation.py` | orders, design, improve, intel |
| `brambleloop/src/brambleloop/creative/standard.py` | orders, improve |
| `brambleloop/src/brambleloop/runtime/commerce_readings.py` | orders, growth |
| `brambleloop/src/brambleloop/ops/retention.py` | growth, design, improve, intel |
| `brambleloop/src/brambleloop/creative/preengineering.py` | design, intel |
| `brambleloop/src/brambleloop/creative/prospecting.py` | design, intel |
| `brambleloop/src/brambleloop/improve/roi.py` | design, improve |
| `brambleloop/src/brambleloop/intel/mission_runtime.py` | design, improve, intel |
| `brambleloop/src/brambleloop/intel/observe.py` | design, intel |
| `brambleloop/src/brambleloop/publish/release_gates.py` | design, improve, intel |

## Additional preserved work

- [platform.uncommitted.diff](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.uncommitted.diff)
- [improve.uncommitted.diff](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.uncommitted.diff)
- [platform_untracked/test_cert_thrash.py](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform_untracked/test_cert_thrash.py)

Do not treat these uncommitted changes as included in mbox heads. No copies of agent source were applied locally. Function evidence in FINDINGS links to exact pinned mbox line or baseline definition; added code need not exist as source on the checkpoint tree.
