"""D-ENG-OWNER-GRANT-DERIVED-KEY: production had no explicit owner-grant key pair, so every
owner press that signs a publication or activation grant raised "signing key unavailable".

Mode S (embedded worker, one service) now derives the pair from BRAMBLELOOP_SECRET_KEY with
HKDF. Mode T never derives. A job process still never signs, and a grant is still signed only
inside the owner's request.
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from brambleloop.core import owner_grant_keys as ogk  # noqa: E402

SECRET = "s" * 48
BASE = {k: v for k, v in os.environ.items()
        if k not in (ogk.SIGNING_KEY_VAR, ogk.VERIFY_KEY_VAR, ogk.SECRET_VAR, ogk.EMBEDDED_VAR)}
DETAIL = {"approval_id": "a1", "principal": "owner", "event": "owner.publication.approved"}


def _env(**extra):
    env = dict(BASE)
    env.update(extra)
    return env


def test_missing_keys_without_secret_still_refuses_clearly():
    with patch.dict(os.environ, _env(), clear=True), ogk.owner_request("sess"):
        assert ogk.key_source() == "absent"
        try:
            ogk.sign("d", DETAIL)
        except ValueError as exc:
            assert "signing key unavailable" in str(exc)
        else:
            raise AssertionError("signed with no key material")


def test_mode_s_derives_a_working_pair():
    with patch.dict(os.environ, _env(**{ogk.SECRET_VAR: SECRET}), clear=True):
        assert ogk.key_source() == "derived_mode_s"
        with ogk.owner_request("sess"):
            seal = ogk.sign("d", DETAIL)
        assert ogk.is_signature(seal)
        assert ogk.verify("d", DETAIL, seal)
        assert not ogk.verify("other-domain", DETAIL, seal)


def test_derived_key_depends_on_the_secret():
    with patch.dict(os.environ, _env(**{ogk.SECRET_VAR: SECRET}), clear=True), \
            ogk.owner_request("sess"):
        seal = ogk.sign("d", DETAIL)
    with patch.dict(os.environ, _env(**{ogk.SECRET_VAR: "t" * 48}), clear=True):
        assert not ogk.verify("d", DETAIL, seal)


def test_mode_t_never_derives():
    with patch.dict(os.environ, _env(**{ogk.SECRET_VAR: SECRET, ogk.EMBEDDED_VAR: "0"}),
                    clear=True):
        assert ogk.key_source() == "absent"
        with ogk.owner_request("sess"):
            try:
                ogk.sign("d", DETAIL)
            except ValueError:
                pass
            else:
                raise AssertionError("Mode T derived a signing key")


def test_grant_still_needs_the_owner_request():
    with patch.dict(os.environ, _env(**{ogk.SECRET_VAR: SECRET}), clear=True):
        try:
            ogk.sign("d", DETAIL)
        except ValueError as exc:
            assert "owner's Command Center request" in str(exc)
        else:
            raise AssertionError("signed a grant outside the owner request")


def test_job_process_never_signs_even_when_derivable():
    saved = dict(ogk._JOB_PROCESS)
    try:
        with patch.dict(os.environ, _env(**{ogk.SECRET_VAR: SECRET}), clear=True), \
                ogk.owner_request("sess"):
            ogk._JOB_PROCESS["is"] = True
            try:
                ogk.sign("d", DETAIL)
            except ValueError as exc:
                assert "runs jobs" in str(exc)
            else:
                raise AssertionError("a job process signed")
    finally:
        ogk._JOB_PROCESS.update(saved)


def test_explicit_pair_wins_over_derivation():
    pair = ogk.generate_keypair()
    with patch.dict(os.environ, _env(**{ogk.SECRET_VAR: SECRET}, **pair), clear=True):
        assert ogk.key_source() == "explicit"
        with ogk.owner_request("sess"):
            seal = ogk.sign("d", DETAIL)
    with patch.dict(os.environ, _env(**{ogk.SECRET_VAR: SECRET}), clear=True):
        assert not ogk.verify("d", DETAIL, seal)


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            n += 1
            print(f"ok {name}")
    print(f"OK {n} passed")
