# Changelog

All notable changes to this project are documented here. Format: Keep a Changelog.

## [Unreleased]

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
