"""Incomplete persisted search evidence is UNKNOWN, never a publish pass."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from brambleloop.publish import release_gates as gates

REQUIRED = ('category', 'attributes', 'copy', 'tags', 'description')


def verdict(checks):
    listing = SimpleNamespace(title='Crochet pattern', description='Original pattern', tags=['crochet'])
    profile = SimpleNamespace(certificate={'checks': checks}, category_status='CHOSEN',
                              taxonomy_id=123, properties=[], verdict='PENDING')
    profile.fingerprint = gates.search_fingerprint(title=listing.title,
        description=listing.description, tags=listing.tags, taxonomy_id=123, properties=[])
    with patch.object(gates, '_search_profile', return_value=profile), \
            patch.object(gates, '_listing', return_value=listing):
        return gates.search_gate(None, slug='fixture', version='1',
            set_verdict={'frames': [{'position': 1, 'may_export': True}]})


def test_every_required_check_must_have_explicit_evidence():
    complete = {key: {'ok': True} for key in REQUIRED}
    assert verdict(complete)['ok'] is True
    assert verdict({})['ok'] is False, 'empty evidence passed search certification'
    for missing in REQUIRED:
        checks = {key: value for key, value in complete.items() if key != missing}
        assert verdict(checks)['ok'] is False, missing


def test_malformed_or_unknown_checks_cannot_pass():
    for invalid in (None, [], 'PASS', {'ok': None}, {'ok': 1}):
        checks = {key: {'ok': True} for key in REQUIRED}
        checks['attributes'] = invalid
        assert verdict(checks)['ok'] is False, repr(invalid)


if __name__ == '__main__':
    for test in (test_every_required_check_must_have_explicit_evidence,
                 test_malformed_or_unknown_checks_cannot_pass):
        test()
        print('OK  ', test.__name__)
    print('0 failed')
