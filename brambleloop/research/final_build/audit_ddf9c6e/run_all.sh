#!/bin/sh
# Re-runs every finance-lane repro. cd brambleloop/research/final_build/audit_ddf9c6e && sh run_all.sh
for p in p0*.py p1*.py p2*.py; do echo "=== $p"; PYTHONPATH=../../../src ../../../../.venv/bin/python $p 2>&1 | tail -25; done
