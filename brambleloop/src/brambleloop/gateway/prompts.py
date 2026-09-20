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


# The blinded head-to-head (#94). Two product ideas in the same closed vocabulary, and one
# question. The system prompt is deliberately silent about where either came from, because a
# judge told that one side is a competitor's stops judging and starts being loyal.
BLINDED_APPEAL = register(Prompt(
    name="creative.blinded_appeal", version="1",
    system=("You are a shopper browsing handmade crochet patterns. You are shown two product "
            "ideas described in the same fields. Pick the one you would rather buy as a gift "
            "or for yourself, and say why in one short sentence about its appeal. Judge only "
            "what is described. Do not assume anything about who made either, where either "
            "is sold, or which was shown first. If they are genuinely equal, still pick the "
            "one you would reach for. Reply with JSON only."),
    template=("Option A: {option_a}\n"
              "Option B: {option_b}\n\n"
              "JSON: {{\"pick\": \"A\" or \"B\", \"reason\": \"...\"}}"),
    output_schema=("pick", "reason"),
    max_output_tokens=200))


# Concept discovery into a proven arena (#104). The system prompt carries the refusals rather
# than hoping for them: every field below is a closed vocabulary validated on return, so a
# model that invents a value produces a structural rejection instead of a plausible-looking
# concept nothing downstream can check.
# Version 2 raises the output budget. Version 1 asked for six concepts of nine fields each
# inside 2000 tokens, and the first live run came back as truncated JSON twice -- the
# gateway's retry produced a second truncation, because a budget that is too small is not a
# transient fault. A prompt that asks for more than it allows room for fails every time and
# reads like a provider problem.
CONCEPT_FIELD = register(Prompt(
    name="creative.concept_field", version="2",
    system=("You invent crochet product concepts for a premium pattern studio. You are given "
            "one product form, one occasion, one recipient lane and a market that is known to "
            "buy in this department. Propose genuinely different products, not one product "
            "with different colours: if two of your concepts would photograph alike, replace "
            "one. Each concept states what the object IS, what it DOES for its owner, and the "
            "physical thing that delivers its feeling -- a structure, a texture, a shape or a "
            "colour relationship -- never a sentence about how lovely it is. Say what the "
            "object is and never how to make it: no numbers of any kind, no instructions, no "
            "materials quantities, no tension figures. Those are produced by a compiler and "
            "anything you say about them is discarded. Never "
            "describe or reproduce another seller's product. Use only the listed vocabulary "
            "values. Reply with JSON only."),
    template=("Form: {form}\nOccasion: {occasion}\nRecipient lane: {make_lane}\n"
              "Market evidence: {evidence}\n"
              "Allowed construction values: {constructions}\n"
              "Allowed feeling values: {feelings}\n"
              "Allowed recipient values: {recipients}\n"
              "Allowed occasion values: {occasions}\n"
              "Invention brief: {brief}\n\n"
              "Propose {count} concepts. JSON: {{\"concepts\": [{{"
              "\"title\": \"...\", \"premise\": \"one sentence, at least twelve words, "
              "describing the object so a buyer could picture it\", "
              "\"construction\": \"...\", \"motif\": \"...\", \"palette_story\": \"...\", "
              "\"recipient\": \"...\", \"occasion\": \"...\", \"feeling\": \"...\", "
              "\"function\": \"what it does for the person who owns it\", "
              "\"wow\": \"the physical mechanism that makes it worth looking at twice\"}}]}}"),
    output_schema=("concepts",),
    max_output_tokens=4000))
