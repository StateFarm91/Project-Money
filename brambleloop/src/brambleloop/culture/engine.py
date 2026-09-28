"""What the culture sweep does with the signals it has just stored.

Requirements 134-138, 141, 143-146, run rather than described. The libraries beside this
module each answer one question -- what a signal decomposes into (`translate`), what it is
allowed to become (`rights`), how strong it is (`score`), when to stop (`radar.exit_check`),
what may be accelerated (`rapid`), what the company owns (`cast`) -- and until this module
nothing asked them anything at runtime. The proof-chain audit of 2026-09-27 found every one
of them tested and unreachable.

**Deterministic, and honest about how little that settles.** The model provider is closed,
so decomposition here comes from a small, reviewed cue table (`CUES`) rather than from a
model reading the topic. A cue is a word the topic contains -- `christmas`, `halloween`,
`nostalgia` -- and what it supplies is the franchise-free half of #134's ten primitives for
that word. A topic the cue table cannot read is recorded as *untranslated, with the reason*,
never given invented primitives; a primitive the cues do not supply is listed as absent.

**Candidates go to creative development, never to engineering.** Every translation is a
`CultureConcept` row at stage `creative_development`. Nothing here drafts a CIR or enqueues
an engineering job: the concept tournament, the jury and the compiler still stand between a
row here and a pattern, and the rapid-response cell (#141) accelerates the path to that
stage without shortening anything after it.

**Unclear rights route, they do not block (#135).** A topic the classifier placed in a
property domain declares its own title as a protected token, so it lands in the original
lane unless somebody has recorded a basis (`clear()`); the opportunity continues as its
emotional territory. Every premise is checked free of every declared token before it is
stored.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from . import cast, radar, rapid, rights, score as scoring, translate

ACTION_SWEEP = "culture.engine"
ACTION_RAPID = "culture.rapid_response"
ACTION_TOURNAMENT = "culture.white_space"
ACTION_CLEARANCE = "culture.clearance"
ACTION_IP = "culture.ip_proposed"

REFERENCE_CHANNEL = "reference"

# Candidate states. `rejected` and `withdrawn` are kept with their reason (#144): an idea
# nobody kept is still something next year's agent should not have to have again.
CANDIDATE = "candidate"
REJECTED = "rejected"
WITHDRAWN = "withdrawn"
LAUNCHED = "launched"

STAGE = "creative_development"

# A signal is strong enough for the white-space tournament (#138) at this score with at
# least half its components observed; the rapid cell (#141) needs `score.ACT_NOW` and a date
# that closes. Below the floor a signal is recorded, scored and remembered, and not developed.
STRONG = 0.5

# The accelerations the rapid cell asks for, each checked through `rapid.check` with no
# bypass. Named here so the audit row can say exactly what was sped up.
RAPID_ACCELERATES: tuple[str, ...] = (
    "research", "concept_tournament", "feasibility", "creative_prototyping")


# ---------------------------------------------------------------------------
# The cue table: what a topic's words settle, and nothing more


@dataclass(frozen=True)
class Cue:
    key: str
    words: tuple[str, ...]
    domain: str
    primitives: dict = field(default_factory=dict)
    eras: tuple[str, ...] = ()
    themes: tuple[str, ...] = ()
    families: tuple[str, ...] = ()
    # (month, day) of the date the cue's demand closes on, when it has one.
    occasion: tuple[int, int] | None = None


CUES: tuple[Cue, ...] = (
    Cue("christmas", ("christmas", "xmas", "advent", "yule"), "seasonal_tradition",
        {"emotion": "warmth and anticipation shared with family",
         "setting": "a living room lit by a decorated tree",
         "ritual": "decorating the house and exchanging gifts at midwinter",
         "colour_language": "deep red, evergreen and candlelight gold",
         "character_archetype": "the host who decorates far past reason",
         "gifting_context": "a handmade gift from one relative to another"},
        eras=("retro_suburban_christmas", "nineties_family_christmas",
              "classic_storybook_winter", "mid_century_holiday",
              "eighties_holiday_maximalism"),
        themes=("chaotic_family_holiday", "over_the_top_decorating",
                "magical_childhood_christmas"),
        families=("stocking", "ornament", "garland", "wreath", "blanket", "pillow",
                  "tableware", "coaster", "wearable"),
        occasion=(12, 25)),
    Cue("stocking", ("stocking", "stockings"), "seasonal_tradition",
        {"object_category": "a stocking hung to be filled",
         "visual_motif_class": "a name worked into a folded cuff"},
        families=("stocking",)),
    Cue("halloween", ("halloween",), "seasonal_tradition",
        {"emotion": "a small, safe fright",
         "setting": "a porch at dusk with the light on",
         "ritual": "dressing up and going door to door",
         "colour_language": "harvest orange, black and bone",
         "visual_motif_class": "simple silhouettes of cats, bats and lanterns",
         "humour_type": "frightening in the way a very small ghost is frightening"},
        eras=("retro_halloween",), themes=("spooky_cute_halloween",),
        families=("amigurumi", "garland", "bag", "coaster", "pillow", "wearable", "blanket",
                  "pet"),
        occasion=(10, 31)),
    Cue("valentine", ("valentine", "valentines"), "seasonal_tradition",
        {"emotion": "sincere affection said out loud",
         "ritual": "exchanging small tokens of affection",
         "colour_language": "blush, red and cream",
         "gifting_context": "one partner giving to the other"},
        themes=("romantic_comedy_valentine",),
        families=("amigurumi", "pillow", "coaster", "wearable", "bag"),
        occasion=(2, 14)),
    Cue("winter", ("winter", "snow", "ski", "skiing", "snowman"), "seasonal_tradition",
        {"emotion": "coziness held against the cold",
         "setting": "a cabin with snow outside the window",
         "colour_language": "cream, oxblood and pine"},
        eras=("vintage_ski_lodge", "classic_storybook_winter"),
        themes=("winter_road_trip", "cozy_movie_night"),
        families=("wearable", "blanket", "pillow", "kitchen", "ornament")),
    Cue("summer", ("summer",), "seasonal_tradition",
        {"setting": "a cottage step in the afternoon sun",
         "colour_language": "sun-bleached stripes and gingham"},
        eras=("cottage_summer",), families=("tableware", "bag", "coaster", "kitchen",
                                            "wearable")),
    Cue("autumn", ("autumn",), "seasonal_tradition",
        {"setting": "a street of bookshops and falling leaves",
         "colour_language": "camel, rust and ivory"},
        eras=("romantic_comedy_autumn",), themes=("cozy_movie_night",),
        families=("wearable", "blanket", "bag", "pillow")),
    Cue("nostalgia", ("nostalgia", "nostalgic", "retro", "vintage"), "nostalgia_era",
        {"emotion": "longing for a remembered version of home"},
        eras=tuple(translate.ERAS), families=("blanket", "pillow", "ornament", "coaster")),
    Cue("meme", ("meme", "memes"), "meme",
        {"humour_type": "a shared in-joke recognised on sight"},
        families=("coaster", "amigurumi", "pillow")),
    Cue("toy", ("toy", "toys"), "nostalgia_era",
        {"setting": "a toy-shop window seen from outside at night",
         "object_category": "a small figure meant to be held"},
        themes=("retro_toy_shop_winter",), families=("amigurumi", "nursery", "ornament")),
)

# Words that make a topic generic rather than somebody's property. A classifier-placed topic
# made only of these and cue words declares no protected token; any other word, and the
# title itself is declared, because a topic this module cannot read is one it cannot clear.
GENERIC_WORDS: frozenset[str] = frozenset({
    "internet", "day", "eve", "holiday", "holidays", "season", "tree", "decoration",
    "decorations", "the", "of", "and", "card", "cards", "party", "market", "markets"})

# Domains whose topics are almost always somebody's work, name or likeness.
PROPERTY_DOMAINS: frozenset[str] = frozenset({
    "film", "television", "music", "celebrity_aesthetic", "sports_culture",
    "internet_moment", "meme", "viral_aesthetic"})

# What each product family is, as a premise can say it.
FAMILY_FORM: dict[str, str] = {
    "blanket": "a throw worked for the back of the sofa",
    "stocking": "a stocking made to hang and be filled",
    "ornament": "a small ornament that hangs from a branch",
    "coaster": "a set of coasters that make a quick evening's make",
    "wreath": "a wreath for the front door",
    "garland": "a garland strung across a mantel",
    "tableware": "table linens for the one meal everybody attends",
    "amigurumi": "a small stuffed figure to hold",
    "wearable": "a hat and scarf worn out into it",
    "bag": "a tote carried to and from it",
    "pillow": "a cushion cover for the reading chair",
    "nursery": "a soft nursery piece for a first one",
    "pet": "a pet's blanket so the dog is included",
    "kitchen": "kitchen cloths and a tea cosy",
    "interactive": "a piece that transforms or opens to reveal something",
}
assert set(FAMILY_FORM) == set(translate.TRANSLATION_FAMILIES)

# The collection role each family can fill (#143). `bundle` is filled by combination.
FAMILY_ROLE: dict[str, str] = {
    "blanket": "flagship", "stocking": "flagship",
    "coaster": "quick_make", "kitchen": "quick_make",
    "ornament": "giftable_mini", "amigurumi": "giftable_mini",
    "wreath": "decor", "garland": "decor", "pillow": "decor", "tableware": "decor",
    "wearable": "wearable_accessory", "bag": "wearable_accessory",
}


def _words(topic: str) -> list[str]:
    return re.sub(r"[^a-z0-9 ]+", " ", (topic or "").replace("_", " ").lower()).split()


def cues_for(topic: str) -> list[Cue]:
    words = set(_words(topic))
    return [c for c in CUES if words & set(c.words)]


# #139: what makes a topic a quote-class asset, read deterministically from the topic itself.
# Wikipedia-style qualifiers name the class outright; a quoted span is dialogue; an
# exclamation or question in a meme / internet-moment title is how catchphrases are titled.
_QUOTE_QUALIFIERS: tuple[tuple[str, str], ...] = (
    ("catchphrase", "slogan"), ("slogan", "slogan"), ("advertising slogan", "slogan"),
    ("tagline", "slogan"), ("motto", "slogan"), ("phrase", "slogan"), ("saying", "slogan"),
    ("expression", "slogan"), ("quotation", "dialogue"), ("quote", "dialogue"),
    ("line", "dialogue"), ("song", "lyric"), ("single", "lyric"),
)
_QUOTED = re.compile(r"[\"\u201c\u201d]([^\"\u201c\u201d]{3,120})[\"\u201c\u201d]")
_QUALIFIER = re.compile(r"\(([^)]*)\)")


def quote_tokens(topic: str, domain: str) -> list[rights.ProtectedToken]:
    """Dialogue, lyric and slogan/catchphrase tokens a topic carries (#139).

    Declared at filing, like the title token, so the listing screen has the phrase itself to
    look for -- the radar may record it as evidence of the humour or moment, and copy may not
    carry it without a recorded clearance.
    """
    cls_of = {"slogan": rights.SLOGAN, "dialogue": rights.DIALOGUE, "lyric": rights.LYRIC}
    out: list[rights.ProtectedToken] = []
    label = _QUALIFIER.sub(" ", topic.replace("_", " ")).strip(" \"\u201c\u201d")
    for quoted in _QUOTED.findall(topic.replace("_", " ")):
        out.append(rights.ProtectedToken(text=quoted.strip(), asset_class=rights.DIALOGUE,
                                         source="declared at filing: quoted span"))
    for qualifier in _QUALIFIER.findall(topic.replace("_", " ")):
        q = qualifier.strip().lower()
        hit = next((cls for word, cls in _QUOTE_QUALIFIERS
                    if q == word or q.endswith(" " + word)), None)
        if hit and label:
            out.append(rights.ProtectedToken(text=label, asset_class=cls_of[hit],
                                             source=f"declared at filing: ({q})"))
    if not out and domain in ("meme", "internet_moment") and label \
            and label.rstrip().endswith(("!", "?")) and len(label.split()) >= 2:
        out.append(rights.ProtectedToken(text=label.rstrip("!? "), asset_class=rights.SLOGAN,
                                         source="declared at filing: exclaimed meme title"))
    return out


def file_topic(topic: str, placed_domain: str = "") -> dict:
    """Which domain a topic is filed under and what it declares as protected.

    Filed by the classifier when it placed the topic, by the cue table otherwise, and not at
    all when neither can -- an unfiled topic is reported, never given a domain.
    """
    cues = cues_for(topic)
    domain = placed_domain if placed_domain in radar.DOMAINS else ""
    if not domain and cues:
        domain = cues[0].domain
    if not domain:
        return {"filed": False, "cues": [],
                "reason": ("neither the classifier nor the cue table can file this topic. "
                           "It is kept as a reading and not treated as a cultural signal")}
    words = _words(topic)
    cue_words = {w for c in cues for w in c.words}
    generic = bool(words) and all(w in cue_words or w in GENERIC_WORDS for w in words)
    tokens: list[rights.ProtectedToken] = []
    if not generic and (placed_domain or domain in PROPERTY_DOMAINS):
        # Conservative by construction: a title this module cannot read is declared as
        # protected, so an unread property reaches the original lane rather than production.
        label = re.sub(r"\s*\(.*?\)\s*", " ", topic.replace("_", " ")).strip()
        cls = (rights.CHARACTER_NAME if domain == "celebrity_aesthetic"
               else rights.WORK_TITLE)
        tokens.append(rights.ProtectedToken(text=label, asset_class=cls,
                                            source="declared at filing: unread title"))
    if not generic:
        tokens.extend(quote_tokens(topic, domain))
    return {"filed": True, "domain": domain, "cues": cues, "tokens": tokens,
            "generic": generic}


# ---------------------------------------------------------------------------
# Dates


def days_to_occasion(occasion: tuple[int, int] | None, today: date) -> int | None:
    if not occasion:
        return None
    month, day = occasion
    target = date(today.year, month, day)
    if target < today:
        target = date(today.year + 1, month, day)
    return (target - today).days


def _occasion(cues: list[Cue]) -> tuple[int, int] | None:
    return next((c.occasion for c in cues if c.occasion), None)


# ---------------------------------------------------------------------------
# Scoring from what has been observed (#136)


def observations_for(db, signal_key: str, *, cues: list[Cue], lane: str,
                     first_seen: str, today: date) -> tuple[dict, dict]:
    """The components something actually observed, with where each value came from.

    An unobserved component is left out, never zeroed: `score.score` names it absent and
    reports the evidence weight beside the number.
    """
    obs: dict = {}
    why: dict = {}

    moment = radar.momentum(db, signal_key, channel=REFERENCE_CHANNEL)
    series = [p for p in radar._series(db, signal_key) if p["channel"] == REFERENCE_CHANNEL]
    if series:
        # Each reference reading is today's views as a share of the window's own peak, so
        # 1.0 is a topic at its highest in four weeks and 0.2 one well past it.
        obs["search_momentum"] = round(float(series[-1]["interest"]), 4)
        why["search_momentum"] = (f"latest reference reading ({series[-1]['on']}), "
                                  f"{moment.get('direction', 'one reading')}")

    mem = radar.memory(db)
    if signal_key in mem["recurring_annually"]:
        obs["recurrence"] = 1.0
        why["recurrence"] = f"seen again: {mem['recurrence_evidence'][signal_key]}"
    elif first_seen and (today - date.fromisoformat(first_seen)).days > 400:
        obs["recurrence"] = 0.0
        why["recurrence"] = "first seen over 400 days ago and not seen again the next year"

    days = days_to_occasion(_occasion(cues), today)
    if days is None:
        obs["make_time_window"] = 1.0
        why["make_time_window"] = "no dated occasion closes this territory"
    else:
        floor = radar.MIN_WINDOW_DAYS
        obs["make_time_window"] = round(max(0.0, min(1.0, (days - floor) / 40.0)), 3)
        why["make_time_window"] = f"{days} days to the occasion against a {floor}-day floor"
        obs["seasonal_fit"] = (1.0 if floor <= days <= 120 else
                               0.5 if 120 < days <= 200 else 0.2 if days > 200 else 0.0)
        why["seasonal_fit"] = f"{days} days before a date people already buy for"

    obs["rights_feasibility"] = 1.0 if lane == rights.DIRECT else 0.5
    why["rights_feasibility"] = (
        "nothing protected, or a recorded basis" if lane == rights.DIRECT else
        "original lane: the territory is sellable, the property is not")

    families = {f for c in cues for f in c.families}
    if families:
        obs["crochet_translatability"] = 1.0
        why["crochet_translatability"] = f"maps onto crochet families {sorted(families)}"
        roles = {FAMILY_ROLE[f] for f in families if f in FAMILY_ROLE}
        obs["product_family_potential"] = round(min(1.0, len(roles) / 5.0), 3)
        why["product_family_potential"] = f"collection roles fillable: {sorted(roles)}"
    return obs, why


# ---------------------------------------------------------------------------
# Persistence helpers


def _existing_basis(db, signal_key: str) -> rights.Basis | None:
    from sqlalchemy import select

    from ..core.models import CultureSignal

    with db.session() as s:
        row = s.scalar(select(CultureSignal).where(CultureSignal.key == signal_key))
        raw = dict(row.basis) if row is not None and row.basis else None
    if not raw or raw.get("kind") not in rights.CLEARANCE_BASES:
        return None
    return rights.Basis(kind=raw["kind"], evidence=raw.get("evidence", ""),
                        recorded_by=raw.get("recorded_by", ""),
                        recorded_on=raw.get("recorded_on", ""), scope=raw.get("scope", ""))


def _signal_row_update(db, signal_key: str, **fields) -> dict:
    from sqlalchemy import select

    from ..core.models import CultureSignal

    with db.session() as s:
        row = s.scalar(select(CultureSignal).where(CultureSignal.key == signal_key))
        if row is None:
            return {}
        for k, v in fields.items():
            if k == "outcome":
                row.outcome = {**(row.outcome or {}), **v}
            else:
                setattr(row, k, v)
        row.updated_at = datetime.now(timezone.utc)
        return {"state": row.state, "first_seen": row.first_seen, "lane": row.lane}


def _signal_snapshot(db, signal_key: str) -> dict:
    from sqlalchemy import select

    from ..core.models import CultureSignal

    with db.session() as s:
        row = s.scalar(select(CultureSignal).where(CultureSignal.key == signal_key))
        if row is None:
            return {}
        return {"key": row.key, "topic": row.topic, "domain": row.domain, "lane": row.lane,
                "state": row.state, "first_seen": row.first_seen,
                "tokens": list(row.protected_tokens or []),
                "sources": list(row.sources or []),
                "primitives": dict(row.primitives or {}), "score": dict(row.score or {}),
                "outcome": dict(row.outcome or {})}


def _tokens_of(snapshot: dict) -> list[rights.ProtectedToken]:
    out = []
    for t in snapshot.get("tokens") or []:
        try:
            out.append(rights.ProtectedToken(text=t["text"], asset_class=t["asset_class"],
                                             source=t.get("source", "")))
        except (KeyError, rights.RightsRefused):
            continue
    return out


def persist_candidate(db, *, signal_key: str, translation: translate.Translation,
                      lane: str, origin: str, tokens: list[rights.ProtectedToken],
                      status: str = CANDIDATE, reason: str = "", priority: str = "standard",
                      detail: dict | None = None) -> dict:
    """Write one translation as a creative-development candidate, or as a kept rejection.

    Idempotent by slug. A premise still carrying a declared token is stored as rejected with
    the refusal, never as a candidate: the rejection is the record (#144).
    """
    from sqlalchemy import select

    from ..core.models import CultureConcept

    detail = {"direct_reference": lane == rights.DIRECT and bool(tokens), **(detail or {})}
    if status == CANDIDATE:
        try:
            rights.check_free_of(f"{translation.slug} {translation.premise}", tokens,
                                 what=f"the {translation.slug!r} translation")
        except rights.RightsRefused as exc:
            status, reason = REJECTED, str(exc)[:500]
    with db.session() as s:
        row = s.scalar(select(CultureConcept).where(CultureConcept.slug == translation.slug))
        if row is not None:
            if priority == "rapid" and row.status == CANDIDATE and row.priority != "rapid":
                row.priority = "rapid"
                row.updated_at = datetime.now(timezone.utc)
                return {"slug": row.slug, "written": False, "reprioritised": True,
                        "status": row.status}
            return {"slug": row.slug, "written": False, "status": row.status}
        s.add(CultureConcept(
            signal_key=signal_key, slug=translation.slug, family=translation.family,
            premise=translation.premise, era=translation.era, theme=translation.theme,
            lane=lane, origin=origin, status=status, stage=STAGE, priority=priority,
            reason=reason, detail=detail))
    return {"slug": translation.slug, "written": True, "status": status}


def candidates(db, *, signal_key: str | None = None, status: str | None = None) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import CultureConcept

    q = select(CultureConcept)
    if signal_key:
        q = q.where(CultureConcept.signal_key == signal_key)
    if status:
        q = q.where(CultureConcept.status == status)
    with db.session() as s:
        return [{"id": r.id, "signal": r.signal_key, "slug": r.slug, "family": r.family,
                 "premise": r.premise, "era": r.era, "theme": r.theme, "lane": r.lane,
                 "origin": r.origin, "status": r.status, "stage": r.stage,
                 "priority": r.priority, "reason": r.reason, "product_slug": r.product_slug}
                for r in s.scalars(q.order_by(CultureConcept.id))]


# ---------------------------------------------------------------------------
# Translation (#134, #137)


def _slug(*parts: str) -> str:
    return "-".join(re.sub(r"[^a-z0-9]+", "-", p.lower()).strip("-") for p in parts if p)[:160]


def era_combinations(signal_key: str, decomposition: translate.Decomposition,
                     cues: list[Cue]) -> list[translate.Translation]:
    """One original concept per era territory the signal belongs to (#137).

    The era is the reusable part: the same topic next year combines with the same era, and
    the form comes from the object the signal's own primitives name, or its first family.
    """
    eras = list(dict.fromkeys(e for c in cues for e in c.eras))
    families = [f for c in cues for f in c.families]
    if not eras or not families:
        return []
    family = next((f for c in cues if "object_category" in c.primitives
                   for f in c.families), families[0])
    theme = next((t for c in cues for t in c.themes), "")
    feeling = (decomposition.primitives.get("emotion")
               or translate.THEMES.get(theme, "") or "the feeling of the season")
    out = []
    for era in eras:
        premise = (f"{FAMILY_FORM[family]}, in the {era.replace('_', ' ')} territory "
                   f"({translate.ERAS[era]}), carrying {feeling}")
        out.append(translate.Translation(slug=_slug(signal_key, era, family), family=family,
                                         premise=premise, theme=theme, era=era))
    return out


def tournament_translations(signal_key: str, decomposition: translate.Decomposition,
                            cues: list[Cue]) -> list[translate.Translation]:
    """#138's broad field: one materially different premise per product family."""
    era = decomposition.primitives.get("era") or next(
        (e for c in cues for e in c.eras), "")
    theme = next((t for c in cues for t in c.themes), "")
    feeling = (decomposition.primitives.get("emotion")
               or translate.THEMES.get(theme, "") or "the feeling of the season")
    ritual = decomposition.primitives.get("ritual", "")
    out = []
    for family in translate.TRANSLATION_FAMILIES:
        premise = (f"{FAMILY_FORM[family]} that carries {feeling}"
                   + (f" through {translate.ERAS[era]}" if era else "")
                   + (f", made for {ritual}" if ritual else ""))
        out.append(translate.Translation(slug=_slug(signal_key, "ws", family), family=family,
                                         premise=premise, theme=theme, era=era))
    return out


def decompose(signal_key: str, cues: list[Cue],
              tokens: list[rights.ProtectedToken]) -> translate.Decomposition:
    answers: dict = {}
    for cue in cues:
        for k, v in cue.primitives.items():
            answers.setdefault(k, v)
    era = next((e for c in cues for e in c.eras), "")
    if era:
        answers.setdefault("era", era)
    return translate.decompose(signal_key, answers, tokens)


# ---------------------------------------------------------------------------
# One signal, end to end


def process_signal(db, *, signal_key: str, topic: str, source: str, observed_on: str,
                   placed_domain: str = "", today: date | None = None) -> dict:
    """Translate, score, clear, era-combine, check the exit and persist -- for one signal."""
    today = today or date.today()
    filed = file_topic(topic, placed_domain)
    if not filed["filed"]:
        return {"signal": signal_key, "filed": False, "reason": filed["reason"]}
    cues: list[Cue] = filed["cues"]
    tokens: list[rights.ProtectedToken] = filed["tokens"]

    # Clearance (#135): recorded once, with any basis already on the record kept rather than
    # reset by the next sweep.
    basis = _existing_basis(db, signal_key)
    recorded = radar.record(db, radar.Signal(
        key=signal_key, topic=topic, domain=filed["domain"], tokens=tuple(tokens),
        sources=(source,) if source else (f"culture.sweep:{observed_on}",),
        first_seen=observed_on), basis=basis)
    routing = recorded["routing"]
    lane = routing["lane"]

    # Translation (#134).
    try:
        dec = decompose(signal_key, cues, tokens)
    except (rights.RightsRefused, translate.TranslationRefused) as exc:
        _signal_row_update(db, signal_key, primitives={"refused": str(exc)[:400]})
        return {"signal": signal_key, "filed": True, "lane": lane, "translated": False,
                "reason": str(exc)[:300]}
    _signal_row_update(db, signal_key, primitives=dec.to_dict())
    if not dec.primitives:
        # Recorded and routed, never given invented primitives: the cue table cannot read
        # this topic, and a model that could is closed. The signal waits, remembered.
        return {"signal": signal_key, "filed": True, "domain": filed["domain"], "lane": lane,
                "protected": [t.text for t in tokens], "translated": False,
                "reason": ("no cue in the deterministic table reads this topic, so none of "
                           "the ten primitives can be supplied without inventing them")}

    snap = _signal_snapshot(db, signal_key)
    # Scoring (#136).
    observed, provenance = observations_for(db, signal_key, cues=cues, lane=lane,
                                            first_seen=snap.get("first_seen", ""),
                                            today=today)
    opp = scoring.score(signal_key, observed)
    scored = {k: v for k, v in opp.to_dict().items() if k != "meaning"}
    scored["provenance"] = provenance
    scored["scored_on"] = today.isoformat()
    _signal_row_update(db, signal_key, score=scored)

    # Era combination (#137).
    combos = era_combinations(signal_key, dec, cues)

    # Exit (#145), before anything new is committed to a closing window.
    days = days_to_occasion(_occasion(cues), today)
    exit_result = radar.exit_check(db, signal_key, days_to_event=days,
                                   channel=REFERENCE_CHANNEL)
    exited = snap.get("state") == radar.EXITED
    exit_recorded = None
    if exit_result["should_exit"] and not exited:
        conditions = ", ".join(r["condition"] for r in exit_result["reasons"])
        reason = (f"exit on {today.isoformat()}: {conditions} "
                  f"({exit_result['reasons']})")[:900]
        lesson = (f"{topic}: capacity moved off this signal because {conditions}; "
                  f"peak reference interest {exit_result['momentum'].get('peak')}")
        exit_recorded = radar.exit_signal(db, signal_key, reason, lesson=lesson)
        withdrawn = withdraw_candidates(db, signal_key, reason=f"trend exited: {conditions}")
        exit_recorded["withdrawn_candidates"] = withdrawn
        exited = True

    # Persist (#144): translations as candidates, or as rejections with the reason.
    written = []
    for t in combos:
        if exited:
            got = persist_candidate(
                db, signal_key=signal_key, translation=t, lane=lane,
                origin="era_combination", tokens=tokens, status=REJECTED,
                reason="the signal's window has closed; not developed (#145)")
        else:
            got = persist_candidate(db, signal_key=signal_key, translation=t, lane=lane,
                                    origin="era_combination", tokens=tokens)
        written.append(got)
    if not exited and any(w["status"] == CANDIDATE for w in written):
        with_state = _signal_snapshot(db, signal_key)
        if with_state.get("state") == radar.OBSERVED:
            _signal_row_update(db, signal_key, state=radar.TRANSLATED)

    return {"signal": signal_key, "filed": True, "domain": filed["domain"], "lane": lane,
            "protected": [t.text for t in tokens], "translated": True,
            "primitives_absent": dec.absent, "score": opp.score,
            "evidence_weight": round(opp.evidence_weight, 3),
            "gate_failures": opp.gate_failures, "actionable": opp.actionable,
            "strong": is_strong(opp), "days_to_occasion": days,
            "era_candidates": [w["slug"] for w in written if w["written"]],
            "exit": exit_recorded, "should_exit": exit_result["should_exit"]}


def is_strong(opp: scoring.Opportunity) -> bool:
    return (not opp.gate_failures and opp.evidence_weight >= scoring.MIN_EVIDENCE_WEIGHT
            and opp.score >= STRONG)


def withdraw_candidates(db, signal_key: str, *, reason: str) -> int:
    from sqlalchemy import select

    from ..core.models import CultureConcept

    n = 0
    with db.session() as s:
        for row in s.scalars(select(CultureConcept).where(
                CultureConcept.signal_key == signal_key,
                CultureConcept.status == CANDIDATE)):
            row.status = WITHDRAWN
            row.reason = reason[:500]
            row.updated_at = datetime.now(timezone.utc)
            n += 1
    return n


# ---------------------------------------------------------------------------
# The white-space tournament (#138) and the rapid cell (#141)


def white_space_tournament(db, signal_key: str, *, priority: str = "standard",
                           origin: str = "white_space") -> dict:
    """A broad field of original translations for one strong signal, persisted."""
    snap = _signal_snapshot(db, signal_key)
    if not snap:
        return {"signal": signal_key, "ran": False, "reason": "no such signal"}
    if snap["state"] == radar.EXITED:
        return {"signal": signal_key, "ran": False, "reason": "the signal has exited"}
    tokens = _tokens_of(snap)
    cues = cues_for(snap["topic"])
    try:
        dec = decompose(signal_key, cues, tokens)
    except (rights.RightsRefused, translate.TranslationRefused) as exc:
        return {"signal": signal_key, "ran": False, "reason": str(exc)[:300]}
    field_ = tournament_translations(signal_key, dec, cues)
    breadth = translate.white_space(signal_key, field_, tokens)

    # Novelty against what is already in development: a premise another signal already put
    # forward is the same idea arriving twice, and is kept as a rejection saying so.
    existing = {c["premise"].lower().strip(): c["slug"] for c in candidates(db)
                if c["signal"] != signal_key}
    written = []
    for t in field_:
        dup = existing.get(t.premise.lower().strip())
        written.append(persist_candidate(
            db, signal_key=signal_key, translation=t, lane=snap["lane"], origin=origin,
            tokens=tokens, priority=priority,
            status=REJECTED if dup else CANDIDATE,
            reason=f"same premise as {dup}" if dup else "",
            detail={"broad_enough": breadth["broad_enough"]}))
    _signal_row_update(db, signal_key, outcome={"white_space": {
        k: breadth[k] for k in ("translations", "families", "family_count",
                                "distinct_premises", "broad_enough", "missing_families")}})
    return {"signal": signal_key, "ran": True, "breadth": breadth,
            "written": sum(1 for w in written if w["written"] and w["status"] == CANDIDATE),
            "rejected": sum(1 for w in written if w["written"] and w["status"] == REJECTED),
            "reprioritised": sum(1 for w in written if w.get("reprioritised"))}


def rapid_response(db, signal_key: str, *, today: date | None = None) -> dict:
    """The rapid cell for one actionable, dated signal (#141).

    Speed is bought only through `rapid.check`, with no bypass: research, the tournament,
    feasibility and prototyping are started now and marked `rapid` so creative development
    takes them first. Every gate after that point is unchanged, and the cell never writes
    past the creative-development stage.
    """
    permitted = [rapid.check(f"{signal_key}:{a}", accelerates=a) for a in RAPID_ACCELERATES]
    tournament = white_space_tournament(db, signal_key, priority="rapid",
                                        origin="rapid_response")
    # Anything already in development for this signal moves to the front too.
    from sqlalchemy import select

    from ..core.models import CultureConcept

    with db.session() as s:
        for row in s.scalars(select(CultureConcept).where(
                CultureConcept.signal_key == signal_key,
                CultureConcept.status == CANDIDATE)):
            row.priority = "rapid"
    record = {"signal": signal_key, "on": (today or date.today()).isoformat(),
              "accelerated": [p["accelerates"] for p in permitted],
              "gates_unchanged": permitted[0]["gates_unchanged"],
              "tournament": {k: tournament.get(k)
                             for k in ("ran", "written", "rejected", "reason")}}
    _signal_row_update(db, signal_key, outcome={"rapid_response": record})
    return record


# ---------------------------------------------------------------------------
# Collection architecture (#143) and owned IP (#146)


def collection_plans(db) -> list[dict]:
    """For each franchise-free theme with candidates, which collection roles are filled."""
    by_theme: dict[str, dict] = {}
    for c in candidates(db, status=CANDIDATE):
        if not c["theme"] or c["theme"] not in translate.THEMES:
            continue
        role = FAMILY_ROLE.get(c["family"])
        if not role:
            continue
        roles = by_theme.setdefault(c["theme"], {})
        roles.setdefault(role, c["slug"])
    plans = []
    for theme, roles in sorted(by_theme.items()):
        filled = dict(roles)
        base = [r for r in translate.COLLECTION_ROLES if r != "bundle" and r in filled]
        if len(base) >= 3:
            # A bundle is the collection sold together; it exists once three of its parts do.
            filled["bundle"] = "+".join(filled[r] for r in base[:3])
        plan = translate.collection(theme, filled)
        plans.append(plan)
    return plans


def propose_ip(db, plans: list[dict]) -> list[dict]:
    """Propose owned elements the evidence supports, and nothing else (#146).

    Two sources, both checked by `cast.propose` against every protected token of every
    signal that contributed: a collection world for a theme whose collection has every role
    filled, and a motif or character for a primitive recurring across two or more signals.
    Proposed is the ceiling here; recurrence is earned by releases.
    """
    from sqlalchemy import select

    from ..core.models import CultureIPElement, CultureSignal

    with db.session() as s:
        signals = [{"key": r.key, "primitives": dict((r.primitives or {}).get("primitives")
                                                     or {}),
                    "tokens": list(r.protected_tokens or []), "state": r.state}
                   for r in s.scalars(select(CultureSignal))]
        have = {r.key for r in s.scalars(select(CultureIPElement))}
    all_tokens = [t for sig in signals for t in _tokens_of(sig)]

    proposals: list[tuple[cast.Element, list[str], dict]] = []
    for plan in plans:
        if not plan["is_a_collection"]:
            continue
        theme = plan["theme"]
        contributing = sorted({c["signal"] for c in candidates(db, status=CANDIDATE)
                               if c["theme"] == theme})
        derived = {}
        for sig in signals:
            if sig["key"] in contributing:
                for k in ("emotion", "setting", "era", "ritual", "colour_language"):
                    if k in sig["primitives"]:
                        derived.setdefault(k, sig["primitives"][k])
        if not derived:
            continue
        admits = tuple(sorted({c["family"] for c in candidates(db, status=CANDIDATE)
                               if c["theme"] == theme}))
        world = cast.World(key=f"world:{theme}", name=theme.replace("_", " ").title(),
                           premise=f"{translate.THEMES[theme]}, as a place products live in",
                           admits=admits)
        element = cast.propose(key=world.key, kind=cast.WORLD, name=world.name,
                               about=f"A collection world where {translate.THEMES[theme]}.",
                               derived_from=derived, declared_tokens=all_tokens)
        proposals.append((element, contributing, {"admits": list(admits),
                                                  "plan_roles": plan["roles_present"]}))

    for primitive, kind in (("visual_motif_class", cast.MOTIF),
                            ("character_archetype", cast.CHARACTER)):
        seen: dict[str, list[str]] = {}
        for sig in signals:
            value = sig["primitives"].get(primitive)
            if value and sig["state"] != radar.EXITED:
                seen.setdefault(value, []).append(sig["key"])
        for value, keys in seen.items():
            if len(keys) < 2:
                continue
            element = cast.propose(
                key=f"{kind}:{_slug(value)}"[:120], kind=kind,
                name=f"Brambleloop {value}"[:160],
                about=f"An owned {kind} drawn from the {primitive.replace('_', ' ')} "
                      f"'{value}', recurring across {len(keys)} cultural signals.",
                derived_from={primitive: value}, declared_tokens=all_tokens)
            proposals.append((element, sorted(keys), {"recurring_primitive": primitive}))

    written = []
    for element, contributing, extra in proposals:
        if element.key in have:
            continue
        with db.session() as s:
            s.add(CultureIPElement(key=element.key, kind=element.kind, name=element.name,
                                   about=element.about, derived_from=element.derived_from,
                                   signals=contributing, status=element.status,
                                   appearances=[], detail=extra))
        have.add(element.key)
        written.append(element.to_dict())
    return written


def roster(db) -> dict:
    from sqlalchemy import select

    from ..core.models import CultureIPElement

    with db.session() as s:
        rows = [{"key": r.key, "kind": r.kind, "name": r.name, "status": r.status,
                 "signals": list(r.signals or []), "appearances": len(r.appearances or [])}
                for r in s.scalars(select(CultureIPElement))]
    return {"elements": rows, "proposed": sum(1 for r in rows if r["status"] == "proposed"),
            "recurring": sum(1 for r in rows if r["status"] == "recurring")}


def ip_direction(db) -> dict:
    """Borrowed against owned candidates by month, through `cast.dependence` (#146)."""
    by_month: dict[str, dict] = {}
    from sqlalchemy import select

    from ..core.models import CultureConcept

    with db.session() as s:
        for r in s.scalars(select(CultureConcept).where(
                CultureConcept.status != REJECTED)):
            month = (r.at or datetime.now(timezone.utc)).strftime("%Y-%m")
            entry = by_month.setdefault(month, {"period": month, "borrowed": 0, "owned": 0})
            entry["borrowed" if (r.detail or {}).get("direct_reference")
                  else "owned"] += 1
    return cast.dependence([by_month[k] for k in sorted(by_month)])


# ---------------------------------------------------------------------------
# Launch outcomes (#144)


def record_launch_outcomes(db) -> dict:
    """Attach measured listing outcomes to the signals whose concepts became products.

    A concept launches when a product carries its slug (or names it in `product_slug`).
    Nothing has launched, and that is reported as a count of zero launches rather than as
    an outcome of zero.
    """
    from sqlalchemy import select

    from ..core.models import CultureConcept, ListingOutcome, Product

    launched: dict[str, list] = {}
    with db.session() as s:
        slugs = {p.slug for p in s.scalars(select(Product))}
        for row in s.scalars(select(CultureConcept).where(
                CultureConcept.status.in_((CANDIDATE, LAUNCHED)))):
            product = row.product_slug or (row.slug if row.slug in slugs else "")
            if not product or product not in slugs:
                continue
            outcomes = [{"period_start": o.period_start, "period_end": o.period_end,
                         "impressions": o.impressions, "visits": o.visits,
                         "orders": o.orders, "favourites": o.favourites}
                        for o in s.scalars(select(ListingOutcome).where(
                            ListingOutcome.product_slug == product))]
            row.status = LAUNCHED
            row.product_slug = product
            launched.setdefault(row.signal_key, []).append(
                {"concept": row.slug, "product": product, "outcomes": outcomes,
                 "measured": bool(outcomes)})
    for key, items in launched.items():
        _signal_row_update(db, key, state=radar.LAUNCHED, outcome={"launches": items})
    return {"signals_with_launches": len(launched),
            "launches": sum(len(v) for v in launched.values())}


# ---------------------------------------------------------------------------
# The clearance lane, when somebody records a basis (#135)


def clear(db, signal_key: str, *, kind: str, evidence: str, recorded_by: str,
          scope: str = "", publication_year: int | None = None) -> dict:
    """Record a basis for direct use, re-routing the signal. Refusals leave it original."""
    snap = _signal_snapshot(db, signal_key)
    if not snap:
        raise rights.RightsRefused(f"no culture signal {signal_key!r}")
    basis = rights.record_basis(kind, evidence=evidence, recorded_by=recorded_by,
                                scope=scope, publication_year=publication_year)
    got = radar.record(db, radar.Signal(
        key=signal_key, topic=snap["topic"], domain=snap["domain"],
        tokens=tuple(_tokens_of(snap)),
        sources=tuple(snap.get("sources") or ()) + (f"clearance:{recorded_by}",)),
        basis=basis)
    if got["routing"]["lane"] == rights.DIRECT:
        from sqlalchemy import select

        from ..core.models import CultureConcept

        with db.session() as s:
            for row in s.scalars(select(CultureConcept).where(
                    CultureConcept.signal_key == signal_key)):
                row.lane = rights.DIRECT
    return {"signal": signal_key, "routing": got["routing"]}


# ---------------------------------------------------------------------------
# The sweep stage


def run(db, readings: list[dict], *, placed: dict | None = None,
        today: date | None = None) -> dict:
    """Everything the sweep does with the signals it just stored, in order.

    Per signal: translate, score, clear, era-combine, check the exit and persist. Then, over
    the whole radar: the white-space tournament for strong signals, the rapid cell for
    actionable dated ones, collection architecture per theme, owned-IP proposals and launch
    outcomes. Nothing here writes past creative development.
    """
    today = today or date.today()
    placed = placed or {}
    processed, unfiled = [], []
    for reading in readings:
        got = process_signal(db, signal_key=reading["signal_key"], topic=reading["article"],
                             source=reading.get("source", ""),
                             observed_on=reading.get("observed_on") or today.isoformat(),
                             placed_domain=placed.get(reading["article"], ""), today=today)
        (processed if got.get("filed") else unfiled).append(got)

    tournaments, rapid_runs = [], []
    for got in processed:
        if not got.get("translated") or got.get("should_exit"):
            continue
        if got["actionable"] and got["days_to_occasion"] is not None:
            rapid_runs.append(rapid_response(db, got["signal"], today=today))
        elif got["strong"]:
            tournaments.append(white_space_tournament(db, got["signal"]))

    plans = collection_plans(db)
    proposed = propose_ip(db, plans)
    launches = record_launch_outcomes(db)
    return {
        "signals": len(processed), "unfiled": [u["signal"] for u in unfiled],
        "translated": sum(1 for p in processed if p.get("translated")),
        "original_lane": sum(1 for p in processed if p.get("lane") == rights.ORIGINAL),
        "exits": [p["signal"] for p in processed if p.get("exit")],
        "strong": [p["signal"] for p in processed if p.get("strong")],
        "tournaments": tournaments, "rapid": rapid_runs,
        "collections": [{"theme": p["theme"], "is_a_collection": p["is_a_collection"],
                         "roles_missing": p["roles_missing"]} for p in plans],
        "ip_proposed": [e["key"] for e in proposed],
        "launches": launches,
        "candidates": len(candidates(db, status=CANDIDATE)),
        "processed": processed,
    }
