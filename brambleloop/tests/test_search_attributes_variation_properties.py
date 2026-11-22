"""F-004/F-007: a property Etsy marks `supports_attributes: false` is not a listing attribute.

Etsy's getPropertiesByTaxonomyId returns, in every node's schema, its custom-variation
properties (Size, Dimensions, Fabric, Finish, Flavor, Pattern, Scent, Weight, Device, Width,
Height, Length, ...) with `supports_attributes: false`. `commerce.category.properties_for`
ignored the flag, so each one with no rule read UNDECIDED, `properties.complete` was False,
and the search certificate's `attributes` check refused every Launch-0 release on the one
crochet-confirmed node -- whatever the product. The flag is Etsy's own statement; only an
explicit False decides, a missing flag stays UNDECIDED (UNKNOWN is never PASS), and a
required property is never waved through.

Run: cd brambleloop && python3 tests/test_search_attributes_variation_properties.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import fixtures_etsy_taxonomy as FX  # noqa: E402
from brambleloop.commerce import category as C  # noqa: E402
from brambleloop.commerce import search as S  # noqa: E402

CM = [{"scale_id": 5, "display_name": "Centimeters", "description": ""}]
VARIATION_ONLY = [(100, "Size"), (504, "Diameter"), (505, "Dimensions"), (506, "Fabric"),
                  (507, "Finish"), (508, "Flavor"), (509, "Height"), (510, "Length"),
                  (511, "Material"), (512, "Pattern"), (513, "Scent"), (514, "Style"),
                  (515, "Weight"), (516, "Width"), (517, "Device")]
LAUNCH0 = {  # category key -> (colours as listing.seo passes them)
    "baby": [("cream", "#FAF6EB"), ("ink", "#1A2B3C")],
    "basket": [("cream", "#FAF6EB"), ("wine", "#6E1F2A")],
    "coaster": [("cream", "#FAF6EB"), ("wine", "#6E1F2A")],
    "ornament": [("cream", "#FAF6EB"), ("forest", "#244A3A")],
    "blanket": [("cream", "#FAF6EB"), ("forest", "#244A3A")],
    "placemat": [("cream", "#FAF6EB"), ("wine", "#6E1F2A")],
}


def _variation(pid, name, *, flag=False, required=False):
    p = FX.prop(pid, name, required=required,
                scales=CM if name in ("Height", "Length", "Width", "Diameter") else ())
    if flag is None:
        p.pop("supports_attributes")
    else:
        p["supports_attributes"] = flag
    p["supports_variations"] = True
    return p


def _snapshot(extra):
    snap = FX.snapshot()
    snap["properties"] = {k: list(v) + list(extra) for k, v in snap["properties"].items()}
    return snap


def _facts(category, colours):
    return C.Facts(category=category, difficulty="confident beginner", colors=colours,
                   width_cm=76.0, height_cm=91.0)


def _attributes_check(props):
    return S.search_certificate(category={"status": "CHOSEN"}, properties=props,
                                attribute_problems=[], copy_gate={"ok": True},
                                tag_problems=[], description_problems=[])["checks"]["attributes"]


def test_variation_only_properties_are_not_attribute_gaps_for_every_launch0_category():
    snap = _snapshot([_variation(*v) for v in VARIATION_ONLY])
    for category, colours in LAUNCH0.items():
        choice = C.choose(snap, category)
        assert choice.status == C.CHOSEN, (category, choice.why)
        props = C.properties_for(snap, choice, _facts(category, colours))
        assert props["complete"] is True, (category, props["gaps"])
        by_name = {d["name"]: d for d in props["decisions"]}
        for _pid, name in VARIATION_ONLY:
            assert by_name[name]["status"] == C.NOT_APPLICABLE, (category, name)
            assert "supports_attributes=false" in by_name[name]["why"]
        # Nothing Etsy refuses as an attribute is sent to updateListingProperty.
        sent = {p["name"] for p in props["payload"]}
        assert not sent & {n for _p, n in VARIATION_ONLY}, sent
        assert {"Primary color", "Craft type", "Skill level"} <= sent, sent
        assert _attributes_check(props)["ok"] is True


def test_the_same_schema_refused_before_the_flag_was_read():
    """The defect, pinned: these properties are UNDECIDED when the flag is ignored."""
    raw = _variation(100, "Size")
    raw.pop("supports_attributes")
    snap = _snapshot([raw])
    props = C.properties_for(snap, C.choose(snap, "baby"), _facts("baby", LAUNCH0["baby"]))
    assert props["complete"] is False
    assert any(g.startswith("UNDECIDED: Size") for g in props["gaps"]), props["gaps"]
    assert _attributes_check(props)["ok"] is False


def test_unknown_flag_is_never_a_pass():
    for flag in (None,):
        snap = _snapshot([_variation(512, "Pattern", flag=flag)])
        props = C.properties_for(snap, C.choose(snap, "baby"), _facts("baby", LAUNCH0["baby"]))
        assert props["complete"] is False, props
        assert _attributes_check(props)["ok"] is False
    snap = _snapshot([{**_variation(512, "Pattern"), "supports_attributes": "false"}])
    props = C.properties_for(snap, C.choose(snap, "baby"), _facts("baby", LAUNCH0["baby"]))
    assert props["complete"] is False, "only Etsy's boolean False decides"


def test_a_required_property_is_never_waved_through():
    snap = _snapshot([_variation(505, "Dimensions", required=True)])
    props = C.properties_for(snap, C.choose(snap, "baby"), _facts("baby", LAUNCH0["baby"]))
    assert props["complete"] is False
    assert any("Dimensions" in g for g in props["gaps"])


def test_an_attribute_property_with_no_rule_still_refuses():
    snap = _snapshot([FX.prop(9100, "Pattern format", ("PDF", "Chart"))])
    props = C.properties_for(snap, C.choose(snap, "baby"), _facts("baby", LAUNCH0["baby"]))
    assert props["complete"] is False
    assert _attributes_check(props)["ok"] is False


def test_a_variation_flag_never_overrides_the_crochet_basis():
    craft = {**FX.prop(3001, "Craft type", ("Crochet", "Knitting")),
             "supports_attributes": False}
    snap = FX.snapshot()
    basis = {"via": "property", "property_id": 3001, "property": "Craft type",
             "value_id": 5000, "value": "Crochet"}
    choice = C.choose(snap, "baby")
    choice.crochet_basis = basis
    snap["properties"][str(choice.taxonomy_id)] = [
        craft if p["property_id"] == 3001 else p
        for p in snap["properties"][str(choice.taxonomy_id)]]
    props = C.properties_for(snap, choice, _facts("baby", LAUNCH0["baby"]))
    craft_d = next(d for d in props["decisions"] if d["property_id"] == 3001)
    assert craft_d["status"] == C.SET and craft_d["values"] == ["Crochet"]


if __name__ == "__main__":
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
