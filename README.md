# rift

A documentation drift linter. You declare facts that live in your code and config —
compose services, env vars, version pins, directory names — and assert that each one
appears in your docs. `rift check` exits 1 when something isn't documented.

It also lints prose, without reading it for meaning. Two more mechanical questions:
**does this document contain text I declared it must not?** (`forbid`) and **is this
document shaped like its siblings?** (`measure`). rift counts; it never interprets. It
reports a number and the threshold you declared it against, and it will never tell you
that prose is bad, machine-written, or good.

That narrowness is the point — it makes every check cheap enough to run in CI and boring
enough to trust. See `docs/prose-linting-design.md` for why each metric was chosen and
which were deliberately excluded.

## Install

```bash
uv sync
uv run rift --help
```

## Commands

Four, and the split between the first two is the one that matters: `check` is the
gate, `list` is how you tune a rule until the gate is worth trusting.

### `init`

Scaffolds a starter `.rift.yaml` with one worked rule. Start here, then read
`know-how/writing-rules.md` before adding the second rule.

### `check`

Runs every rule and **exits 1** if any error-severity rule fails. This is what CI
runs. Takes an optional project root (default `.`) and `-c/--config` (default
`.rift.yaml`, resolved relative to the root).

**Exit codes:** `0` all rules pass, or only warnings failed · `1` at least one
error-severity rule failed · `2` no config file found, or a malformed rule.

### `list`

The per-entity breakdown — every ✓ and every ✗, not just the failures. This is the
tuning surface, and each rule kind reports the thing that is useful for it:
`require` lists entities, `forbid` lists sites, `permit` lists *vocabulary*
(unique tokens by frequency), `measure` lists every file with its value.

`rift list -r <substring>` filters to matching rule names.

**Write a rule at `severity: warning`, run `list`, read every ✗, and promote to
`error` only when the list is empty for reasons you agree with.** A mostly-red
rule trains everyone to skim past red.

### `stats`

The full metric table for a file set. Never judges, always exits 0, needs no
config — the surface for asking whether a chapter is unlike its siblings before
committing to a threshold.

```bash
rift stats 'ch*.md'
rift stats 'ch*.md' -m sentence -s '\{[~>][^}]*\}'   # filter metrics, strip markup
```

## Config

`.rift.yaml` is a list of rules. A rule carries **exactly one** of four shapes;
more than one is a config error.

| Shape | Asks | Reports |
|---|---|---|
| `extract` + `require` | does each extracted string appear? | missing entities |
| `extract` + `forbid` | where does each extracted string appear? | `file:line` sites |
| `extract` + `permit` | what appears that is **not** in the extracted set? | `file:line` sites |
| `measure` + `expect` | what is this number, and is it in bounds? | values and thresholds |

`extract` feeds the first three: where a set of strings comes from is orthogonal
to what you then assert about it.

```yaml
rules:
  - name: "compose services → mention in design.md"
    severity: error          # error (default) fails the build; warning only reports
    extract:
      file: "compose*.yml"
      yaml_keys: "services"
    require:
      in: "docs/design.md"
      as: mention
```

### Extractors

Exactly one per rule. `files` and `dirs_with` stand alone; the rest need a `file:` glob.

| Key | Yields |
|---|---|
| `file: <glob>` | Selects the source files for the four extractors below. Globbed from the project root — **not recursive** unless you write `**`. |
| `yaml_keys: <a.b.c>` | The keys of the mapping at that dotted path. `services` on a compose file gives you the service roster. |
| `yaml_values: <a.b.c>` | The values of the mapping, or the items of the list, at that path. |
| `env_names: true` | Variable names matching `^[A-Z_][A-Z0-9_]*=`. Comments, blank lines, indented lines and lowercase names are skipped. |
| `regex: <pattern>` | The first group that **matched**, or the whole match if the pattern has no groups. Compiled with `MULTILINE`, so `^` and `$` anchor per line. An alternation is the normal way to extract a roster a codebase spells two ways — `(?:"(\w+)" in config\|config\.get\("(\w+)")` — and the unmatched branch's `None` is skipped. |
| `lines: true` | Each non-empty line of `file:` that doesn't start with `#`, stripped. For a roster or banned list kept as plain text. |
| `list: [a, b]` | The literal strings, written inline in the rule. Standalone — a banned list is *your* taste, so it belongs in the config rather than a repo data file. |
| `files: <glob>` | The *stem* of each matching file (`apps/one.py` → `one`). Standalone, and **lossy** — `a/index.md` and `b/index.md` collapse to one entity. |
| `paths: <glob>` | The path of each matching file, relative to the root (`apps/one.py`). Standalone. Reach for this over `files:` whenever two matches could share a stem. |
| `dirs_with: <glob>` | The parent directory name of each matching file (`apps/alpha/Dockerfile` → `alpha`). Recursive; skips `.git`, `.venv`, `__pycache__`, `node_modules`, `.playground`. Standalone. |

### Matchers

`require.as` decides what "documented" means. `require.in` is the doc glob — or a
**list** of globs, since a real document set is often several (`["[1-4]_*/*.md",
"preface.md"]`) and there is no single glob that spells that. Default
`docs/**/*.md`; the entity passes if **any** matching file satisfies it. `forbid.in`
and `measure.files` take the same string-or-list.

`as: regex` compiles with `MULTILINE`, matching the `regex:` extractor and
`pattern:` counting — so `^` and `$` anchor per line everywhere in a config.

| `as:` | Passes when the entity… |
|---|---|
| `mention` (default) | appears anywhere as a **plain substring**. No word boundary — `api` is satisfied by `rapid`. Permissive by design. |
| `wrap: <pattern>` | not an `as:` value but an override for it: the escaped entity is substituted into your pattern at `${entity}`. Use it to ask about a *marked* term rather than a bare word — `wrap: '[\[{]~${entity}[\]}]'` matches `[~cpu]` and `{~cpu}` but not the word "cpu". |
| `word` | appears as a whole word (`\b`-wrapped, literal). **The default for `forbid`** — without it, banning `just` flags `adjusted`. Whitespace *inside* a multi-word entity matches any run, so `not merely` is still found when a hard-wrapped line splits it. |
| `regex` | the entity *is* a pattern, matched as written. |
| `sentence_start` | appears as a whole word **opening a sentence**. Not expressible as `as: regex`: every pattern in a config anchors `^` per *line*, and a sentence that begins mid-line has no anchor at all. Because splitting is crude, a spurious boundary yields a **false** site — never a missed one. |
| `heading` | appears in a heading of any level (`#`–`######`). |
| `heading_N` | appears in a heading of exactly level N. `heading_2` matches `##` and rejects `#` and `###`. |
| `table_cell` | appears inside a single `\|` … `\|` cell on one line. |
| `mermaid_node` | appears as a whole word inside a ` ```mermaid ` fence. Occurrences outside the fence don't count. |

`require.exists: true` is the inverse rule and ignores `in`/`as`: it treats each
extracted string as a path relative to the project root and passes if that path
exists. This is how you catch docs that describe files nobody ever wrote.

`require.case_insensitive: true` lowercases both the entity and the document before
matching. (`heading` and `heading_N` are already case-insensitive; the flag is a
no-op for them.)

An unrecognised `as:` value never matches, which surfaces as every entity being
reported missing.

## Prose rules

### `forbid` — a banned lexicon

```yaml
  - name: "no AI-tic phrasing"
    severity: warning
    extract:
      file: "prose/banned.txt"
      lines: true
    forbid:
      in: "chapters/*.md"
      as: word
```

```
⚠  no AI-tic phrasing  [3 occurrences]
   chapters/ch01.md:5   delve
   chapters/ch01.md:5   rich history of
   chapters/ch02.md:3   tapestry
```

`forbid` reads the document **masked**: fenced code, inline code, HTML tags, link
URLs and blockquotes are blanked before matching, because none of them is your
prose and a linter that fires on a quotation is one you switch off in a week.
`include_quotes: true` puts blockquotes back in play.

**Quotes are opt-in; code is never.** The two exclusions look alike and are not.
A blockquote is *someone else's prose* — still prose, so there are documents you
legitimately want to lint it in, which is what the flag is for. Code is not prose
at all. **rift will not grow a mode that reads inside a code block**, in any rule
kind: a stub, a bare `except`, a mutable default argument and an untyped
signature are all real defects and all of them belong to a code linter. Point
`ruff` at your fences and rift at your prose.

**`require` is never masked.** It asks whether something is *documented*, and a
code fence is documentation — masking it would break every rule that documents an
env var inside a bash block.

**Allowances.** Plain `forbid` is zero tolerance. Two optional keys generalise it
without turning it into a counting rule — the report is still `file:line` sites:

| Key | Means |
|---|---|
| `max_per_file: N` | the first N in each file are fine; report the rest. *"Mark a glossary term only on first use in a chapter."* |
| `max_files: N` | the entity may appear in at most N files; report the excess. *"Never define a footnote label twice."* |

**Declared exceptions.** `exclude:` takes literal phrases whose occurrences are
exempt. Masking already handles blockquotes, but a banned word also turns up
inside an *inline* quotation of someone else, or as a letter of an acronym:

```yaml
    forbid:
      in: "chapters/*.md"
      as: word
      case_insensitive: true
      exclude:
        - 'basically clerical work'   # Backus, quoted
        - 'Basically Available'       # the B in BASE
```

Name the phrase rather than loosening the pattern. `exclude: ['basically ']`
would quietly stop catching the tic everywhere; the list above keeps the ban
intact and puts each exemption where a reader can argue with it. Phrases are
literal, and matched with the rule's own `case_insensitive` setting.

rift ships **no banned list**. What counts as bad phrasing is taste, and taste
lives in your `.rift.yaml`.

### `permit` — an allowlist

The mirror of `forbid`. Where `forbid` bans the extracted set, `permit` bans
everything **but** it, and reports the same `file:line` sites.

```yaml
  - name: "no proper noun outside the roster"
    severity: warning
    extract:
      file: "glossary.yaml"
      yaml_keys: "people"
    permit:
      in: "chapters/*.md"
      of: '^[A-Z]'
```

```
⚠  no proper noun outside the roster  [2 unpermitted]
   chapters/ch02.md:41   Corbató
   chapters/ch05.md:9    Multics
```

Read masked, exactly like `forbid`, and `include_quotes: true` works the same
way. The unit is the token (`\w+`, Unicode), and **all-digit tokens are never
judged** — a year is not a spelling. That is the only judgment built in.

| Key | Means |
|---|---|
| `of: <regex>` | only tokens matching this are subject to the rule. Absent, every token is judged. Matched against the token **as written**, before lowercasing — which is what makes `^[A-Z]` mean "proper noun" rather than nothing at all. |
| `case_insensitive: true` | membership is decided on the folded form. `of:` still sees the source form. |
| `strip: [<regex>, …]` | blank renderer markup before tokenising, as `measure` does. Reach for it whenever markers carry slugs: `[Enigma]{~encryption}` otherwise reports `encryption`, which is apparatus rather than a word anyone misspelled. |

**An empty permitted set reports every token**, which is the opposite polarity to
`require` and deliberate. A malformed source file makes the extractor yield
nothing, and zero entities makes a `require` rule *silently pass* — the known gap
below. For `permit` the same emptiness is maximally loud.

**`permit` cannot see identifiers in backticks.** It reads masked prose, so inline
code and fences are blank to it — which means it is the wrong tool for asking
whether a README documents an API. That is what `require` is for, and it is why
`require` alone reads the document unmasked.

There is no `exclude`, no `max_per_file` and no `max_files`: the permitted set
*is* the allowance, and a second one on top of it would be two ways to spell the
same exemption. A malformed `of:` pattern **exits 2** rather than reporting
nothing — a typo that makes a rule silently green is the one failure a linter
cannot afford.

**`rift list` is the surface that makes this usable.** `check` reports sites;
`list` reports *vocabulary* — unique unpermitted tokens with their counts, most
frequent first. A first run against a real book emits sites in the thousands, and
a flat site list is untriageable where a ranked vocabulary is a worklist.

**Spelling is one instance of this shape**, and rift ships no dictionary — same
principle as `forbid` shipping no banned list. Vendor one:

```bash
aspell dump master en_US > dict/en.txt
```

Then point `extract` at `file: "dict/*.txt"`, so the vendored wordlist and a
hand-curated `dict/terms.txt` union without the 120k-line blob ever churning —
the diff a reviewer reads is the term file.

### `measure` — statistics over a file set

```yaml
  - name: "no chapter reads like a different author"
    measure:
      files: "chapters/*.md"
      metric: burrows-delta
    expect:
      vs-siblings: 2.0
```

| `expect` | Fails a file whose value… |
|---|---|
| `min` / `max` | is outside an absolute bound |
| `vs-siblings: K` | is more than K standard deviations from the mean of the **other** files |

**Reach for `vs-siblings` first.** It self-calibrates: the comparison set is your
own document set, so it needs no tuning as the set grows, and it encodes no
opinion about what any number should be — only that one file should not differ
sharply from its peers. A set of fewer than 4 files is reported with a warning and
**not** judged; silently passing or failing would both be lies about what was
checked. An absent `expect` reports the number and passes.

#### Metrics

Each takes one document and returns one number, read masked and stripped — so a
file is never credited for its code blocks nor penalised for its markers.

| Metric | Family | Measures |
|---|---|---|
| `mean-sentence-length` | rhythm | mean tokens per sentence |
| `sentence-length-cv` | rhythm | burstiness, σ/μ. Human prose runs high, uniform prose low |
| `short-sentence-ratio` | rhythm | share of sentences under 6 tokens — the emphasis beat uniform prose lacks |
| `sentence-length-autocorr` | rhythm | lag-1 autocorrelation. Humans write in runs; uniform-random sits near zero |
| `mattr` | texture | moving-average type-token ratio over a 200-token window. Length-independent, unlike raw TTR |
| `hapax-ratio` | texture | share of tokens appearing exactly once |
| `self-repetition` | texture | share of 4-grams occurring more than once |
| `repeated-sentence-openers` | texture | consecutive sentences opening on the same token, per 1000 tokens |
| `sections` | structure | count of `##` headings |
| `words-per-section` | structure | prose tokens divided by section count |
| `mean-paragraph-length` | structure | mean tokens per paragraph |
| `max-paragraph-length` | structure | tokens in the longest paragraph — the wall of text a mean absorbs |
| `paragraph-length-cv` | structure | σ/μ of paragraph lengths |
| `mean-heading-length` | structure | mean tokens per heading |
| `opening-paragraphs` | structure | blocks between the `#` title and the first `##` |
| `word-count` | size | prose tokens in the document |
| `burrows-delta` | voice | authorial fingerprint from the rates of the most frequent tokens. **Set-level**, and noisy at chapter length — rank it rather than trusting the absolute value |

Every one is language-agnostic — `\w+` tokenising and punctuation-based sentence
splitting, so Spanish works unchanged. Readability scores are deliberately absent:
Flesch and its relatives bake in English syllable assumptions *and* a theory of
good writing.

**A per-file number says how bad, never which one.** `max-paragraph-length`
reports that a chapter contains a 400-word block; it cannot say where, because
one file yields one value. To get the offender's location, measure `word-count`
under a paragraph zone — every paragraph becomes its own key:

```yaml
  - name: "no paragraph over 200 words"
    measure:
      files: "chapters/*.md"
      metric: word-count
      zone: { unit: paragraph }
    expect:
      max: 200
```

```
✗  no paragraph over 200 words  [3 out of bounds]
   chapters/ch03.md#42   397.00   above max 200
```

Reach for the zoned rule to enforce a cap someone must act on, and for the metric
when the per-file view is the point — a `rift stats` column, or `vs-siblings`
across chapters, neither of which a zone can reach.

**Do not bound `paragraph-length-cv` to police this.** A cap on variation
punishes the length variation good prose wants: a document of uniform 90-word
paragraphs scores well and reads as machine output. Bound the top end only.

**`strip:` renderer markup before measuring.** Marker syntax is apparatus, not
prose, and leaving it in corrupts every metric: `[Tony Hoare]{~hoare-tony}`
tokenises as *"tony hoare hoare tony"*, and a marker carrying a caption leaks the
whole caption into the sentence stream. A chapter then measures as having
different prose when only its markup differs.

```yaml
    measure:
      files: "chapters/*.md"
      metric: sentence-length-cv
      strip: ['\{[~>][^}]*\}', '\[>[^\]]*\]']
```

rift knows no renderer — the patterns come from your config. `rift stats` takes
the same via repeatable `-s/--strip`. Measured on a real book: leaving markers in
moved one chapter's burstiness from 0.70 to 0.79 and made it read as an outlier
it was not.

**Apparatus** is counted with a caller-supplied regex, so rift knows nothing about
your renderer:

```yaml
    measure:
      files: "chapters/*.md"
      pattern: '\{~[a-z0-9-]+\}'
      per: 1000
    expect:
      vs-siblings: 2.5
```

### `zone:` — part of a file, not all of it

Most style rules are about a *region*: the opening paragraph, the last section,
the stretch between two renderer macros. `zone:` restricts a rule to one, and
takes the same shape on `forbid`, `permit` and `measure`.

A rule carries **exactly one** of the two forms. Both is a config error.

```yaml
  - name: "no italicised meta-frame on the opening or closing paragraph"
    extract:
      list: ['^_[^_]+_$']
    forbid:
      in: "chapters/*.md"
      as: regex
      zone: { unit: paragraph, index: [0, -1] }
```

```yaml
  - name: "no second-person address outside the journey"
    extract:
      list: ["tú", "contigo"]
    forbid:
      in: "capitulos/*.md"
      as: word
      zone: { after: '\\sep2', before: '\\sep3' }
```

| Key | Form | Means |
|---|---|---|
| `unit` | structural | `paragraph` or `section`. A paragraph is a run of non-blank lines; a section is delimited by `##` (not `###`), and the text before the first `##` is zone 0 |
| `index` | structural | which zones, as a list of integers with Python semantics — `[-1]` is the last. Omit it and you get every zone |
| `after` | delimited | a regex; the region starts after its **first** match |
| `before` | delimited | a regex; the region ends at its **first** match |

Both bounds are optional: `after` alone runs to end of file, `before` alone from
the start. The region **excludes** the bound matches themselves, so a banned word
inside the `\sep2` line is not a site. One region per file, first match wins for
each bound — no nesting, no overlaps. A region selector that resolves ambiguity is
a parser, and a zone that silently lands on the wrong span produces a rule that is
confidently wrong about where it looked.

**A site must be fully contained.** `as: word` joins words with `\s+` and spans a
line break, and `as: regex` runs MULTILINE, so a match that straddles a zone edge
is genuinely possible — and is not reported.

**An unresolvable zone fails the rule.** A missing bound, an inverted pair or an
index past the end yields one entry per file, carrying the rule's own severity:

```
✗  no second-person address outside the journey  [1 occurrences]
   capitulos/03-el-rio.md   zone matched nothing
```

A declared zone that does not exist is a broken rule, the same class as a rule
pointed at a renamed file. `rift list` prints the same line in yellow and still
exits 0 — `list` reports, it never judges.

**Zones resolve after masking and before `strip:`.** That ordering is the only one
that works, and each half was a real bug. Resolving on raw text would split
`unit: section` on a `##` **inside a code fence**. Stripping first would blank the
very renderer macro a delimited bound is usually written against, making every
zone in that rule unresolvable — and the rule green.

**A zoned `measure` takes exact counts, not statistics.** `pattern:`, or
`metric: word-count`. Every other metric with a zone is a config error, and so is
`per:` — it turns a count into a ratio — and so is `expect: vs-siblings`, because
with zones "the siblings" is ambiguous between the other zones of this file and
the same zone in other files. A count over a span is as correct as a count over a
file; a coefficient of variation over a span is not, because a zone is short
enough that crude sentence splitting dominates.

Zoned `measure` keys report the zone as well as the path — `chapters/ch01.md#2` —
because a number out of bounds in one section of a forty-section chapter is not a
fact about the chapter.

**Two traps worth knowing before you reach for a structural zone:**

- **An index-less `unit: paragraph` is not "the whole file".** It is the union of
  the paragraph spans, and `paragraph_spans` drops headings, list items and table
  rows. A `forbid` under it silently stops reporting a banned word in a heading.
  If you want the whole file, use no zone.
- **`include_quotes: true` cannot be reached through a paragraph zone.**
  Blockquote lines are dropped from `paragraph_spans` regardless of masking, so a
  rule that opted back into quoted prose loses it again the moment it adds one.
  Use a delimited zone, or none.

**`zone:` is not available on `require`.** `matcher.check` returns a bool and
early-returns on the first file in the glob that matches — it is existential over
the document set by design. Every request for a zoned `require` was a *per-file*
claim (*the promise must land in the first 100 words*), and existentially all of
them pass the moment one chapter in forty complies. A zone narrows where in a file
the search happens; it cannot change what the question is asked over. It unlocks
when `per_file:` does.

### `measure` counts, `forbid` locates

Both can express "this text should be rare". Pick by what you need back: a
**budget** ("at most 3 em-dashes per 1000 words") is `measure` + `pattern` +
`expect: {max: N}` and yields a number; a **ban** ("never this phrase") is
`forbid` and yields sites.

## Known gaps

- **A source file that won't parse makes its rule pass silently.** The extractor
  swallows every exception, so malformed YAML yields zero entities, and zero
  entities is indistinguishable from "everything is documented". Pinned by
  `test_unparseable_yaml_yields_nothing_instead_of_raising`.
- **`mention` is still a plain substring.** `api` is satisfied by `rapid`. This is
  now a choice rather than a gap: reach for `as: word` when precision matters.
  `mention` stays permissive because existing rules depend on it.
- **A roster entity must be the string that actually appears.** `Dijkstra` passes
  where `Edsger W. Dijkstra` fails; there is no alias mechanism. Roster the
  surname, or use `as: regex`.
- **A multi-word `as: word` entity spans a paragraph break.** Whitespace inside
  the entity compiles to `\s+`, which does not stop at a blank line, so a phrase
  whose first word ends a paragraph and whose second opens the next reports a
  site. Rare, and narrowing it costs a pattern nobody can read.
- **Sentence splitting is deliberately crude**, though it is no longer
  English-shaped: opening punctuation is skipped before the capital test, so
  Spanish `¿` and `¡` open sentences correctly. `Ph.D.` over-splits. Every file in
  a set is over-split by the same rule, so comparisons stay valid where the
  absolute count does not — and no metric here depends on that count being right.
  `as: sentence_start` is the one consumer that pays for it: a spurious boundary
  makes the word after it look sentence-initial, so the failure mode is a **false
  site**, never a missed one.

## Development

```bash
uv run pytest -q
```

152 tests covering every extractor, every matcher, every metric, and the CLI exit
codes. Metric expectations are **hand-computed from the definitions**, never pasted
from a run — a test whose expected value came from the code under test asserts
nothing. Each metric also carries a discrimination test (a uniform fixture and a
varied one, asserting it separates them in the right direction).

**A linter that cannot fail is worse than no linter**, because it licenses
shipping. After touching `matcher.py`, `measure.py` or the `expect` predicates,
mutation-test: break the thing on purpose and confirm the suite goes red.
