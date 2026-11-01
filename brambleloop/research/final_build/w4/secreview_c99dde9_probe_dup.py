"""Probe: a duplicate open size halt (PG insert race: FOR UPDATE locks no row when none
exists) is folded by ops.health hygiene WITHOUT its measured releases; the lift then
withholds only the kept row's releases, and the folded release is publishable."""
import sys
sys.path[:0] = ["tests", "src"]
import test_physfix as T
from brambleloop.core.models import Incident
from brambleloop.gates.incidents import IncidentTracker
from brambleloop.ops import incident_lifecycle
from brambleloop.publish import release_gates
from brambleloop.runtime import release as R

db = T._db()
a = T._basket_medium(); T._certify(db, a)
a2 = T._basket_medium(); a2.version = "1.2.9"; T._certify(db, a2)
print("A", a.version, "A2", a2.version)
print("A2 reasons before:", release_gates.for_publish(db, slug=a2.slug, version=a2.version, read_only=True)["reasons"][:3])
T._run(db, "physical.record", T._inputs(a, scope="full_make", holds_shape=True, measured_width_cm=40.0))
with db.session() as s:
    i1 = [i for i in s.query(Incident).all() if i.signature.startswith("physical-size:")][0]
    sig, det, at = i1.signature, dict(i1.detail), i1.at
    # The concurrent first failure of A2 (same design -> same signature) that the PG race inserts.
    e = dict(det["measured_releases"][0]); e.update(version=a2.version, content_hash=R._content_hash_of(a2))
    s.add(Incident(severity="P1", signature=sig, summary="dup", product_slug=a.slug,
                   halts_publication=True, detail={**det, "measured_releases": [e]}))
with db.session() as s:
    print("hygiene:", incident_lifecycle.hygiene(s)["duplicates"])
b = T._geometry_changed_medium("1.3.1"); T._certify(db, b)
job = T._run(db, "physical.record", T._inputs(b, scope="full_make", holds_shape=True, tester_ref="tester-2",
                                               content_hash=R._content_hash_of(b)))
out = R.lift_size_halt(db, incident_id=i1.id, physical_test_id=job.outputs["physical_test_id"],
                       actor="owner:cc:s", stepped_up=True, reason="re-made")
print("lift withheld:", out["withheld"])
print("open size halts:", [i.id for i in IncidentTracker(db).open_incidents(a.slug) if i.signature.startswith("physical-size:")])
print("A  for_publish size-withheld:", T._size_withheld(db, a))
print("A2 for_publish size-withheld:", T._size_withheld(db, a2))
print("A2 all reasons:", release_gates.for_publish(db, slug=a2.slug, version=a2.version, read_only=True)["reasons"])
