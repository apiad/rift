# Prose linting — implementation plan

**Spec:** `docs/prose-linting-design.md`
**Status:** in progress, started 2026-08-26.

Two vertical slices. Each ends with rift able to do something end to end from a
`.rift.yaml`, not with a layer completed. Slice 1 is the feature that was asked
for; slice 2 is the larger statistical engine that sits on the same foundation.

## Slice 1 — lexicon rules (`forbid`)

Delivers: a banned-phrase list in `.rift.yaml` that reports `file:line` sites.

| # | Task | Verify |
|---|---|---|
| 1.1 | `src/rift/text.py`: `mask()` blanks fenced code, inline code, link URLs, HTML tags, and blockquotes, replacing each with spaces of equal length and preserving `\n`. `line_of(text, pos)`. | A banned word inside a fence on line 3 and in prose on line 40 reports line **40**. Fails if `mask` deletes. |
| 1.2 | `extractor.py`: `list:` (inline literals, standalone) and `lines:` (non-empty non-`#` lines of `file:`). | `list: [a, b]` yields `{a, b}`; a `#` comment line yields nothing. |
| 1.3 | `matcher.py`: `as: word` (`\b`-wrapped) and `as: regex` (entity is the pattern). | `just` does not match `adjusted`; `api` does not match `rapid`. Existing `mention` permissiveness still pinned. |
| 1.4 | `matcher.py`: `find(root, entity, forbid) -> [(path, line, entity)]`. Visits every file and every site — no early return. | Three occurrences across two files yield three sites, not one. |
| 1.5 | `cli.py`: `forbid` branch in `check` and `list`; reject a rule carrying more than one of `require`/`forbid`/`measure`. | End-to-end `.rift.yaml` with a banned list exits 1 and prints sites. Malformed rule exits 2 with a named error. |

**Decision made during 1.1, recorded here because the spec does not say it
outright:** masking applies to `forbid` and `measure`, **never to `require`**.
`require` asks *is this documented*, and a code fence is documentation — masking
it would break every existing rule that documents an env var inside a bash block.
`forbid` asks *is this in my prose*, and a code fence is not prose.

## Slice 2 — statistical rules (`measure` / `expect`)

Delivers: `rift stats` and threshold rules over the metric catalogue.

| # | Task | Verify |
|---|---|---|
| 2.1 | `text.py`: `tokens()`, `sentences()`, `paragraphs()` per the spec's Definitions. | Hand-computed fixture counts, not output-pasted. |
| 2.2 | `measure.py`: rhythm + texture + structure metrics. | Each ships a hand-computed fixture **and** a discrimination test (uniform vs varied, correct direction). |
| 2.3 | `measure.py`: `burrows_delta()` over a document set. | Known-answer: the doc with a deliberately different function-word profile ranks highest. Ranking asserted, not absolute value. |
| 2.4 | `measure.py`: `pattern` counting with `per: N` normalisation. | Count over masked text; a match inside a fence does not count. |
| 2.5 | `cli.py`: `measure`/`expect` branch with `min`/`max`/`vs-siblings`; degenerate-set warning (<4 files) and zero-variance pass. | A 2-file set warns and passes rather than silently passing. |
| 2.6 | `cli.py`: `rift stats <glob>` — full table, exit 0 always. | Reports numbers with no config file present. |

**Structure metrics read raw text, not masked text.** `sections`,
`mean-heading-length` and `opening-paragraphs` are about markdown structure;
masking headings away would zero them.

## Closing tasks

| # | Task | Verify |
|---|---|---|
| 3.1 | Mutation-test both new branches: make the `forbid` comparison return no sites, make `expect` always pass. | Suite goes red for each. A gate that cannot fail is the one bug rift cannot ship. |
| 3.2 | README: extractor table, matcher table, the third rule kind, and the `measure` counts / `forbid` locates split. | `rift --help` and README agree. |
| 3.3 | Close the superseded word-boundary item in `tasks.md`. | — |
