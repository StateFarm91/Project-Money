"""Pinned prompt versions (Master Plan section 27).

A prompt is not a string, it is a dependency. If a prompt can be edited in place then two
runs of "the same" job are not comparable, a regression cannot be attributed, and the audit
trail records a call to something that no longer exists.

So prompts are immutable, versioned, content-hashed, and referenced by `name@version`
everywhere a model is called. Editing one means adding a new version; the old text stays so
last month's output can still be explained.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass


class UnknownPrompt(KeyError):
    pass


class PromptIsImmutable(RuntimeError):
    """Someone tried to edit a released prompt instead of publishing a new version."""


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    system: str
    template: str
    output_schema: tuple[str, ...] = ()
    max_output_tokens: int = 2048

    @property
    def ref(self) -> str:
        return f"{self.name}@{self.version}"

    @property
    def sha256(self) -> str:
        return hashlib.sha256(
            f"{self.system}\x00{self.template}".encode()).hexdigest()

    def render(self, **kwargs) -> str:
        missing = [k for k in _placeholders(self.template) if k not in kwargs]
        if missing:
            # A silently empty placeholder is how a prompt ends up asking a model about
            # nothing and getting a confident answer about nothing.
            raise KeyError(f"{self.ref} is missing template values: {missing}")
        return self.template.format(**kwargs)


def _placeholders(template: str) -> list[str]:
    import string

    return [f for _, f, _, _ in string.Formatter().parse(template) if f]


_REGISTRY: dict[str, Prompt] = {}


def register(prompt: Prompt) -> Prompt:
    if prompt.ref in _REGISTRY:
        existing = _REGISTRY[prompt.ref]
        if existing.sha256 != prompt.sha256:
            raise PromptIsImmutable(
                f"{prompt.ref} already exists with different text. Publish a new version "
                f"instead of editing a released one, or last month's output becomes "
                f"unexplainable.")
        return existing
    _REGISTRY[prompt.ref] = prompt
    return prompt


def get(ref: str) -> Prompt:
    if ref not in _REGISTRY:
        raise UnknownPrompt(f"no prompt {ref!r}; have {sorted(_REGISTRY)}")
    return _REGISTRY[ref]


def all_prompts() -> list[Prompt]:
    return sorted(_REGISTRY.values(), key=lambda p: p.ref)


# ---- the starting prompt set ---------------------------------------------
#
# Deliberately narrow. Section 2 is absolute that a model never supplies pattern
# instructions, so none of these ask for stitch counts, rows or construction. They ask for
# the things a model is genuinely better at than code: naming, positioning, and reading
# customer sentiment. Everything load-bearing stays deterministic.

CONCEPT_NAMING = register(Prompt(
    name="concept.naming", version="1",
    system=("You name crochet patterns for a premium studio. Names are evocative, short and "
            "literal about what the object is. Never claim a property of the item such as "
            "size, difficulty, yarn quantity or fit -- those come from the pattern data, not "
            "from you. Reply with JSON only."),
    template=("Category: {category}\nMotifs: {motifs}\nSeason: {season}\n"
              "Propose three names. JSON: {{\"names\": [\"...\", \"...\", \"...\"]}}"),
    output_schema=("names",)))

LISTING_POLISH = register(Prompt(
    name="listing.polish", version="1",
    system=("You improve the readability of an Etsy listing description. You may reorder and "
            "rephrase. You may not add, remove or alter any factual claim: sizes, yardage, "
            "gauge, difficulty, stitch names, colours and terms must survive verbatim. If you "
            "cannot improve it without changing a fact, return it unchanged. Reply with JSON "
            "only."),
    template=("Description:\n{description}\n\n"
              "JSON: {{\"description\": \"...\", \"changed_facts\": false}}"),
    output_schema=("description", "changed_facts")))

REVIEW_MINING = register(Prompt(
    name="review.mining", version="1",
    system=("You read genuine customer messages and extract themes. Never invent a message, a "
            "reviewer or a sentiment. Quote only what is present. Reply with JSON only."),
    template=("Messages:\n{messages}\n\n"
              "JSON: {{\"themes\": [{{\"theme\": \"...\", \"count\": 0, "
              "\"is_defect_report\": false}}]}}"),
    output_schema=("themes",)))
