"""ENG-DEMAND-SUPPLY: a demand score computed from stored market evidence only.

The problem (production, 2026-11-20). The concept pool had 34 concepts: 16 drafted, 18 held,
0 promotable undrafted. Engine convenience chose what entered engineering (flat décor and
seasonal pieces, the shapes the first engines could make), so the catalogue became coasters,
garlands and placemats. Meanwhile the observed market buys chunky low-sew amigurumi, baby
items, cushions and clothing (TEARDOWN_HIGHLAND_COW_AMIGURUMI, TEARDOWN_MADELINEMAECO_CAPYBARA,
D-OWNER-CORE-FAMILIES).

This module scores demand per **cluster** (family / form / subject) from what the factory
has already recorded. It makes no network call and no model call, and it never invents a
signal:

* ``benchmark_listings`` (the nine research shops' scanned catalogues):
  - ``num_favorers``: the favourites level;
  - ``favorers_history``: favourites velocity, only from two or more dated readings;
  - ``review_count`` / ``review_history``: reviews and their velocity, only where a scan stored
    them per listing;
  - ``is_bestseller`` and ``in_baskets``: only where a scan stored them;
  - ``last_seen``: the recency weight.
* ``serp_snapshots``: the rank attention a cluster holds in captured marketplace searches
  (1/sqrt(rank), so rank 1 = 1.0).
* ``TEARDOWN_OBSERVATIONS``: the dated facts the owner recorded at purchase for the two
  benchmark teardowns (bestseller, review count, "in 20+ baskets"). Only numbers and the
  cluster are stored here, never a competitor title or design.

**UNKNOWN is never zero.** A signal that was never observed takes no part in the value. It
lowers the *confidence* instead, and the evidence score shrinks toward a low prior (`PRIOR`)
as confidence falls. So a cluster with no evidence scores the prior: never 0 (which would read
as "measured no demand"), and never high (which would read as demand nobody saw).

**The owner core-family boost** (D-OWNER-CORE-FAMILIES, "the shop's huge hits") is added on
top, in the owner's order: amigurumi/stuffed animals, baby, pillows/cushions, then garments.
The boost is scaled by confidence (half the boost at zero confidence, the full boost when
measured). Core families therefore lead on equal evidence, but a core cluster nobody observed
cannot outrank a strongly measured one.

Flat décor and seasonal pieces get no boost. They lead only when the evidence ranks them.

Everything is deterministic: the same rows give the same scores, byte for byte.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# ---- the taxonomy: family / form / subject ------------------------------------------------

AMIGURUMI, BABY, PILLOW, GARMENT = "amigurumi", "baby", "pillow_cushion", "garment"
# D-OWNER-CORE-FAMILIES: the owner named exactly three permanent core families.
CORE_FAMILIES: tuple[str, ...] = (AMIGURUMI, BABY, PILLOW)   # the owner's order
# Strictly decreasing in the owner's order, so equal evidence ranks them in that order.
CORE_BOOST: dict[str, float] = {AMIGURUMI: 0.30, BABY: 0.26, PILLOW: 0.22}
# Review b18-a B-1: garments carry a smaller routine (non-owner) weighting, recorded in
# D-ENG-DEMAND-SUPPLY. They are NOT core: every reading labels them `core: False`.
SECONDARY_BOOST: dict[str, float] = {GARMENT: 0.18}
# The families either boost names (the owner's three, then the routine secondary weighting).
BOOSTED_FAMILIES: tuple[str, ...] = CORE_FAMILIES + tuple(SECONDARY_BOOST)


def family_boost(family: str) -> float:
    """The full-confidence boost for a family: owner core first, else the secondary weight."""
    return CORE_BOOST.get(family, SECONDARY_BOOST.get(family, 0.0))

# Ordered: the first family whose words match wins. A lovey is a baby item even though it has
# an animal head; a baby cardigan is a garment (clothing); a cushion with a face is a cushion.
_FAMILY_WORDS: tuple[tuple[str, str], ...] = (
    (BABY, r"\b(?:lovey|loveys|comforter|security blanket|snuggle square|rattle|teether|"
           r"pacifier clip)\b"),
    (GARMENT, r"\b(?:cardigan|sweater|jumper|pullover|vest|tank|tee|t-shirt|top|dress|"
              r"romper|cardi|shrug|bolero|poncho|kimono|jacket|coat|hoodie|skirt|"
              r"sweatshirt|garment|clothing|hat|hats|beanie|beanies|bonnet|balaclava|"
              r"socks|slippers|mittens|gloves)\b"),
    (PILLOW, r"\b(?:pillow|pillows|cushion|cushions|bolster|pouf|ottoman)\b"),
    (AMIGURUMI, r"\b(?:amigurumi|stuffed|plush|plushie|plushies|stuffie|softie|toy|toys|"
                r"doll|keychain)\b"),
    (BABY, r"\b(?:baby|babies|newborn|infant|nursery|bib|bootie|booties|layette|"
           r"swaddle|cocoon)\b"),
    ("blanket", r"\b(?:blanket|throw|afghan|graphghan|granny square blanket)\b"),
    # CLOTHING-E2E: hats, socks and slippers are graded clothing (the wearable engines size
    # them on the CYC head and foot charts), so they read as the garment family; a scarf or
    # cowl is still an accessory.
    ("accessory", r"\b(?:scarf|cowl|shawl|shawlette|wrap|headband|ear warmer|bandana)\b"),
    ("bag", r"\b(?:bag|tote|pouch|purse|clutch|backpack|bucket bag)\b"),
    ("seasonal_decor", r"\b(?:christmas|halloween|easter|valentine|valentines|thanksgiving|"
                       r"garland|ornament|ornaments|stocking|pumpkin|wreath|advent)\b"),
    ("home_decor", r"\b(?:coaster|coasters|placemat|placemats|runner|wall hanging|"
                   r"basket|baskets|dishcloth|washcloth|potholder|trivet|rug|mat|doily|"
                   r"plant hanger|planter|cosy|cozy|bunting)\b"),
)
_CATEGORY_FAMILY: dict[str, str] = {
    "amigurumi": AMIGURUMI, "toy": AMIGURUMI, "baby": BABY, "nursery": BABY,
    "pillow": PILLOW, "cushion": PILLOW, "garment": GARMENT, "blanket": "blanket",
    "mosaic_blanket": "blanket", "graphghan": "blanket", "hat": GARMENT,
    "sock": GARMENT, "slipper": GARMENT, "top": GARMENT, "dress": GARMENT,
    "cardigan": GARMENT, "sweater": GARMENT, "vest": GARMENT,
    "scarf": "accessory", "shawl": "accessory", "bag": "bag",
    "seasonal_decor": "seasonal_decor", "ornament": "seasonal_decor",
    "stocking": "seasonal_decor", "coaster": "home_decor", "placemat": "home_decor",
    "runner": "home_decor", "wall_decor": "home_decor", "basket": "home_decor",
    "flower": "home_decor", "pet": "home_decor", "wedding": "home_decor",
}
# The research pods that name a family outright (intel.pods keys).
_POD_FAMILY: dict[str, str] = {"amigurumi": AMIGURUMI, "baby": BABY, "garments": GARMENT,
                               "garment": GARMENT, "pillows": PILLOW, "blankets": "blanket",
                               "seasonal": "seasonal_decor", "accessories": "accessory",
                               "bags": "bag", "home_decor": "home_decor"}

_FORM_WORDS: dict[str, tuple[tuple[str, str], ...]] = {
    AMIGURUMI: (("low_sew", r"\b(?:no[- ]?sew|low[- ]?sew|minimal sew(?:ing)?)\b"),
                ("chunky", r"\b(?:chunky|chenille|jumbo|giant|big|velvet|plushy)\b"),
                ("mini", r"\b(?:mini|tiny|pocket|keychain|small)\b")),
    BABY: (("lovey", r"\b(?:lovey|loveys|comforter|security blanket|snuggle square)\b"),
           ("blanket", r"\b(?:blanket|swaddle|cocoon|afghan)\b"),
           ("hat", r"\b(?:hat|bonnet|beanie)\b"),
           ("booties", r"\b(?:bootie|booties|socks|shoes)\b"),
           ("toy", r"\b(?:rattle|teether|toy|amigurumi|plush)\b")),
    PILLOW: (("character", r"\b(?:cow|bear|bunny|cat|dog|frog|fox|animal|face|duck|"
                           r"capybara|sheep|lamb|pig|chick|owl|penguin)\b"),
             ("floor", r"\b(?:floor|pouf|ottoman|bolster)\b")),
    GARMENT: (("cardigan", r"\b(?:cardigan|cardi|shrug|bolero|jacket|coat|kimono)\b"),
              ("sweater", r"\b(?:sweater|jumper|pullover|sweatshirt|hoodie)\b"),
              ("vest", r"\b(?:vest|tank|slipover)\b"),
              ("top", r"\b(?:top|tee|t-shirt|cami)\b"),
              ("dress", r"\b(?:dress|romper|skirt)\b"),
              ("hat", r"\b(?:hats?|beanies?|bonnet|balaclava)\b"),
              ("footwear", r"\b(?:socks|slippers)\b")),
}
DEFAULT_FORM = "standard"

# Subjects: the animal or character a product is (an original design takes the subject, never
# a competitor's character or name). Order matters for compound words ("highland cow").
_SUBJECTS: tuple[tuple[str, str], ...] = (
    ("highland_cow", r"\bhighland\s+cow\b"), ("capybara", r"\bcapybaras?\b"),
    ("axolotl", r"\baxolotls?\b"), ("bear", r"\b(?:bear|bears|teddy)\b"),
    ("bunny", r"\b(?:bunny|bunnies|rabbit|rabbits|hare)\b"), ("cow", r"\b(?:cow|cows)\b"),
    ("cat", r"\b(?:cat|cats|kitten|kitty)\b"), ("dog", r"\b(?:dog|dogs|puppy|pup)\b"),
    ("fox", r"\bfox(?:es)?\b"), ("frog", r"\bfrogs?\b"), ("duck", r"\b(?:duck|ducks|duckling)\b"),
    ("penguin", r"\bpenguins?\b"), ("octopus", r"\b(?:octopus|octopi)\b"),
    ("whale", r"\bwhales?\b"), ("dinosaur", r"\b(?:dino|dinos|dinosaur|dinosaurs)\b"),
    ("dragon", r"\bdragons?\b"), ("elephant", r"\belephants?\b"), ("giraffe", r"\bgiraffes?\b"),
    ("lion", r"\blions?\b"), ("sheep", r"\b(?:sheep|lamb|lambs)\b"), ("pig", r"\b(?:pig|piglet)s?\b"),
    ("hedgehog", r"\bhedgehogs?\b"), ("owl", r"\bowls?\b"), ("bee", r"\b(?:bee|bees|bumblebee)\b"),
    ("turtle", r"\b(?:turtle|tortoise)s?\b"), ("mouse", r"\b(?:mouse|mice)\b"),
    ("unicorn", r"\bunicorns?\b"), ("chick", r"\bchicks?\b"), ("seal", r"\bseals?\b"),
    ("otter", r"\botters?\b"), ("sloth", r"\bsloths?\b"), ("koala", r"\bkoalas?\b"),
    ("panda", r"\bpandas?\b"), ("snail", r"\bsnails?\b"), ("mushroom", r"\bmushrooms?\b"),
    ("fruit", r"\b(?:strawberry|strawberries|cherry|lemon|avocado|banana|peach)\b"),
    ("ghost", r"\bghosts?\b"),
)
ANY = "*"
GENERAL = "general"


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[_]+", " ", str(text or "").lower())).strip()


@dataclass(frozen=True)
class Cluster:
    family: str
    form: str
    subject: str

    @property
    def key(self) -> str:
        return f"{self.family}/{self.form}/{self.subject}"

    def levels(self) -> tuple[tuple[str, str, str], ...]:
        """The cluster and its two parents, most specific first."""
        return ((self.family, self.form, self.subject), (self.family, self.form, ANY),
                (self.family, ANY, ANY))


def classify(title: str = "", *, category: str = "", tags=(), pod: str = "") -> Cluster:
    """The cluster a title (and its category, tags and pod) belongs to. Deterministic."""
    text = _fold(" ".join([str(title or ""), " ".join(str(t) for t in tags or ())]))
    family = None
    for fam, rx in _FAMILY_WORDS:
        if re.search(rx, text):
            family = fam
            break
    if family is None:
        family = (_CATEGORY_FAMILY.get(str(category or ""))
                  or _POD_FAMILY.get(str(pod or "")) or "other")
    # A category or pod that names a core family outranks a weaker word match (an
    # "amigurumi" category concept titled "... Cosy Bear" is amigurumi, not home décor).
    strong = _CATEGORY_FAMILY.get(str(category or "")) or _POD_FAMILY.get(str(pod or ""))
    if strong in BOOSTED_FAMILIES and family not in BOOSTED_FAMILIES:
        family = strong
    form = DEFAULT_FORM
    for name, rx in _FORM_WORDS.get(family, ()):
        if re.search(rx, text):
            form = name
            break
    subject = GENERAL
    for name, rx in _SUBJECTS:
        if re.search(rx, text):
            subject = name
            break
    return Cluster(family, form, subject)


# ---- signals ------------------------------------------------------------------------------

# Weights sum to 1.0. Velocity outweighs level: a listing gathering favourites now is selling
# now; a large old count may be history.
SIGNAL_WEIGHTS: dict[str, float] = {
    "favourites": 0.20, "favourites_velocity": 0.25, "reviews": 0.15,
    "review_velocity": 0.10, "bestseller": 0.10, "baskets": 0.05, "serp_rank": 0.15,
}
PRIOR = 0.20                    # the evidence score with zero confidence (UNKNOWN, not 0)
HALF_LIFE_DAYS = 30.0           # recency: a reading this old counts half
MAX_AGE_DAYS = 180              # older readings are not current market evidence
SAMPLE_K = 3.0                  # confidence grows as n / (n + SAMPLE_K)
MIN_OBSERVATIONS = 3            # a level with fewer is backed off to its parent
LEVEL_CONFIDENCE = (1.0, 0.85, 0.70)   # exact cluster, family+form, family
# Saturation points (stated, not fitted): where a signal reads as fully strong.
FAV_SATURATION = 2000           # favourites
FAV_VELOCITY_HALF = 2.0         # favourites per day at which the signal reads 0.5
REVIEW_SATURATION = 300
REVIEW_VELOCITY_HALF = 0.5      # reviews per day at which the signal reads 0.5
BASKETS_SATURATION = 20         # "in 20+ baskets"

MEASURED, PARTIAL, UNKNOWN = "MEASURED", "PARTIAL", "UNKNOWN"


def _norm_level(n: float, sat: float) -> float:
    return min(1.0, math.log1p(max(0.0, n)) / math.log1p(sat))


def _norm_rate(v: float, half: float) -> float:
    v = max(0.0, v)
    return v / (v + half)


def _int(v):
    if isinstance(v, bool) or v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _aware(v):
    if v is None:
        return None
    if isinstance(v, str):
        try:
            v = datetime.fromisoformat(v)
        except ValueError:
            return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def velocity(history, key: str = "n") -> float | None:
    """Per-day change between the first and last dated readings; None (UNKNOWN) with fewer
    than two readings or less than a day between them. A falling count is 0, not negative:
    favourites removed are not negative demand."""
    pts = []
    for h in history or ():
        at, n = _aware((h or {}).get("at")), _int((h or {}).get(key))
        if at is not None and n is not None:
            pts.append((at, n))
    if len(pts) < 2:
        return None
    pts.sort()
    days = (pts[-1][0] - pts[0][0]).total_seconds() / 86400.0
    if days < 1.0:
        return None
    return max(0.0, (pts[-1][1] - pts[0][1]) / days)


def listing_signals(detail: dict) -> dict[str, float | None]:
    """Normalised signals from one stored listing's detail. None is UNKNOWN, never 0."""
    d = dict(detail or {})
    fav = _int(d.get("num_favorers"))
    fav_v = velocity(d.get("favorers_history"))
    rev = _int(d.get("review_count"))
    rev_v = velocity(d.get("review_history"))
    best = d.get("is_bestseller")
    baskets = _int(d.get("in_baskets"))
    return {
        "favourites": None if fav is None else _norm_level(fav, FAV_SATURATION),
        "favourites_velocity": None if fav_v is None else _norm_rate(fav_v, FAV_VELOCITY_HALF),
        "reviews": None if rev is None else _norm_level(rev, REVIEW_SATURATION),
        "review_velocity": None if rev_v is None else _norm_rate(rev_v, REVIEW_VELOCITY_HALF),
        "bestseller": None if not isinstance(best, bool) else (1.0 if best else 0.0),
        "baskets": None if baskets is None else min(1.0, baskets / BASKETS_SATURATION),
        "serp_rank": None,
    }


def recency_weight(seen, now: datetime) -> float:
    seen = _aware(seen)
    if seen is None:
        return 0.0
    age = max(0.0, (now - seen).total_seconds() / 86400.0)
    if age > MAX_AGE_DAYS:
        return 0.0
    return 0.5 ** (age / HALF_LIFE_DAYS)


# The owner's recorded teardown facts at purchase (2026-11-20). Numbers and clusters only:
# never a competitor's title, character, wording or design.
TEARDOWN_OBSERVATIONS: tuple[dict, ...] = (
    {"ref": "research/benchmarks/TEARDOWN_HIGHLAND_COW_AMIGURUMI.md", "at": "2026-11-20",
     "cluster": (AMIGURUMI, DEFAULT_FORM, "highland_cow"),
     "detail": {"is_bestseller": True, "review_count": 77, "in_baskets": 20}},
    {"ref": "research/benchmarks/TEARDOWN_MADELINEMAECO_CAPYBARA.md", "at": "2026-11-20",
     "cluster": (AMIGURUMI, "low_sew", "capybara"),
     "detail": {"is_bestseller": True, "review_count": 15, "in_baskets": 20}},
)


# ---- the index ----------------------------------------------------------------------------

@dataclass
class _Agg:
    n: int = 0
    weight: float = 0.0
    sums: dict = field(default_factory=dict)       # signal -> weighted sum of values
    known: dict = field(default_factory=dict)      # signal -> weight of known readings
    shops: set = field(default_factory=set)
    sources: set = field(default_factory=set)

    def add(self, signals: dict, w: float, *, shop: str = "", source: str = "") -> None:
        if w <= 0:
            return
        self.n += 1
        self.weight += w
        if shop:
            self.shops.add(shop)
        if source:
            self.sources.add(source)
        for s, v in signals.items():
            if v is None:
                continue
            self.sums[s] = self.sums.get(s, 0.0) + w * float(v)
            self.known[s] = self.known.get(s, 0.0) + w


def _score(agg: _Agg | None, family: str, level: int) -> dict:
    """The demand reading of one aggregate. Pure arithmetic over the stored readings."""
    signals: dict[str, dict] = {}
    known_w = 0.0
    value_acc = 0.0
    coverage = 0.0
    for s, W in SIGNAL_WEIGHTS.items():
        kw = (agg.known.get(s, 0.0) if agg else 0.0)
        if agg is None or kw <= 0:
            signals[s] = {"value": None, "coverage": 0.0, "status": UNKNOWN}
            continue
        v = agg.sums[s] / kw
        cov = min(1.0, kw / agg.weight) if agg.weight > 0 else 0.0
        signals[s] = {"value": round(v, 4), "coverage": round(cov, 4), "status": MEASURED}
        known_w += W
        value_acc += W * v
        coverage += W * cov
    n = agg.n if agg else 0
    value = (value_acc / known_w) if known_w > 0 else None
    confidence = coverage * (n / (n + SAMPLE_K)) * LEVEL_CONFIDENCE[level] if n else 0.0
    evidence = (confidence * value + (1.0 - confidence) * PRIOR) if value is not None else PRIOR
    boost = family_boost(family) * (0.5 + 0.5 * confidence)
    status = MEASURED if confidence >= 0.5 else PARTIAL if confidence > 0 else UNKNOWN
    return {"score": round(min(1.0, evidence + boost), 4),
            "evidence_score": round(evidence, 4), "value": None if value is None else
            round(value, 4), "confidence": round(confidence, 4), "boost": round(boost, 4),
            "status": status, "observations": n, "signals": signals,
            "shops": sorted(agg.shops) if agg else [],
            "sources": sorted(agg.sources) if agg else []}


class DemandIndex:
    """Every cluster's aggregated readings, built once from the stored rows."""

    def __init__(self, aggs: dict[tuple, _Agg], *, as_of: datetime, basis: dict):
        self.aggs = aggs
        self.as_of = as_of
        self.basis = basis

    def cluster_score(self, cluster: Cluster) -> dict:
        """The most specific level with enough observations; its parents otherwise. A level
        backed off to is labelled, and its confidence discounted (LEVEL_CONFIDENCE)."""
        for level, key in enumerate(cluster.levels()):
            agg = self.aggs.get(key)
            if agg is not None and agg.n >= MIN_OBSERVATIONS:
                out = _score(agg, cluster.family, level)
                break
        else:
            # Nothing has enough observations: the best partial reading, or none.
            level, agg = next(((lv, self.aggs[k]) for lv, k in enumerate(cluster.levels())
                               if k in self.aggs), (2, None))
            out = _score(agg, cluster.family, level)
        out.update(cluster=cluster.key, level=("cluster", "family+form", "family")[level],
                   core=cluster.family in CORE_FAMILIES, as_of=self.as_of.isoformat())
        return out

    def score(self, title: str = "", *, category: str = "", tags=(), pod: str = "") -> dict:
        return self.cluster_score(classify(title, category=category, tags=tags, pod=pod))

    def clusters(self, *, min_observations: int = 1) -> list[dict]:
        """Every exact cluster with readings, ranked by score (then key, for a stable order)."""
        out = []
        for key, agg in self.aggs.items():
            if ANY in key or agg.n < min_observations:
                continue
            out.append(self.cluster_score(Cluster(*key)))
        return sorted(out, key=lambda r: (-r["score"], r["cluster"]))

    def families(self) -> list[dict]:
        out = []
        for key, agg in self.aggs.items():
            if key[1] == ANY and key[2] == ANY:
                out.append({**_score(agg, key[0], 2), "family": key[0],
                            "core": key[0] in CORE_FAMILIES})
        for fam in CORE_FAMILIES:                      # a core family never silently absent
            if not any(r["family"] == fam for r in out):
                out.append({**_score(None, fam, 2), "family": fam, "core": True})
        return sorted(out, key=lambda r: (-r["score"], r["family"]))


def _add(aggs: dict, cluster: Cluster, signals: dict, w: float, **kw) -> None:
    for key in cluster.levels():
        aggs.setdefault(key, _Agg()).add(signals, w, **kw)


def build_index(listings=(), serp=(), *, now: datetime | None = None,
                teardowns=TEARDOWN_OBSERVATIONS) -> DemandIndex:
    """The index from plain rows (testable without a database).

    `listings`: dicts {benchmark_key, title, pod, last_seen, audit_state, detail}.
    `serp`: dicts {query, captured_at, rank_list}."""
    now = _aware(now) or datetime.now(timezone.utc)
    aggs: dict[tuple, _Agg] = {}
    n_listings = n_serp = n_tear = 0
    for row in listings:
        if row.get("audit_state") == "withdrawn":
            continue
        w = recency_weight(row.get("last_seen"), now)
        detail = dict(row.get("detail") or {})
        cluster = classify(row.get("title") or "", tags=detail.get("tags") or (),
                           pod=row.get("pod") or "")
        sig = listing_signals(detail)
        if w > 0 and any(v is not None for v in sig.values()):
            _add(aggs, cluster, sig, w, shop=str(row.get("benchmark_key") or ""),
                 source="benchmark_listings")
            n_listings += 1
    # SERP: the latest snapshot per query within the window; rank attention per entry.
    latest: dict[str, dict] = {}
    for snap in serp:
        q = str(snap.get("query") or "")
        at = _aware(snap.get("captured_at"))
        if not q or at is None:
            continue
        if q not in latest or at > _aware(latest[q]["captured_at"]):
            latest[q] = snap
    for q in sorted(latest):
        snap = latest[q]
        w = recency_weight(snap.get("captured_at"), now)
        qc = classify(q)
        for e in snap.get("rank_list") or []:
            rank = _int((e or {}).get("rank"))
            if rank is None or rank < 1:
                continue
            fam = _POD_FAMILY.get(str(e.get("pod") or "")) or (
                qc.family if qc.family != "other" else None)
            if fam is None:
                continue
            # The query names the form and subject only when it names the same family.
            cluster = (Cluster(fam, qc.form, qc.subject) if fam == qc.family
                       else Cluster(fam, DEFAULT_FORM, GENERAL))
            sig = {s: None for s in SIGNAL_WEIGHTS}
            sig["serp_rank"] = 1.0 / math.sqrt(rank)
            fav = _int(e.get("favourites"))
            if fav is not None:
                sig["favourites"] = _norm_level(fav, FAV_SATURATION)
            _add(aggs, cluster, sig, w, source="serp_snapshots")
            n_serp += 1
    for t in teardowns or ():
        w = recency_weight(t["at"] + "T00:00:00+00:00", now)
        sig = listing_signals(t["detail"])
        if w > 0:
            _add(aggs, Cluster(*t["cluster"]), sig, w, shop="owner_teardown",
                 source=t["ref"])
            n_tear += 1
    return DemandIndex(aggs, as_of=now, basis={
        "listings_read": n_listings, "serp_entries_read": n_serp,
        "teardown_observations": n_tear, "prior": PRIOR, "weights": dict(SIGNAL_WEIGHTS),
        "core_boost": dict(CORE_BOOST), "secondary_boost": dict(SECONDARY_BOOST),
        "rule": "UNKNOWN is never 0: a missing signal lowers confidence and the score "
                "shrinks toward the prior; it never scores high"})


def index(db, *, now: datetime | None = None) -> DemandIndex:
    """The index from the stored rows. Read-only; an unreadable table contributes nothing
    (its readings are UNKNOWN), never an invented value."""
    from sqlalchemy import select

    now = _aware(now) or datetime.now(timezone.utc)
    listings, serp = [], []
    try:
        from ..core.models import BenchmarkListing

        with db.session() as s:
            for r in s.scalars(select(BenchmarkListing)):
                listings.append({"benchmark_key": r.benchmark_key, "title": r.title,
                                 "pod": r.pod, "last_seen": r.last_seen,
                                 "audit_state": r.audit_state, "detail": dict(r.detail or {})})
    except Exception:  # noqa: BLE001 - unreadable: no readings, never invented ones
        listings = []
    try:
        from ..core.models import SerpSnapshot

        since = now - timedelta(days=MAX_AGE_DAYS)
        with db.session() as s:
            for r in s.scalars(select(SerpSnapshot).where(SerpSnapshot.captured_at >= since)):
                serp.append({"query": r.query, "captured_at": r.captured_at,
                             "rank_list": list(r.rank_list or [])})
    except Exception:  # noqa: BLE001
        serp = []
    return build_index(listings, serp, now=now)


def concept_score(ix: DemandIndex, *, title: str = "", category: str = "",
                  pod: str = "") -> dict:
    return ix.score(title, category=category, pod=pod)


# ---- engines: may this concept be built today, and if not, which engine is needed ---------

def engine_verdict(slug: str, payload: dict | None = None, *, title: str = "",
                   category: str = "") -> dict:
    """{"known", "certified", "family", "status", "reason"} for a concept.

    `certified` is True when `cir.draft` has a certified (verified or physical-gated) engine
    for it, or an engineered design under its slug. `known` is False when the payload names
    too little to say; such a concept is not gated here (its draft decides, as before)."""
    p = dict(payload or {})
    title = str(p.get("title") or title or "")
    category = str(p.get("category") or category or "")
    try:
        from ..runtime.pipeline import ENGINEERED

        if slug in ENGINEERED:
            return {"known": True, "certified": True, "family": "engineered",
                    "status": "verified", "reason": f"engineered design {ENGINEERED[slug]}"}
    except Exception:  # noqa: BLE001 - no pipeline: fall through to the routing
        pass
    try:
        from .launch0 import LEGACY_DUPLICATES

        if slug in LEGACY_DUPLICATES:
            return {"known": True, "certified": True, "family": "engineered",
                    "status": "verified", "reason": "routed to its Launch-0 engineered design"}
    except Exception:  # noqa: BLE001
        pass
    if not title or not category:
        return {"known": False, "certified": False, "family": None, "status": None,
                "reason": "the offer names no title and category"}
    from ..creative import construction_families as CF
    from ..creative import fallback_constructions as FC

    form, construction = str(p.get("form") or ""), str(p.get("construction") or "")
    try:
        if form and construction:
            r = CF.route(category=category, title=title, form=form, construction=construction,
                         slug=slug, rationale=str(p.get("rationale") or ""),
                         premise=str(p.get("premise") or ""))
            fam = r["family"]
            ok = bool(r["admitted"])
            return {"known": True, "certified": ok, "family": fam,
                    "status": r.get("status") or CF.status_of(fam),
                    "reason": r.get("reason") or ""}
        plan = FC.plan(category=category, title=title, slug=slug,
                       rationale=str(p.get("rationale") or ""))
    except Exception as exc:  # noqa: BLE001 - an unroutable concept is not known-buildable
        return {"known": True, "certified": False, "family": "unroutable", "status": "none",
                "reason": f"routing failed: {type(exc).__name__}: {str(exc)[:160]}"}
    fam = plan["family"]
    if fam == FC.REFUSED:
        label = CF.hold_family(CF.draft_hold(category, title)) or category
        return {"known": True, "certified": False, "family": label,
                "status": CF.status_of(label),
                "reason": (f"{CF.HOLD_PREFIX}{label}: {plan.get('why') or ''}"
                           + (f" (needs {plan['needs']})" if plan.get("needs") else ""))}
    status = CF.status_of(fam)
    if status not in CF.ADMITTED_STATUSES:
        f = CF.FAMILIES.get(fam)
        return {"known": True, "certified": False, "family": fam, "status": status,
                "reason": (f"{CF.HOLD_PREFIX}{fam}: the {fam} engine is {status}"
                           + (f": {f.gaps}" if f is not None else ""))}
    return {"known": True, "certified": True, "family": fam, "status": status, "reason": ""}


# What a held family needs built, in words an engineer can act on. A family absent from here
# is named by its own key.
ENGINE_NEEDS: dict[str, str] = {
    "amigurumi": "amigurumi shape library: shaped heads, limbs and join-as-you-go bodies "
                 "beyond the ball-body bear/bunny (new animals, low-sew, chunky)",
    "lovey": "lovey heads beyond bear/bunny",
    "garment": "garment intake routing: a POOL garment concept re-proposed as fitted_garment "
               "so the certified raglan / one-piece engines draft it",
    "amigurumi_features": "cushion appliqué faces and features beyond the highland cow",
    "garment_one_piece": "one-piece sweater: pin the adult (non-child) category through intake",
    "garment_side_to_side": "side-to-side vest: pin a research concept through intake",
    "garment_drop_shoulder": "drop-shoulder pullover: pin a research concept through intake",
    "seasonal_decor": "seasonal décor shapes (garland units, shaped ornaments)",
    "ornament": "small closed or shaped pieces (ornaments)",
    "hat": "fitted hat crown and brim from a sourced head chart with height and ease",
    "mosaic": "overlay mosaic charts (stitches that reach past the previous row)",
    "flower": "motifs worked in rounds and joined",
    "motif": "motifs worked in rounds and joined",
    "triangle": "triangle shawl stitch patterns (lace, lattice)",
    "tote": "tote: pin a research concept through certification",
    "cosy": "egg cosy: pin a research concept through certification",
    "pouch": "pouch: two-colour asset agreement",
    "stocking": "stocking: motif and certification proof",
    "flat_panel": "shaped flat pieces (discs, wall hangings, hats) beyond one rectangle",
    "vessel": "one release per basket (sets) in the vessel engine",
    "nursery": "nursery mobiles: several shaped pieces assembled",
    "applique_cushion": "more cushion appliqué faces",
    "panel_pair": "panel-pair cushions: physical sample",
}


def engine_need(family: str | None) -> str:
    return ENGINE_NEEDS.get(str(family or ""), f"a certified {family} engine")


def engine_demand(waiting: list[dict]) -> list[dict]:
    """Rank the engines the waiting concepts need: highest demand first, then most concepts.

    `waiting`: dicts {slug, family, demand (a concept_score dict or float), reason}. A
    concept's demand is recorded with it, so the ranking is the evidence, not a guess."""
    by: dict[str, dict] = {}
    for w in waiting:
        fam = str(w.get("family") or "unknown")
        d = w.get("demand")
        score = d.get("score") if isinstance(d, dict) else d
        score = float(score) if isinstance(score, (int, float)) else PRIOR
        e = by.setdefault(fam, {"engine": fam, "build": engine_need(fam), "concepts": [],
                                "top_demand": 0.0, "demand_sum": 0.0})
        e["concepts"].append({"slug": w.get("slug"), "demand": round(score, 4),
                              "cluster": (d or {}).get("cluster") if isinstance(d, dict)
                              else None, "reason": str(w.get("reason") or "")[:240]})
        e["top_demand"] = max(e["top_demand"], score)
        e["demand_sum"] += score
    out = []
    for e in by.values():
        e["concepts"].sort(key=lambda c: (-c["demand"], str(c["slug"])))
        e["top_demand"] = round(e["top_demand"], 4)
        e["demand_sum"] = round(e["demand_sum"], 4)
        e["count"] = len(e["concepts"])
        out.append(e)
    out.sort(key=lambda e: (-e["top_demand"], -e["count"], e["engine"]))
    for i, e in enumerate(out, start=1):
        e["rank"] = i
    return out


def pool_reclassification(ix: DemandIndex | None = None) -> list[dict]:
    """Every static POOL concept: its demand, whether a certified engine builds it, and the
    engine it needs when none does. Ranked by demand. This is the re-classification of the
    held concepts the owner asked for."""
    from ..radar.opportunity import POOL

    ix = ix or build_index((), ())
    out = []
    for seed in POOL:
        v = engine_verdict(seed.slug, {"title": seed.title, "category": seed.category,
                                       "rationale": seed.rationale})
        d = ix.score(seed.title, category=seed.category)
        out.append({"slug": seed.slug, "title": seed.title, "category": seed.category,
                    "season": seed.season, "cluster": d["cluster"], "demand": d["score"],
                    "demand_status": d["status"], "buildable": v["certified"],
                    "engine": v["family"], "engine_status": v["status"],
                    "needs": None if v["certified"] else engine_need(v["family"]),
                    "reason": v["reason"]})
    return sorted(out, key=lambda r: (-r["demand"], r["slug"]))


# ---- the readings Mission Control and readback show ----------------------------------------

ENGINE_DEMAND_ACTION = "supply.engine_demand"


def recorded_engine_demand(db, *, limit: int = 2000) -> list[dict]:
    """The latest engine-demand record per concept, from the audit log (what admission saw)."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    latest: dict[str, dict] = {}
    with db.session() as s:
        for rid, artifact, detail in s.execute(
                select(AuditLog.id, AuditLog.artifact, AuditLog.detail)
                .where(AuditLog.action == ENGINE_DEMAND_ACTION)
                .order_by(AuditLog.id.desc()).limit(limit)):
            slug = artifact or (detail or {}).get("slug")
            if slug and slug not in latest:
                latest[slug] = dict(detail or {}, slug=slug, _id=rid)
        # A concept admitted after its engine-demand record has its engine now: it is no
        # longer demand for one.
        admitted: dict[str, int] = {}
        if latest:
            for rid, artifact in s.execute(
                    select(AuditLog.id, AuditLog.artifact)
                    .where(AuditLog.action == "supply.admitted",
                           AuditLog.artifact.in_(list(latest)))):
                admitted[artifact] = max(admitted.get(artifact, 0), rid)
    return [{k: v for k, v in r.items() if k != "_id"} for slug, r in latest.items()
            if admitted.get(slug, 0) < r["_id"]]


def panel(db, *, now: datetime | None = None) -> dict:
    """Mission Control's Demand panel: the ranked engine list, the top clusters and families,
    and the POOL re-classification. Read-only."""
    ix = index(db, now=now)
    waiting = recorded_engine_demand(db)
    pool = pool_reclassification(ix)
    held_pool = [{"slug": r["slug"], "family": r["engine"], "demand": r["demand"],
                  "reason": r["reason"]} for r in pool if not r["buildable"]]
    intake_held, intake_error = intake_engine_demand(db, ix)
    seen = {w["slug"] for w in waiting}
    rest = [h for h in intake_held + held_pool if h["slug"] not in seen]
    merged, slugs = list(waiting), set(seen)
    for h in rest:
        if h["slug"] not in slugs:
            merged.append(h)
            slugs.add(h["slug"])
    engines = engine_demand(merged)
    return {"readable": True, "as_of": ix.as_of.isoformat(), "basis": ix.basis,
            "engines": engines, "families": ix.families(),
            "clusters": ix.clusters()[:40], "pool": pool,
            "pool_counts": {"total": len(pool),
                            "buildable": sum(1 for r in pool if r["buildable"]),
                            "held": sum(1 for r in pool if not r["buildable"])},
            "intake_held": len(intake_held), "intake_error": intake_error,
            "rule": ix.basis["rule"]}


def intake_engine_demand(db, ix: DemandIndex) -> tuple[list[dict], str | None]:
    """Research and original concepts intake held for their construction: engine demand,
    each with its stored-evidence demand reading."""
    from ..creative.construction_families import hold_family
    from .production_inventory import _intake_construction_holds

    holds, err = _intake_construction_holds(db)
    out = []
    for slug, h in sorted(holds.items()):
        fam = hold_family(h["reason"]) or "unknown"
        d = ix.score(str(h.get("title") or slug.replace("-", " ")))
        out.append({"slug": slug, "family": fam, "demand": d, "reason": h["reason"],
                    "source": "radar.intake"})
    return out, err


def readback(db, *, now: datetime | None = None) -> dict:
    """The advisory readback section: counts and the top of the engine list only."""
    p = panel(db, now=now)
    return {"readable": True, "as_of": p["as_of"],
            "engines_needed": len(p["engines"]),
            "top_engines": [{"rank": e["rank"], "engine": e["engine"], "count": e["count"],
                             "top_demand": e["top_demand"]} for e in p["engines"][:5]],
            "top_families": [{"family": f["family"], "score": f["score"],
                              "status": f["status"]} for f in p["families"][:6]],
            "pool_counts": p["pool_counts"],
            "basis": {k: p["basis"][k] for k in ("listings_read", "serp_entries_read",
                                                 "teardown_observations")}}
