# Design — rift

This file changes when the architecture changes: how the modules divide the work,
the contracts between them, and the rules with their reasons. What rift does for a
user is in `README.md`; how to do a job here is in `know-how/`.

## What rift is not

rift has no model of what prose *means*. It answers "does this string exist in the
code but not in the docs", "where does this banned string appear", and "what is
this number", and nothing else. Every proposal to make it smarter should be weighed
against the thing that makes it useful: its output is boring, fast, and always
literally true.

## Components

```
src/rift/extractor.py   what to pull out of the codebase
src/rift/matcher.py     what counts as "documented", and what is banned
src/rift/text.py        masking, tokens, sentences, and their spans
src/rift/measure.py     text in, numbers out
src/rift/cli.py         check / list / stats / init + exit codes
```

One concern per module, and each readable on its own. There is no line budget;
rift grows when it earns it. What must not degrade is the property that makes it
worth running: you can read the module behind any given rule and believe its
output.

## Module contracts

The functions worth knowing before you change anything. Everything else in these
modules is a private helper.

**`src/rift/extractor.py` — where a set of entities comes from.**

| Function | Contract |
|---|---|
| `extract(root, config) -> set[str]` | dispatches on the single extractor key in `config`. **Swallows every read error**, so a malformed or missing source yields the empty set — the first entry under Known gaps in the README. |
| `extract_with_sites(root, config) -> [(str, Path, int)]` | the site-preserving mirror of `extract`. Yields one triple per **occurrence** (not per value), so a value repeated in one file appears twice. `list:` yields `[]` — a literal list has no source to point at, and the CLI rejects the shape. Per-file extractors (`paths`, `files`, `yaml_keys`, `yaml_values`) report line 1. `unique` is the sole consumer. |
| `substitutions(config) -> [(Pattern, str)]` | the compiled `sub:` pairs, in the order they apply. Raises `ValueError` on a malformed shape and `re.error` on a bad pattern or replacement; the CLI calls it at validation time so a typo exits 2 before any rule runs. `extract` and `extract_with_sites` both apply it to every value. |
| `resolve_globs(root, patterns) -> list[Path]` | one glob or a list of them, deduplicated and sorted. Every `in:`, `file:` and `files:` goes through it. |

**`src/rift/matcher.py` — what counts as satisfied, banned, or unpermitted.**

| Function | Contract |
|---|---|
| `check(root, entity, require) -> bool` | *is it anywhere?* Returns as soon as it knows. Reads the document **unmasked** — `require` asks whether something is documented, and a code fence is documentation. Takes no zone; see the README for why. |
| `find(root, entity, forbid, spans=None) -> [(Path, int, str)]` | *where is it?* Visits every file and every occurrence, no early return. Reads **masked**. |
| `unpermitted(root, allowed, permit, spans=None) -> [(Path, int, str)]` | *what is here that should not be?* Takes the **whole allowed set** and walks the document once — unlike the two above, which take one entity and are called once per extracted string. |
| `duplicates(sites, scope) -> [[(str, Path, int)]]` | *what appears twice?* Consumes `extract_with_sites` output. `scope='across-files'` groups values that span more than one file; `scope='within-file'` groups values that repeat inside one file. Unknown scope raises. |
| `contain_gaps(root, spec, spans=None) -> ([(Path, int, str)], [Path])` | *does every zone match?* Walks each zone in scope; a zone whose body does not match `spec['matches']` is an offender (path, zone-index, first-heading-line). Empty zones and `where_heading_not` hits are skipped. Files whose `zone:` resolves to nothing come back in the second list. |

`spans` is a rule's resolved `zone:`, precomputed **once per file** by the caller
and passed down. `None` means the rule has no zone; a dict means a file absent
from it is not scanned. It is precomputed because `find` runs once per extracted
entity, so resolving inside it would emit one unresolved-zone report per entity
per file — 411 glossary terms over 30 chapters is 12,330 identical failures from
one broken bound. A site counts only if **fully contained** in a span.

**`src/rift/text.py` — normalisation shared by the matcher and the metrics.**

| Function | Contract |
|---|---|
| `mask(text, include_quotes=False)` | **blanks, never deletes.** Offsets must keep indexing the original file or every reported line number is wrong. |
| `strip_patterns(text, patterns)` | blanks caller-supplied renderer markup. Same blanking contract. |
| `tokens` / `token_spans` | `\w+`, Unicode. `tokens` lowercases and drops offsets; `token_spans` keeps both, which is what `permit` needs. |
| `sentences` / `sentence_spans` / `sentence_start_offsets` | crude splitting on purpose. `sentence_start_offsets` gives the first *word* offset, not the span start. |
| `paragraphs` / `paragraph_spans` | runs of non-blank lines, block elements removed. |
| `section_spans(text)` | the text split at every `##`, contiguous and gapless. The preamble is zone 0, emitted even when empty. |
| `zone_spans(text, zone)` | the single place either `zone:` form is interpreted. Takes **already-masked** text. Returns `[]` for a zone this document cannot resolve — the empty list is the signal, not an exception, because the caller has to tell "no zone" from "empty selection". |
| `line_of(text, pos)` | 1-indexed line for an offset. |


The `*_spans` functions are the primitives; the string and token versions are thin
wrappers over them. **Change a span function and the metrics move** — the metric
suite passing untouched is the acceptance condition for any edit here.

**`src/rift/measure.py` — text in, numbers out.** Pure functions, no filesystem.
`METRICS` maps every documented metric name to its function; `burrows_delta` is
separate because it needs the whole file set rather than one document.

**`src/rift/cli.py` — the commands and the exit codes.** `RULE_KINDS` is the
roster of rule kinds; `_rule_kind` rejects a rule carrying more than one. Both
`check_cmd` and `list_cmd` dispatch on kind **explicitly**, with a final `else`
that fails loudly; the comment on that `else` in `check_cmd` says why.

`_kinds_or_exit` validates every rule before any of them runs, which is what its
docstring promises and what `_validate_zone` relies on: a typo in rule twenty
must not cost nineteen rules of work and nineteen printed results first.

Two return types are pairs rather than lists, and in both cases the second half
is the files whose zone matched nothing. `_occurrences` returns
`(sites, unresolved)` because both callers format a site as `{path}:{line}`, so
carrying an unresolved entry through the site tuple would mean inventing a fake
`:0`. `_values` returns `(values, unresolved)` and its keys are `Path` when the
spec is unzoned and `(Path, zone_index)` when it is not — `_key_path` and
`_render_key` are the two places that difference is handled.

## Rules

**A linter that cannot fail is worse than no linter**, because it licenses
shipping. Two consequences follow, and neither is negotiable here.

1. **Every new extractor or matcher ships with a test that fails without it.**
   Not a test that passes: a test you have watched go red.
2. **After changing `matcher.py`, mutation-test the suite.** Break the matcher on
   purpose (make it `return True`) and confirm tests fail. The `heading` matcher
   shipped in v0.1.0 completely broken: `rf'^#{1,6}'` in an f-string compiles to
   `^#(1, 6)`, because `{1,6}` is a replacement field, not a quantifier, and no
   test existed to notice. That bug reported every entity as undocumented, in a
   tool whose entire job is to be believed about that.

Watch for this class generally: **regex built inside f-strings**. Any `{n,m}`
quantifier must be doubled (`{{1,6}}`), and nothing will tell you otherwise
except a test.

**Tests write real files into a real temporary tree.** `tests/conftest.py` gives
every test a `repo` root and a `write` helper. Do not mock the filesystem: the
whole program is filesystem behaviour, and a mocked test here would assert nothing.

**rift lints itself, from the code that dispatches.** `.rift.yaml` extracts six
rosters (rule kinds, matchers, extractor keys, `expect` predicates, metrics and
`zone` sub-keys) from the code that dispatches on them, so adding one and
forgetting the README fails the build. Functions are wiring and are not rostered.
The reason behind each rule's shape, and the two features deliberately left
unused, are in the comments of `.rift.yaml`.
