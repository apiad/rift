# `permit` and sentence scope — design

**Status:** approved 2026-08-27, not yet implemented.
**Scope:** a third assertion kind (`permit`), one new matcher (`sentence_start`),
one new metric (`repeated-sentence-openers`), and one fix to `as: word`. Plus the
offset-carrying sentence and paragraph spans that the first two need.

This extends `prose-linting-design.md`. Its four principles govern here unchanged
and are not restated: no LLM, no encoded taste, language-agnostic, mechanical
rather than semantic.

## Why this exists

rift asks two membership questions today. `require` asks *does this string appear
in the docs*. `forbid` asks *where does this string appear in the prose*. Both take
a set of strings you named and look for them.

The missing question is the mirror of `forbid`: **does any string appear that I
never named?** A denylist catches what you thought to ban. An allowlist catches
what you did not think of at all, which on a 268-page book is the larger set.

Two defects in `books-tsoc` are invisible to every rule that exists:

- **A typo.** Nothing counts it, nothing bans it, and it reaches the PDF.
- **A proper noun that is not on the roster.** The book marks a figure at first
  mention; a name that was never marked is a name the glossary does not know, and
  the existing rule can only check the reverse direction — that every glossary
  entry is used.

A third defect is unreachable for a different reason: **a sentence-initial tic**.
Every regex in a rift config compiles with `MULTILINE`, so `^` anchors to a line,
not to a sentence. A paragraph written as one long line — which is how this book
is written — has exactly one anchorable position in it. "No sentence opens with
*However*" cannot be written today at any level of cleverness.

## What was rejected, and why

These were considered in the same discussion and are not deferred — they are out.

**Grammar checking.** Needs a parse. The serious implementations are a POS tagger
plus per-language morphological dictionaries plus n-gram confusion sets plus tens
of thousands of hand-written rules; that is the NLP the project excluded, and it
is excluded per language, so it cannot satisfy principle 3. A regex approximation
of grammar produces a checker that is confidently wrong, which is worse than no
checker because it licenses shipping.

**A passive-voice ban.** Three independent reasons, any one sufficient:

1. Past participles cannot be identified without a lexicon. `be + \w+ed` misses
   every irregular (*written, known, built, taken, made, done, seen, understood,
   held, set, cut, read*) and false-fires on adjectival complements (*was tired,
   is interested, was complicated*).
2. Even a perfect detector flags correct prose. "The Enigma was broken at
   Bletchley Park." "The last Multics installation was shut down in 2000." A book
   of largely agentless history wants the passive there. `writing-rules.md`
   disqualifies exactly this: if the honest response to a red line is *"that's
   fine actually"*, the rule is noise.
3. "Passive is bad" is encoded taste — principle 2 — and taste that is wrong on
   the merits.

The defensible question is density relative to siblings: detector errors are
roughly uniform across chapters, so the *ranking* survives a detector whose
absolute number does not. That needs **no new code** and belongs in a consumer's
config, recorded in `know-how/writing-rules.md`:

```yaml
  - name: "passive density vs siblings"
    measure:
      files: *prose
      pattern: '\b(?:is|are|was|were|be|been|being)\s+(?:\w+ly\s+)?\w+(?:ed|en)\b'
      per: 1000
    expect: { vs-siblings: 2.0 }
```

**A per-sentence word ceiling.** `sentence-length-cv`, `short-sentence-ratio` and
`sentence-length-autocorr` already describe cadence at file level. A hard ceiling
is encoded taste that fires on deliberate long sentences.

**A dictionary shipped with rift.** Principle 2 applies to lexicons exactly as it
applies to thresholds — the same reason `forbid` ships zero entries. The consumer
vendors a wordlist: `aspell dump master en_US > dict/en.txt`.

## `permit` — the third assertion kind

`permit` names the set that is allowed and reports everything else.

```yaml
  - name: "every word is one we have accepted"
    severity: warning
    extract: { file: "dict/*.txt", lines: true }
    permit:
      in: *prose
      strip: ['\{[~>][^}]*\}', '\[\^[^\]]*\]']
      case_insensitive: true
```

Because `extract` globs, `dict/*.txt` unions a vendored `en.txt` with a curated
`dict/terms.txt`. That split matters in practice: the 120k-line blob never churns,
so the diff a reviewer reads is the term file, and every new proper noun is an
explicit line someone added.

`extract` stays orthogonal. The permitted set can equally come from `yaml_keys`
over `glossary.yaml`, from a `regex`, or from an inline `list`.

### Semantics

- **What is checked.** Every word token in the document, masked exactly as
  `forbid` masks it (fences, inline code, HTML tags, link URLs, blockquotes;
  `include_quotes: true` puts quotations back in play).
- **Not `text.tokens()`.** That function lowercases and returns bare strings. Both
  are wrong here: a site report needs an offset to derive a line from, and `of:`
  needs the token as written. `permit` uses `token_spans` (below) and folds case
  only when the rule asks for it.
- **`strip:` is required in practice, not optional.** Renderer markup tokenises as
  prose: `[Tony Hoare]{~hoare-tony}` yields `hoare`, `tony`, `hoare`, `tony`, and a
  footnote label yields its slug. Without `strip:`, every glossary key and every
  footnote label is reported as an unknown word and the rule is unusable. It takes
  the same patterns as `measure.strip` and uses the same `text.strip_patterns`.
- **`of:` — which tokens are subject to the rule.** An optional regex; only tokens
  matching it are checked. Default: every token. This is what makes `permit` more
  than a spellchecker — `of: '^[A-Z]'` against `glossary.yaml`'s keys asks *is
  every proper noun on the roster*, which is a different and arguably more valuable
  rule than the dictionary one.
- **Digits.** A token that is entirely digits is never checked. A year is not a
  spelling.
- **Case.** `case_insensitive` behaves as it does in every other rule: both sides
  fold. No new case machinery, and in particular no rule about sentence-initial
  capitalisation. **`of:` is applied to the token as written, before any folding**
  — otherwise `of: '^[A-Z]'` and `case_insensitive: true` would silently select
  nothing, which is the failure mode where a rule passes by matching no rows.
- **No `exclude`.** `forbid.exclude` exists because a denylist cannot name its own
  exceptions. An allowlist is nothing but its exceptions; adding the key would be
  a second way to spell the same thing.
- **Allowances do not apply.** `max_per_file` and `max_files` are meaningful for a
  banned phrase and meaningless for an unknown word.

### Report shape

`rift check` reports sites, in `forbid`'s format:

```
⚠  every word is one we have accepted  [3 occurrences]
   1_theory/ch02-computability.md:41   recieve
   3_software/ch06-process.md:12       teh
   4_ai/ch04-deep-learning.md:9        Bengios
```

`rift list` reports **unique unknown tokens with their occurrence counts, most
frequent first.** This is not cosmetic. The first run against a real book will
emit on the order of a thousand sites, and a flat list of sites cannot be triaged;
a frequency-ranked list of distinct tokens can, because the top of it is
overwhelmingly real terms that belong in `dict/terms.txt`. Without this surface the
feature is not usable on its intended consumer.

### Why it is not a variant of `find`

`check(root, entity, require)` and `find(root, entity, forbid)` each take **one**
entity and are called once per extracted string by `cli.py`. `permit` inverts the
loop: it needs the whole permitted set in hand and walks the document's tokens
once. Calling `find` per dictionary word would be 120,000 passes over the book.

So it is a new function in `matcher.py` alongside the other two — taking the set
rather than a member of it — and a third branch in `check_cmd` and `list_cmd`
rather than a reuse of the `forbid` branch. `RULE_KINDS` in `cli.py` grows to
`("require", "forbid", "permit", "measure")`, which `_rule_kind` already validates
as mutually exclusive with no change.

## `as: sentence_start`

A new matcher, joining `heading` / `table_cell` / `mermaid_node`.

```yaml
  - name: "no throat-clearing openers"
    extract: { list: ["However", "Moreover", "Indeed", "Ultimately", "In fact"] }
    forbid: { in: *prose, as: sentence_start, case_insensitive: true }
```

**It is not a regex.** Sentence segmentation cannot be expressed as a pattern over
the raw text, so `_pattern_for` keeps returning the ordinary `\b`-wrapped word
pattern and `find` applies a **post-filter**: compute sentence spans over the
already-masked text, then keep only those matches whose start coincides with a
sentence start. Everything else in `find` — globbing, masking, `line_of`,
`exclude` — is reused untouched.

Two consequences, both stated rather than hidden:

- Splitting stays as crude as it is today. `Ph.D.` over-splits, which for this
  matcher yields a *false site*, not a missed one. That is the right direction for
  a warning-severity rule and the wrong direction for an error; the docs say so.
- `require` with `as: sentence_start` is accepted and answers "does this word open
  a sentence anywhere", which is a strange thing to require but costs nothing to
  support and is stranger to reject.

## `repeated-sentence-openers` metric

*Two consecutive sentences opening with the same word* is a genuine tic, purely
mechanical, and encodes no taste — it is a self-comparison, like `vs-siblings`.

Expressing it as a `forbid` would need a fourth rule kind with no `extract`, which
is disproportionate machinery for one rule. It is a count, so it is a metric:
consecutive-opener repeats per 1000 words, one number per file.

```yaml
  - name: "openers do not stutter"
    measure:
      files: *prose
      metric: repeated-sentence-openers
      strip: ['\{[~>][^}]*\}', '\[\^[^\]]*\]']
    expect: { vs-siblings: 2.0 }
```

Needs only the existing token-list `text.sentences()`. No spans.

## Wrap-safe `as: word`

A multi-word entity currently compiles to `\b{escaped}\b` with the space literal,
so `not merely` split across a newline is not seen. `books-tsoc` writes one
paragraph per line and was never bitten; a hard-wrapped repo would be.

Runs of whitespace inside the entity compile to `\s+`. **`word` only** — `mention`
stays a plain substring, because existing rules depend on that and `forbid`'s
default is already `word`.

There are **two** call sites and fixing one leaves the other broken:
`_pattern_for` (used by `find`, so `forbid`) and the separate `as_type == "word"`
branch inside `_matches` (used by `check`, so `require`). A test must cover both.

This is a behaviour change in the direction of catching more, which is correct for
`forbid`, and it goes in the CHANGELOG as a change rather than a fix.

## Spans in `text.py`

Both new features need character offsets, and nothing in `text.py` carries one.
`tokens()` lowercases and returns bare strings; `sentences()` returns token lists;
`paragraphs()` returns strings and additionally drops block-element lines, so
position cannot be recovered downstream from any of the three.

Three span-returning functions, each a list of `(start, end)` into the text as
given:

| New | For | Existing function becomes |
|---|---|---|
| `token_spans(text)` | `permit` — the line to report, and the token as written for `of:` | `tokens()` wraps it, still lowercasing |
| `sentence_spans(text)` | `sentence_start` — where a sentence begins | `sentences()` wraps it |
| `paragraph_spans(text)` | prerequisite of the above; `paragraphs()` discards block lines | `paragraphs()` wraps it |

**No metric may change its value as a result.** The measurement engine is the
regression risk in this change; the existing metric tests are the guard, and they
must pass unmodified.

## Testing

The repo's bar applies without softening: every new matcher and rule kind ships
with a test that was watched to fail, metric expectations are hand-computed from
the definition rather than pasted from a run, and `matcher.py` gets a mutation
pass afterwards.

Cases that a weaker suite would miss:

- **`permit` with an empty permitted set** reports every token, not zero. The
  extractor swallows parse errors and yields an empty set, and for `require` that
  silently passes — the known gap. For `permit` the same emptiness must be
  maximally loud, which is the opposite polarity and needs its own test.
- **`permit` respects the mask**, so a misspelling inside a code fence is not a
  site. Separate tests per masked region, not one "exclusions work" test.
- **`permit` without `strip:`** reports marker slugs — asserted deliberately, so
  that the documented requirement is pinned rather than assumed.
- **`of:` narrows and does not merely filter the report** — a token failing `of:`
  must not be checked even when it is absent from the set.
- **`of: '^[A-Z]'` together with `case_insensitive: true` still selects tokens.**
  If `of:` were applied after folding this selects nothing and the rule reports
  clean, which is a green that means the opposite of what it says.
- **`sentence_start` rejects a mid-sentence occurrence on the same line**, which is
  the whole point of the matcher and the case a line-anchored implementation would
  pass by accident.
- **`sentence_start` accepts the first sentence of a paragraph**, the boundary the
  span logic is most likely to get wrong by one.
- **`repeated-sentence-openers`** carries a discrimination test: a stuttering
  fixture and a varied one, asserting separation in the right direction.
- **Wrap-safe `word`** is tested through `forbid` *and* through `require`.

## Out of scope

- **`strip:` for `forbid`.** `permit` needs it and gets it. Whether `forbid` should
  also take it is a real question — a banned word inside a marker slug is a false
  site today — but it is a separate change to a shipped rule kind and does not
  block this one. Revisit after `permit` is in use.
- **Wiring `books-tsoc` up to `permit`.** Deliberately not part of this work.
  Landing the mechanism and a thousand-token triage in the same change makes it
  impossible to tell which one broke.
- **Automatic dictionary generation.** rift never writes a wordlist. `aspell dump`
  is a documented recipe, not a feature.
- **Sentence-scoped `measure`.** Files remain the unit for metrics, as in the
  parent design.
