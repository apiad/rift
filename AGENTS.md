# AGENTS.md — rift

Read this before touching anything in this repo.

## What rift is

A documentation drift linter. Rules in `.rift.yaml` extract strings from code and
config (compose service names, env var names, version pins, directory names) and
assert each one is documented. `rift check` exits 1 when it isn't.

It is deliberately mechanical. It has no model of what your prose *means*; it
answers "does this string exist in the code but not in the docs" and nothing
else. Every proposal to make it smarter should be weighed against the thing that
makes it useful — that its output is boring, fast, and always literally true.

`README.md` is the full rule reference and is the doc to update when you change
an extractor or matcher.

## Language policy

**English. Everything.** Code, comments, identifiers, error strings, CLI help,
commit messages, tests, docs, know-how. No exceptions.

## Layout

```
src/rift/extractor.py   what to pull out of the codebase
src/rift/matcher.py     what counts as "documented" — and what is banned
src/rift/text.py        masking, tokens, sentences, and their spans
src/rift/measure.py     text in, numbers out
src/rift/cli.py         check / list / stats / init + exit codes
tests/                  one file per module
```

One concern per module, and each readable on its own. There is no line budget —
rift grows when it earns it. What must not degrade is the property that makes it
worth running: you can read the module behind any given rule and believe its
output.

## Public API

The functions worth knowing before you change anything. Everything else in these
modules is a private helper.

**`src/rift/extractor.py` — where a set of entities comes from.**

| Function | Contract |
|---|---|
| `extract(root, config) -> set[str]` | dispatches on the single extractor key in `config`. **Swallows every read error**, so a malformed or missing source yields the empty set — see the blind spot below. |
| `resolve_globs(root, patterns) -> list[Path]` | one glob or a list of them, deduplicated and sorted. Every `in:`, `file:` and `files:` goes through it. |

**`src/rift/matcher.py` — what counts as satisfied, banned, or unpermitted.**

| Function | Contract |
|---|---|
| `check(root, entity, require) -> bool` | *is it anywhere?* Returns as soon as it knows. Reads the document **unmasked** — `require` asks whether something is documented, and a code fence is documentation. |
| `find(root, entity, forbid) -> [(Path, int, str)]` | *where is it?* Visits every file and every occurrence, no early return. Reads **masked**. |
| `unpermitted(root, allowed, permit) -> [(Path, int, str)]` | *what is here that should not be?* Takes the **whole allowed set** and walks the document once — unlike the two above, which take one entity and are called once per extracted string. |

**`src/rift/text.py` — normalisation shared by the matcher and the metrics.**

| Function | Contract |
|---|---|
| `mask(text, include_quotes=False)` | **blanks, never deletes.** Offsets must keep indexing the original file or every reported line number is wrong. |
| `strip_patterns(text, patterns)` | blanks caller-supplied renderer markup. Same blanking contract. |
| `tokens` / `token_spans` | `\w+`, Unicode. `tokens` lowercases and drops offsets; `token_spans` keeps both, which is what `permit` needs. |
| `sentences` / `sentence_spans` / `sentence_start_offsets` | crude splitting on purpose. `sentence_start_offsets` gives the first *word* offset, not the span start. |
| `paragraphs` / `paragraph_spans` | runs of non-blank lines, block elements removed. |
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
that fails loudly — see the warning below.

## rift lints itself

`.rift.yaml` points rift at rift: eleven rules over its own API rosters, the paths
its docs name, and its own prose. `rift check` runs in CI beside the suite.

**If you add a rule kind, a matcher, an extractor key, an `expect` predicate or a
metric, a rule here fails until you document it.** That is the whole point — those
five rosters are extracted from the code that dispatches on them, so the config
cannot drift from the implementation without someone noticing.

Two of rift's own features are deliberately unused, and the config says why:
`measure`/`vs-siblings` needs four files in a set and there are two know-how docs,
and `permit` reads masked prose so it cannot see identifiers in backticks. Do not
add either to prove a point — a config that lies is worse than a thin one.

## The rule that matters most here

**A linter that cannot fail is worse than no linter**, because it licenses
shipping. Two consequences that are not negotiable in this repo:

1. **Every new extractor or matcher ships with a test that fails without it.**
   Not a test that passes — a test you have watched go red.
2. **After changing `matcher.py`, mutation-test the suite.** Break the matcher on
   purpose (make it `return True`) and confirm tests fail. The `heading` matcher
   shipped in v0.1.0 completely broken — `rf'^#{1,6}'` in an f-string compiles to
   `^#(1, 6)`, because `{1,6}` is a replacement field, not a quantifier — and no
   test existed to notice. That bug reported every entity as undocumented, in a
   tool whose entire job is to be believed about that.

Watch for this class generally: **regex built inside f-strings**. Any `{n,m}`
quantifier must be doubled (`{{1,6}}`), and there is nothing that will tell you
otherwise except a test.

## Testing

```bash
uv run pytest -q
```

Tests use a `repo` fixture (a `tmp_path` project root) and a `write` helper. Write
real files into a real temporary tree; do not mock the filesystem — the whole
program is filesystem behaviour, and a mocked test here would assert nothing.

## Know-how

- **[writing-rules](know-how/writing-rules.md)** — reach for it when authoring or
  tuning a `.rift.yaml`: which rule shapes carry their weight, which look good and
  produce only noise, and how to pick a matcher.
- **[measuring-prose](know-how/measuring-prose.md)** — reach for it before pointing
  `measure`/`expect` or `rift stats` at any body of writing. Chiefly: strip the
  renderer's markup or you are measuring apparatus density, not prose — a silent
  failure that promotes whichever chapter has the most glossary markers to your
  top outlier.

## Status

v0.3.0, with `v0.4.0` unreleased on `main`. Four rule kinds: `require` (does it
appear), `forbid` (where does it appear), `permit` (what appears that should
not), `measure`/`expect` (what is this number). Two real consumers —
`repos/ainbox/.rift.yaml` (5 rules) and `repos/books-tsoc/.rift.yaml` (25 rules,
which replaced ~450 lines of bespoke Python test code).

CI runs the suite on push and PR (3.11, 3.13); a `v*` tag runs `release.yml`,
which gates on the suite, checks the tag matches `pyproject.toml`, builds
sdist+wheel and publishes with the CHANGELOG section for that version.

**Releasing:** bump `pyproject.toml`, run `uv lock`, add the CHANGELOG section,
commit, then push an annotated `vX.Y.Z` tag. Everything after the tag is
automatic. Both workflows use `uv sync --locked`, so forgetting `uv lock` fails
the build rather than shipping — v0.2.0 was cut by hand with the lock stale at
`0.1.0` and nothing caught it.

Not on PyPI; installed on zion as an editable uv tool (`uv tool install
--editable`). Publishing to PyPI is a deliberate open question — see `tasks.md`.
