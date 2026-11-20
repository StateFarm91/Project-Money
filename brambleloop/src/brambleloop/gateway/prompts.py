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
    # F-316: no default. An output budget is sized to the shape asked for, by whoever writes
    # the prompt, and `register` refuses a prompt that leaves it unset or above the cap.
    max_output_tokens: int = 0

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


# F-316 (Output Token Discipline): the largest output any prompt or routing task may ask for.
# The largest declared shape is a concept field (CONCEPT_FIELD, `concept_generation`), and a
# budget beyond it is room for a model to ramble at our expense rather than room an answer
# needs. `routing.OUTPUT_TOKEN_CAP` is this same number.
OUTPUT_TOKEN_CAP = 4000


class PromptRefused(ValueError):
    """A prompt with no output schema or an output budget nobody sized."""


def register(prompt: Prompt) -> Prompt:
    if prompt.ref in _REGISTRY:
        existing = _REGISTRY[prompt.ref]
        if existing.sha256 != prompt.sha256:
            raise PromptIsImmutable(
                f"{prompt.ref} already exists with different text. Publish a new version "
                f"instead of editing a released one, or last month's output becomes "
                f"unexplainable.")
        return existing
    # F-316: every paid answer is a closed JSON shape with a budget sized to it. A prompt with
    # no required fields accepts any JSON object, and one with no budget (or a vast one) pays
    # for whatever the model chooses to write -- both are refused here, at definition time.
    if not prompt.output_schema:
        raise PromptRefused(
            f"{prompt.ref} declares no output_schema: a paid answer must be a closed JSON "
            f"shape, so a prose or half-populated reply is rejected rather than billed and "
            f"passed on")
    if not 0 < int(prompt.max_output_tokens) <= OUTPUT_TOKEN_CAP:
        raise PromptRefused(
            f"{prompt.ref} max_output_tokens={prompt.max_output_tokens!r}: it must be set "
            f"explicitly, sized to its schema, and at most {OUTPUT_TOKEN_CAP}")
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
    output_schema=("names",),
    max_output_tokens=200))

LISTING_POLISH = register(Prompt(
    name="listing.polish", version="1",
    system=("You improve the readability of an Etsy listing description. You may reorder and "
            "rephrase. You may not add, remove or alter any factual claim: sizes, yardage, "
            "gauge, difficulty, stitch names, colours and terms must survive verbatim. If you "
            "cannot improve it without changing a fact, return it unchanged. Reply with JSON "
            "only."),
    template=("Description:\n{description}\n\n"
              "JSON: {{\"description\": \"...\", \"changed_facts\": false}}"),
    output_schema=("description", "changed_facts"),
    max_output_tokens=2048))

REVIEW_MINING = register(Prompt(
    name="review.mining", version="1",
    system=("You read genuine customer messages and extract themes. Never invent a message, a "
            "reviewer or a sentiment. Quote only what is present. Reply with JSON only."),
    template=("Messages:\n{messages}\n\n"
              "JSON: {{\"themes\": [{{\"theme\": \"...\", \"count\": 0, "
              "\"is_defect_report\": false}}]}}"),
    output_schema=("themes",),
    max_output_tokens=1500))


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

# Version 3 (REL2) carries the two free deterministic gates the winner is held to after the
# field has been paid for: the season's motif grammar (#110) and, for a generic form, the
# silhouette qualifiers (#108). October's fields lost 46 winners to "declared no motifs" and 29
# to "generic form" because the prompt never named either; the gates themselves are unchanged
# and still decide. Version 2 stays registered so earlier output remains explainable.
CONCEPT_FIELD_V3 = register(Prompt(
    name="creative.concept_field", version="3",
    system=CONCEPT_FIELD.system,
    template=("Form: {form}\nOccasion: {occasion}\nRecipient lane: {make_lane}\n"
              "Market evidence: {evidence}\n"
              "Allowed construction values: {constructions}\n"
              "Allowed feeling values: {feelings}\n"
              "Allowed recipient values: {recipients}\n"
              "Allowed occasion values: {occasions}\n"
              "Season motif grammar: {motif_grammar}\n"
              "Silhouette: {silhouette}\n"
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


# ---- ENG-AUTOCODER (D-OWNER-AUTOCODER, 2026-11-20): the in-production coding team ----------
#
# One step of the plan -> edit loop (`improve.autocoder`), and the independent review
# of the finished diff. Neither prompt decides anything that ships: deterministic rails
# (`improve.autocoder_safety`) and the repository's own tests are the gate, and a diff any
# rail refuses is never pushed whatever these answers say. v2 (B19 A1): nothing the model
# writes runs in production; the suites it names run in the CI sandbox after review and push. Edits are structured (exact
# search/replace on one file, or a new file), never free-form patches, so every change the
# model proposes is applied and checked by code. Output is capped at the F-316 maximum: a
# step that needs more says so and continues on the next iteration.
AUTOCODER_STEP = register(Prompt(
    name="autocoder.step", version="2",
    system=("You are a careful senior Python engineer working inside the Brambleloop "
            "repository on one engineering change request (ECR). You act only through the "
            "JSON actions listed below; you never see or run anything else. Rules you may "
            "not break, and which code enforces whatever you write: never edit deploy, "
            "release, spend, gate, child-safety, auth, authority or approval code; never "
            "delete a test, remove or weaken an assertion, or add a skip; never add a model "
            "call, network request, subprocess or secret; keep the diff small. Patterns are "
            "deterministic software: pattern arithmetic and every gate stay in code. "
            "Make the smallest change that meets the acceptance criteria, add or extend a "
            "test that proves it, and name it in targets. Nothing runs here: the targeted "
            "suites run in a CI sandbox after independent review, and a red result refuses "
            "the change, so read the code carefully before you finish. "
            "Reply with JSON only."),
    template=("ECR:\n{ecr}\n\nEditable roots: {roots}\nProtected (never edit): {protected}\n"
              "Iteration {iteration} of {max_iterations}. Budget left: {budget}\n\n"
              "Repository orientation:\n{orientation}\n\n"
              "Transcript of your previous actions and what they returned:\n{transcript}\n\n"
              "Actions (any number per reply, applied in order):\n"
              "  {{\"op\": \"list\", \"path\": \"dir/\"}}\n"
              "  {{\"op\": \"read\", \"path\": \"file\", \"start\": 1, \"end\": 200}}\n"
              "  {{\"op\": \"grep\", \"pattern\": \"regex\", \"path\": \"dir-or-file\"}}\n"
              "  {{\"op\": \"edit\", \"path\": \"file\", \"old\": \"exact unique text\", "
              "\"new\": \"replacement\"}}\n"
              "  {{\"op\": \"create\", \"path\": \"new file\", \"content\": \"...\"}}\n"
              "JSON: {{\"plan\": \"one or two sentences\", \"actions\": [...], "
              "\"targets\": [\"tests/test_x.py\"], \"done\": false, "
              "\"summary\": \"what changed and why, when done\"}}"),
    output_schema=("plan", "actions", "done"),
    max_output_tokens=4000))

AUTOCODER_REVIEW = register(Prompt(
    name="autocoder.review", version="2",
    system=("You are an independent code reviewer for an autonomous coding agent. You did "
            "not write this diff and you owe it nothing. Block it unless every check holds: "
            "no gate, guard, ceiling, safety or authority check is weakened or bypassed; no "
            "test is deleted, skipped or made weaker; no assertion is vacuous (always true, "
            "or looping over something that may be empty); no secret, token or credential "
            "appears; no new spend, network or process-execution path exists; the change "
            "does what the ECR asks and the summary claims nothing the diff and test results "
            "do not show. The tests have NOT run yet: they run in a CI sandbox only after you "
            "SHIP, so judge the code itself. When unsure, BLOCK. Reply with JSON only."),
    template=("ECR:\n{ecr}\n\nAgent's summary:\n{summary}\n\n"
              "Deterministic rails: {rails}\nTest results:\n{tests}\n\nDiff:\n{diff}\n\n"
              "JSON: {{\"verdict\": \"SHIP\" or \"BLOCK\", \"checks\": {{"
              "\"no_weakened_gates\": true, \"no_deleted_or_skipped_tests\": true, "
              "\"no_vacuous_assertions\": true, \"no_secrets\": true, "
              "\"no_spend_paths\": true, \"honest\": true, \"meets_ecr\": true}}, "
              "\"reasons\": [\"...\"]}}"),
    output_schema=("verdict", "checks", "reasons"),
    max_output_tokens=1200))
