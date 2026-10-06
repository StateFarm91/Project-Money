#!/bin/sh
cd "$(dirname "$0")" && PYTHONPATH=../../../src /home/user/Project-Money/brambleloop/.venv/bin/python -W ignore "$@" 2>&1
