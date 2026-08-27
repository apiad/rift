# Zone scoping — design

**Status:** approved 2026-08-27; revised the same day after review; not yet
implemented.
**Scope:** a `zone:` key on `require`, `forbid`, `permit` and `measure` that
restricts a rule to part of a document instead of all of it. No new rule kind, no
new extractor, no new metric.

The five design principles in [`prose-linting-design.md`](prose-linting-design.md)
govern this and are not restated except where a decision turns on one.

## Why this exists

Surveying four books' style guides on 2026-08-27 — the `/revise` skill,
`repos/enciclopedia`, `repos/books-mhai` and `repos/books-codex` — turned up about
206 stated writing rules. Roughly 44% are expressible with rift as it stands and
37% need a human reader. Of the remainder, **one missing primitive was requested
by all four independently**, and it is always the same sentence: *this rule
applies to part of the file, not the whole of it.*

Ten surviving requests, after removing the ones that wanted to read inside code
blocks (out of scope permanently — see the parent design) and one that `require`
cannot serve (below). They come in three shapes:

**A — a window from a file boundary.** Scan only the first or last 200 words for
scaffolding tics; no rhetorical-question stack at the opening; no italicised
meta-frame on the first or last paragraph.

**B — a structural position.** The closing section must come last; the opening
paragraph is 45–70 words; bold at most once per section.

**C — a region delimited by other matches.** No `tú` in the opening and closing
but fine mid-chapter; no bold title before the first blockquote.

**A and B are the same feature** — "the first 100 words" and "the first paragraph"
are both a structural unit selected by index from an end, and `text.paragraph_spans`
already produces the spans.

**C is not, and cannot be folded in.** `repos/enciclopedia` forbids `## H2` inside
a chapter entirely, so its chapters have no headings at all and their internal
regions are delimited by custom `\sepN` renderer macros. There is no structural
marker rift can see. Structural zones alone would leave a third of the surviving
demand unwritable.

## Zones are always computed on masked text

**One rule, no exceptions, for every rule kind: zone spans are resolved on
`mask(text)`, before `strip_patterns` runs.** This is the decision the rest of the
design hangs on, and it was wrong in the first draft.

Two reasons, both found by review rather than by reasoning:

**A zone must never be able to select code.** `text.paragraph_spans` drops block
elements, but a fence's *delimiter* lines are block elements while its *contents*
are not. On unmasked text a document opening with a code fence yields the code as
paragraph `[0]`:

```
UNMASKED:  [0] 'this is code\nand more code'   [1] 'Real first prose paragraph.'
MASKED:    [0] 'Real first prose paragraph.'   [1] 'Second prose paragraph.'
```

`require` reads unmasked, so a `require` zone resolved the same way would make
`index: [0]` select a code block — reopening a settled boundary through a key
that looks purely structural. Resolving spans on masked text closes it. `require`
still *matches* unmasked within the span it is given, so "a code fence is
documentation" survives for content; only zone **selection** is masked.

**`strip:` would otherwise erase the bound.** `unpermitted` and `_values` both
apply `strip_patterns` after masking, and the motivating delimited bound is a
renderer macro — exactly what `strip:` is for. A rule stripping `\\sep\d` as
apparatus makes every delimited zone in that same rule unresolvable. Verified:
with `strip: ['\\sep\d']` the bound is gone before any zone could see it.
Resolving zones between `mask` and `strip_patterns` is the only ordering that
works.

Masking is idempotent, so passing an already-masked span to a metric that masks
again costs nothing.

## The two forms

A rule carries **exactly one** form. Both is a `ConfigError`, matching the rule
`extract` already follows for its own keys.

### Structural

```yaml
  - name: "no italicised meta-frame on the opening or closing paragraph"
    extract:
      list: ['^_[^_]+_$']
    forbid:
      in: "chapters/*.md"
      as: regex
      zone: { unit: paragraph, index: [0, -1] }
```

- **`unit`** is `paragraph` or `section`.
- **`index`** is a list of integers with Python semantics, so `-1` is the last
  zone.

A **paragraph** is what `text.paragraph_spans` returns.

A **section** is delimited by `measure._H2` — `##` only, excluding `###` — reusing
the same compiled regex the `sections` metric already uses, so a config has one
definition of "section" rather than two. Text before the first `##` is zone 0,
which is what makes "the chapter opening" addressable in a file whose first
heading is its title.

**An index-less structural zone is a trap, and stays legal.**
`zone: {unit: paragraph}` selects the union of paragraph spans, which is **not**
the whole file: headings, list items and table rows are dropped, so a `forbid`
silently stops reporting a banned word in a heading. Anyone reaching for it wants
no zone at all. Forbidding it would be a special case; the README says this
plainly instead.

A related consequence, because quotes were made opt-in deliberately:
`include_quotes: true` **cannot be reached through a paragraph zone**. `_BLOCK`
drops `>` lines from `paragraph_spans` regardless of masking, so a rule that opted
back into quoted prose loses it again the moment it adds a paragraph zone. Use a
delimited zone, or no zone.

### Delimited

```yaml
  - name: "no second-person address outside the journey"
    extract:
      list: ["tú", "contigo"]
    forbid:
      in: "capitulos/*.md"
      as: word
      zone: { after: '\\sep2', before: '\\sep3' }
```

- **`after`** and **`before`** are regexes, compiled `MULTILINE` like every other
  pattern in a config. Both are optional: `after` alone runs to end-of-file,
  `before` alone runs from start-of-file.
- **The first match wins for each bound**, always. One region per file. No
  nesting, no multiple regions, no overlap resolution.
- The region **excludes the bound matches themselves**, so a banned word inside
  the `\sep2` line is not a site.
- If the resolved start lands **after** the resolved end, the region is empty and
  the zone counts as unresolvable — see below. Otherwise a config whose two
  patterns are the right way round in one chapter and the wrong way round in
  another would go quietly green on the second.

That bluntness is the design, not a shortcut. A region selector that resolves
ambiguity is a parser, and a zone that silently lands on the wrong span produces a
rule that is confidently wrong about where it looked.

## A site must be fully contained

`matcher.find` already filters its `exclude` spans by full containment
(`s <= m.start() and m.end() <= e`), and it must here too. Matches genuinely
straddle zone edges: `_word_pattern` joins words with `\s+` and is documented to
span a blank line, and `as: regex` runs `MULTILINE`. Testing only the start offset
would report a site for a match that mostly lies outside the zone.

## `measure.zone` takes `pattern:` only

Zoning a **metric** is rejected — `metric:` together with `zone:` is a
`ConfigError`. Two independent reasons:

**Statistical.** The parent design's rule is that no metric may depend on absolute
sentence counts being correct, which is why every sentence metric is a ratio or a
sibling comparison. A zone is short enough that crude splitting dominates, and
restricting zoned measures to absolute `min`/`max` thresholds — the first draft's
answer — puts them on exactly the footing that rule forbids.

**Ambiguity.** `vs-siblings` compares a file against *the other files*; with zones
"the others" could be the other zones of this file or the same zone across files.
`burrows-delta` has the same problem in a different key: it is inherently
cross-document, so zoning it silently redefines "document" as "zone". Rejecting at
the `metric:` key catches both, where a guard on `vs-siblings` alone would miss
`burrows-delta` entirely.

**`per:` is also rejected with a zone.** Its denominator is the span's token
count, which is noisy at zone length for the same reason.

What remains is a raw `pattern:` count over a zone — which is exactly the request
that motivated zoning `measure` at all (*bold at most once per section*), and it
is exact rather than statistical.

## An unresolvable zone fails the rule

The first draft said an unresolvable zone would "emit a note and decline to
judge", citing the degenerate-set precedent. **That precedent does not do what I
claimed.** `cli.py` prints notes, then falls through to the green `✓` and exits 0
— a note is a loud annotation on a *pass*. And the note channel exists only on the
`measure` branch: `find`, `unpermitted` and `_occurrences` return sites and
nothing else.

So an unresolvable zone is **a failure entry**, carrying the rule's own severity
through the existing `failures` machinery:

```
✗  no second-person address outside the journey  [1 occurrences]
   capitulos/03-el-rio.md   zone matched nothing
```

No new channel, no signature change to three functions, and a declared zone that
does not exist is genuinely a broken rule — the same class as a rule pointed at a
renamed file, which is the failure this repo has already paid for once.

## `require` zones narrow within a file, not across files

`matcher.check` returns `True` on the **first** file in the glob that matches — it
is existential over the glob by design. A zone narrows *where in a file* it looks;
it cannot make `require` ask the question per-file.

So the request "the guide's surname is required in the footnote" is **not covered
by this design** and has been dropped from the list above: it would pass when one
chapter in forty satisfies it. Making `require` per-file is a separate feature
with its own key (`per_file:`) and its own evidence, and is out of scope here.

## Where it lands in the code

- **`text.py`** grows `zone_spans(text, zone) -> list[tuple[int, int]]`, built on
  `paragraph_spans` plus a new `section_spans` using `measure._H2`. Single place
  either form is interpreted. Callers pass already-masked text.
- **`matcher.find`** and **`matcher.unpermitted`** filter sites to those fully
  contained in a selected span — the same shape as the `sentence_start` filter
  already in `find`. Zone spans are computed **once per file**, hoisted out of the
  per-entity loop: `find` is called once per extracted entity and re-masks every
  file, so a 411-entry glossary over 30 chapters would otherwise recompute spans
  ~12,000 times.
- **`matcher.check`** restricts the text it searches. Zones are sliced from the
  masked text **before** `check` folds the document with `str.lower()`, which is
  not length-preserving in Unicode (`İ` folds to two codepoints) and would shift
  every offset. `require.exists: true` ignores `in:` and `as:` because it tests a
  path — a `zone:` beside it is a `ConfigError`.
- **`cli._values`** masks for zone resolution (it currently holds raw text and
  never masks), slices, then applies `strip_patterns` and counts.
- **`cli._values`'s return type changes** and this ripples further than the two
  functions the first draft named. Keys are currently `Path` and
  `.relative_to(root)` is called on them in `check_cmd`, `list_cmd` and
  `stats_cmd` (`cli.py:235`, `349`, `383`). A zoned key becomes
  `(Path, zone_index)`; every one of those sites plus `_apply_expect` must be
  updated together.
- **`cli.list_cmd`'s measure branch calls `_values` and `_apply_expect` bare**,
  with no `ConfigError` handler, so today an unknown metric tracebacks in
  `rift list` while exiting 2 cleanly in `rift check`. Adding new `ConfigError`s
  without fixing that hole doubles it. Fix it in the same change.
- **`cli._kinds_or_exit`** validates zone shape up front. Its docstring already
  promises a malformed config fails "before any work"; three new errors raised
  deep in execution would break that promise, costing nineteen rules of work and
  nineteen printed results before a typo in rule twenty is reported.

## Testing

The repo's bar, unsoftened — every new behaviour ships with a test watched to
fail, and `matcher.py` gets a mutation pass afterwards.

Cases a weaker suite would miss:

1. **A zoned `forbid` must reject an occurrence *outside* the zone.** A test that
   only asserts the in-zone site is found passes against an implementation that
   ignores `zone:` entirely. This is the same vacuity that shipped twice already —
   the `sentence_start` whitespace fixture and the `permit.strip` fixture — and it
   is the test to write first.
2. **`index: [-1]` selects the last zone, not the first.** An off-by-one that
   silently picks zone 0 passes any single-zone fixture, so the fixture needs at
   least three zones with distinguishable content.
3. **A paragraph zone on a document opening with a code fence must not select the
   code** — asserted under `require`, which is the kind that reads unmasked and
   the only one where this can regress.
4. **A delimited zone survives a `strip:` that targets the bound pattern.**
   Without the mask-then-zone-then-strip ordering this silently reports nothing.
5. **A delimited zone excludes the bound matches themselves.**
6. **An unresolvable zone fails**, asserted on the exit code *and* the reported
   text — an exit-code-only test passes against an implementation that reports
   nothing at all.
7. **`metric:` + `zone:` exits 2**, including for `metric: burrows-delta`
   specifically, and the message names the rule.
8. **A zoned `measure` key survives `relative_to`** in all three commands —
   `check`, `list` and `stats`.
9. **A malformed zone exits 2 before any rule output is printed**, which is what
   pins the up-front validation rather than a mid-run raise.
10. **An unzoned rule behaves exactly as before.** The whole existing suite
    passing untouched is the acceptance condition, the same one the span refactor
    carried.

## Out of scope

- **Sliding windows with a run-length condition.** `/revise` wants "flag 3 or more
  *consecutive* paragraphs with no first- or second-person pronoun". That is a
  scan for a run satisfying a predicate, not a zone selection; bending `zone:` to
  fit it would produce a key meaning two different things.

- **Per-file `require`.** See above. A real gap, a different key, separate
  evidence.

- **Composing the two forms.** No `unit: section` *and* `after:` in one rule. Each
  composition rule is a semantics somebody must hold in their head to predict what
  a config does.

- **Multiple delimited regions per file.** First match wins for each bound.

- **Zoning a `metric:` or using `per:` with a zone.** Recorded above.

- **Reading inside code blocks.** Settled permanently in the parent design, and
  zones do not reopen it — spans are resolved on masked text precisely so that
  they cannot.

---

*Revised after a review that checked every claim this spec made about rift's
internals against `src/` and found ten that did not hold. Four changed the design:
zones must resolve on masked text (otherwise a `require` paragraph zone selects a
code fence, and `strip:` erases delimited bounds); zoned `measure` takes
`pattern:` only rather than `metric:` with absolute thresholds; an unresolvable
zone fails rather than emitting a note, because the precedent cited for the note
prints green and exits 0; and `require` zones cannot deliver the per-file request
that had been listed as covered.*
