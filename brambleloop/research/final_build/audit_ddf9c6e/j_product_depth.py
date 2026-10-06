"""Do size variants count toward launch.readiness catalogue_depth (MIN_LISTINGS_TO_OPEN=8)?"""
from types import SimpleNamespace as NS
from brambleloop.launch import readiness as R
from brambleloop.products import launch0 as L
from brambleloop.publish import eligibility as E
import inspect
print("MIN_LISTINGS_TO_OPEN =", R.MIN_LISTINGS_TO_OPEN)
cir_slugs = sorted(s for s in L.launch_scope_slugs() if s != "nursery-nesting-baskets")
print("launch-0 CANDIDATES (products):", L.LAUNCH0_SLUGS)
print("in-scope CIR slugs (each its own Listing/PatternVersion):", cir_slugs)
class DB:  # minimal stand-in: _launch_scope_counts only reads Product ids -> slugs
    def session(self): 
        import contextlib
        @contextlib.contextmanager
        def cm():
            yield NS(scalars=lambda q: [NS(id=i, slug=s) for i, s in enumerate(cir_slugs)])
        return cm()
import brambleloop.launch.readiness as RM
RM_select = None
# patch sqlalchemy select usage by monkeypatching legacy_status to the real one and select to identity
import sqlalchemy
orig = sqlalchemy.select
sqlalchemy.select = lambda *a, **k: None
certified = [NS(product_id=i, version="1.0.0", certificate={"granted": True, "policy_version": "x"}) for i, _ in enumerate(cir_slugs)]
counted, legacy = R._launch_scope_counts(DB(), certified)
sqlalchemy.select = orig
print("counted versions:", counted["versions"], "distinct products:", len(L.LAUNCH0_SLUGS), "legacy:", len(legacy))
