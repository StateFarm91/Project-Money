"""D-ENG-BFL-REGIONAL-HOST: BFL calls go to a regional host, and only to a BFL API host.

The owner's new-format key was refused by the global host (422 "Invalid API key format") and
accepted by api.us.bfl.ai. Every BFL request URL is built through flux_contract.bfl_url.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.gateway import credentials, flux_contract as F, images  # noqa: E402


def test_default_is_the_us_region():
    assert F.bfl_host({}) == "https://api.us.bfl.ai"
    assert F.ENDPOINT == "https://api.us.bfl.ai/v1/flux-3-image"
    assert F.bfl_url("https://api.bfl.ai/v1/credits", {}) == "https://api.us.bfl.ai/v1/credits"


def test_override_only_to_a_bfl_api_host():
    assert F.bfl_host({F.HOST_ENV_VAR: "api.eu.bfl.ai"}) == "https://api.eu.bfl.ai"
    assert F.bfl_host({F.HOST_ENV_VAR: "https://api.bfl.ai/"}) == "https://api.bfl.ai"
    for bad in ("evil.example.com", "api.bfl.ai.evil.com", "delivery.eu.bfl.ai", " ", "x"):
        assert F.bfl_host({F.HOST_ENV_VAR: bad}) == "https://api.us.bfl.ai", bad


def test_non_bfl_urls_are_never_rewritten():
    for url in ("https://api.openai.com/v1/images/generations",
                "https://delivery.eu.bfl.ai/x.png", "https://api.bfl.ai.evil.com/v1/x"):
        assert F.bfl_url(url, {F.HOST_ENV_VAR: "api.eu.bfl.ai"}) == url


def test_credentials_check_uses_the_chosen_host():
    seen = {}

    def http(method, url, headers, body, timeout):
        seen["url"], seen["headers"] = url, headers
        return 200, '{"credits": 738.6}'

    out = credentials.check_bfl({"BRAMBLELOOP_IMAGE_KEY_BFL": "k", F.HOST_ENV_VAR: "api.eu.bfl.ai"},
                                http=http)
    assert seen["url"] == "https://api.eu.bfl.ai/v1/credits" and seen["headers"]["x-key"] == "k"
    assert out["status"] == credentials.OK, out


def test_every_bfl_provider_endpoint_is_regional():
    for p in images.PROVIDERS:
        if p.dialect in ("bfl", "bfl3"):
            assert p.endpoint.startswith("https://api.us.bfl.ai/"), p.endpoint


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("OK")
