# Zone scoping — design

**Status:** approved 2026-08-27; revised the same day after review;
implemented and released as `v0.6.0` the same day.
**Scope:** a `zone:` key on `forbid`, `permit` and `measure` that restricts a rule
to part of a document instead of all of it. Deliberately **not** on `require` —
see below. No new rule kind, no new extractor, no new metric.

The five design principles in [`prose-linting-design.md`](prose-linting-design.md)
govern this and are not restated except where a decision turns on one.

## Why this exists

Surveying four books' style guides on 2026-08-27 — the `/revise` skill,
`repos/enciclopedia`, `repos/books-mhai` and `repos/books-codex` — turned up about
206 stated writing rules. Roughly 44% are expressible with rift as it stands and
37% need a human reader. Of the remainder, **one missing primitive was requested
by all four independently**, and it is always the same sentence: *this rule
applies to part of the file, not the whole of it.*

Nine requests are served here. Removed first were the ones wanting to read inside
code blocks (out of scope permanently — see the parent design); removed second
were two that are per-file claims dressed as zones, which `require` cannot serve
and which wait on `per_file:` (below). The nine come in three shapes:

**A — a window from a file boundary.** Scan only the first or last 200 words for
scaffolding tics; no rhetorical-question stack at the opening; no italicised
meta-frame on the first or last paragraph.

**B — a structural position.** The opening paragraph is 45–70 words; bold at most
once per section.

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

## `zone:` applies to `forbid`, `permit` and `measure` — not `require`

**`zone:` on a `require` rule is a `ConfigError`**, and this is a scope decision
rather than an oversight.

`matcher.check` returns a bool and early-returns on the **first** file in the glob
that matches: it is existential over the document set by design. Every surviving
`require` + zone request is a **per-file** claim — *the closing section must come
last*, *the promise must land in the first 100 words* — and existentially all of
them pass the moment one chapter in forty complies. A zone narrows *where in a
file* the search happens; it cannot change what the question is asked over, so it
cannot rescue any of them.

Two further consequences fall out of the same fact, and each would have to be
documented as a wart if `require` kept zones: `check` has no failure channel, so
an unresolvable zone in one file would be invisible whenever another file matched;
and when nothing matched at all, the entity would be reported as *missing* with no
indication that the zone rather than the content was the cause.

`zone:` becomes available on `require` when `per_file:` does. Until then the error
names the reason, so nobody re-derives it.

A third argument corroborates it. `require` is the one kind that reads **unmasked**,
and `paragraph_spans` treats a fence's *delimiter* lines as block elements while
its *contents* are ordinary prose. On unmasked text a document opening with a code
fence yields the code as paragraph `[0]`:

```
UNMASKED:  [0] 'this is code\nand more code'   [1] 'Real first prose paragraph.'
MASKED:    [0] 'Real first prose paragraph.'   [1] 'Second prose paragraph.'
```

So a `require` zone would also have made `index: [0]` select a code block,
reopening a settled boundary through a key that looks purely structural. Excluding
`require` removes that hazard along with the semantic one.

## Zones resolve between `mask` and `strip_patterns`

**Two of the three read masked text already; `measure` does not.** `find` and
`unpermitted` call `mask()` themselves, so their zone spans resolve on exactly the
text the rule is scanning and offsets stay aligned with `text.line_of` for free.
`cli._values` holds **raw** text and never masks — each metric masks its own input
instead — so the zoned `measure` path **gains a masking pass** it does not have
today.

That is not a detail to defer to the implementation notes. Resolving zones on raw
text would split `unit: section` on a `##` **inside a code fence**, which is the
precise failure `measure.py`'s module docstring says it is careful to avoid, and
it would pass every fixture that happens not to contain a fence.

The ordering against `strip_patterns` is the second half. `unpermitted` strips
after masking and `_values` strips the raw text; under this design both become
mask → resolve zones → strip. The reason is that the motivating delimited bound is
a renderer macro — exactly what `strip:` is for — so a rule stripping `\\sep\d` as
apparatus makes every delimited zone in that same rule unresolvable. Verified:
with `strip: ['\\sep\d']` the bound is gone before any zone could see it.

**Mask, then resolve zones, then strip** is the only ordering that works, and for
`measure` the first of those three steps is new.

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

A **section** is delimited by `text._H2` — `##` only, excluding `###` — the same
compiled regex the `sections` metric uses, relocated so both share it (see the
implementation notes). A config has one definition of "section", not two. Text before the first `##` is zone 0,
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

## `measure.zone` takes exact counts, not statistics

A zoned measure may use `pattern:`, or `metric: word-count`. **Every other metric
with a `zone:` is a `ConfigError.`**

The line is *exact count* versus *statistic*. A count over a span is as correct as
a count over a file — `pattern_count` and `word_count` both just count things.
Everything else in `METRICS` is a ratio, a coefficient of variation, an
autocorrelation or a mean, and those are the ones that go wrong at zone length.
Two independent reasons, both of which apply only to the statistics:

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

**`per:` is also rejected with a zone.** It turns an exact count into a ratio
against the span's token count, which lands it back among the statistics.

What remains serves both requests that motivated zoning `measure`: *bold at most
once per section* is a raw `pattern:` count, and *the opening paragraph is 45–70
words* is `metric: word-count` with `min`/`max`. Both are exact.

The allowlist is a set of two rather than a property rift can infer, so it is
written where an implementer will find it and other exact counts (`sections`,
`opening-paragraphs`) can join it when a real rule needs them — not before.

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

A declared zone that does not exist is genuinely a broken rule — the same class as
a rule pointed at a renamed file, which is the failure this repo has already paid
for once.

**Two things this costs, stated rather than waved at.** The first draft claimed
"no new channel, no signature change", which was the same shape of claim as the
note-channel error it was replacing.

**It is one entry per file, not per entity.** `find` is called once per extracted
entity (`cli._occurrences`), so producing the entry inside that loop would emit
411 glossary entries × 30 chapters = 12,330 identical `zone matched nothing`
failures from a single broken bound, of which six print and the rest become
`(+12,324 more)` — burying every real finding in the rule. Zone resolution is
therefore hoisted **above** the entity loop, into `_occurrences`, which produces
one entry per `(rule, file)` and passes the resolved spans down.

**That is a signature change**, and hoisting is what makes it a small one:
`find` and `unpermitted` take precomputed spans rather than a `zone` dict, and
`_occurrences` — which already builds `failures` strings directly — owns both the
resolution and the reporting. The alternative was smuggling the entry through the
`(Path, int, str)` site tuple that `check_cmd` and `list_cmd` both render as
`{path}:{line}   {entity}`, which would have meant inventing a fake `:0`.

**The label follows the rule kind**, since `check_cmd` renders one label per rule:
`[N occurrences]` on `forbid`, `[N unpermitted]` on `permit`, `[N out of bounds]`
on `measure`. There is no fifth label for zone failures.

## Where it lands in the code

- **`_H2` moves from `measure.py` into `text.py`**, and `measure` imports it from
  there. This is a prerequisite, not a tidy-up: `measure.py` already does
  `from .text import mask, paragraphs, sentences, tokens` and `text.py` imports
  nothing local — it is the base of the module graph. Having `text` reach into
  `measure` for `_H2` is a circular import that fails at load, and the parent
  design names that direction as the wrong shape in so many words. Moving the
  regex down keeps the single definition of "section" with the arrows pointing
  the right way.
- **`text.py`** grows `zone_spans(text, zone) -> list[tuple[int, int]]`, built on
  `paragraph_spans` plus a new `section_spans` using the relocated `_H2`. Single
  place either form is interpreted. Callers pass already-masked text.
- **`cli._occurrences`** resolves zones **once per file, above the entity loop**,
  emits one failure entry per unresolved file, and passes the spans down.
- **`matcher.find`** and **`matcher.unpermitted`** take precomputed spans and
  filter sites to those **fully contained** in one — the same shape as the
  `sentence_start` filter already in `find`.
- **`matcher.check`** is untouched: `require` does not take zones.
- **`cli._values`** masks for zone resolution (it currently holds raw text and
  never masks), slices, then applies `strip_patterns` and counts. Every metric
  masks its own input, so a zoned slice is masked twice — which is safe because
  **`mask` is idempotent, and by construction rather than by luck**: it only ever
  replaces with spaces, and each of its patterns needs a literal delimiter
  (`` ` ``, `<`, `](`, a line-leading `>` or fence marker) that the first pass has
  already blanked, so a second pass has nothing left to match. Verified on nested
  inline-code-containing-HTML, a blockquote inside a fence, an unterminated fence
  running to EOF, and adjacent link URLs — idempotent and length-preserving on all
  four. **The masking is scoped to the zoned path only.** Composing it the other way round flips strip
  and mask relative to today; both blank to spaces so results agree in practice,
  but confining the change to zoned rules makes "an unzoned rule behaves exactly
  as before" true by construction rather than by luck.
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
3. **`zone:` on a `require` rule exits 2**, and the message says why rather than
   only that the key is unknown.
4. **A delimited zone survives a `strip:` that targets the bound pattern.**
   Without the mask-then-zone-then-strip ordering this silently reports nothing.
5. **A delimited zone excludes the bound matches themselves.**
6. **An unresolvable zone fails**, asserted on the exit code *and* the reported
   text — an exit-code-only test passes against an implementation that reports
   nothing at all. Asserted with a **multi-entity** rule, so that one broken bound
   yields one entry rather than one per entity; a single-entity fixture cannot
   tell the two apart.
7. **A statistical metric with a `zone:` exits 2** — asserted for
   `metric: sentence-length-cv` *and* for `metric: burrows-delta` specifically,
   since the latter is the one a `vs-siblings` guard would have missed. The
   converse is asserted too: `metric: word-count` with a zone is **accepted**, so
   the allowlist is pinned from both sides rather than degenerating into a
   blanket ban.
8. **A zoned `measure` key survives `relative_to`** in `check` **and** `list` —
   two commands, not three. `stats_cmd` builds its own spec from CLI flags
   (`{"files": files, "strip": list(strip)}`) with no config and no zone key, so
   it cannot produce a zoned key at all; asserting three commands would silently
   test the unzoned path in one of them, which is the vacuity this section exists
   to catch. `rift stats` is unaffected by this feature and gains no flag.
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

- **`zone:` on `require`, and per-file `require`.** The two are the same item:
  `check` is existential over the glob, so zoning it cannot express any of the
  per-file claims that wanted it. `zone:` on `require` is a `ConfigError` and
  unlocks when `per_file:` lands, which is a different key with its own evidence.

- **Composing the two forms.** No `unit: section` *and* `after:` in one rule. Each
  composition rule is a semantics somebody must hold in their head to predict what
  a config does.

- **Multiple delimited regions per file.** First match wins for each bound.

- **Zoning a `metric:` or using `per:` with a zone.** Recorded above.

- **Reading inside code blocks.** Settled permanently in the parent design, and
  zones do not reopen it — spans are resolved on masked text precisely so that
  they cannot.

---

*Revised twice, both times after a review that checked this spec's claims about
rift's internals against `src/` rather than against the spec's own reasoning.*

*The first pass found ten claims that did not hold. Four changed the design:
zones resolve between `mask` and `strip_patterns` (otherwise `strip:` erases a
delimited bound); zoned `measure` takes `pattern:` only rather than `metric:` with
absolute thresholds; an unresolvable zone fails rather than emitting a note,
because the precedent cited for the note prints green and exits 0; and `require`
zones could not deliver the per-file request listed as covered.*

*The second pass found four more. One was blocking and load-bearing for the rest:
instructing `text.section_spans` to import `measure._H2` is a circular import that
fails at load, since `measure` already imports from `text` and `text` is the base
of the module graph — so `_H2` moves down instead. The others removed `zone:` from
`require` entirely rather than documenting a half-feature, made the unresolvable-zone
entry one-per-file instead of one-per-entity (12,330 identical failures from a
single broken bound), and cut a vacuous third from a test, since `rift stats`
builds its own spec and can never produce a zoned key.*

*Fixing those surfaced a cost the first pass had hidden: restricting zoned
`measure` to `pattern:` also killed "the opening paragraph is 45–70 words", which
needs `word-count`. So the rule is no longer `pattern:`-only — it is **exact
counts versus statistics**, `pattern:` and `metric: word-count` against everything
that is a ratio, a coefficient of variation, an autocorrelation or a mean. That is
what the first pass was reaching for and stated too narrowly.*
