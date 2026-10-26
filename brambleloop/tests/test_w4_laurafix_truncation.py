"""W4-LAURAFIX: Laura's CEO briefing failed in production with "Model synthesis unavailable:
model call failed (MalformedModelOutput)" and dumped hundreds of repeated incidents.

Production evidence (owner test against c498888, /api/spend-report): task
`laura.ceo_briefing@3`, 1 call, tokens_in 29,629, tokens_out 600 -- exactly the task's
max_output_tokens. The v3 prompt asked for "the ids ... of the additional records that best
answer it" with no upper bound, chosen from a 231-record evidence pack (about 200 of them
repeated open incidents). The JSON reply was cut off at the output cap and
`parse_model_json` rightly refused it. Billed CA$0.136905; the CA$0.50/day cap held.

This file reproduces that shape (production-like incidents: ops.sentinel
StringDataRightTruncation x15, dead letters, image errors, mandatory P0/P1/halting ones) with
a stub transport that behaves like a model obeying its prompt and is cut at the cap exactly
as the provider does (stop_reason "max_tokens"). Against c498888 the first test fails with
"model call failed (MalformedModelOutput)". The fix:

(a) the prompt (v4) asks for at most K ids per component, K = the renderer's own limit;
(b) a compliant reply fits under the computed output-token bound;
(c) truncation is reported as truncation, not as a generic malformed reply;
(d) repeated incidents are grouped by root cause before the pack is built, in both paths,
    and every mandatory (P0/P1/halting) incident is still shown as its group, with count.

No network, no API key, no real model call.
Run: cd brambleloop && PYTHONPATH=src:tests .venv/bin/python tests/test_w4_laurafix_truncation.py
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta, timezone

import w3_laura_cc_harness as H  # noqa: E402  (isolated environment, network refused)

from sqlalchemy import select, update  # noqa: E402

from brambleloop.core.models import Agent, CostEntry, Incident  # noqa: E402
from brambleloop.gateway import laura_briefing, routing  # noqa: E402
from brambleloop.gateway.model_gateway import ModelResponse  # noqa: E402
from brambleloop.laura.agency import briefing, talk  # noqa: E402

import os as _os_ceo  # noqa: E402
# f87e430 review R-2: the briefing synthesis is behind BRAMBLELOOP_LAURA_CEO_MODEL (default
# OFF). This suite exercises the ON behaviour; test_w4_laura_ceo proves OFF makes no call.
_os_ceo.environ["BRAMBLELOOP_LAURA_CEO_MODEL"] = "1"

DB = H.DB
Q = ("Laura, give me a complete but concise CEO briefing. Tell me what Brambleloop "
     "accomplished in the last 24 hours, what each department is working on, what is "
     "preventing our first Etsy sale, and the five most important things you need me to "
     "decide. Separate verified facts from unknowns, and tell me what you can handle without "
     "my involvement.")
PURPOSE = laura_briefing.PROMPT.ref
NOW = datetime.now(timezone.utc)

# The stub's tokenizer: one token per 3 bytes of output, roughly what a BPE tokenizer gives
# JSON id lists (`"E123",` is ~3 tokens). It only decides where the stub cuts; the bound under
# test is proven against the stricter 1 token <= 1 byte (see laura_briefing.output_token_bound).
STUB_BYTES_PER_TOKEN = 3

H.seed_company()

# Mandatory, distinct incidents (each must survive grouping and appear, verbatim).
MANDATORY = {
    "p0": "systemic failure: 3 departments failed their last 5 runs; publication halted",
    "auth": "Etsy OAuth token expired; re-authorise the app as the account holder",
    "etsy401": ("Etsy API returned 401. You must re-authorise the app as the account holder; "
                "until then no listing can be read."),
}
# Repeated incidents from a few root causes, shaped like production (one row per occurrence,
# per-instance signatures, so the store's own signature dedupe does not collapse them).
REPEATS = (
    # (count, severity, job_type, error, summary template)
    (15, "P1", "ops.sentinel",
     "StringDataRightTruncation: value too long for type character varying(200)",
     "job {n} (ops.sentinel) dead-lettered after 3 attempts: StringDataRightTruncation: "
     "value too long for type character varying(200)"),
    (80, "P1", "image.render", "ImageProviderError: upstream 502 Bad Gateway",
     "dead letter: job {n} (image.render) failed 3 times: ImageProviderError: upstream 502 "
     "Bad Gateway"),
    (60, "P1", None, None,
     "image {h} for listing harbour-shawl failed QC: ImageDecodeError: truncated PNG stream"),
    (30, "P1", "seo.cycle", "TimeoutError: read timed out after 30s",
     "dead letter: job {n} (seo.cycle) TimeoutError: read timed out after 30s"),
)


def _seed_production_incidents(tag: str, scale: int = 1) -> int:
    """Seed the production-shaped open incidents; returns how many rows were written."""
    n = 0
    with DB.session() as s:
        s.add(Incident(severity="P0", signature=f"{tag}:systemic", halts_publication=True,
                       summary=MANDATORY["p0"], at=NOW - timedelta(minutes=5)))
        s.add(Incident(severity="P1", signature=f"{tag}:etsy_auth", halts_publication=True,
                       summary=MANDATORY["auth"], at=NOW - timedelta(hours=2)))
        s.add(Incident(severity="P2", signature=f"{tag}:etsy401", halts_publication=True,
                       summary=MANDATORY["etsy401"], at=NOW - timedelta(hours=1)))
        n += 3
        for g, (count, sev, jt, err, tpl) in enumerate(REPEATS):
            for k in range(count * scale):
                num = 4000 + g * 10000 + k
                detail = {"job_type": jt, "error": err} if jt else {}
                s.add(Incident(severity=sev, signature=f"{tag}:g{g}:{num}",
                               summary=tpl.format(n=num, h=f"{num * 2654435761:x}"),
                               detail=detail,
                               at=NOW - timedelta(hours=20) + timedelta(minutes=k)))
                n += 1
        for k in range(5):
            s.add(Incident(severity="P2", signature=f"{tag}:noise:{k}",
                           summary=f"minor P2 note {k}"))
            n += 1
    return n


def _resolve(tag: str) -> None:
    with DB.session() as s:
        s.execute(update(Incident).where(Incident.signature.like(f"{tag}:%"))
                  .values(resolved=True))


def _set_laura_ceiling(cad: float) -> None:
    with DB.session() as s:
        s.execute(update(Agent).where(Agent.name == "laura")
                  .values(daily_cost_ceiling_cad=cad))


def _ledger():
    with DB.session() as s:
        return list(s.scalars(select(CostEntry).where(
            CostEntry.purpose.like("laura.ceo_briefing@%"))))


# ---- the stub transport -----------------------------------------------------------------

_BOUNDED = re.compile(r"^- ([a-z_]+) \(at most (\d+)\): (.*)$", re.M)


def _obedient_reply(user: str, *, ignore_bound: bool = False) -> dict:
    """What a model that does exactly what the prompt says returns.

    v4 prompt: per listed component, the first K selectable ids. v3 prompt (no bound): every
    id listed for the component, which is what "the ids of the additional records that best
    answer it" invites when nothing caps it -- and what production's 600-token reply was."""
    comps = re.search(r"^Requested components, in order: (.*)$", user, re.M).group(1)
    comps = [c.strip() for c in comps.split(",")]
    bounded = {m.group(1): (int(m.group(2)), re.findall(r"[EP]\d+", m.group(3)))
               for m in _BOUNDED.finditer(user)}
    pack = {m.group(1): m.group(2).split(",") for m in re.finditer(
        r"^(E\d+) \| ([^|]*) \|", user, re.M)}
    pids = re.findall(r"^(P\d+) \(", user, re.M)
    sections = []
    for c in comps:
        if bounded and not ignore_bound:
            if c not in bounded:
                continue
            k, ids = bounded[c]
            sections.append({"component": c, "evidence": ids[:k]})
            continue
        ids = [e for e, cs in pack.items() if c in cs]
        if c == "autonomous":
            ids = pids + ids
        if ids:
            sections.append({"component": c, "evidence": ids})
    return {"sections": sections}


class CapCuttingStub:
    """A transport that answers like the real provider: the reply is cut at `max_tokens`
    and the response says so (`stop_reason: "max_tokens"`, output_tokens == the cap)."""

    name = "anthropic"
    cost_per_1k_input_cad = 0.001
    cost_per_1k_output_cad = 0.001

    def __init__(self, model, calls, *, ignore_bound=False, report_stop_reason=True,
                 overrun=False):
        self.model = model
        self.overrun = overrun
        self.calls = calls
        self.ignore_bound = ignore_bound
        self.report_stop_reason = report_stop_reason

    def complete(self, system, user, *, max_tokens):
        reply = _obedient_reply(user, ignore_bound=self.ignore_bound)
        if self.overrun:      # a model that ignores the bound and keeps going past any cap
            for sec in reply["sections"]:
                sec["evidence"] = sec["evidence"] * 40
        text = json.dumps(reply, indent=2)
        raw = text.encode()
        tokens = math.ceil(len(raw) / STUB_BYTES_PER_TOKEN)
        stop = "end_turn"
        if tokens > max_tokens:
            text = raw[: max_tokens * STUB_BYTES_PER_TOKEN].decode("utf-8", "ignore")
            tokens, stop = max_tokens, "max_tokens"
        self.calls.append({"max_tokens": max_tokens, "user": user, "reply": text,
                           "tokens": tokens, "stop": stop})
        kw = dict(text=text, provider=self.name, model=self.model,
                  input_tokens=(len(system) + len(user)) // 4, output_tokens=tokens,
                  latency_ms=0.0)
        try:   # c498888's ModelResponse has no stop_reason field: the reproduction still runs
            return ModelResponse(**kw, stop_reason=stop if self.report_stop_reason else "")
        except TypeError:
            return ModelResponse(**kw)


def _factory(calls, **kw):
    return lambda model: CapCuttingStub(model, calls, **kw)


def _incident_lines(answer: str) -> list[str]:
    return [l for l in answer.splitlines() if "incident" in l and l.startswith("- ")]


# ---- tests ------------------------------------------------------------------------------

TAG = "laurafix"
SEEDED = _seed_production_incidents(TAG)


def test_production_shape_reproduction_compliant_model_is_not_cut_off():
    """The defect itself. At c498888: the reply runs past the 600-token cap, is cut, and the
    briefing reads 'model call failed (MalformedModelOutput)'. Fixed: the prompt bounds the
    reply, the compliant answer fits, and the model's selection is used."""
    calls: list = []
    _set_laura_ceiling(0.50)
    try:
        r = talk.converse(DB, Q, session_public_id="s_fix_repro",
                          provider_factory=_factory(calls))
    finally:
        _set_laura_ceiling(0.0)
    assert calls, "the model path ran"
    print("    stub reply tokens:", calls[0]["tokens"], "cap:", calls[0]["max_tokens"],
          "stop:", calls[0]["stop"], "| synthesis:", r["synthesis"]["source"],
          r["synthesis"]["reason"])
    assert "MalformedModelOutput" not in r["answer"], r["answer"][:300]
    assert calls[0]["stop"] == "end_turn", (calls[0]["tokens"], calls[0]["max_tokens"])
    assert r["synthesis"]["source"] == "model", r["synthesis"]
    assert r["synthesis"]["rejected"] == [], r["synthesis"]["rejected"]


def test_a_prompt_requests_a_bounded_number_of_ids_per_component():
    assert laura_briefing.PROMPT.version == "4", laura_briefing.PROMPT.ref
    assert "at most" in laura_briefing.PROMPT.system
    pack = briefing.evidence_pack(DB)
    parsed = briefing.parse(Q)
    props = briefing.proposals(pack)
    values = briefing.prompt_values(Q, parsed, pack, props)
    user = laura_briefing.PROMPT.render(**values)
    bounded = {m.group(1): (int(m.group(2)), re.findall(r"[EP]\d+", m.group(3)))
               for m in _BOUNDED.finditer(user)}
    # K is exactly the number of optional lines the renderer shows for that component
    assert len(parsed["components"]) == 6 and len(bounded) == 4, (parsed, bounded)
    for comp in parsed["components"]:
        k = briefing.PICK_LIMITS[comp]
        if k == 0:                # decisions / facts_unknowns: wholly code-rendered
            assert comp not in bounded, comp
            continue
        assert bounded[comp][0] == k, (comp, bounded.get(comp), k)
        # selectable ids exclude the mandatory records (code shows them first anyway)
        must = {m["id"] for m in briefing.mandatory(pack, comp)}
        assert not must & set(bounded[comp][1]), comp
        assert set(bounded[comp][1]) <= briefing._allowed_ids(comp, pack, props, 5), comp
    assert briefing.PICK_LIMITS == {"last_window": 6, "departments": 6, "blockers": 6,
                                    "decisions": 0, "facts_unknowns": 0, "autonomous": 4}
    # the renderer really shows K optional picks at the first (fullest) cap level
    for comp in ("last_window", "departments", "blockers", "autonomous"):
        assert briefing.pick_limit(comp, briefing.CAP_LEVELS[0]) == briefing.PICK_LIMITS[comp]
    # validate() trims to K deterministically (first K optional ids, in the model's order)
    for comp in ("last_window", "blockers", "departments"):
        allowed = sorted(briefing._allowed_ids(comp, pack, props, 5),
                         key=lambda i: int(i[1:]))
        must = {m["id"] for m in briefing.mandatory(pack, comp)}
        optional = [i for i in allowed if i not in must]
        acc, rej = briefing.validate({"sections": [{"component": comp, "evidence": allowed}]},
                                     pack, parsed, props)
        assert not rej, rej
        assert acc[comp]["ids"] == optional[:briefing.PICK_LIMITS[comp]], (comp, acc[comp])
        assert acc[comp]["trimmed"] == len(allowed) - len(acc[comp]["ids"]), acc[comp]


def test_b_compliant_reply_fits_under_the_computed_output_bound():
    bound = laura_briefing.OUTPUT_TOKEN_BOUND
    # one number, in three places that must not drift
    assert routing.TASKS[laura_briefing.TASK].max_output_tokens == bound
    assert laura_briefing.PROMPT.max_output_tokens == bound
    assert bound == laura_briefing.output_token_bound(briefing.PICK_LIMITS)
    # the worst compliant reply (every component, K ids each, widest ids, indent 4, fenced)
    worst = laura_briefing.worst_case_reply(briefing.PICK_LIMITS)
    worst_bytes = len(worst.encode())
    assert json.loads(worst.strip().removeprefix("```json").removesuffix("```"))
    # tokens <= bytes for any BPE tokenizer, so this is an upper bound, with 25% headroom
    assert worst_bytes * laura_briefing.HEADROOM <= bound, (worst_bytes, bound)
    assert bound <= 2048, bound          # still a small, cheap allowance
    # and the actual compliant reply over the production-shaped pack is far below it
    calls: list = []
    _set_laura_ceiling(0.50)
    try:
        talk.converse(DB, Q, session_public_id="s_fix_b", provider_factory=_factory(calls))
    finally:
        _set_laura_ceiling(0.0)
    assert calls[0]["max_tokens"] == bound
    assert len(calls[0]["reply"].encode()) <= worst_bytes
    assert calls[0]["tokens"] < bound / 2, (calls[0]["tokens"], bound)
    print(f"    bound {bound} tokens; worst compliant reply {worst_bytes} bytes; "
          f"stub reply {calls[0]['tokens']} tokens")


def test_c_truncation_is_reported_as_truncation():
    from brambleloop.core.resilience import MalformedModelOutput, OutputTruncated

    assert issubclass(OutputTruncated, MalformedModelOutput)   # every old handler still fires
    for report, basis in ((True, "stop_reason=max_tokens"),
                          (False, "output_tokens reached the cap")):
        calls: list = []
        _set_laura_ceiling(0.50)
        try:
            before = len(_ledger())
            r = talk.converse(DB, Q, session_public_id=f"s_fix_c_{report}",
                              provider_factory=_factory(calls, ignore_bound=True,
                                                        report_stop_reason=report,
                                                        overrun=True))
        finally:
            _set_laura_ceiling(0.0)
        assert calls and calls[0]["stop"] == "max_tokens", calls[:1]
        reason = r["synthesis"]["reason"]
        assert r["synthesis"]["source"] == "unavailable", r["synthesis"]
        assert reason.startswith(
            f"model output truncated at the {laura_briefing.OUTPUT_TOKEN_BOUND}-token "
            f"output cap"), reason
        assert basis in reason, reason
        assert "MalformedModelOutput" not in r["answer"]
        assert f"Model synthesis unavailable: {reason}" in r["answer"], r["answer"][:400]
        assert "deterministic fallback" in r["answer"]
        billed = _ledger()[before:]          # a cut-off reply was still paid for: billed
        assert len(billed) == 1 and billed[0].tokens_out == laura_briefing.OUTPUT_TOKEN_BOUND
        assert r["synthesis"]["truncated"] is True


def test_c2_the_provider_exposes_its_stop_reason():
    """The real provider reads `stop_reason` from the Messages API body, and a replayed
    answer keeps it, so the gateway can name a cut-off reply on the production path."""
    import time

    from brambleloop.gateway import anthropic as gw

    prov = gw.AnthropicProvider(model=routing.TIERS[routing.STANDARD].model)
    body = {"content": [{"type": "text", "text": '{"sections": [{"comp'}],
            "stop_reason": "max_tokens", "model": prov.model,
            "usage": {"input_tokens": 29629, "output_tokens": 600}}
    r = prov._read(body, time.time())
    assert r.stop_reason == "max_tokens" and r.output_tokens == 600, r
    assert gw._decode_response(gw._encode_response(r)).stop_reason == "max_tokens"
    assert prov._read({"content": [], "usage": {}}, time.time()).stop_reason == ""


def test_d_fallback_groups_repeats_and_keeps_every_mandatory_incident():
    r = talk.converse(DB, Q, session_public_id="s_fix_d")      # CA$0.00: no model call
    assert r["synthesis"]["source"] == "unavailable"
    a = r["answer"]
    inc = _incident_lines(a)
    text = "\n".join(inc)
    for m in MANDATORY.values():
        assert m in text, (m, text)
    # one line per root cause, with its count and last time
    assert "(15 occurrences" in text and "StringDataRightTruncation" in text, text
    assert "(80 occurrences" in text and "ImageProviderError" in text, text
    assert "(60 occurrences" in text and "ImageDecodeError" in text, text
    assert "(30 occurrences" in text and "TimeoutError" in text, text
    assert sum("StringDataRightTruncation" in l for l in inc) == 1, inc
    assert all(", last at " in l for l in inc if "occurrences" in l), inc
    # severity order: P0 first
    assert MANDATORY["p0"] in inc[0], inc[:2]
    # lower-severity incidents are counted, never dropped silently
    assert re.search(r"\+\d+ more open lower-severity incident", a), a
    # short executive layout
    assert len(a) <= briefing.MAX_ANSWER_CHARS and len(a.splitlines()) <= briefing.MAX_LINES
    # the expandable evidence: one fact per group with count, first/last seen, example ids
    groups = [f for f in r["facts"] if f.get("occurrences", 1) > 1]
    assert {f["occurrences"] for f in groups} >= {15, 80, 60, 30}, groups
    for f in groups:
        assert f["first_seen"] <= f["last_seen"] and f["examples"], f
        assert len(f["examples"]) <= briefing.GROUP_EXAMPLES
        assert all(e["source"].startswith("incidents:") for e in f["examples"]), f
    assert r["synthesis"]["incidents"]["raw"] >= 188, r["synthesis"]["incidents"]
    assert r["synthesis"]["incidents"]["groups"] <= 10, r["synthesis"]["incidents"]
    # the label is precise about why the model was not used
    assert a.splitlines()[1].startswith("Model synthesis unavailable: laura has no "
                                        "authorised daily model budget"), a.splitlines()[1]


def test_cost_estimate_prompt_shrank():
    parsed = briefing.parse(Q)
    grouped = briefing.evidence_pack(DB)
    flat = briefing.evidence_pack(DB, group_incidents=False)       # c498888's pack shape
    props = briefing.proposals(grouped)
    after = laura_briefing.estimate(briefing.prompt_values(Q, parsed, grouped, props))
    before = laura_briefing.estimate(briefing.prompt_values(Q, parsed, flat, props))
    print(f"    pack {len(flat['items'])} -> {len(grouped['items'])} records; input tokens "
          f"{before['input_tokens']} -> {after['input_tokens']}; padded estimate "
          f"CA${before['estimate_cad_padded']:.4f} -> CA${after['estimate_cad_padded']:.4f}")
    assert len(flat["items"]) >= 200, len(flat["items"])        # production: 231
    assert len(grouped["items"]) <= 60, len(grouped["items"])
    assert after["input_tokens"] * 3 <= before["input_tokens"], (before, after)
    assert after["estimate_cad_padded"] < before["estimate_cad_padded"]
    assert after["input_tokens"] <= routing.TASKS[laura_briefing.TASK].typical_input_tokens


def test_large_incident_set_both_paths():
    """1,000+ open incident records: the pack, the prompt and the answer stay bounded, every
    mandatory incident is shown, and a compliant model reply fits under the cap."""
    tag = "laurafix_big"
    _resolve(TAG)                    # this tag's rows only, so the counts below are exact
    written = _seed_production_incidents(tag, scale=5)          # 3 + 925 + 5 rows
    with DB.session() as s:
        for k in range(80):                                      # pad to well over 1,000
            s.add(Incident(severity="P1", signature=f"{tag}:pad:{k}",
                           summary=f"dead letter: job {9000 + k} (ops.sentinel) "
                                   f"StringDataRightTruncation: value too long",
                           detail={"job_type": "ops.sentinel",
                                   "error": "StringDataRightTruncation: value too long"}))
    written += 80
    assert written >= 1000, written
    try:
        pack = briefing.evidence_pack(DB)
        assert len(pack["items"]) <= 60, len(pack["items"])
        fb = talk.converse(DB, Q, session_public_id="s_fix_big_fb")
        calls: list = []
        _set_laura_ceiling(0.50)
        try:
            md = talk.converse(DB, Q, session_public_id="s_fix_big_md",
                               provider_factory=_factory(calls))
        finally:
            _set_laura_ceiling(0.0)
        assert md["synthesis"]["source"] == "model", md["synthesis"]
        assert calls[0]["stop"] == "end_turn" and calls[0]["tokens"] < calls[0]["max_tokens"]
        est = laura_briefing.estimate(briefing.prompt_values(
            Q, briefing.parse(Q), pack, briefing.proposals(pack)))
        assert est["input_tokens"] <= routing.TASKS[laura_briefing.TASK].typical_input_tokens
        for r in (fb, md):
            text = "\n".join(_incident_lines(r["answer"]))
            for m in MANDATORY.values():
                assert m in text, (m, text)
            assert "(155 occurrences" in text, text            # 15 x 5 + 80 padding
            assert r["synthesis"]["incidents"]["raw"] >= 1000, r["synthesis"]["incidents"]
            assert len(r["answer"]) <= briefing.MAX_ANSWER_CHARS
            assert len(r["answer"].splitlines()) <= briefing.MAX_LINES
        print(f"    {written} rows -> {len(pack['items'])} pack records, "
              f"{fb['synthesis']['incidents']}, input tokens {est['input_tokens']}")
    finally:
        _resolve(tag)


if __name__ == "__main__":
    H.run(globals())
