# Reverify publication name and audience truth

Stacked on quality hold-before-incident PR #108 (`2339771`). The actual daily asset-truth Worker previously did not call the existing publication `eligibility.name_truth` gate. A synthetic adult-exempt ring pillow listing with a child-directed tag passed quality re-verification even though that publication gate required a child assignment.

The recheck now reuses the existing name-truth gate for stored listing copy, including the gate's child-audience, count, assembly and applicable fabric/name checks. Its existing quality hold and recovery workflow applies to those findings. It creates no audience assignment, owner decision or physical evidence. The complete gate may conservatively hold other cases already refused at publication; finite language coverage and concurrent listing/evidence changes remain open.

Python 3.11 tmpfs SQLite quality/withholding/actual Worker regression passed 32/32; independent reviewer reran the focused Worker case 1/1. Tests use synthetic release/listing records. No purchase, publication, deployment, PostgreSQL test or production acceptance occurred. Integrators must preserve other A1/A2 and shared evidence-contract work.
