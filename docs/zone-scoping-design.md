# Zone scoping — design

**Status:** approved 2026-08-27, not yet implemented.
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

Eleven surviving requests, after removing the ones that wanted to read inside code
blocks (out of scope permanently — see the parent design). They come in three
shapes:

**A — a window from a file boundary.** Scan only the first or last 200 words for
scaffolding tics; the reader's promised gain must land in the first 100 words; no
rhetorical-question stack at the opening; no italicised meta-frame on the first or
last paragraph.

**B — a structural position.** The closing section must come last; the opening
paragraph is 45–70 words; bold at most once per section.

**C — a region delimited by other matches.** No `tú` in the opening and closing
but fine mid-chapter; no bold title before the first blockquote; the guide's
surname banned in the body and required in the footnote.

**A and B are the same feature** — "the first 100 words" and "the first paragraph"
are both a structural unit selected by index from an end, and `text.paragraph_spans`
already produces the spans.

**C is not, and cannot be folded in.** `repos/enciclopedia` forbids `## H2` inside
a chapter entirely, so its chapters have no headings at all and their internal
regions are delimited by custom `\sepN` renderer macros. There is no structural
marker rift can see. Structural zones alone would leave a third of the surviving
demand unwritable.

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
  zone. Omitted, every zone is selected — which for `measure` means one value per
  zone, and for `forbid` means the **union of those spans**.

That union is **not** the whole file, and the difference is a trap worth naming.
`text.paragraph_spans` drops block elements — headings, list items, table rows,
fences — so `zone: {unit: paragraph}` with no index silently narrows a `forbid`
to body prose only, and a banned word in a heading stops being reported. Anyone
reaching for an index-less structural zone almost certainly wants no zone at all.
It is legal because forbidding it would be a special case, but the README says
this plainly.

A **paragraph** is what `text.paragraph_spans` already returns: a run of non-blank
lines with block elements removed.

A **section** is a heading line through to just before the next heading **of any
level**, with the text before the first heading as zone 0. This is crude, and
crude on purpose: honouring heading depth would mean a hierarchy parser, and the
existing `sections` metric already counts `##` without one. The zone-0 rule is
what makes "the chapter opening" addressable in a file whose first heading is its
title.

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
- If the resolved start lands **after** the resolved end, the region is empty.
  That is treated as an unresolvable zone, not as a silent zero — same note, same
  refusal to judge. Otherwise a config whose two patterns are the right way round
  in one chapter and the wrong way round in another would go quietly green on the
  second.

That bluntness is the design, not a shortcut. A region selector that resolves
ambiguity is a parser, and a zone that silently lands on the wrong span produces a
rule that is confidently wrong about where it looked — the one failure a linter
cannot afford.

## `measure` and the cardinality problem

Zoning `measure` changes its result from one number per file to one number per
zone. `min` and `max` are unaffected. `vs-siblings` is not: it compares a file
against *the other files*, and with zones in play "the others" could mean the
other zones of this file or the same zone across files. Both are defensible, which
is exactly why rift should not pick one silently.

**`measure.zone` together with `expect.vs-siblings` is a `ConfigError`.** Zoned
measures take `min` and `max` only. This unlocks the real request behind the
feature — *bold at most once per section*, which is a `max` — without inventing a
comparison semantics nobody asked for.

Zoned values report with the zone appended, `chapters/ch01.md#3`, so a failure
names the span it came from rather than only the file.

## When a zone does not resolve

An `after:` pattern that matches nothing could reasonably mean "no region, so no
sites", and that would be silently green — the blind spot this repo has already
paid for once, where a rule pointed at a renamed file reports pass forever.

So an unresolvable zone follows the precedent `_apply_expect` already sets for a
file set below four: it emits a note and declines to judge that file.

```
⚠  no second-person address outside the journey
   zone matched nothing in capitulos/03-el-rio.md; reported, not judged
```

The rule neither passes nor fails quietly on that file. A zone that never resolves
across the whole glob is therefore visible on every run rather than discovered
months later.

## Interaction with masking

Zones are computed on the **masked** text — the same text the rule scans — so
offsets stay aligned and `text.line_of` keeps reporting the true line. This
matters for the delimited form in particular: an `after:` pattern that would have
matched inside a code fence does not match, because by the time zones are computed
the fence is blank. That is the correct behaviour for `forbid`, `permit` and
`measure`, all of which read masked.

`require` reads **unmasked**, by the long-standing rule that a code fence is
documentation. Its zones are therefore computed on unmasked text. The asymmetry is
inherited rather than introduced, but it is worth stating because it means the same
`zone:` block can select a different span under `require` than under `forbid`.

## Where it lands in the code

- **`text.py`** grows `zone_spans(text, zone) -> list[tuple[int, int]]`, built on
  the existing `paragraph_spans` plus a new `section_spans`. It is the single
  place either form is interpreted.
- **`matcher.find`** and **`matcher.unpermitted`** filter their sites to those
  whose offset falls inside a selected span — the same shape as the
  `sentence_start` filter already in `find`, which is the precedent for adding a
  positional constraint without inventing a second way to match.
- **`matcher.check`** restricts the text it searches rather than filtering sites,
  since it answers a boolean and has no sites to filter. `require.exists: true`
  already ignores `in:` and `as:` — it tests a path, not a document — so a `zone:`
  alongside it is meaningless and is a `ConfigError` rather than a key that looks
  like it did something.
- **`cli._values`** applies zones before measuring, producing one entry per zone,
  and `_apply_expect` gains the `vs-siblings` rejection above.

## Testing

The repo's bar, unsoftened — every new behaviour ships with a test watched to
fail, and `matcher.py` gets a mutation pass afterwards.

Cases a weaker suite would miss:

1. **A zoned `forbid` must reject an occurrence *outside* the zone.** A test that
   only asserts the in-zone site is found passes against an implementation that
   ignores `zone:` entirely. This is the same vacuity that shipped twice already —
   once in the `sentence_start` whitespace fixture, once in the `permit.strip`
   fixture — and it is the test to write first.
2. **`index: [-1]` selects the last zone, not the first.** An off-by-one that
   silently selects zone 0 would pass any single-zone fixture, so the fixture needs
   at least three zones with distinguishable content.
3. **A delimited zone excludes the bound matches themselves**, so a banned word
   inside the `\sep2` macro line is not a site.
4. **An unresolvable zone emits the note and does not fail**, asserted on both the
   note text and the exit code — a test on the exit code alone would pass against
   an implementation that silently reported nothing.
5. **`measure.zone` with `vs-siblings` exits 2**, and the message names the rule.
6. **Zone spans are computed on masked text for `forbid` and unmasked for
   `require`**, pinned by a fixture where a fence contains the bound pattern.
7. **An unzoned rule behaves exactly as before.** The whole existing suite passing
   untouched is the acceptance condition, the same one the span refactor carried.

## Out of scope

- **Sliding windows with a run-length condition.** `/revise` wants "flag 3 or more
  *consecutive* paragraphs with no first- or second-person pronoun". That is not a
  zone selection — it is a scan for a run that satisfies a predicate, and bending
  `zone:` to fit it would produce a key that means two different things. If it
  earns its place it is a separate feature with its own name.

- **Composing the two forms.** No `unit: section` *and* `after:` in one rule. Each
  extra composition rule is a semantics somebody has to hold in their head to
  predict what a config does; if a real rule needs both, that is evidence to
  revisit, not a reason to guess now.

- **Multiple delimited regions per file.** First match wins for each bound. A
  document with three `\sep2` macros gets one zone, not three.

- **`vs-siblings` on zoned measures.** Recorded above; the comparison set is
  genuinely ambiguous and picking one silently is worse than refusing.

- **Reading inside code blocks.** Settled permanently in the parent design. Zones
  do not reopen it: a zone selects a span of the text a rule already reads, and for
  `forbid`, `permit` and `measure` that text has its fences blanked before zones
  are computed.
