"""Certification C-3 remainder and C-54: no paid provider is reachable outside a ceiling.

The spend-path scanner in test_model_spend_paths looks for client method calls. A module that
builds an HTTP request to a provider host by hand is invisible to it -- visual/d_judge.py did
exactly that, with no ceiling in code. These tests pin every file that addresses a paid
provider host, and prove the one outside the gateway refuses before any request is built.
"""
from __future__ import annotations

import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from brambleloop.visual import d_judge  # noqa: E402

PAID_HOSTS = re.compile(
    r"api\.openai\.com|api\.anthropic\.com|generativelanguage\.googleapis\.com|api\.bfl\.ai"
    r"|volces\.com|fal\.run|api\.replicate\.com|api\.stability\.ai")

# Each file allowed to address a paid provider, and what holds its ceiling. A new file here is
# a decision about spend, made in review, not a refactor.
DECLARED = {
    "brambleloop/gateway/images.py": "images.generate reserves via check_budget_cad first",
    "brambleloop/gateway/anthropic.py": "the model gateway checks check_budget_cad first",
    "brambleloop/visual/d_judge.py": "research judge: refuses without an operator cap (C-54)",
    # Reviewed 2026-10-07 (W4-SPENDA F-106/F-103): GET-only reads of the providers' own
    # cost-report endpoints, refused without an owner-supplied admin key; no billable call.
    "brambleloop/ops/provider_accounts.py": "read-only billing settlement: GET cost reports, "
                                            "refuses with no admin key",
}


def test_every_file_addressing_a_paid_provider_is_declared():
    found = set()
    for base, _dirs, files in os.walk(SRC):
        for name in files:
            if name.endswith(".py"):
                path = Path(base) / name
                if PAID_HOSTS.search(path.read_text(encoding="utf-8")):
                    found.add(str(path.relative_to(SRC)))
    assert found <= set(DECLARED), f"undeclared paid-provider callers: {sorted(found - set(DECLARED))}"


def test_the_scan_would_see_a_new_one():
    assert PAID_HOSTS.search('urllib.request.Request("https://api.openai.com/v1/images")')


def _no_network(*a, **k):
    raise AssertionError("a request was attempted")


def test_the_research_judge_refuses_with_no_cap_before_any_request(tmp_path=None):
    real = urllib.request.urlopen
    urllib.request.urlopen = _no_network
    old = os.environ.pop("BRAMBLELOOP_RESEARCH_JUDGE_CAP_USD", None)
    try:
        for bad in (None, "", "0", "-1", "nan", "lots"):
            if bad is None:
                os.environ.pop("BRAMBLELOOP_RESEARCH_JUDGE_CAP_USD", None)
            else:
                os.environ["BRAMBLELOOP_RESEARCH_JUDGE_CAP_USD"] = bad
            try:
                d_judge.see(str(ROOT / "does-not-matter.png"))
            except d_judge.JudgeSpendRefused as e:
                assert "refused before the call" in str(e)
            else:
                raise AssertionError(f"cap {bad!r} was accepted")
    finally:
        urllib.request.urlopen = real
        os.environ.pop("BRAMBLELOOP_RESEARCH_JUDGE_CAP_USD", None)
        if old is not None:
            os.environ["BRAMBLELOOP_RESEARCH_JUDGE_CAP_USD"] = old


def test_the_research_judge_refuses_a_call_whose_worst_case_passes_the_cap():
    real = urllib.request.urlopen
    urllib.request.urlopen = _no_network
    before = d_judge._spent_usd
    try:
        os.environ["BRAMBLELOOP_RESEARCH_JUDGE_CAP_USD"] = "1.00"
        d_judge._spent_usd = 1.00 - d_judge._worst_case_usd() / 2
        try:
            d_judge.see(str(ROOT / "does-not-matter.png"))
        except d_judge.JudgeSpendRefused as e:
            assert "would pass" in str(e)
        else:
            raise AssertionError("a call past the cap was allowed")
    finally:
        d_judge._spent_usd = before
        urllib.request.urlopen = real
        os.environ.pop("BRAMBLELOOP_RESEARCH_JUDGE_CAP_USD", None)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
