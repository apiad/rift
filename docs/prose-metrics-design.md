# Prose metrics — design

**Status:** approved 2026-08-26, not yet implemented.
**Scope:** a second rule kind for rift — `measure` / `expect` — plus the
measurement engine behind it.

## Why this exists

rift today answers one question: *does this string exist in the code but not in
the docs?* This adds a second: *is this document shaped like its siblings, and
does it still read like the same hand wrote it?*

The motivating case is a book drafted with agent help. Across a single day of
revision on `repos/books-tsoc`, four separate defects reached the rendered PDF
that no test could see: a chapter that opened unlike every other chapter, prose
that flattened into uniform sentence lengths, an em-dash density that tripled in
one section, and glossary markers clustered in one Part and absent from another.
Each was caught by a human or an agent reading carefully. None was caught
mechanically, because nothing was counting.

## Design principles

These are constraints, not preferences. A change that violates one is wrong even
if it is useful.

1. **No LLM.** Not as a dependency, not as an optional backend, not "for the
   hard cases". rift's output must be reproducible and explainable from the
   source alone.
2. **No encoded taste.** rift ships **no default thresholds**. A rule with no
   `expect:` reports its number and passes. Every judgment about what is too
   uniform or too long lives in the consumer's `.rift.yaml`.
3. **Language-agnostic.** Every metric must work unchanged on Spanish
   (`repos/enciclopedia`) and on English. This rules out readability scores —
   Flesch and its relatives bake in English syllable assumptions *and* a theory
   of good writing, which is exactly the taste principle 2 forbids.
4. **Mechanical, not semantic.** rift reports a distance and the threshold it
   was measured against. It never characterises prose. It must never emit the
   word "AI", "machine-written", or "bad".
5. **Push mechanical as close to semantic as it goes.** Within 1–4, prefer the
   metric with the most interpretive reach. Burrows's Delta over raw word
   counts; sentence-length autocorrelation over a bare mean.

## Definitions

Every metric below is stated in terms of tokens, sentences and paragraphs. Those
three words carry the whole design's language-agnosticism, so they are defined
here rather than left to the implementer.

**Token.** A maximal run of Unicode word characters, lowercased. `\w+` with
Unicode semantics, which covers accented Latin, Cyrillic and CJK-adjacent scripts
without a per-language rule. Numbers count as tokens. Markup does not: strip
markdown syntax, code fences, inline code, link URLs, HTML tags and any
configured `pattern` markers before tokenising, so a chapter is not penalised for
carrying more glossary markers than its neighbour.

**Sentence.** A split on `[.!?…]+` followed by whitespace and an uppercase letter
or digit, plus end-of-paragraph. This is deliberately crude, and the crudeness is
the point: it is the same crudeness in every language, so a comparison *between*
files is valid even where the absolute count is not. Abbreviations ("Ph.D.",
"e.g.") will over-split. That is acceptable because every file in a set is
over-split by the same rule, and every metric that uses sentences is either a
ratio or a comparison against siblings.

**A metric that depends on absolute sentence counts being correct does not belong
in this design.** None of the catalogued metrics does.

**Paragraph.** A run of non-empty lines delimited by blank lines, after markdown
block elements (headings, fences, tables, list blocks) are removed.

## The flagship: voice divergence

**Burrows's Delta**, the standard method in authorship attribution.

Given a set of documents:

1. Tokenise each to lowercase word tokens.
2. Take the *N* most frequent tokens across the whole set (default N = 150).
3. For each document, compute each token's relative frequency.
4. Z-score each token's frequency across the document set.
5. A document's Delta against the set centroid is the mean absolute z-score.

It reaches "a different hand wrote this" because the most frequent tokens in any
language are function words — articles, prepositions, auxiliaries — whose rates
are an authorial fingerprint writers do not consciously control. It needs no
dictionary, no stopword list, and no knowledge of the language, which satisfies
principle 3 for free.

**Known limitation, stated up front.** Delta is normally applied to whole novels.
On ~3,000-word chapters the absolute values are noisy. It will still *rank*
correctly — the outlier chapter will have the highest Delta — which is why the
recommended threshold is `vs-siblings`, a relative comparison against the set's
own spread, rather than any fixed ceiling. A fixed `max:` is supported but
documented as the weaker choice.

## Metric catalogue

Every metric is a pure function from text (or a token/sentence sequence) to a
float. Each is computed per file; a project-level aggregate is the set.

### Voice

| Metric | Definition |
|---|---|
| `burrows-delta` | mean absolute z-score across the top-N frequent tokens, against the set centroid |

### Rhythm

| Metric | Definition |
|---|---|
| `sentence-length-cv` | coefficient of variation (σ/μ) of sentence length in tokens. **Burstiness.** Human prose runs high; generated prose runs low |
| `short-sentence-ratio` | proportion of sentences under 6 tokens. Humans use them for emphasis; uniform prose has almost none |
| `sentence-length-autocorr` | lag-1 autocorrelation of the sentence-length series. Humans write in runs — several long, then a short one. Uniform-random lengths sit near zero |
| `mean-sentence-length` | tokens per sentence |

### Texture

| Metric | Definition |
|---|---|
| `mattr` | moving-average type-token ratio over a fixed window (default 200 tokens). Length-independent, unlike raw TTR |
| `hapax-ratio` | proportion of tokens appearing exactly once |
| `self-repetition` | proportion of 4-grams that occur more than once in the document |

### Structure

| Metric | Definition |
|---|---|
| `paragraph-length-cv` | coefficient of variation of paragraph length in tokens |
| `mean-paragraph-length` | tokens per paragraph |
| `sections` | count of `##` headings |
| `words-per-section` | tokens divided by section count |
| `mean-heading-length` | tokens per heading |
| `opening-paragraphs` | blocks between the `#` title and the first `##` |

### Apparatus

| Metric | Definition |
|---|---|
| `pattern` | occurrences of a caller-supplied regex, optionally normalised `per:` N tokens |

`pattern` is how apparatus is counted without rift knowing anything about any
renderer. Glossary markers, timeline markers, footnote references and em-dashes
are all the same mechanism with a different regex, supplied by the consumer.

## Rule shape

A rule carries `extract`/`require` (existing) **or** `measure`/`expect` (new).
Both in one rule is a config error.

```yaml
rules:
  - name: "chapters keep human sentence rhythm"
    severity: error
    measure:
      files: "[1-4]_*/ch*.md"
      metric: sentence-length-cv
    expect:
      min: 0.35

  - name: "no chapter reads like a different author"
    measure:
      files: "[1-4]_*/ch*.md"
      metric: burrows-delta
    expect:
      vs-siblings: 2.0

  - name: "glossary markers are evenly spread"
    measure:
      files: "[1-4]_*/ch*.md"
      pattern: '\{~[a-z0-9-]+\}'
      per: 1000
    expect:
      vs-siblings: 2.5
```

### `expect` predicates

| Key | Meaning |
|---|---|
| `min` / `max` | absolute bounds on the metric |
| `vs-siblings: K` | fail a file whose metric is more than K standard deviations from the mean of the other files in the set |

`vs-siblings` is the predicate to reach for first. It self-calibrates: it needs
no tuning when a book grows, and it encodes no opinion about what any number
should be — only that one file should not differ sharply from its peers. This is
a recommendation about which predicate to *write*, not a threshold rift ships;
principle 2 stands, and a rule with no `expect:` still passes.

**Degenerate sets.** `vs-siblings` requires at least 4 files to be meaningful and
at least 2 to be computable. With fewer than 4, rift reports the number, emits a
warning that the set is too small to judge, and passes. It must not silently
pass, and it must not fail — either would be a lie about what was checked.

**Zero variance.** If every file has the identical metric value, σ is 0 and the
z-score is undefined. Treat as "no outlier" and pass.

## Module boundaries

```
src/rift/measure.py   text -> numbers. Pure functions. No YAML, no rules,
                      no filesystem, no config. All the maths.        (~150 lines)
src/rift/extractor.py unchanged
src/rift/matcher.py   unchanged
src/rift/cli.py       + a branch for measure-rules, + a `stats` command  (~50 lines)
```

`measure.py` knows nothing about rift. It takes strings and returns floats, which
makes it testable against hand-computed fixtures with no repo fixture at all.

The rule layer stays thin: read files, call `measure`, apply `expect`, report.

## CLI

- `rift check` — runs every rule, including measure-rules. Exits 1 on failure.
  Unchanged contract.
- `rift stats <glob>` — reports the full metric table for a file set and exits 0
  always. This is the agent-facing surface: no thresholds, no judgment, just
  numbers to read. It is what an agent runs to ask "is this chapter unlike its
  siblings" without anyone having written a rule.

## Testing

rift's standing rule applies and is the reason this section exists:

> **A linter that cannot fail is worse than no linter**, because it licenses
> shipping.

1. **Every metric ships with a hand-computed fixture.** A test asserting
   `sentence_length_cv("...") == 0.0` for three sentences of identical length,
   computed by hand, not by running the implementation and pasting the output.
   A test whose expected value came from the code under test asserts nothing.
2. **Every metric ships a discrimination test**: two fixtures, one uniform and
   one varied, asserting the metric separates them in the expected direction.
   This is what catches a metric that computes *something* but not the thing.
3. **Mutation-test the predicates.** After changing `expect` handling, make the
   comparison `return True` and confirm the suite goes red. rift shipped a
   `heading` matcher in v0.1.0 that could never match, because no test would have
   noticed. The same class of bug is available here.
4. **Burrows's Delta gets a known-answer test**: a set where one document is
   built from a deliberately different function-word profile, asserting it ranks
   highest. Its absolute value is not asserted — only the ranking, which is the
   property the design actually relies on.

## Out of scope

- **Readability scores.** Principle 3.
- **Banned-phrase lists shipped with rift.** A consumer can express these today
  with `pattern` + `expect: {max: 0}`. rift shipping its own list would be taste.
- **Drift over time.** Comparing today's metrics against a committed baseline is
  a real and different feature, needing a baseline format and a refresh
  workflow. `vs-siblings` covers the common case without any of that machinery.
  Revisit once this is in use.
- **Per-section metrics.** Files are the unit. Sections could be a later
  granularity; nothing in this design forecloses it.
