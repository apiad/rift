# Prose linting — design

**Status:** approved 2026-08-26, not yet implemented.
**Scope:** two new rule kinds for rift — `measure` / `expect` (statistics) and
`forbid` (prohibited lexicon) — plus extractor and matcher additions that serve
both, and the measurement engine behind the first.

## Why this exists

rift today answers one question: *does this string exist in the code but not in
the docs?* This adds two more:

- *Is this document shaped like its siblings, and does it still read like the
  same hand wrote it?* — the `measure` / `expect` rule kind.
- *Does this document contain text I have declared it must not?* — the `forbid`
  rule kind.

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
2. **No encoded taste.** rift ships **no default thresholds and no default
   lexicons**. A rule with no `expect:` reports its number and passes; `forbid`
   ships zero entries. Every judgment about what is too uniform, too long, or
   too AI-tic lives in the consumer's `.rift.yaml`.
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

### Masking, not deleting

Both rule kinds need the same regions taken out of play before they look at the
text: fenced code, inline code, link URLs, HTML tags. One function serves both,
and it **masks** rather than deletes — an excluded region is replaced by spaces
of equal length.

This is not a stylistic preference. `forbid` reports `file:line` for every site
it finds, so byte offsets into the masked text must still index the original
file. Deleting a code fence shifts every subsequent line number and makes the
report wrong. `measure` re-tokenises and is indifferent, so masking costs it
nothing. A single implementation, one caller that depends on the offsets and one
that does not, is strictly safer than two implementations that agree today.

**Blockquotes are masked too, by default.** Quoted material is someone else's
prose: it should not move your voice metrics and must not trip your banned
lexicon. `include_quotes: true` on a rule puts them back in play.

**Masking applies to `forbid` and `measure`, never to `require`.** This was not
obvious until implementation and is easy to get backwards. `require` asks whether
something is **documented**, and a code fence is documentation — masking it would
break every existing rule that documents an env var inside a bash block.
`forbid` asks whether something is in **your prose**, and a code fence is not.

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

A rule carries exactly one of three shapes. More than one in a single rule is a
config error, and must be reported as one rather than silently resolved by
precedence.

| Shape | Kind | Asks |
|---|---|---|
| `extract` + `require` | existing | does each extracted string appear? |
| `extract` + `forbid` | new | where does each extracted string appear, if anywhere? |
| `measure` + `expect` | new | what is this number, and is it in bounds? |

`extract` is shared by the first two: the source of a set of strings is
orthogonal to what you then assert about it.

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

**Zero variance is two different cases**, and collapsing them hides the outlier
the check most needs to catch. Because `vs-siblings` is leave-one-out, σ is taken
over the *other* files:

- **All files identical.** The held-out value equals the sibling mean. No outlier;
  pass.
- **Siblings identical, held-out file differs.** σ is 0 but the z-score is not
  undefined — it is infinite, and the file is maximally outlying. This must
  **fail**, reported as `differs from identical siblings (<value>)`.

The naive reading — "σ is 0, skip the division" — silently passes exactly the
case where every chapter has two sections and one has twenty. Pinned by
`test_vs_siblings_flags_a_file_that_differs_from_identical_siblings`.

## Lexicon rules: coverage and prohibition

Two requirements that look unrelated turn out to be one shape with the fold
inverted:

- *Every Turing laureate in my roster is mentioned somewhere in the book.*
- *No chapter contains any phrase on my banned list.*

Both take a set of strings and ask about its presence in a document set. They
differ in the fold, and — decisively — in what a failure **is**.

| | coverage | prohibition |
|---|---|---|
| input | a set of strings | a set of strings |
| fold over the doc set | OR — appears somewhere | NOR — appears nowhere |
| unit of failure | a **missing entity** | a **present occurrence** |
| report | a checklist | `file:line` sites |

The fold inverts for free. The report unit is what forces new code, and it is
where the value is: *"delve is present"* is nearly useless, *`ch03.md:2 delve`*
is actionable.

### Coverage needs nothing new

This works against rift as it stands today. It was run, not reasoned about:

```yaml
- name: "every laureate in the roster is mentioned"
  extract: {file: "data/laureates.yaml", yaml_values: "laureates"}
  require: {in: "[1-4]_*/ch*.md", as: mention}
```

rift knows nothing about any renderer because `data/laureates.yaml` is an
ordinary YAML file that happens to live in the book. **The roster is the
consumer's artifact, not rift's.** That boundary is the whole reason this fits.

**Why there is no `in_files: N` predicate.** The obvious objection to coverage is
that a roster can be satisfied by an appendix nobody reads, so you would want to
demand mentions in *N* distinct files. It does not apply here: rift matches
source `.md`, and generated apparatus — indexes, appendices, tables of contents —
is produced at render time and never exists in the source set. The failure mode
the predicate would guard against is structurally unreachable, so the predicate
is not worth its lines. **This holds only while generated apparatus stays out of
the source tree**; a build that writes an appendix back into `.md` would
reintroduce it.

**Known limitation.** `mention` is a substring test, so a roster entry must be
the string that actually appears in the prose. `Dijkstra` passes where
`Edsger W. Dijkstra` fails. Roster surnames. rift has no alias mechanism and this
design deliberately does not add one: every shape considered turned `extract`'s
return type from `set[str]` into a set of groups, rippling through `matcher`, the
`list` command and the report — a large change for a case `as: regex` already
covers.

### Prohibition needs `forbid:`

A rule carries `require:` **or** `forbid:`, never both. Both are fed by the same
`extract:`.

```yaml
- name: "no AI-tic phrasing"
  severity: warning
  extract:
    list: [delve, tapestry, "rich history of"]
  forbid:
    in: "[1-4]_*/ch*.md"
    as: word
```

**Why this cannot be a config trick.** Prohibition is expressible today by
inverting an extract — pull the banned phrases *out of the prose* with a regex
and require them to appear in a file that does not exist. Run against real rift,
that prints:

```
✗  AI-tic phrases  [3 missing]
   Moreover   delve   tapestry
```

It says **missing** about three strings that are *present*. rift's one
non-negotiable property is that its output is literally true, and the workaround
breaks it. It also matched inside a code fence and inside a direct quotation, and
collapsed three occurrences into one entity with no line numbers. `forbid` exists
because the report has to be honest and locatable, not because the fold is hard.

**Report shape.** One line per occurrence, not per entity:

```
✗  no AI-tic phrasing  [4 occurrences]
   1_theory/ch03.md:2   delve
   1_theory/ch03.md:2   tapestry
   1_theory/ch03.md:3   Moreover
   2_practice/ch07.md:41  delve
```

### Supporting additions

Four small pieces, each serving both rule kinds.

| Addition | What it is | Why |
|---|---|---|
| `extract: {list: [...]}` | literal strings inline in the rule | A banned list **is** taste, and principle 2 puts taste in `.rift.yaml`. Unlike a roster, it cannot come from a repo data file |
| `extract: {file: X, lines: true}` | non-empty, non-`#` lines of a text file | For lists too large for the YAML. Also gives a plain-text roster with no YAML at all |
| `as: word` | `\b`-wrapped match | **Mandatory** for `forbid`, not optional: banning `just` would otherwise flag `adjusted`. Closes the open `tasks.md` item; `mermaid_node` already does this internally |
| `as: regex` | the entity *is* the pattern | Prohibited regexes, and the escape hatch for roster surface forms. Composes with `list:` |

### `measure` counts, `forbid` locates

Both kinds can express "this text should be rare", which risks two ways to say
one thing. The split is by what you get back:

- **A budget** — *at most 3 em-dashes per 1000 words* — is `measure` with
  `pattern` and `expect: {max: N}`. It yields a number.
- **A ban** — *never this phrase* — is `forbid`. It yields sites.

`forbid` therefore stays binary and grows no count predicates.

## Module boundaries

```
src/rift/text.py      masking, tokenising, sentence and paragraph splitting.
                      Pure. The Definitions section, in code.
src/rift/measure.py   text -> numbers. Pure functions. No YAML, no rules,
                      no filesystem, no config. All the maths.
src/rift/extractor.py + `list:` and `lines:` extractors
src/rift/matcher.py   + `as: word`, `as: regex`, + a `find` returning occurrences
src/rift/cli.py       + a measure-rule branch, + a forbid-rule branch,
                      + a `stats` command
```

`text.py` exists so that the masking rule has exactly one implementation. Both
`measure.py` and `matcher.py` depend on it and neither depends on the other —
`matcher` importing `measure` to reach a stripper would be the wrong shape and
would invite the maths to leak sideways.

`measure.py` knows nothing about rift. It takes strings and returns floats, which
makes it testable against hand-computed fixtures with no repo fixture at all.

`matcher.py` gains a second entry point beside `check`: `find(root, entity,
forbid) -> list[(path, line, entity)]`. `check` answers *is it anywhere?* and can
return early; `find` must visit every file and every site, because the report is
the occurrences. Neither is expressible in terms of the other without discarding
what the caller needs.

The rule layer stays thin: read files, call the engine, apply the predicate,
report.

## CLI

- `rift check` — runs every rule, of all three kinds. Exits 1 on failure.
  Unchanged contract. A `forbid` rule reports occurrences with `file:line`; a
  `require` rule reports missing entities, as today. The summary counts rules,
  not occurrences, so one noisy chapter cannot drown the roster rules.
- `rift list` — for a `forbid` rule, lists every occurrence rather than a
  per-entity ✓/✗. A banned entry that appears nowhere is not interesting and is
  not printed.
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
5. **Masking preserves line numbers.** A fixture with a banned word inside a code
   fence on line 3 and again in prose on line 40, asserting the reported line is
   40 — not 40-minus-the-fence. This is the assertion that catches a stripper
   that deletes instead of masks, and nothing else will.
6. **`as: word` gets a negative test.** `just` must not match `adjusted`, and
   `api` must not match `rapid`. rift's existing suite already pins that
   `mention` *is* substring-permissive; the new matcher needs the opposite pinned
   with equal force, or the two will drift into each other.
7. **Region exclusion gets one test per region**: fenced code, inline code, link
   URL, HTML tag, blockquote — each asserting a banned word inside it does not
   fire, plus one asserting `include_quotes: true` puts blockquotes back. A
   single "exclusions work" test would pass with four of the five broken.
8. **`find` is tested for multiplicity, not just presence.** Three occurrences of
   one entity across two files must yield three sites. A `find` that early-returns
   like `check` would satisfy any test that only asserts non-empty.

## Out of scope

- **Reading inside a code block, in any rule kind.** Not a gap and not deferred —
  a boundary. `mask` blanks fences for `forbid`, `permit` and `measure`, and no
  inverse mode will be added. Surveying four books' style guides (2026-08-27)
  turned up eleven rules that wanted it: no `...` stubs, no `TODO`, no mutable
  default arguments, no bare `except Exception`, `Optional[X]` versus `X | None`,
  annotation coverage. Every one is real, and every one belongs to a code linter
  with a parser — `ruff` answers all of them exactly, where rift could only
  approximate them with regex.

  Note the asymmetry with blockquotes, which look like the same exclusion and are
  not. A quotation is *someone else's prose*, so `include_quotes` exists to put
  it back in play when a document genuinely wants it linted. Code is not prose,
  so there is nothing to put back.

- **Readability scores.** Principle 3.
- **Any banned list shipped with rift.** The `forbid` *mechanism* is in scope; a
  list of phrases to put in it is not. rift ships zero entries. What counts as
  AI-tic is taste, and taste lives in the consumer's `.rift.yaml` — principle 2
  applies to lexicons exactly as it applies to thresholds.
- **Aliases for roster entities.** Reasoned through under Lexicon rules and
  rejected on cost: it changes `extract`'s return type across the whole codebase
  to serve a case `as: regex` covers.
- **`in_files: N` coverage depth.** Reasoned through and rejected as unreachable
  while generated apparatus stays out of the source tree. See Lexicon rules.
- **Drift over time.** Comparing today's metrics against a committed baseline is
  a real and different feature, needing a baseline format and a refresh
  workflow. `vs-siblings` covers the common case without any of that machinery.
  Revisit once this is in use.
- **Per-section metrics.** Files are the unit. Sections could be a later
  granularity; nothing in this design forecloses it.
