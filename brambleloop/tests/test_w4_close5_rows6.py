"""W4-CLOSE5 batch 7: F-019 Plural/Root Waste Detector and F-046 No Paid-Rank Myth.

  F-019  "Do not burn tag slots on singular/plural variants Etsy already root-matches."
  F-046  "Never model Etsy Ads or Etsy Plus as organic ranking boosts."

The mapping called both MISSING. F-019 is built on the deployed tree: `commerce.search` folds
plurals in `intent_key` (`_stem_word`), `_acceptable_tag` refuses a phrase whose folded key an
already-chosen tag carries, and `tag_diversity_problems` turns a surviving pair into a blocking
TAG_SEMANTIC_DUPLICATE in the release gate. No test asserted the singular/plural case itself.
F-046 had no guard at all; these tests are it: the organic ranking modules read no paid-media
input, and recorded ad and Etsy Plus spend leaves every ranking dimension unchanged.

Local, deterministic; no provider, no network.
Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_close5_rows6.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "brambleloop"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from brambleloop.commerce import search  # noqa: E402
from brambleloop.commerce.search import Query  # noqa: E402

PAIRS = [("crochet blanket", "crochet blankets"), ("granny square", "granny squares"),
         ("bunny amigurumi", "bunnies amigurumi"), ("baby blanket", "blankets baby")]


# ---- F-019 ----------------------------------------------------------------------------------

def test_f019_plural_and_singular_fold_to_one_root_and_ss_is_not_a_plural():
    for one, many in PAIRS:
        assert search.intent_key(one) == search.intent_key(many), (one, many)
    assert search._stem_word("bunnies") == "bunny"
    assert search._stem_word("dress") == "dress"           # not a plural
    assert search.intent_key("crochet dress") != search.intent_key("crochet dre")


def test_f019_tag_selection_never_spends_two_slots_on_one_root():
    queries = []
    for i, (one, many) in enumerate(PAIRS):
        # the plural is worth slightly more, so it is chosen first and the singular must lose
        queries += [Query(one, 0.50 - i * 0.01, 0.20), Query(many, 0.52 - i * 0.01, 0.20)]
    queries += [Query("mosaic throw", 0.30, 0.20), Query("textured afghan", 0.25, 0.20)]
    tags = search.choose_tags(queries)
    assert search.semantic_duplicates(tags) == [], tags
    keys = [search.intent_key(t) for t in tags]
    assert len(keys) == len(set(keys)), tags
    for one, many in PAIRS:
        assert (one in tags) + (many in tags) <= 1, (one, many, tags)
    assert "mosaic throw" in tags, "the freed slot went to a distinct search"
    # a must-include plural blocks the singular the value pass would otherwise take
    tags = search.choose_tags([Query("crochet blanket", 0.9, 0.1)],
                              must_include=["crochet blankets"])
    assert tags == ["crochet blankets"], tags
    assert not search._acceptable_tag("granny squares", ["granny square"], {})


def test_f019_a_surviving_plural_pair_blocks_in_the_release_gate():
    problems = search.tag_diversity_problems(["crochet blanket", "crochet blankets", "boho"])
    assert len(problems) == 1 and problems[0].startswith("TAG_SEMANTIC_DUPLICATE"), problems
    assert search.tag_diversity_problems(["crochet blanket", "granny square"]) == []
    release = (SRC / "runtime" / "release.py").read_text()
    assert "search_mod.tag_diversity_problems(copy.tags)" in release
    assert "search_mod.tag_diversity_problems(tags)" in (SRC / "seo" / "packages.py").read_text()


# ---- F-046 ----------------------------------------------------------------------------------

# The modules that model organic ranking: query value and tag choice, the SEO copy and its
# certificate, and the five ranking-readiness dimensions.
ORGANIC = ["commerce/search.py", "commerce/seo.py", "commerce/ranking_readiness.py",
           *sorted(p.relative_to(SRC).as_posix() for p in (SRC / "seo").glob("*.py"))]
PAID_MODULES = {"paid_media", "ads_readiness", "insights_budget", "channel_comparison"}
# commerce.search_policy holds both sides: the organic search rules (`certificate_problems` on
# its default `search_guidance` source, which the search certificate stamps) and the Etsy Ads
# thresholds. The organic modules may use the first, never the second.
PAID_NAMES = {"onsite_ads_terms", "ads_plan_findings", "ADS_SOURCE", "advertising_rules",
              "offsite_ads_terms", "attributed_roas", "listing_readiness"}
PAID_WORD = re.compile(r"(etsy[\s_]?plus|etsy[\s_]?ads|offsite[\s_]?ads|\bads\b|ad_spend|"
                       r"\broas\b|paid_media|ads_readiness|promoted)", re.I)


def _code_names_and_strings(tree: ast.AST) -> list[str]:
    """Identifiers, attribute names, imports and non-docstring string constants."""
    docs = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if n.body and isinstance(n.body[0], ast.Expr) and \
                    isinstance(getattr(n.body[0], "value", None), ast.Constant):
                docs.add(id(n.body[0].value))
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            out.append(n.id)
        elif isinstance(n, ast.Attribute):
            out.append(n.attr)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            out += [a.name for a in n.names] + ([n.module] if getattr(n, "module", None) else [])
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs:
            out.append(n.value)
    return out


def test_f046_no_organic_ranking_module_reads_a_paid_media_input():
    assert len(ORGANIC) >= 5, ORGANIC                       # the scan is not vacuous
    found = []
    for rel in ORGANIC:
        tree = ast.parse((SRC / rel).read_text())
        for tok in _code_names_and_strings(tree):
            last = tok.rsplit(".", 1)[-1]
            if last in PAID_MODULES or last in PAID_NAMES or PAID_WORD.search(tok):
                found.append(f"{rel}: {tok!r}")
    assert not found, ("an organic ranking module reads a paid-media input; Etsy Ads and Etsy "
                       f"Plus are spend, never an organic ranking boost: {found}")
    # the scan would catch one (self-check against a planted line)
    planted = ast.parse("from ..commerce import paid_media\nboost = cost('etsy_plus')\n"
                        "t = search_policy.onsite_ads_terms()\n")
    assert sum(1 for t in _code_names_and_strings(planted)
               if t.rsplit('.', 1)[-1] in PAID_MODULES | PAID_NAMES or PAID_WORD.search(t)) >= 3
    # the organic use of search_policy is the organic source only
    from brambleloop.commerce import search_policy
    assert search_policy.SOURCE != search_policy.ADS_SOURCE


def test_f046_ad_and_etsy_plus_spend_leave_every_ranking_dimension_unchanged():
    import test_ranking_readiness as rrt
    from brambleloop.commerce import ranking_readiness as rr
    from brambleloop.core.models import CostEntry

    db = rrt._db()
    desc = rrt._listing(db)
    rrt._search_profile(db, desc)
    before = rr.profile(db, rrt.SLUG, rrt.VERSION)
    with db.session() as s:
        for kind, purpose, amt in (("ads", "etsy_ads", 250.0), ("ads", "offsite_ads", 90.0),
                                   ("api", "etsy_plus_subscription", 13.0)):
            s.add(CostEntry(agent="growth", kind=kind, purpose=purpose, amount_cad=amt,
                            product_slug=rrt.SLUG, provider="etsy",
                            detail={"etsy_plus": purpose.startswith("etsy_plus")}))
    after = rr.profile(db, rrt.SLUG, rrt.VERSION)
    assert after["dimensions"] == before["dimensions"], (before, after)
    assert after["search_certificate"] == before["search_certificate"]
    assert rr.summary(after) == rr.summary(before)
    assert after["blended_score"] is None
    # query value is demand x (1 - competition): there is no paid term to add
    q = Query("crochet blanket", 0.5, 0.2)
    assert q.value == round(0.5 * 0.8, 4)
    assert set(Query.__dataclass_fields__) == {"phrase", "demand", "competition", "intent",
                                               "provenance", "read_at", "family"}


if __name__ == "__main__":
    fails = 0
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    assert ran >= 5, "no tests collected"
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing of {ran}")
    sys.exit(1 if fails else 0)
