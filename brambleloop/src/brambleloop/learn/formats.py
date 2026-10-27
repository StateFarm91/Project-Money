"""One truth, many formats (F-804) -- W4-C11.

"Each approved lesson has one canonical factual/teaching specification that can produce an
article, concise FAQ, printable guide, diagram set, short video script, long video script,
email, social carousel, short-form clips and pattern-specific help without factual drift."

The canonical specification is `learn.models.Lesson.spec` (its revision is the sha256 of the
spec; any change resets reviews). Every format here is rendered from that spec alone, by fixed
templates -- no model writes a word -- and carries the revision it was rendered from. Two
things keep the formats from drifting:

* `facts(spec)` is the closed set of numbers and stitch names the spec states (hook size,
  each step's repeat/consumes/produces, numbers in its own instructions, step positions);
* `drift(spec, text)` lists every number and every stitch name in a rendered text that is not
  in that set -- in the lesson's own terminology, longest name first, so "half double crochet"
  is not read as "double crochet" and a UK "double crochet" in a US lesson is caught.

`render_all` refuses (raises) when any format drifts, and renders only an approved lesson
unless `allow_draft` is passed for an editor preview.
"""
from __future__ import annotations

import re

from ..cir import stitches

FORMATS = ("article", "faq", "printable_guide", "diagram_set", "short_video_script",
           "long_video_script", "email", "social_carousel", "short_clips", "pattern_help")
SHORT_VIDEO_BEATS = 5
CAROUSEL_SLIDES = 10
CLIP_SECONDS = 15
_NUM = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])")


class FormatDrift(ValueError):
    """A rendered format states something the canonical specification does not."""


def _name(code: str, terminology: str) -> str:
    st = stitches.get(code)
    return st.name_uk if terminology == "UK" else st.name_us


def _norm(n: str) -> str:
    return str(float(n)).rstrip("0").rstrip(".")


def facts(spec: dict) -> dict:
    t = spec.get("terminology", "US")
    steps = spec.get("steps") or []
    numbers = {_norm(str(spec.get("assumptions", {}).get("hook_mm")))}
    names = set()
    for i, step in enumerate(steps, 1):
        numbers |= {_norm(str(i)), _norm(str(step.get("repeat"))),
                    _norm(str(step.get("consumes"))), _norm(str(step.get("produces")))}
        numbers |= {_norm(n) for n in _NUM.findall(str(step.get("instruction") or ""))}
        names.add(_name(step["stitch"], t))
    numbers.add(_norm(str(len(steps))))
    numbers |= {_norm(n) for n in _NUM.findall(str(spec.get("learner_problem") or ""))}
    # A stitch the specification's own words name is stated by it, whether or not a step
    # teaches it ("chain 1 and turn").
    own = " ".join([str(spec.get("learner_problem") or "")] +
                   [str(s.get("instruction") or "") for s in steps])
    names |= set(_names_in(own, t))
    return {"numbers": numbers, "stitch_names": names, "terminology": t}


def _names_in(text: str, terminology: str) -> list[str]:
    rest, found = str(text).lower(), []
    for name in sorted({_name(c, terminology) for c in stitches.known_codes()},
                       key=len, reverse=True):
        pat = re.compile(rf"\b{re.escape(name.lower())}\b")
        if pat.search(rest):
            found.append(name)
            rest = pat.sub(" ", rest)
    return found


def drift(spec: dict, text: str) -> list[str]:
    f = facts(spec)
    out = [f"number {n} is not in the specification" for n in sorted(
        {_norm(n) for n in _NUM.findall(text)} - f["numbers"])]
    out += [f"stitch {name!r} is not taught by the specification"
            for name in _names_in(text, f["terminology"]) if name not in f["stitch_names"]]
    return out


def _steps(spec):
    t = spec.get("terminology", "US")
    for i, s in enumerate(spec["steps"], 1):
        yield i, s, _name(s["stitch"], t)


def _title(spec) -> str:
    p = str(spec["learner_problem"]).strip()
    return p[:1].upper() + p[1:]


def render(spec: dict, fmt: str, *, revision: str, slug: str, pattern_topics=None) -> dict:
    a = spec["assumptions"]
    t = spec.get("terminology", "US")
    hook = _norm(str(a["hook_mm"]))
    kit = f"a {hook} mm hook and {a['yarn_weight']} yarn ({t} terms)"
    steps = list(_steps(spec))
    if fmt == "article":
        body = "\n".join([f"# {_title(spec)}", f"You need {kit}."] +
                         [f"{i}. {s['instruction']}" for i, s, _ in steps])
    elif fmt == "faq":
        body = "\n".join([f"Q: What do I need?\nA: {kit.capitalize()}."] +
                         [f"Q: How many stitches does step {i} make?\nA: {s['produces']} "
                          f"{n} from {s['consumes']}." for i, s, n in steps])
    elif fmt == "printable_guide":
        body = "\n".join([_title(spec), f"Kit: {kit}"] +
                         [f"[ ] {i}. {s['instruction']} (makes {s['produces']})"
                          for i, s, _ in steps])
    elif fmt == "diagram_set":
        from . import technique as T
        from .accessibility import alt_text

        items = []
        for _i, s, n in steps:
            code = s["stitch"]
            items.append({"stitch": code, "alt": alt_text(n, code, s.get("loop", "both")),
                          "svg_sha256": (T.digest(code, s.get("loop", "both"))
                                         if code in T.supported() else None)})
        body = "\n".join(i["alt"] for i in items)
        return {"format": fmt, "revision": revision, "slug": slug, "body": body,
                "items": items}
    elif fmt in ("short_video_script", "long_video_script"):
        beats = [f"Beat {i}: {s['instruction']}" for i, s, _ in steps]
        if fmt == "short_video_script":
            beats = beats[:SHORT_VIDEO_BEATS]
            body = "\n".join([f"Open: {_title(spec)}"] + beats)
        else:
            body = "\n".join([f"Open: {_title(spec)}", f"Kit: {kit}"] + beats +
                             [f"Check: step {i} makes {s['produces']} {n}"
                              for i, s, n in steps])
    elif fmt == "email":
        body = "\n".join([f"Subject: {_title(spec)}", f"You need {kit}.",
                          f"Read it here: /learn/{slug}?revision={revision}"])
        return {"format": fmt, "revision": revision, "slug": slug, "body": body,
                "checked_text": "\n".join(body.splitlines()[:2])}
    elif fmt == "social_carousel":
        slides = [_title(spec)] + [s["instruction"] for _i, s, _ in steps]
        body = "\n---\n".join(slides[:CAROUSEL_SLIDES])
    elif fmt == "short_clips":
        clips = [{"seconds": CLIP_SECONDS, "caption": s["instruction"]} for _i, s, _ in steps]
        body = "\n".join(c["caption"] for c in clips)
        return {"format": fmt, "revision": revision, "slug": slug, "body": body,
                "clips": clips}
    elif fmt == "pattern_help":
        wanted = set(pattern_topics or ())
        rel = [(i, s, n) for i, s, n in steps if f"stitch:{s['stitch']}" in wanted]
        body = "\n".join([f"Help for this pattern: {_title(spec)}"] +
                         [f"{i}. {s['instruction']}" for i, s, _ in rel]) if rel else ""
    else:
        raise ValueError(f"unknown format {fmt!r}")
    return {"format": fmt, "revision": revision, "slug": slug, "body": body}


def render_all(db, slug: str, *, pattern_topics=None, allow_draft: bool = False) -> dict:
    from .models import Lesson
    from .service import eligible

    with db.session() as s:
        row = s.get(Lesson, slug)
        if row is None:
            raise LookupError(f"no lesson {slug!r}")
        spec, revision, approved = dict(row.spec), row.revision, eligible(row)
    if not approved and not allow_draft:
        raise PermissionError(f"lesson {slug!r} is not approved at revision {revision}")
    out, drifted = {}, {}
    for fmt in FORMATS:
        r = render(spec, fmt, revision=revision, slug=slug, pattern_topics=pattern_topics)
        problems = drift(spec, r.get("checked_text", r["body"]))
        if problems:
            drifted[fmt] = problems
        out[fmt] = r
    if drifted:
        raise FormatDrift(f"formats drift from revision {revision}: {drifted}")
    return {"slug": slug, "revision": revision, "approved": approved, "formats": out}
