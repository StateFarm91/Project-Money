from _h import *
from brambleloop.finance.accounting import policy, reconciliation as R, controller
from brambleloop.core.models import OwnerAction
db = mkdb(seed=True)
R.import_statement(db, "bank", [{"external_id":"c1","at":NOW-timedelta(days=30),"kind":"owner_contribution","amount":20000.0,"reference":"seed"}], now=NOW)
controller.run_cycle(db, now=NOW)
with db.session() as s:
    s.add(OwnerAction(requirement_key="auth:big", action="approve", reason="x", max_cost_cad=5000.0, done=True))
def t(label, **p):
    base = {"amount_cad": 900.0, "purpose":"promoted listings test", "proposer":"growth", "expected_contribution_cad": 2000.0,
            "authority":{"type":"owner_action","ref":"auth:big"}}
    base.update(p)
    r = policy.check_spend(db, base, now=NOW)
    print(f"{label:34s} -> {r['verdict']:9s} allow={r['allow']} blocks={[c['rule'] for c in r['checks'] if c['outcome']=='block']}")
t("kind=ads amount=900 (cap check)", kind="ads")
t("kind=advertising amount=900", kind="advertising")
t("kind='ads ' amount=900", kind="ads ")
t("kind=etsy_ads amount=900", kind="etsy_ads")
t("kind=ads amount=NaN", kind="ads", amount_cad=float("nan"))
t("kind=ads amount=NaN str", kind="ads", amount_cad="nan")
t("kind=ads amount=inf", kind="ads", amount_cad=float("inf"))
t("kind=ads expected NaN", kind="ads", amount_cad=10.0, expected_contribution_cad=float("nan"))
t("kind=advertising amount=NaN", kind="advertising", amount_cad=float("nan"))
t("kind=advertising amount=1e9 (above auth)", kind="advertising", amount_cad=1e9)
t("kind=advertising amount=4999 > caps", kind="advertising", amount_cad=4999.0, expected_contribution_cad=0.0)
# propose path with NaN
from brambleloop.growth import ads_readiness as AR
for d in (float("nan"),):
    try:
        r = AR.propose(db, "moss-stitch-cowl", daily_budget_cad=d, days=10, funding="owner_cash", hypothesis="h", stop_condition="s")
        print("propose NaN ->", r["status"], r["verdict"], r["reasons"][:2])
    except Exception as e: print("propose NaN EXC", repr(e)[:120])
