# Prose allowlists and sentence scope — implementation plan

**Spec:** `docs/prose-allowlists-and-sentence-scope-design.md`
**Status:** in progress 2026-08-27.
**Target:** `v0.4.0`.

Four slices, ordered cheapest-first so the risky one lands last against a suite
that has already grown. Each ends with rift able to do something end to end from
a `.rift.yaml`, not with a layer completed.

## Global constraints

- **Every new matcher and rule kind ships with a test watched go red.** AGENTS.md,
  non-negotiable. A test that only asserts the positive case would pass against a
  plain `as: word` implementation and assert nothing.
- **Metric expectations are hand-computed from the definition**, never pasted from
  a run.
- **`text.py`'s refactor is proved by the absence of change**: the existing metric
  tests must pass untouched. If one needs editing, the refactor is wrong.
- **After touching `matcher.py`, mutation-test.** Break `_matches` to `return True`
  and confirm the suite goes red.
- English everywhere. Conventional commits. One slice per commit.

## The trap this plan exists to avoid

`cli.check_cmd` (line 204) and `cli.list_cmd` (line 277) both dispatch
`if require / elif forbid / else measure`. **An unrecognised kind falls into the
`measure` branch**, which is exactly how `list_cmd` came to raise
`KeyError: 'forbid'` on every measure rule until `14ce59e` fixed it three weeks
into the feature's life. Adding a fourth kind re-arms that bug in both commands.
Slice D converts both to explicit per-kind branches with a final `else` that
raises `ConfigError`, and pins it with a test.

## Slice A — whitespace-tolerant `as: word`

Delivers: a multi-word ban that survives a line wrap.

| # | Task | Verify |
|---|---|---|
| A.1 | `matcher.py`: `_word_pattern(entity)` → `r'\b' + r'\s+'.join(re.escape(p) for p in entity.split()) + r'\b'`. Empty entity returns `None`. | `not merely` compiles to `\bnot\s+merely\b`. |
| A.2 | Call it from **both** sites: `_pattern_for`'s `as_type == "word"` branch (serves `forbid`) **and** `_matches`'s `as_type == "word"` branch (serves `require`). | Fixing only the first leaves `require` broken identically — a test per site. |
| A.3 | README: note under `as: word` that whitespace inside an entity matches any run, **including a paragraph break**. CHANGELOG entry saying this catches more than before. | — |

**Red-first:** a fixture with `not\nmerely` across a line break, asserted to yield
one site. Fails today.

**Known edge, documented rather than engineered around:** `\s+` spans a blank
line, so a phrase whose first word ends a paragraph and whose second word opens
the next reports a site. Rare, and narrowing it costs a pattern nobody can read.

## Slice B — `repeated-sentence-openers`

Delivers: a metric for the tic of consecutive sentences opening on the same word.

| # | Task | Verify |
|---|---|---|
| B.1 | `measure.py`: `repeated_sentence_openers(text) -> float` — count `i` where `sents[i][0] == sents[i-1][0]`, normalised **per 1000 tokens**. Uses the existing token-list `text.sentences()`; no spans. | Hand-computed: 4 sentences, 2 consecutive repeats, 20 tokens → `100.00`. |
| B.2 | Register `"repeated-sentence-openers"` in `measure.METRICS`. | `rift stats` lists it; a `measure` rule resolves it. |
| B.3 | Discrimination test: a fixture with every sentence opening differently vs one built from repeats, asserting separation in the right direction. | Uniform → `0.0`; repetitive → strictly greater. |

Language-agnostic by construction — it compares tokens to tokens and knows no
vocabulary.

## Slice C — `as: sentence_start`

Delivers: `forbid` rules that fire only on sentence-initial occurrences.

| # | Task | Verify |
|---|---|---|
| C.1 | `text.py`: `paragraph_spans(text) -> [(start, end)]`, and `paragraphs()` reduced to `[text[s:e] for s, e in paragraph_spans(text)]`. | Existing paragraph tests pass **untouched**. Today's `"\n".join(current)` over consecutive lines is byte-identical to the slice. |
| C.2 | `text.py`: `_split_sentence_spans(text, base)` mirroring `_split_sentences`, and `sentence_spans(text) -> [(start, end)]` over the paragraph spans. `sentences()` reduced to token lists over those spans. | Existing sentence and metric tests pass **untouched**. |
| C.3 | `text.py`: `sentence_start_offsets(text) -> set[int]` — the offset of the **first word character** of each sentence span, since a span may open on whitespace. | A sentence beginning mid-line yields its true offset, not the line start. |
| C.4 | `matcher.py`: `_pattern_for` returns the word pattern for `sentence_start` (so `find` does not bail on `None`); `find` filters matches to those whose `m.start()` is in `sentence_start_offsets(text)` — computed on the **masked** text, since that is what `find` scans and what `line_of` indexes. | — |
| C.5 | `matcher.py`: same branch in `_matches`, so `require`'s `as: sentence_start` works rather than silently reporting every entity missing. | — |
| C.6 | README: matcher table row, plus the false-site caveat next to it. | — |

**Red-first, and this is the test that matters:** a fixture with the entity
**mid-sentence only**, asserted to yield **zero** sites. A test that only asserts
the sentence-initial site is found passes against a plain `as: word`
implementation and proves nothing about this feature.

**Caveat to document, not fix:** splitting stays crude (`text._split_sentences`;
`Ph.D.` over-splits), so a spurious boundary yields a **false** site. It never
yields a missed one. That asymmetry goes in the README beside the matcher.

## Slice D — `permit`

Delivers: an allowlist rule reporting every prose token outside a declared set.

| # | Task | Verify |
|---|---|---|
| D.1 | `text.py`: `token_spans(text) -> [(offset, original)]` from the existing `_TOKEN.finditer` — **not** lowercased, since `of:` judges the source form. `tokens()` reduced to `[t.lower() for _, t in token_spans(text)]`. | Existing token and metric tests pass **untouched**. |
| D.2 | `matcher.py`: `unpermitted(root, allowed, permit) -> [(path, line, token)]`. Reads masked (`include_quotes` honoured). Skips `raw.isdigit()`. Applies `of:` to `raw`; membership on `raw.lower()` when `case_insensitive`, else `raw`. A malformed `of:` regex raises `ConfigError` → exit 2. | Three unknown tokens across two files → three sites. A year is never a site. A bad `of:` exits 2, not green. |
| D.3 | `cli.py`: `"permit"` into `RULE_KINDS`; **convert both dispatches to explicit branches** with a final `else: raise ConfigError` — see "The trap" above. | A rule carrying both `permit` and `forbid` exits 2 via `_rule_kind`. |
| D.4 | `cli.py`: `check_cmd` permit branch — sites, label `"unpermitted"`, same truncation as `forbid`. | Exit 1 on an error-severity permit rule with sites. |
| D.5 | `cli.py`: `list_cmd` permit branch — **unique tokens with counts, most frequent first**, not sites. This is what makes the first run against a real book triageable. | 5 occurrences of one unknown token and 1 of another → two rows, the 5 first. |
| D.6 | README: third rule kind in the shapes table, `permit` section, `of:` semantics. CHANGELOG. | — |

**Red-first:** a doc containing a token absent from the permitted set, asserted to
yield one site. Then the inverse: every token present → zero sites.

**Deliberately absent** (spec, Out of scope): no `exclude`, no `max_per_file`, no
`max_files`. The permitted set is the allowance.

**Decision made here, because the spec does not say it outright:** a malformed
`of:` regex is a `ConfigError`, **not** a swallowed exception. `matcher.find`
returns `[]` on `re.error`, which means a typo'd pattern makes a rule silently
green — the repo's own documented blind spot, and the one failure mode rift
cannot afford. A new rule kind is not bound by that choice, so `permit` fails
loudly instead. The existing behaviour of `find` is left alone; changing it is a
separate decision with existing configs behind it.

## Closing

| # | Task | Verify |
|---|---|---|
| E.1 | Mutation-test: `_matches` → `return True`; `unpermitted` → `return []`; the `sentence_start` filter → pass-through. | Suite goes red for each. A gate that cannot fail is the one bug rift cannot ship. |
| E.2 | Full suite green; `rift check` against `repos/books-tsoc` unchanged — 25 rules, same counts. Slice A is the only change that could move them. | Any moved count is investigated, not accepted. |
| E.3 | Bump `pyproject.toml`, `uv lock`, CHANGELOG section, tag `v0.4.0`. | `uv sync --locked` in CI fails on a stale lock — v0.2.0 shipped with it stale. |

**Not in this plan** (spec, Out of scope): wiring `permit` into `books-tsoc`. The
mechanism lands first; landing it with a thousand-token triage would make it
impossible to tell which of the two broke.
