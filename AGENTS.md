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
src/rift/extractor.py   what to pull out of the codebase  (~80 lines)
src/rift/matcher.py     what counts as "documented"       (~55 lines)
src/rift/cli.py         check / list / init + exit codes  (~117 lines)
tests/                  40 tests, one file per module
```

One concern per module, and each module readable on its own. There is no line
budget — rift grows when it earns it. What must not degrade is the property that
makes it worth running: you can read the module behind any given rule and believe
its output.

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

## Status

v0.1.0. One real consumer: `repos/ainbox/.rift.yaml` (5 rules). Not on PyPI, not
wired into any CI. The natural next steps are a word-boundary option for
`mention` and making an unparseable source file a loud failure instead of a silent
pass — both listed under "Known gaps" in the README.
