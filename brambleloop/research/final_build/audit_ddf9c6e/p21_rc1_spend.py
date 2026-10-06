from _h import *
from sqlalchemy import select, func
from brambleloop.gateway import model_gateway as mg, prompts, anthropic as gw
from brambleloop.agents.registry import Registry
from brambleloop.core.models import CostEntry, SpendReservation, Agent
class P:
    name="p"; model="claude-haiku-4-5"; cost_per_1k_input_cad=0.5; cost_per_1k_output_cad=2.0
    def __init__(s, mode): s.mode=mode
    def complete(s, system, user, *, max_tokens):
        if s.mode=="garbage": return mg.ModelResponse(text="NOT JSON", provider="p", model=s.model, input_tokens=3000, output_tokens=1500, latency_ms=1)
        if s.mode=="nousage": return mg.ModelResponse(text="NOT JSON", provider="p", model=s.model, input_tokens=0, output_tokens=0, latency_ms=1)
        raise TimeoutError("read timeout after send")
ref = sorted(prompts._REGISTRY)[0]
vals = {k:"x" for k in prompts._placeholders(prompts._REGISTRY[ref].template)}
for mode in ("garbage","nousage","timeout"):
    db = mkdb()
    with db.session() as s: s.scalar(select(Agent).where(Agent.name=="cfo")).daily_cost_ceiling_cad = 50.0
    g = mg.ModelGateway([P(mode)], registry=Registry(db))
    try: g.complete_json(ref, agent="cfo", values=vals)
    except Exception as e: err=type(e).__name__
    with db.session() as s:
        c = s.scalar(select(func.sum(CostEntry.amount_cad)) ) or 0; n = s.scalar(select(func.count(CostEntry.id)))
        res = [(r.amount_cad, r.actual_cad, r.released_at is not None) for r in s.scalars(select(SpendReservation))]
    print(f"{mode:8s} err={err:22s} cost_rows={n} recorded_cad={round(c,4)} reservations(amount,actual,released)={res}")
