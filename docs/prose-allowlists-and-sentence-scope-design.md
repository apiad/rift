# Prose allowlists and sentence scope — design

**Status:** approved 2026-08-27, not yet implemented.
**Scope:** one new rule kind (`permit`), one new matcher (`as: sentence_start`),
one new metric (`repeated-sentence-openers`), and one fix to literal matching
(whitespace inside a multi-word entity). Target release `v0.4.0`.

This is slice 3 of the prose work. Slice 1–2 are
[`prose-linting-design.md`](prose-linting-design.md); its five design principles
govern everything below and are not restated here except where a decision turns
on one.

## Why this exists

The question that started it: can rift check spelling, grammar, passive voice and
"specific grammatical constructions" without an LLM and without NLP?

Three of those four are answered **no**, and the reasoning is recorded in
[Out of scope](#out-of-scope) rather than left for someone to re-derive. What
survived is the fourth, generalised: the constructions worth banning are mostly
*sentence-scoped*, and rift cannot express a sentence scope today because every
regex in a config anchors per **line**. And underneath the spelling request sits
a shape rift genuinely lacks — an **allowlist**.

rift can say *these strings must appear in the docs* (`require`) and *these
strings must not appear in the prose* (`forbid`). It cannot say *nothing outside
this set may appear in the prose*. Spelling is one instance of that shape. "No
proper noun outside the roster" and "no acronym outside the glossary" are two
more, and on a book with a 411-entry glossary they are likely worth more than the
spellcheck.

## 1. `permit` — a third assertion kind

The mirror of `forbid`. Where `forbid` bans the extracted set, `permit` bans
everything *but* the extracted set, and reports the same thing `forbid` reports:
`file:line  <token>` sites.

```yaml
  - name: "every word is a word we have accepted"
    severity: warning
    extract: { file: "dict/*.txt", lines: true }
    permit:
      in: *prose
      of: '^[A-Za-zÀ-ÿ]'        # optional: which tokens the rule judges
      case_insensitive: true
```

`extract` stays orthogonal, which is the whole reason this is cheap: the
permitted set can come from `lines:` over a vendored wordlist, from `yaml_keys:`
over `glossary.yaml`, from `regex:`, or from an inline `list:`.

### Semantics

- **Unit is the token**, per `text.tokens()` — `\w+`, lowercased, Unicode. The
  document is read **masked** (`text.mask`), exactly as `forbid` reads it, so
  code fences, inline code, link URLs, HTML tags and blockquotes are already out
  of play, and `include_quotes: true` puts blockquotes back.
- **All-digit tokens are never judged.** A year is not a spelling. This is the
  one piece of built-in behaviour, and it is a fact about tokens rather than a
  taste about prose.
- **`of:`** is an optional regex; only tokens matching it are subject to the
  rule. Absent, every token is judged. This is what makes `permit` more than a
  spellchecker — `of: '^[A-Z]'` against a roster is "no proper noun outside the
  roster". **`of:` is matched against the token as it appears in the source, before
  lowercasing**, or a case-sensitive filter could never match anything — this is
  the one place a token's original form survives, and it is the reason the roster
  example above is expressible at all. Membership against the permitted set is
  still decided on the folded form when `case_insensitive` is set.
- **`case_insensitive`** behaves as everywhere else: both sides fold. No new
  case machinery, and in particular rift does **not** acquire an opinion about
  which words should be capitalised.
- **No `exclude`, no `max_per_file`, no `max_files`.** The permitted set *is* the
  allowance; a second allowance mechanism on top of it would be two ways to spell
  the same exemption.

### Report shape

`rift check` reports sites, like any `forbid`. `rift list` reports **unique
unjudged tokens with their occurrence counts, most frequent first** — not sites.
This asymmetry is deliberate and it is what makes the feature usable: the first
run against a 268-page book emits on the order of a thousand sites, and a flat
site list is untriageable where a frequency-ranked vocabulary is a worklist. A
`permit` rule without this surface would be shipped and switched off in a week.

### Where it lands in the code

`matcher.check` and `matcher.find` both take **one entity** and are called once
per extracted string by `cli.check_cmd` / `cli._occurrences`. `permit` inverts
that: it takes the **whole set** and walks the document once. So it is a new
function beside them rather than a variant of either —

```python
def unpermitted(root: Path, allowed: set[str], permit: dict) -> list[tuple[Path, int, str]]
```

— reusing `extractor.resolve_globs`, `text.mask` and `text.line_of`. It cannot
use `text.tokens()` as it stands: that returns lowercased strings and discards
the offsets, and `permit` needs both the offset (to report a line) and the
original form (for `of:`). `text._TOKEN.finditer` already yields exactly that, so
this is a span-returning sibling of `tokens()` — the same shape as §2's change,
but over tokens rather than sentences, and independent of it.
`"permit"` joins `cli.RULE_KINDS`, which is what makes
`cli._rule_kind` reject a rule carrying both `permit` and `forbid`, and both
`check_cmd` and `list_cmd` grow a branch for it. `list_cmd` is the one that
matters: it crashed on `measure` for exactly this reason as recently as `14ce59e`.

## 2. `as: sentence_start`

A new matcher for `forbid`, joining `heading` / `table_cell` / `mermaid_node`.

```yaml
  - name: "no throat-clearing openers"
    extract: { list: ["However", "Moreover", "Indeed", "Ultimately", "In fact"] }
    forbid: { in: *prose, as: sentence_start, case_insensitive: true }
```

**It is not expressible as a regex over the raw text**, because it needs
segmentation — and this is precisely why it cannot be written in a config today:
`as: regex` compiles `MULTILINE`, so `^` anchors per line, and a sentence that
begins mid-line has no anchor at all.

Implementation is therefore a **post-filter, not a pattern**. `matcher._pattern_for`
returns the ordinary `as: word` pattern; `matcher.find` computes the sentence
spans of the masked text and keeps only the sites whose match begins one. This
reuses the entire existing path and adds no second way to match a literal.

### What `text.py` has to grow

`text.sentences()` returns `list[list[str]]` — token lists — and `text.paragraphs()`
returns strings. Both are offset-free, so nothing downstream can report a line.
Both grow span-returning variants, with the existing APIs kept as thin wrappers
over them, so that **no metric changes behaviour**. That last clause is the
acceptance condition for this section: the metric suite must be untouched and
still green.

### The honest caveat

Sentence splitting stays as crude as it is (`text._split_sentences`; `Ph.D.`
over-splits). For a *metric* that is harmless, because every file is over-split
by the same rule and comparisons survive. For this matcher it is not harmless: a
spurious boundary yields a **false site**. It never yields a missed one. That
asymmetry goes in the README next to the matcher, not into a footnote — a rule
whose failure mode is undocumented is a rule someone will stop believing.

## 3. `repeated-sentence-openers`

*"No two consecutive sentences open with the same word"* is a real tic, needs no
lexicon, and encodes no taste — it is a self-comparison, like `vs-siblings`. As a
`forbid` it would need a fourth rule kind with no `extract`, which is a great deal
of architecture for one rule. It is a count, so it is a metric: **consecutive-opener
repeats per 1000 words**, one number per file, joining `measure.METRICS` beside
`self_repetition`.

Needs only the existing token-list `text.sentences()` — no spans, no new
machinery, language-agnostic by construction.

## 4. Whitespace-tolerant literal matching

A multi-word entity is compiled as `rf'\b{re.escape(entity)}\b'`, so the single
space in `not merely` is a literal space and the phrase is invisible when it wraps
a line. `books-tsoc` writes one paragraph per line and was never bitten;
`repos/enciclopedia` is hard-wrapped and would be.

Runs of whitespace inside the entity compile to `\s+`. **Two sites, and the
second is easy to miss**: `matcher._pattern_for` (which serves `forbid`) and the
`as_type == "word"` branch of `matcher._matches` (which serves `require`). Fixing
only the first leaves `require`'s `as: word` broken in the same way.

This changes the behaviour of existing configs in the direction of catching more,
which is correct for a ban and worth a CHANGELOG entry saying so.

## Testing

Per `AGENTS.md`, which is not negotiable here:

1. **Every new matcher and rule kind ships with a test that has been watched go
   red.** In particular `as: sentence_start` must be shown to reject a
   mid-sentence occurrence of the same word — a test that only asserts the
   sentence-initial site is found would pass against a plain `as: word`
   implementation and assert nothing about this feature at all.
2. **`matcher.py` is mutation-tested after the change.** Break `_matches` to
   `return True` and confirm the suite fails.
3. **`permit`'s multiplicity is tested**, as `find`'s was: three unknown tokens
   across two files must yield three sites, and `list` must fold them to a ranked
   vocabulary.
4. **The new metric carries a discrimination test** — a fixture with no repeated
   openers and one built from them, asserting separation in the right direction —
   and its expected value is **hand-computed from the definition**, never pasted
   from a run.
5. **`text.py`'s refactor is proved by the absence of change**: the existing
   metric tests pass untouched.

## Out of scope

- **Grammar checking.** Not "hard" — excluded. It needs a parse, and the
  production answer (LanguageTool) is a POS tagger plus per-language
  morphological dictionaries plus n-gram confusion sets plus tens of thousands of
  hand-written rules. That is the NLP principle 1 excludes, and it is excluded
  per-language, which principle 3 forbids independently. A regex approximation of
  grammar is a linter that lies, which is worse than no linter.

- **A passive-voice matcher.** Two independent reasons. *Detection*: past
  participles cannot be identified without a lexicon — `be + \w+ed` misses every
  irregular (*written, known, built, taken, made, done, seen, understood*) and
  false-fires on adjectives (*was tired, is interested, was complicated*) — and
  the lexicon would be per-language, against principle 3. *Judgment*: the passive
  is correct in a great deal of good prose, especially historical narration where
  the agent is deliberately backgrounded ("the Enigma was broken at Bletchley
  Park"), so a ban fires on correct writing, which `know-how/writing-rules.md`
  disqualifies outright. "Passive is bad" is encoded taste against principle 2,
  and it is taste that does not survive contact with the literature.

  The defensible question — *is one chapter markedly more passive than its
  siblings?* — needs **no new code**, because detector error is roughly uniform
  across a file set and so the ranking survives a detector the absolute number
  would not. It is a `pattern` density with `vs-siblings`, and it belongs in
  `know-how/writing-rules.md` as a recipe rather than in rift as a feature.

- **Any dictionary shipped with rift.** Principle 2, exactly as it applies to
  banned lists. `permit` is the mechanism; the wordlist is the consumer's.
  `aspell dump master en_US > dict/en.txt` is the recipe, and because `extract`
  globs, `file: "dict/*.txt"` unions the vendored dictionary with a curated
  `dict/terms.txt` — so the 120k-line blob never churns and the diff a reviewer
  reads is the term file.

- **A per-sentence length ceiling.** Reasoned through and dropped. The file-level
  rhythm metrics (`sentence-length-cv`, `short-sentence-ratio`,
  `sentence-length-autocorr`) already cover cadence, and a hard ceiling is encoded
  taste that fires on deliberate long sentences — the "yeah, that's fine actually"
  failure that `know-how/writing-rules.md` says disqualifies a rule.

- **Wiring `permit` into `books-tsoc`.** The mechanism lands first. Landing it
  together with a thousand-token triage would make it impossible to tell which of
  the two broke.
