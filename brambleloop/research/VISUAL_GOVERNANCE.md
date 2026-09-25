# Visual spend governance, and `Material.fibre_content` — 2026-09-25

**Department:** Visual / Reliability (LANE B)
**Phase:** `BRAMBLELOOP_PHASE=shadow`. **CA$0.00 spent**: no model call, no image generation,
nothing deployed, nothing published, nothing activated. No secret was written anywhere.
**Branch:** an isolated worktree. Committed, **not pushed and not merged**.

Evidence labels, as elsewhere in this repository: **SOURCED** — read from the file, the
document or the production reading that governs it, on a recorded date. **INFERRED** — this
department reasoned, and the reasoning can be argued with. **UNKNOWN** — not established, and
not filled in with a plausible answer.

Reading behind this: `research/RELIABILITY_AUDIT.md` (2026-09-24),
`research/RELIABILITY_WAVE2.md` (2026-09-25) and `research/CHILDRENS_STATEMENTS.md` §3 and §5
(2026-09-25), all of which named work in files their departments were right not to reach into.

---

## 1. The holes wave 2 left in Visual, and what each one was

**SOURCED — the state of the tree before this session**, re-read on 2026-09-25 rather than
taken from the audit:

| file | wrote a ledger row | called `check_budget` | passed `agent=` | released its reservation |
|---|---|---|---|---|
| `visual/inspect.py` | yes | yes | **no** | **no** |
| `visual/model_registry.py` ×3 | yes | **no** | — | — |
| `visual/photoreal.py` | yes | **no** | — | — |
| `visual/tournament.py` | yes | **no** | — | — |
| `visual/bible.py` | yes | **no** | — | — |

Seven provider calls across five modules. Every one of them wrote a `spend_report.record`
row naming an agent, and not one of them told the pre-call guard which agent it was — in four
of the five files because there was no pre-call guard at all. So the ledger knew whose money
it was and the control did not, which is the same defect in two shapes:

* **`inspect.py`** checked the authorised month and nothing else. `asset_inspection` is the
  purpose that spent CA$8.84 across 504 calls in the month to 2026-09-25
  (**SOURCED** — `RELIABILITY_WAVE2.md` §"Left for the departments that own the files"), and
  `quality_director`'s daily ceiling was checked by nobody on the path that spent it. It also
  took a reservation and never gave it back, so a padded estimate was held for its full
  five-minute TTL after the bill was already known — and `inspect_image` makes **two** calls
  in a row, so the second was checked against a month carrying the first one's dead claim.
* **the other four** were not ceiling-checked before the call by anything at all.
  `spend_report.record` is a pure writer -- it adds a `CostEntry` and returns its id, and
  enforces nothing (**SOURCED**, read 2026-09-25). The only daily check anywhere near these
  paths is `agents.registry.record_cost`'s, which is used exclusively by the model gateway
  and in any case runs *after* the provider has answered. A row written after the money left
  is a measurement. Neither is a control.

### What was built

All seven now go through the **existing** mechanism and nothing else: `check_budget(...,
agent=, purpose=)` before the call, `release_reservation(id, actual_cad=cost)` after it, and
on every exit path including a refusal. No second mechanism, no bypass, no `reserve=False`,
and no argument that a Visual call is different. **SOURCED** — `tests/test_model_spend_paths.py`
reads the source of all seven and fails on one missing any of the four.

Six decisions inside that work, each of which could have gone the other way:

1. **The agent is a module constant now, not a literal inside the ledger call.**
   `inspect.AGENT`, `model_registry.OBSERVE_AGENT` / `HAIR_AGENT`, `photoreal.AGENT`,
   `bible.AGENT`, `tournament.JUDGE_AGENT` / `JUDGE_PURPOSE`. The guard and the bill read the
   same constant, because a daily ceiling enforced against one name and billed against
   another enforces nothing, and the two names sitting in two places is how they come apart.
2. **`model_registry.compare_identity` and `compare_hair` show two images, so the estimate
   carries two image allowances.** `2 * gw.IMAGE_TOKENS_ESTIMATE`. `tournament._judge` takes
   `len(image_refs)`. **INFERRED**: sizing a multi-image call on one image's tokens is a
   guard that stays green while the bill multiplies, and this build has been optimistic about
   the image-token figure twice already (`RELIABILITY_WAVE2.md` §1).
3. **`bible.judge` estimates on `prompt(axes)`, the prompt it is actually about to send** —
   not `prompt()`. A frame asked about three axes sends a shorter prompt, and a guard sized on
   a prompt nobody is sending is arithmetic about a different call.
4. **A refusal arrives where the caller already handles "could not be judged".**
   `AgentCeilingExceeded` subclasses `BudgetExceeded` subclasses `PermanentError`, so it lands
   in each function's existing `except`. That is the right outcome and it was checked rather
   than assumed: `photoreal.gate` reads an unread frame as `unjudged`, never `clear`;
   `model_registry.drift_check` reads an `{"error": ...}` as maximum drift; `inspect`'s note
   says in as many words that an unmade check is unjudged and never a pass. **A refused call
   cannot pass anything.**
5. **`tournament._judge` raises the refusal and its batch loops stop on it.** The second
   half is the one that matters and it is the defect this session's own change would
   otherwise have introduced — §5 item 5. A ceiling refusal scored as "this candidate judged
   badly" would have ranked the field by how much budget was left when each one came up, and
   gone on paying for image renders to ask a question already refused.
6. **`estimated_cad` is the padded pre-call estimate, not the actual cost.**
   `photoreal`, `bible` and `model_registry.compare_hair` passed `estimated_cad=cost` — the
   bill compared with itself. That made the estimate-versus-actual column of the spend report
   report perfect estimation on three paths by construction. **This is a defect fixed, not a
   check weakened**: the column now carries the number that was actually reserved against the
   ceiling.

**UNKNOWN — whether any of this fires in production.** Nothing was deployed. `market_radar`
at CA$3.94 against CA$4.00 on 2026-09-24 is the reading that says the agent ceiling will bite;
there is no equivalent daily reading for `quality_director` or `creative_director` in front of
this department, so how often these seven call sites refuse is not established.

### A naming discrepancy, recorded rather than silently resolved

The brief for this session lists `src/brambleloop/brand/bible.py` among the files that call
`spend_report.record` and never `check_budget`. **SOURCED — it does not.** `brand/bible.py`
is the brand system: a palette, type, crop rules and a character bible, with no provider call
and no ledger write anywhere in it. The file wave 2 actually names is **`visual/bible.py`**,
and that is the one with the hole and the one that was fixed. `visual/bible.py` appears in
neither the "you own" nor the "do not touch" list of this session's brief; it is Visual's, the
audit addressed it to Visual, and it is treated as in scope. If that was wrong, the change is
one self-contained function.

---

## 2. The question the audit could not answer, measured

> Is there any remaining model-spend call site in `src/` that reaches a provider without
> passing through `check_budget`?

Wave 2 closed six paths **by name**. Naming six is not the claim "there are no others", and
the gap between those two statements is exactly the room a seventh gets added in. So it is
measured: `tests/test_model_spend_paths.py` parses every module under `src/` with `ast`, finds
every call to a provider's `see` or `complete`, and compares that set against the set whose
enclosing function calls `check_budget`.

**SOURCED — the scan, run on this tree, 2026-09-25.** Fifteen provider call sites. Thirteen
guarded. **Two are not**, and neither is in a file this department may edit:

| site | owner | what is open |
|---|---|---|
| `gateway/model_gateway.py::complete_json` | the gateway | Bills through `agents.registry.record_cost`, which checks the agent's daily ceiling **after** the provider has answered and checks the authorised month **not at all**. A post-hoc check is a measurement, not a control. The cross-process reservation never touches this path, so two workers running pinned prompts against a month with CA$1 left both find room. |
| `publish/motif_fidelity.py::check` | Publishing (`publish/**`) | One vision call per customer-facing asset. It is checked by nothing **and billed by nothing** — no `spend_report.record`, no `CostEntry` — so this call site is invisible to the monthly total as well as unguarded by it. That is worse than the shape the audit's §2 describes: money that leaves without a row is money the ceiling above it is then computed wrong from. |

Both are pinned in `KNOWN_UNGUARDED` with exact equality in both directions: a new unguarded
site fails the test, and closing one of these fails it too, with a message saying to delete the
entry in the same commit. A list of open holes that still names a closed one stops being read.

### The bigger finding: image generation is outside the mechanism entirely

**SOURCED — nine functions in `src/` render an image, and not one of them passes through
`check_budget`:** `gateway/image_bench.py::_run_inside`, `gateway/images.py::reference_probe`
and `::probe`, `publish/model_photography.py::make`, `publish/owned_photography.py::make`,
`visual/portrait_repair.py::propose`, `visual/reference_pack.py::_render`,
`visual/tournament.py::generate_candidates` and `::stress_test` (eleven call sites).

**SOURCED — they cannot, today, and the reason is in the mechanism rather than in them.**
`check_budget` prices a call with `estimate_cad(model, input_tokens, output_tokens)` against
`PRICES_USD_PER_MTOK`, which is a **per-token** table. An image render is priced **per image**
(`gateway.images.ImageProvider.cad_per_image`) and its provider keys — `gpt-image-2`,
`flux-2-pro`, `nano-banana-2` — are not in that table at all, so calling `check_budget` on one
raises *"has no price on file, so its cost cannot be checked against the ceiling"* instead of
checking anything.

**INFERRED — this is the largest remaining hole in the owner's rule**, because image renders
are the most expensive single calls this company makes (`image_bench.run` renders thirty per
candidate) and they reach the provider with no pre-call ceiling check and no reservation at
all. Two of the eleven sites are in a file this department owns (`visual/tournament.py`) and
were deliberately **not** given a bypass or a second, image-shaped ceiling of their own: the
owner's rule is one mechanism, and inventing a second one in a Visual file is the exact move
the rule forbids.

**What would close it, for the owner of `gateway/anthropic.py`** (not written here, because
it is a change to the shared mechanism and it needs the gateway's own judgement on the
estimate):

```
check_budget(db, *, model, input_tokens=0, max_tokens=0, images=0, ...)

    estimate = estimate_cad(model, input_tokens=..., output_tokens=...) when the model is
    in PRICES_USD_PER_MTOK, and images * gateway.images.BY_KEY[model].cad_per_image * 
    ESTIMATE_PADDING when it is an image provider key. One function, one padding, one
    reservation row, one refusal message. An image call then reserves, checks and releases
    like every other.
```

The eleven sites are pinned in `KNOWN_IMAGE_GENERATION` so the set cannot grow while this is
true, and the test asserts that those three provider keys are still absent from
`PRICES_USD_PER_MTOK` — so the day somebody prices them, the test says to re-read this finding
rather than silently continuing to excuse the sites.

### What the scan can and cannot see

Stated in the test file itself, because a check that overstates its reach is requirement 40's
defect wearing a new hat:

* It reads the **source**, not a run. A provider reached through a callback the scanner cannot
  follow would be missed. **UNKNOWN** — whether such a path exists; none was found.
* A `check_budget` anywhere in the enclosing function counts as guarding every provider call
  in it. True of every call site in this repository today; it would stop being true of a
  function that checked once and called twice on different estimates.
* The exclusion list (`self.queue.complete`, which marks a job done) is one entry, is checked
  against `queue.durable.JobQueue` for being genuinely not a provider, and is checked for
  still existing in `src/` — an exclusion list nobody prunes is where a real spend path hides.

---

## 3. `Material.fibre_content`

Built to `research/CHILDRENS_STATEMENTS.md` §5's specification, which is quoted verbatim in
`tests/test_cir_fibre.py`.

```python
fibre_content: tuple[tuple[str, int], ...] = ()
```

Validated in `Material.__post_init__`: a closed vocabulary (`cir.model.FIBRES`), whole
percentages in 1..100, no fibre stated twice, and a sum of exactly 100 when non-empty.
Normalised to descending percentage with alphabetical ties.

**Why normalised rather than kept as declared.** `CIR.fingerprint` hashes `to_dict` and is
the pipeline's idempotency key, so two declaration orders of one composition would give one
design two fingerprints and re-run certification for nothing — the inverse of the defect that
property's docstring was written about.
Descending by weight is also how a composition is customarily written, so the document gets
the customary order without the writer deciding it in a second place.

**Why validated in `__post_init__` rather than in the compiler.** The field arrives three
ways — typed by a product module, round-tripped through `CIR.from_dict` where JSON has turned
every tuple into a list, and reconstructed from a document — and a field validated in one of
the three is a field validated in none. `test_a_composition_that_survived_serialisation_is_
still_validated` is the one that proves the JSON path is not a way past the rules.

### The round trip, and B-005

Decision B-005 forbids the writer and the reverse compiler sharing parsing code, so the field
needed a grammar on each side:

* **Writer** — `cir/writer.py::material_line` puts the composition on the Materials line with
  the yarn it describes: `dk cotton (cream), 100% cotton; dk cotton (wine), 55% cotton, 45%
  linen`. With the yarn rather than in a footnote, because a composition floating free of the
  yarn it describes is the kind of fact that gets attached to the wrong one.
* **Reverse** — `cir/reverse.py::parse_fibre_content` finds the Materials line with its own
  regex, splits on `;`, and looks for a percent sign followed by a word. It does not import
  the writer and does not know how the writer spelled anything.
  `test_the_reverse_compiler_reads_a_line_no_writer_in_this_repository_produced` feeds it
  `Aran Wool Blend [ivory] - 70 % merino and 30% nylon` — a space before the percent sign, a
  dash where the writer puts a comma, and the word "and" between the pairs — and it reads it. That is what makes this a check rather than a
  comparison of one function with itself.
* **`reverse.compare`** raises `REVERSE_FIBRE_CONTENT` when the recovered structure differs
  from the CIR's, in **both** directions: a document that lost the composition, a document
  that invented one, and a composition attached to the wrong yarn are three separate tests,
  each proved against the injected defect.
* **Silence on both sides is not a finding.** Every existing CIR states nothing and every
  existing document prints nothing; making that pair a finding would bury the real ones under
  eleven copies of a gap everybody already knows about. `test_a_pattern_that_states_nothing_
  prints_nothing` pins that **not one byte of any existing document changes**.

### The eleven existing CIRs get **no** values, and that is the decision

**SOURCED — there is no source to read a composition from.** Every Launch-0 material is a
generic yarn description: `"worsted acrylic"`, `"worsted cotton"`, `"dk cotton"`,
`"chunky acrylic"`, built in `products/builder.py`, `products/texture.py`,
`products/vessels.py` and `products/nordic_forest.py`. No manufacturer, no product, no ball
band, no supplier declaration. Nothing states what any of these yarns is made of.

**INFERRED — and writing one anyway would be the exact inference the owner forbade.**
`(("acrylic", 100),)` derived from the word "acrylic" in a yarn name is not a reading of a
source; it is a guess given a schema field to live in, which is worse than the gap because the
field's whole purpose is to be the place where a *stated* fact lives. `publish/substitution.py`
reads a fibre *class* out of the same name and `publish/pdf.fibres_named` reads a fibre *word*
out of it; both are honest readings of a yarn description, and a yarn description is not a
composition. So the eleven stay empty, `test_the_eleven_launch0_cirs_state_no_fibre_content`
pins it, and the failure message tells whoever changes that to say where they read it.

**An empty field never reads as "no fibre concerns."** It reads as "not stated", and the
consumer refuses: `publish/pdf.fibres_named` already returns nothing and reports
`fibre_and_care` unrenderable when no fibre can be established, and `build_pattern_pdf`
refuses the product rather than shipping it. `test_an_empty_field_never_reads_as_no_fibre_
concerns` pins both halves.

**UNKNOWN, unchanged:** the fibre *content* of any Brambleloop pattern. What is SOURCED is
still the fibre the pattern was written for, from the yarn name. The field now exists so that
the day a real yarn with a real ball band is specified, the fact has somewhere to live that
the document prints and an independent reader can check.

### The two fibre vocabularies

`cir.model.FIBRES` is the same seventeen words as the union of
`publish.substitution.FIBRE_CLASSES`. The schema cannot import `publish` — `publish` reads
`cir` and the arrow must not turn round — so this is a second copy of one fact, which is the
drift this repository keeps meeting.
`test_the_two_fibre_vocabularies_are_the_same_seventeen_words` fails the moment they disagree,
in either direction, and names which words moved. **No diff is required of Lane D for this**;
if the owner of `publish/substitution.py` would rather delete the copy than pin it, the move
is to hoist `FIBRE_CLASSES` itself into `cir/model.py` (the taxonomy is a property of the
vocabulary) and re-export it, and then delete that test.

---

## 4. Diffs left for other owners

### 4.1 `publish/pdf.py` — `fibres_named` should prefer the stated field (**owner: Lane D / Publishing**)

The one `CHILDRENS_STATEMENTS.md` §5 asked for: *"With that field present,
`publish.pdf.fibres_named` reads it in preference to the yarn name."* Per material rather than
all-or-nothing, so a CIR that states a composition for one yarn and not the other reports
exactly that instead of falling back wholesale. Apply to the body of `fibres_named`:

```diff
@@ def fibres_named(cir: CIR) -> tuple[tuple[str, ...], str]:
     known = sorted({fibre for family in substitution.FIBRE_CLASSES.values()
                     for fibre in family})
     found: list[str] = []
     silent: list[str] = []
+    stated: list[str] = []
+    inferred: list[str] = []
     for material in cir.materials:
-        name = (material.name or "").lower()
-        words = set(re.findall(r"[a-z]+", name))
-        hits = [fibre for fibre in known if fibre in words]
+        if material.states_fibre_content:
+            # The source stated a composition. Preferred over the yarn name without
+            # exception: a name is a description this module reads a fibre word out of,
+            # and a composition is a fact somebody recorded.
+            hits = [fibre for fibre, _percent in material.fibre_content]
+            stated.append(material.color_id or material.name or "(unnamed)")
+        else:
+            name = (material.name or "").lower()
+            words = set(re.findall(r"[a-z]+", name))
+            hits = [fibre for fibre in known if fibre in words]
+            if hits:
+                inferred.append(material.color_id or material.name
+                                or "(unnamed)")
         if not hits:
             silent.append(material.name or "(unnamed)")
             continue
         for fibre in hits:
             if fibre not in found:
                 found.append(fibre)
 
     if silent:
         return (), (
-            f"the yarn name(s) {sorted(set(silent))} name no fibre this module recognises, "
-            f"and cir.model.Material has no fibre field to fall back on. Naming a fibre here "
-            f"would be inventing one")
+            f"the yarn name(s) {sorted(set(silent))} name no fibre this module recognises "
+            f"and state no cir.model.Material.fibre_content. Naming a fibre here would be "
+            f"inventing one")
+    if stated and not inferred:
+        return tuple(found), (
+            "read from cir.model.Material.fibre_content, a composition the CIR records "
+            "because a source stated it, rather than inferred from a yarn name")
+    if stated:
+        return tuple(found), (
+            f"read from cir.model.Material.fibre_content for {sorted(set(stated))} and "
+            f"inferred from the free-text yarn name for {sorted(set(inferred))}, against "
+            f"publish.substitution.FIBRE_CLASSES. The second is a yarn description and not "
+            f"a fibre content")
     return tuple(found), (
         "read from cir.model.Material.name, the free-text yarn name, against "
-        "publish.substitution.FIBRE_CLASSES. The CIR schema records no fibre field and no "
-        "fibre content")
+        "publish.substitution.FIBRE_CLASSES. No material states a "
+        "cir.model.Material.fibre_content, so this names the fibre the pattern was written "
+        "for and not a fibre content")
```

**This diff was applied to a scratch copy of `pdf.py`, exercised, and reverted** — it is Lane
D's to land, not this department's. With it applied: a CIR stating nothing reads the same as
today; a CIR stating one of two compositions reports which yarn each fibre came from
(`for ['cream'] and inferred ... for ['wine']`); a CIR stating both reports the composition
alone; and `Material(name="Bernat Blanket")` with neither still returns `()` with *"Naming a
fibre here would be inventing one"*. `tests/test_childrens.py` (38) and
`tests/test_cir_fibre.py` (19) both pass with the patch applied and with it reverted.

The docstring's paragraph beginning *"`cir.model.Material` has `name`, `yarn_weight`, … **There
is no fibre field**"* is now false and needs replacing with: the schema records
`fibre_content`, it is empty on every Launch-0 material because no source states one, and the
yarn-name reading is the documented fallback for that case and is never a composition.

**The free-text inference is not dead code and must not be deleted.** §5 anticipated that it
would become so; it has not, because no CIR states a composition, and deleting the fallback
today would make every children's product unrenderable. It becomes deletable when every CIR a
children's gate can reach states a composition, and not before.

### 4.2 `publish/motif_fidelity.py::check` — a provider call that is neither checked nor billed (**owner: Lane D / Publishing**)

Not a diff, because the estimate is the caller's judgement: it shows the render **and** the
chart, so it needs two image allowances. The shape is `creative/reference.py::read_listing`
verbatim — `check_budget(..., agent=<the publishing agent>, purpose="motif_fidelity")` before
`provider.see`, `release_reservation` on both exits, and a `spend_report.record` row, which
this call site has never written at all. Until then its spend is invisible to the monthly
total that every other ceiling in the company is computed from.

### 4.3 `gateway/model_gateway.py::complete_json` — post-hoc is not a control (**owner: the gateway**)

`check_budget(db, model=provider.model, input_tokens=len(user)//4,
max_tokens=prompt.max_output_tokens, agent=agent, purpose=prompt.ref)` before
`breaker.call(...)`, released in `_record`. Note that this loops over providers and retries,
so each attempt needs its own reservation or the loop re-checks against a stale claim — the
same mistake `intel/vision.py` made with `uncommitted_cad`.

### 4.4 `gateway/anthropic.py::check_budget` — teach it a per-image estimate (**owner: the gateway**)

§2 above. Eleven call sites are waiting on it and two of them are in Visual's files.

### 4.5 `gateway/anthropic.py::release_reservation` — it reads a clock its caller cannot set (**owner: the gateway**)

**SOURCED — found by a test failing on this tree, and it is not this diff's.**
`check_budget` takes a `now` and threads it into the reservation's expiry, deliberately:
wave 2's own comment says a caller that supplies a timestamp would otherwise write a
reservation that reads as already expired. `release_reservation` takes no `now` at all and
reads the wall clock. So a caller that supplies an instant on the way in **cannot** supply one
on the way out, and its release lands on the other side of the row's expiry. That is the same
two-clocks defect wave 2 found in `registry.spend_today` and fixed, left half-done on the
return path.

```diff
-def release_reservation(db, reservation_id: int | None, *,
-                        actual_cad: float | None = None) -> bool:
+def release_reservation(db, reservation_id: int | None, *,
+                        actual_cad: float | None = None,
+                        now: datetime | None = None) -> bool:
@@
-    return reservations.release(db, reservation_id, actual_cad=actual_cad)
+    return reservations.release(db, reservation_id, actual_cad=actual_cad, now=now)
```

`finance.reservations.release` already takes `now`, so this is a passthrough and nothing
below it changes. It bit nothing in production (every production caller uses the wall clock at
both ends); what it bit was
`test_cost_governance_wave2.py::test_release_returns_the_money_and_records_what_the_call_
actually_cost`, which reserved at the frozen `NOW` and released at the wall clock and was
therefore **green only during the five minutes after 12:00 UTC on the frozen date**. Fixed in
the test (§5 item 8); the asymmetry is the gateway's to close.

### 4.6 `intel/childrens.py` — the statement can say more once a CIR states a composition (**owner: Children's Safety Deliverable**)

`StatementFacts.fibres` is a tuple of fibre words, and `fibre_and_care`'s text is written
around "the fibre this pattern was written for". When a material states a composition, the
statement could state it — `55% cotton, 45% linen` — and the sentence about the ball band
deciding the finished object stays true and stays necessary. Not done here: the statement
wording is that department's and changing it from outside is how one decision acquires two
surfaces.

### 4.7 Test fixtures corrected in four suites (**applied, listed so no owner is surprised**)

`check_budget` refuses a model with no entry in `PRICES_USD_PER_MTOK` — *"an unpriced call is
an unbounded one"* — and `AnthropicProvider.__post_init__` refuses to construct one for the
same reason. Four suites inject a fake provider declaring `model = "test"`, which production
therefore cannot build, and which the new pre-call guard correctly refuses. **Diagnosis: the
artefact is right and the instrument was out of date.** The fixture predates there being any
pre-call guard on these paths, when an unpriced fake was harmless.

One line each, `model = "test"` → `model = "claude-sonnet-5"` (the model
`routing.route("asset_inspection")` actually returns), with a trailing comment:

| file | line | was |
|---|---|---|
| `tests/test_model_freeze.py` | 34 | `"test"` |
| `tests/test_photoreal_calibration.py` | 34, 157 | `"test-model"`, `"test"` |
| `tests/test_portrait_repair.py` | 35, 130, 379 | `"test"` |
| `tests/test_reference_pack.py` | 668 | `"test"` |

**No assertion was changed, no threshold moved and no check removed.** 22 tests across those
four suites went red on the guard and are green on the fixture. `tests/test_bible.py:96` also
declares `"test-model"` and was left alone: it passes no `db`, so it reaches no guard, and
changing a fixture that is not broken is not a fix.

---

## 5. Defects found, ranked, including the ones not fixed

1. **Image generation reaches a provider with no ceiling check at all** — eleven call sites,
   nine functions, the most expensive calls this company makes. **Not fixed**: the mechanism
   cannot price a per-image call, and building a second ceiling for images is the one thing
   the owner's rule forbids. §2, with the change the gateway needs.
2. **`publish/motif_fidelity.py::check` spends and writes no ledger row.** **Not fixed** —
   `publish/**` is Lane D's. Worse than an unguarded path: unbilled spend makes the monthly
   total that every other ceiling reads *wrong*, rather than merely unchecked.
3. **`gateway/model_gateway.py::complete_json` has no pre-call check.** **Not fixed** — the
   gateway's. Its daily check runs after the money has left and it never sees the month.
4. **Five Visual spend paths unguarded, one unreleased.** **Fixed**, §1.
5. **A ceiling refusal would have been scored as a candidate that judged badly.** Found while
   adding the guard to `tournament._judge` and fixed in the same change, because it is a
   defect this session's own diff would otherwise have introduced. `BudgetExceeded` is a
   `PermanentError` and `generate_candidates` already caught `PermanentError` per candidate
   and continued, so a refusal would have been recorded as that candidate's screen failure
   and the loop would have gone on to **render the next one** -- paying for an image, on a
   path no ceiling check reaches, to ask a question the budget had already refused, once per
   remaining seed note. The same hole in `stress_test` is worse: `compare_identity` returns
   an error dict rather than raising, `identity.drift_check` reads a dict with no dimensions
   as maximum drift, and a finalist would have been **disqualified because the budget ran
   out** on the run that decides whether she becomes the brand's permanent identity. Both
   now stop and report `stopped_by`; the floor for a run with no judged scene is
   `unverifiable`, not `fail`. `model_registry`'s three functions mark a ceiling refusal
   with an additive `ceiling` key so a loop can tell it from a model that failed -- every
   existing reader still sees an `error` and still treats the dimension as unmeasured.
   **Fixed**, two tests, both proved against an injected refusal.
6. **`estimated_cad=cost` on three paths** made the spend report's estimate-versus-actual
   column compare the bill with itself. **Fixed** in `photoreal.judge`, `bible.judge` and
   `model_registry.compare_hair`.
7. **`gateway.release_reservation` takes no `now` while `check_budget` does.** **Not fixed**
   -- `gateway/**`. §4.5, with the two-line diff.
8. **`test_cost_governance_wave2.py::test_release_returns_the_money_...` was green for five
   minutes a day.** Pre-existing, time-dependent, and nothing to do with this diff: it
   reserved at a frozen instant and released at the wall clock, so the row was already
   expired and `release` correctly returned `False`. Demonstrated by re-running the same
   sequence with `now=NOW` passed to `finance.reservations.release` (True) and without
   (False), at 12:55 UTC against a 12:05 expiry. **Fixed** by taking the reservation at the
   real instant; every assertion is unchanged, the public wrapper is still what is
   exercised, and the underlying asymmetry is §4.5's.
9. **`cir.model.Material` recorded no fibre** (`CHILDRENS_STATEMENTS.md` §9 item 3).
   **Fixed**, §3.
10. **Four test fixtures declared a model production cannot construct.** **Fixed**, §4.7.
11. **`model_registry`'s error strings are truncated to 200 characters**, which cuts a
    ceiling refusal off before the sentence saying the work resumes at the next UTC day and
    how to raise the permission. **Not fixed and recorded in the test that noticed it**: the
    truncation is pre-existing, it applies to provider failures too, and widening it is a
    decision about every error those three functions return.
12. **`brand/bible.py` named in the brief where `visual/bible.py` was meant.** Recorded in §1
    rather than silently resolved.

## 6. What is still blocked, and what would unblock it

* **A fibre content claim for any Brambleloop product** — blocked on a yarn somebody has
  actually specified, with a ball band or a supplier declaration behind it. Not a code
  problem any more: the field, the writer, the reverse compiler and the tests are in place and
  the day a source exists the fact has somewhere to live. Unblocked by a merchandising
  decision naming real yarn, not by a session.
* **Image-render spend governance** — blocked on `check_budget` learning a per-image estimate
  (§2, §4.4). Owner: the gateway.
* **The two unguarded text call sites** — blocked on their owners (§4.2, §4.3).
* **Any claim that the seven Visual guards refuse anything in production** — blocked on a deploy, which
  this department does not perform. What is established is the code and the tests, on this
  tree, at CA$0.00.

## 7. Tests

Run as `PYTHONPATH=src <python> tests/<file>.py`. `run_tests.sh` was **not** run: the
integrator runs it.

**New:** `tests/test_model_spend_paths.py` (12 checks) and `tests/test_cir_fibre.py`
(20 checks). **Thirty-two checks added, none removed, no threshold lowered.** Two existing
checks changed and both were the instrument rather than the artefact, diagnosed in §4.7 and
§5 item 8; no assertion was relaxed in either.

Proved against an injected defect, so neither stops being a test once the defect is fixed:

* Deleting the `check_budget` block from `visual/photoreal.py::judge` makes
  `test_no_model_spend_path_reaches_a_provider_without_the_ceiling_check` name
  `('brambleloop/visual/photoreal.py', 'judge')` and
  `test_every_visual_spend_path_passes_its_agent_and_releases_its_reservation` say *"checks no
  ceiling"*. Restored; both green. A synthetic unguarded module is also fed to the scanner
  directly, so the check does not depend on the tree being broken to be exercised.
* Stripping `, 100% cotton` out of a rendered pattern makes `reverse.compare` return exactly
  `["REVERSE_FIBRE_CONTENT"]`; moving it to the other yarn does too; adding one the CIR never
  stated does too; and a document claiming 60% + 30% is refused as unparseable naming 90%.
* Making `writer.material_line` return the yarn name without its composition -- the exact
  shape of "the fact is in the CIR and not in the document" -- fails five checks, including
  `test_the_composition_reaches_the_customers_document` with *"the composition never reached
  the buyer"*. That one is measured on the **rendered PDF bytes** read back with `pypdf`,
  not on `write_pattern`'s string: `CHILDRENS_STATEMENTS.md` §4's rule, that a check which
  cannot see the artefact it exists to measure is not a check. Restored; all twenty green.
  The rendered document carries `Materials: dk cotton (cream), 55% cotton, 45% linen; dk
  cotton (wine)` and the page count is unchanged, so the composition is not displacing
  anything.

Suites re-run on the final code, chosen by grepping for every consumer of what this diff
touches (`check_budget`, `release_reservation`, `spend_report.record`, `Material`,
`write_pattern`, `reverse.compare`, `fibres_named`, and every module edited):

| suite | passing | | suite | passing |
|---|---|---|---|---|
| `test_model_spend_paths` **(new)** | 12 | | `test_cir_fibre` **(new)** | 20 |
| `test_compiler` | 9 | | `test_reverse` | 12 |
| `test_twin` | 6 | | `test_visual` | 10 |
| `test_cost_governance_wave2` | 39 | | `test_spend_governance` | 35 |
| `test_spend_policy` | 24 | | `test_finance` | 16 |
| `test_governor` | 16 | | `test_health` | 34 |
| `test_reliability` | 17 | | `test_defects` | 16 |
| `test_intel` | 38 | | `test_provider_trial` | 22 |
| `test_platform` | 22 | | `test_takeover` | 11 |
| `test_creators` | 39 | | `test_universe` | 13 |
| `test_lanes` | 26 | | `test_roles` | 35 |
| `test_veto` | 17 | | `test_improve` | 24 |
| `test_mechanisms` | 16 | | `test_layout_qa` | 16 |
| `test_visual_inspection` | 24 | | `test_model_identity` | 22 |
| `test_model_photography` | 44 | | `test_owned_photography` | 30 |
| `test_final_standard` | 28 | | `test_parity` | 8 |
| `test_blinded` | 37 | | `test_image_bench` | 59 |
| `test_creative` | 11 | | `test_gateway` | 30 |
| `test_model_tournament` | 18 | | `test_model_freeze` | 14 |
| `test_reference_pack` | 43 | | `test_photoreal_calibration` | 19 |
| `test_portrait_repair` | 21 | | `test_bible` | 13 |
| `test_engine` | 41 | | `test_executor` | 34 |
| `test_build2` | 11 | | `test_maturity` | 15 |
| `test_benchmark_garment` | 12 | | `test_benchmark_matrix` | 10 |
| `test_family` | 17 | | `test_collections` | 12 |
| `test_seasonal_cycle` | 15 | | `test_brand` | 23 |
| `test_fabric` | 8 | | `test_swarm` | 6 |
| `test_friction` | 19 | | `test_shop_package` | 18 |
| `test_teardown_reader` | 12 | | `test_persistence` | 10 |
| `test_clusters` | 15 | | `test_continuity` | 15 |
| `test_acceptance_gates` | 23 | | `test_childrens` | 38 |
| `test_products` | 16 | | `test_geometry` | 44 |
| `test_texture` | 25 | | `test_rowcycle` | 20 |
| `test_quality` | 17 | | `test_motif_fidelity` | 14 |
| `test_assembly` | 14 | | `test_grading` | 8 |
| `test_specification` | 10 | | `test_launch0` | 50 |
| `test_commerce` | 53 | | `test_gates` | 33 |
| `test_benchmarks` | 16 | | `test_certification` | 7 |
| `test_artefacts` | 23 | | `test_deliverable` | 14 |
| `test_calibration` | 27 | | `test_dimensions` | 17 |
| `test_colour` | 7 | | `test_accessibility` | 9 |
| `test_deliverable_qa` | 48 | | | |

**Eighty-three suites, 1,792 checks, all green, zero failing.** `test_childrens` is green **both** with
the §4.1 patch applied and with it reverted.

