# Changelog

All notable changes to this project are documented here. Format: Keep a Changelog.

## [Unreleased]

## [v0.7.0] - 2026-09-02

### Features

- **`max-paragraph-length` metric** — tokens in the longest paragraph. The
  sixteenth metric, and the first that reports an offender rather than a shape.

  It exists because the two paragraph metrics already here both miss the defect
  a reader actually hits. Measured on a real prologue, before and after its
  three longest paragraphs were split (identical text otherwise — splitting cost
  zero words): `mean-paragraph-length` moved 83.1 → 80.2, a three-token shift
  across a 400-token defect, because one wall among 160 paragraphs cannot move
  a mean. `max-paragraph-length` moved 403 → 198.

  `paragraph-length-cv` is the more interesting non-answer. It does move
  (0.665 → 0.561), so it is not blind — but it cannot distinguish *one wall of
  text* from *healthy variation*, since both raise it. Bounding it flags the
  document that drops a one-sentence paragraph for emphasis, which is the effect
  you were trying to protect. Bound the top end; never bound the variation.

### Documentation

- **The zoned idiom for locating the offender**, in the README beside the metric
  table. A per-file number says how bad, never which one. `measure` a
  `word-count` under `zone: {unit: paragraph}` and every paragraph becomes its
  own key, so the report reads `chapters/ch03.md#42   397.00   above max 200`.
  This needed no new code — it has worked since zoning shipped in v0.6.0 — but
  nothing pointed at it, and the per-file metric is the wrong tool for a cap
  somebody has to act on. The metric is for the views a zone cannot reach: a
  `rift stats` column, and `vs-siblings` across chapters.

- **A rift token is not a word**, in `know-how/measuring-prose.md`. Tokenising
  is `\w+`, so `25.9` counts as two and `six-point` as two. The same paragraph
  reads 198 by rift and 184 by `len(p.split())` — a 7% spread concentrated
  entirely in whichever paragraph carries the statistics, which makes `max: 200`
  tighter than "200 words" and tightest on data-heavy prose. Set the bound
  against `rift stats`, not against a count from another tool.

## [v0.6.0] - 2026-08-27

### Features

- **`zone:` restricts a rule to part of a document.** Available on `forbid`,
  `permit` and `measure`, in two forms: structural
  (`{unit: paragraph|section, index: [0, -1]}`, Python index semantics) and
  delimited (`{after: <regex>, before: <regex>}`, first match wins for each
  bound, bounds excluded from the region). A rule carries exactly one form.

  Surveying four books' style guides turned up about 206 stated writing rules,
  and one missing primitive was requested by all four independently — always the
  same sentence: *this rule applies to part of the file, not the whole of it.*
  Nine requests are served here, including the two that motivated zoning
  `measure`: **bold at most once per section**, and **the opening paragraph is
  45–70 words**.

  Three details are the design rather than the implementation:

  - **Zones resolve after masking and before `strip:`.** Resolving on raw text
    splits `unit: section` on a `##` inside a code fence — the precise failure
    `measure.py` documents itself as avoiding — and stripping first blanks the
    renderer macro a delimited bound is usually written against, making every
    zone in that rule unresolvable and the rule green. Both halves have a
    fixture; both go red under mutation.
  - **A site must be fully contained.** `as: word` joins words with `\s+` and
    spans a line break, so matches genuinely straddle zone edges.
  - **An unresolvable zone fails the rule**, one entry per file rather than per
    entity. Resolution is hoisted above the entity loop: `find` runs once per
    extracted string, so a single broken bound over a 411-term glossary and 30
    chapters would otherwise emit 12,330 identical failures and bury every real
    finding. `rift list` prints the same line in yellow and exits 0.

- **A zoned `measure` takes exact counts, not statistics.** `pattern:`, or
  `metric: word-count`. Every other metric with a zone is a config error, as is
  `per:` and as is `expect: vs-siblings`. A count over a span is as correct as a
  count over a file; a ratio, a coefficient of variation, an autocorrelation or a
  mean is not, because a zone is short enough that crude sentence splitting
  dominates. `vs-siblings` is rejected separately from the metric allowlist
  rather than folded into it — `pattern:` is not a `metric:`, so the allowlist
  alone misses a zoned pattern count compared against siblings.

  Zoned `measure` keys report the zone with the path — `chapters/ch01.md#2`.

- **`zone:` is a config error on `require`,** and the message says why rather
  than only that the key is unknown. `matcher.check` early-returns on the first
  file in the glob that matches: it is existential over the document set, so
  every per-file claim that wanted a zone passes the moment one chapter in forty
  complies. It unlocks when `per_file:` does.

- **Every malformed zone exits 2 before any rule runs**, from `_kinds_or_exit` —
  unknown sub-keys, both forms at once, neither form, an unknown unit, a
  non-integer index, a bound that does not compile. Compiling the bounds up front
  matters: `find` swallows `re.error`, so a typo'd bound would otherwise make the
  rule silently green.

### Fixes

- **`rift list` tracebacked on an unknown metric** where `rift check` exited 2
  cleanly. Its `measure` branch called `_values`/`_apply_expect` with no
  `ConfigError` handler.

- **`_apply_expect`'s degenerate-set guard counted entries, not files.** Reachable
  only if the `vs-siblings` rejection is ever relaxed, and kept as depth against
  that: with zoned keys a two-file set would otherwise be judged against
  "siblings" that are its own other zones.

### Internals

- `_H2` moves from `measure.py` to `text.py`. Both the `sections` metric and the
  new `section_spans` need it, and `text` is the base of the module graph, so
  having `text` reach up for it is a circular import that fails at load.
- `text` gains `section_spans` and `zone_spans`; `matcher.find` and
  `matcher.unpermitted` take precomputed spans; `cli._occurrences` and
  `cli._values` return `(results, unresolved)`.
- A twelfth self-lint rule covers the `zone` sub-keys. It uses `wrap:` rather
  than `as: table_cell`, because with `table_cell` it passed on a README with the
  row deleted — `index` was satisfied by an unrelated `a/index.md`, and `after`
  and `before` are ordinary English words that match some cell on almost any
  page.

## [v0.5.1] - 2026-08-27

### Fixes

- **Sentence splitting was English-shaped, which broke every sentence metric on
  Spanish.** The splitter required an uppercase letter or digit immediately after
  the terminator, and Spanish opens questions and exclamations with `¿` / `¡`
  *before* the capital. The same five-sentence passage split into five sentences
  in English and **three** in Spanish, so `mean-sentence-length`,
  `sentence-length-cv`, `short-sentence-ratio`, `sentence-length-autocorr` and
  `repeated-sentence-openers` all read wrong on dialogue-heavy Spanish prose, and
  `as: sentence_start` could not fire on any Spanish question. Opening
  punctuation is now skipped before the capital test.

  The uppercase requirement itself is unchanged, so this only ever finds *more*
  boundaries: `e.g. "foo"` still does not split. Brackets are deliberately not
  openers — `[`, `(` and `{` are markdown and marker syntax far more often than
  sentence punctuation, and including them split a run of glossary markers into
  new sentences and moved a metric that had a test pinning its value.

  Found by surveying four books' style guides for what rift would need to lint
  them; `repos/enciclopedia` is Spanish and dialogue-heavy, and would have been
  measured wrong from the first run.

### Notes

**Scope decision recorded, not a change:** rift will not grow a mode that reads
inside a code block, in any rule kind. The same survey found eleven rules that
wanted one — stubs, bare `except`, mutable default arguments, annotation
coverage — and every one belongs to a code linter with a parser rather than to a
prose linter with a regex. Blockquotes stay opt-in via `include_quotes` because a
quotation is still prose; code is not. See `docs/prose-linting-design.md`.


## [v0.5.0] - 2026-08-27

rift now lints rift. `.rift.yaml` carries eleven rules over its own API rosters,
the paths its docs name, and its own prose, and `rift check` runs in CI beside
the suite and on the release tag. Writing that config found both fixes below,
which is the argument for having a consumer — made once already by `books-tsoc`,
and made again here against rift itself.


### Features

- **`permit.strip`** — blank renderer markup before tokenising, as `measure`
  already does. Without it `[Enigma]{~encryption}` reports `encryption`, and a
  marker whose slug repeats its display text reports the name twice over. Slug
  fragments are apparatus, and no dictionary should have to absorb them.

### Fixes

- **`forbid.exclude` did not survive a line wrap.** It compiled the phrase with
  `re.escape`, so the space in an exempting phrase was a literal space — and an
  exempting phrase in wrapped prose spans a line break as its *normal* shape,
  not as an edge case. Same defect `as: word` had, in the feature added one
  commit later. Both now share `_flexible_whitespace`. Found by pointing rift at
  its own README.
- **The `regex:` extractor silently dropped entities after an unmatched
  alternation branch.** It took `group(1)` unconditionally, so a branch that did
  not participate handed `None` to `.strip()`, and the `except Exception` around
  the per-file loop swallowed the error — discarding every *remaining* match in
  that file. The result was not zero entities, which looks suspicious, but a
  partial roster that reports pass. It now takes the first group that matched.
  This is the extractor shape a codebase needs whenever a roster is spelled two
  ways, which is most of them.

### Notes

235 tests. Both fixes were demonstrated before being fixed and mutation-tested
after: reverting `_captured` to `group(1)` and making `permit` ignore `strip`
each turn the suite red.

**One test written for `permit.strip` was vacuous and had to be replaced.**
`[Alan Turing]{~turing-alan}` tokenises to the same folded words with or without
stripping, so the fixture passed against an implementation that ignored `strip:`
entirely. The fixture now uses a marker whose slug differs from its display text
(`[Enigma]{~encryption}`). Second time this class of mistake has surfaced in two
releases — a fixture that cannot distinguish the two behaviours asserts nothing.

Every rule in `.rift.yaml` was watched to fail before being trusted: dropping a
matcher row, dropping an `expect` predicate, renaming a module and falsifying the
version each turn their rule red.

## [v0.4.0] - 2026-08-27

One new rule kind and a sentence scope, both of which came from asking whether
rift could check spelling, grammar and passive voice. Three of those four are
recorded as out of scope with their reasoning in
`docs/prose-allowlists-and-sentence-scope-design.md`; what survived is the shape
underneath them.

### Changed

- **`as: word` tolerates a line wrap inside a multi-word entity.** The space in
  `not merely` was a literal space, so the phrase was invisible the moment the
  line broke between its two words; whitespace inside an entity now matches any
  run. This catches strictly more than before, which is the correct direction
  for a ban but will move counts in a hard-wrapped repo. Boundaries are
  unchanged — `not merely` still does not match `not merelyish`. Fixed at both
  sites: `forbid` reads `_pattern_for`, `require` has its own `as: word` branch.

### Features

- **`permit` — a fourth rule kind.** The mirror of `forbid`: where `forbid` bans
  the extracted set, `permit` bans everything but it. rift could say *this must
  appear in the docs* and *this must not appear in the prose*, but not *nothing
  outside this set may appear*. Spelling is one instance; "no proper noun outside
  the roster" and "no acronym outside the glossary" are the others. `of:` selects
  which tokens the rule judges and sees the token **as written**, before
  lowercasing, which is what makes `^[A-Z]` mean "proper noun". No dictionary
  ships with rift — vendor one with `aspell dump master en_US`.
  - `rift list` reports *vocabulary* for a permit rule — unique tokens with
    counts, most frequent first — rather than sites. Without that surface the
    first run against a real document set is untriageable.
  - A malformed `of:` pattern **exits 2**. `find` swallows `re.error`, which
    makes a typo'd rule silently green; a new rule kind is not bound by that.
  - Both `check` and `list` now dispatch on kind explicitly, with an `else` that
    fails loudly. `if/elif/else` with `measure` as the fallback is how `list`
    came to raise `KeyError` on every measure rule.
- **`as: sentence_start` matcher** — bans a word only where it opens a sentence,
  which no config could express before: every pattern anchors `^` per line, and a
  sentence beginning mid-line has no anchor. Implemented as the ordinary literal
  match plus a span filter, so there is no second way to match a literal.
  `case_insensitive` does **not** fold the document for this matcher — splitting
  keys on the capital after the terminator, so folding would erase every boundary
  and the matcher would find nothing.
- **`repeated-sentence-openers` metric** — consecutive sentences opening on the
  same token, per 1000 tokens. Adjacency is the claim: a word that opens two
  sentences with another between them is not the tic, so it counts pairs rather
  than opener frequency. Needs no lexicon and knows no vocabulary, so it works
  unchanged on Spanish.
- **`forbid.exclude`** — literal phrases whose occurrences are exempt from an
  otherwise-good ban. Came from `books-tsoc`, where "basically" is a real tic
  twice over and unavoidable twice over: once inside a quotation of Backus, once
  as the B in BASE. Naming the two phrases keeps the ban intact everywhere else,
  which loosening the pattern would not.

### Fixes

- **`rift list` no longer crashes on a `measure` rule.** It handled `require` and
  `forbid` and treated everything else as `forbid`, so the first measure rule in
  a config raised `KeyError: 'forbid'` and killed the whole listing — including
  the forbid rules it had not reached yet. Measure rules now report every
  measured file with its value, and the out-of-bounds ones carry their reason.

### Notes

229 tests. Seven mutants run against the new code; **one initially survived** —
`sentence_start_offsets` returning raw span starts instead of first-token offsets
passed all 211 tests, because `_TERMINATOR` is `[.!?…]+\s+` and already consumes
the gap between sentences, so the fixture built on that gap could not
discriminate. The case that does is an indented paragraph; there is now a test
for it at both the text and the matcher level, and the mutant dies.

`rift check` over a frozen `books-tsoc` snapshot is byte-identical before and
after this release — the whitespace-tolerant `as: word` change moved nothing in
a repo that writes one paragraph per line, which is what it predicted.

## [v0.3.0] - 2026-08-26

Three primitives, all of which came from encoding a real book's style guide
(`books-tsoc`) rather than from imagining what a config might want.

### Features

- **`word-count` metric** — prose tokens, masked and stripped like every other
  metric.
- **`forbid` allowances.** `max_per_file: N` allows the first N occurrences in
  each file and reports the rest (*"mark a glossary term only on first use in a
  chapter"*). `max_files: N` allows the entity in at most N files and reports the
  excess (*"never define a footnote label twice"*). Plain `forbid` is unchanged:
  zero tolerance.
- **`wrap:`** — substitute the escaped entity into a caller-supplied pattern via
  `${entity}`, so a rule can ask about a *marked* term rather than a bare word.
- **`extract.file` takes a list of globs**, like `in:`.

### Fixes

- `wrap` is a correctness fix, not a convenience. *"Every glossary entry is used"*
  with `as: mention` reported 26 unused entries; the true number was 34, because
  the entry `abstraction` was being satisfied by the ordinary word *abstraction*
  appearing in prose.

### Notes

189 tests. Seven mutants run against the new code; **one initially survived** — the
`wrap` escaping test had the entity and the document the wrong way round and
asserted nothing about escaping. Rewritten so an entity carrying a regex metachar
must match literally; the mutant now dies.

## [v0.2.1] - 2026-08-26

### Other

- **CI, at last.** `ci.yml` runs the suite on push and PR against Python 3.11 and
  3.13. `release.yml` fires on a `v*` tag and runs the suite *before* publishing,
  checks the tag matches `pyproject.toml`, builds sdist and wheel, and publishes
  using the hand-written CHANGELOG section for this version.
- **`uv sync --locked` was broken on the v0.2.0 tag** — that release was cut with
  `uv.lock` still pinned at `0.1.0`. Both workflows now use `--locked`, so a stale
  lockfile fails the build instead of shipping.

## [v0.2.0] - 2026-08-26

rift went from one rule kind to three. It still answers *"does this thing exist in
the code but not in the docs?"*, and now also *"does this document contain text I
declared it must not?"* and *"is this document shaped like its siblings?"*

It remains mechanical: it counts and locates, never interprets, and ships no
default thresholds or lexicons. Every judgement lives in the consumer's
`.rift.yaml`.

### Features

- **`forbid` rule kind** — a banned lexicon of words, phrases or regexes, reported
  as `file:line` occurrences rather than a per-entity checklist. Reads the
  document *masked*: fenced code, inline code, HTML tags, link URLs and
  blockquotes are blanked first, because none of them is your prose and a linter
  that fires on a quotation is one you switch off in a week.
- **`measure` / `expect` rule kind** — 14 stylometric metrics across rhythm,
  texture, structure and voice, with `min` / `max` / `vs-siblings` predicates.
  `vs-siblings` self-calibrates against the set's own spread, so it needs no
  tuning as a document set grows.
- **`burrows-delta`** — authorial fingerprinting from the rates of the most
  frequent tokens. Needs no dictionary, no stopword list and no knowledge of the
  language, so it works on Spanish unchanged.
- **`rift stats`** — the full metric table for a file set. Never judges, always
  exits 0. The surface for asking whether a chapter is unlike its siblings with
  no rule written.
- **New extractors** — `list:` (inline literals), `lines:` (a plain-text roster),
  `paths:` (root-relative paths; the non-lossy sibling of `files:`).
- **New matchers** — `as: word` (`\b`-wrapped, the default for `forbid`) and
  `as: regex`.
- **`in:` and `measure.files` accept a list of globs**, since a real document set
  is usually several and no single glob spells that.
- **`strip:`** — blank renderer markup before measuring, so metrics report prose
  rather than apparatus density.

### Fixes

- `heading` matcher could never match a real heading — `{1,6}` inside an f-string
  is a replacement field, not a quantifier.
- `find()` compiled without `MULTILINE` while the `regex:` extractor used it, so
  `^---$` matched only at start-of-file; `check()` had the same gap one branch
  over. Three meanings of `^` in one config is a trap.
- Renderer markup was measured as prose: `[Tony Hoare]{~hoare-tony}` tokenised as
  *"tony hoare hoare tony"*, and marker captions leaked into the sentence stream.
  A chapter carrying more markers than its neighbours measured as having different
  prose — silently, and plausibly.

### Notes

Two real consumers: `apiad/ainbox` (5 rules) and `apiad/books-tsoc` (8 rules,
which replaced three hand-written Python test files, ~450 lines). The migration
was verified by injecting each defect the old suite caught into a throwaway copy
and running both — rift caught all nine, and two the old suite missed.

171 tests. Metric expectations are hand-computed from the definitions, never
pasted from a run, and every metric carries a discrimination test. Both new rule
kinds were mutation-tested: a linter that cannot fail is worse than no linter.

Not on PyPI, and not wired into any CI — the largest remaining gap.

## [v0.1.0] - 2026-08-10

### Features

- Documentation drift linter: declare facts that live in code and config
  (compose services, env vars, version pins, directory names) and assert each
  appears in the docs. `extract` / `require`, five extractors, five matchers.
- `rift check`, `rift list`, `rift init`.

Never tagged at the time; recorded here for continuity.
