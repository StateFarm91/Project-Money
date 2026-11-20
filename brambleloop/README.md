# Brambleloop Studio

A premium crochet publishing company and the autonomous operating system that runs it.

Canonical spec: `spec/01_Brambleloop_Master_Plan_v1.2.pdf`. Live status: `BUILD_STATE.md`.
Decisions and their reasoning: `DECISION_LOG.md`.

## The core idea

**Patterns are software releases.** A crochet pattern that does not work is a refund, a bad
review and a customer who wasted forty hours and CA$60 of yarn. So a pattern is never written
prose that a model guessed — it is compiled, executed and independently re-read by machinery
that can fail the release.

```
Market Brief -> Original Design -> CIR -> Deterministic Compiler -> Digital Twin -> Charts
  -> Written Pattern -> Reverse Compiler -> Adversarial QA -> Physical Test (if required)
  -> Asset Truth -> Policy Gate -> Quality Release Certificate
```

## What is built today

The CIR engine, with 27 passing tests. Everything else in the master plan is still ahead.

```bash
cd brambleloop
python3 tests/test_compiler.py    # deterministic compiler
python3 tests/test_reverse.py     # writer + reverse compiler
python3 tests/test_twin.py        # digital twin
```

### CIR — Crochet Intermediate Representation (`src/brambleloop/cir/`)

`model.py` holds the canonical pattern: components, rows, ops, repeats, gauge, materials,
colours. Every stitch in `stitches.py` declares how much fabric it *consumes* and *produces*,
which is what turns "does this pattern work?" into arithmetic.

`compiler.py` resolves each row against the fabric available to it and fails on any
disagreement — over-run, under-run, a repeat that does not divide evenly, a declared stitch
count that does not match the computed one, an unknown colour, an empty row. Nothing
downstream can override it.

```
Rnd 4: [sc in next 2 sts, inc in next st] x 6. (24 sts)
       consumes (2+1)x6 = 18   available 18 ✓   produces (2+2)x6 = 24 ✓   declared 24 ✓
```

`writer.py` renders the customer-facing pattern (US or UK terminology, magic-ring aware).
`reverse.py` then parses that text back into structure **with no knowledge of the source CIR**
and diffs the two. Writer and reverse compiler deliberately share no parsing code: if they
shared a grammar, a clean round trip would only prove the bug was symmetric. This is what
catches a bad PDF edit, a translation slip or a copy tweak before a customer hits it at row 40.

`twin.py` executes the validated stitches into a cell-level fabric model — chart and colour
grids, finished dimensions from gauge, per-colour yardage. Downstream gates use it to answer
questions about the actual object: does this listing image show a motif the pattern does not
contain? Is "fits a queen bed" supported by the gauge? Yardage carries an explicit ±20%
tolerance until a physical test calibrates it, because inventing precision would be exactly
the unsupported claim the Policy Gate exists to block.

The twin refuses to model a pattern that failed compilation — a twin built on broken
arithmetic is fiction.

## Status

Shadow Mode, pre-deployment. Nothing is connected to live customers, listings or spend.
No cloud deployment, no Etsy shop, CA$0 spent, CA$0 revenue, 0 customers. `BUILD_STATE.md`
is kept honest about this.
