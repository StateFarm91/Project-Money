# Physical yarn-colour completeness

Stacked on `codex/physical-numeric-input-validation` at `2a9ce57`. The physical sample assessment compared only the intersection of estimated and recorded yarn colours. A synthetic two-colour full-make could pass with one colour's mass omitted and could be used to calibrate.

The assessment now fails without a positive reported measurement for each colour the sampled components are estimated to use, and does not compute a calibration factor for that incomplete record. It leaves the existing per-component estimator in charge of which colours apply; swatch scope continues to use its distinct gauge path. Unknown extra colours remain errors. This does not establish the accuracy or provenance of the estimate or authenticate the physical observation, and an incorrectly estimated component colour can cause a conservative hold.

Synthetic tests exercise the actual `physical.record` Worker for missing, zero and complete colour inputs, check failed evidence cannot calibrate, and grant no real tester authority or physical evidence. Independent reviewer reran focused tests 3/3. PostgreSQL, evidence fencing, integrator review and production verification remain open. No purchase, deployment, publication or real physical sample was created.
