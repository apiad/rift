# Changelog

All notable changes to this project are documented here. Format: Keep a Changelog.

## [Unreleased]

### Changed

- **`as: word` tolerates a line wrap inside a multi-word entity.** The space in
  `not merely` was a literal space, so the phrase was invisible the moment the
  line broke between its two words; whitespace inside an entity now matches any
  run. This catches strictly more than before, which is the correct direction
  for a ban but will move counts in a hard-wrapped repo. Boundaries are
  unchanged — `not merely` still does not match `not merelyish`. Fixed at both
  sites: `forbid` reads `_pattern_for`, `require` has its own `as: word` branch.

### Features

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
