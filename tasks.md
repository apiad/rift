# rift — tasks

## Open

### 🟠 An unparseable source file makes its rule pass silently (2026-08-10)

`extractor.extract` wraps every read in `except Exception: pass`. When the source
file is malformed — or has been renamed, or deleted — the extractor yields zero
entities, and a rule with zero entities reports **pass**. So a rule pointed at a
file that no longer exists is permanently, silently green, which is the one
failure mode a linter cannot afford: it licenses shipping.

Pinned as current behaviour by `test_unparseable_yaml_yields_nothing_instead_of_raising`
and listed under "Known gaps" in the README. Not fixed because it is a behaviour
change nobody asked for.

The fix is small: let the exception carry the filename and surface it as a rule
error distinct from "entities missing" — a rule whose *source* is broken should
fail loudly and differently from a rule whose *docs* are incomplete. Worth adding
a matching exit code, or at minimum a red line that says `could not read X`.

### 🟠 `mention` has no word-boundary option (2026-08-10)

`as: mention` is a plain substring test, so `api` is satisfied by `rapid` and
`db` by `sandbox-dbg`. Short entity names therefore produce false greens — the
linter says documented when nothing of the sort is in the doc.

Workaround today is to reach for `table_cell` or `heading` where precision
matters, which is what `know-how/writing-rules.md` recommends. The real fix is a
`word_boundary: true` option on `mention` (`mermaid_node` already does the
`\b`-wrapped thing internally, so the machinery exists).

**Superseded by `docs/prose-linting-design.md` (2026-08-26)**, which specifies it
as `as: word` — a matcher alongside `mention` rather than a flag on it, because
the `forbid` rule kind cannot work without word boundaries and needs to *require*
them rather than opt in. Implement it there, not here.

### 🔜 Not wired into any CI (2026-08-10)

Nothing runs `rift check` on a push, in this repo or in its one consumer. Until
it does, it only catches drift when somebody remembers to look — and the whole
argument for making the check mechanical and fast was that it could run
unattended.

Smallest useful step: a GitHub Actions job on `apiad/ainbox` that runs
`rift check` and fails the build on an error-severity rule. rift is not on PyPI,
so that job has to install it from git.

### 🔵 Repo is private — decide whether to publish (2026-08-10)

Created private on 2026-08-10 as the cautious default. There is nothing
Alex-specific in it: 250 lines, no credentials, no domain knowledge. If it goes
public, it wants a PyPI release too, since installing a linter from a git URL is
most of the friction in adopting one.

## Done

### ✅ Brought home from the VPS, tested and documented (2026-08-10)

Built autonomously on the VPS on 2026-08-09 and found the next morning living on
exactly one disk with no git remote at all, one commit, four `.pyc` files
committed, no `.gitignore`, no tests and no documentation of any kind.

Now `apiad/rift` (private): `main`, clean ignore rules, `uv.lock` pinned, README
with the full extractor/matcher reference, `AGENTS.md`, and
`know-how/writing-rules.md` carrying what the AInBox pilot taught about which
rule shapes carry their weight — those lessons had been sitting in a
`.playground` file on the VPS that any cleanup would have deleted.

### ✅ The `heading` matcher could never match a heading (2026-08-10, found by the new tests)

`rf'^#{1,6}\s+.*{esc}'` — inside an f-string, `{1,6}` is a replacement field, not
a regex quantifier. It evaluated to the tuple `(1, 6)` and compiled to
`^#(1, 6)\s+...`, which only matches the literal text `#1, 6 `. Every rule using
`as: heading` reported all of its entities as undocumented, in a tool whose
entire job is to be believed about exactly that.

Fixed in `d0047f1`. The general hazard is **regex built inside f-strings**: any
`{n,m}` quantifier has to be doubled, and nothing will tell you otherwise except
a test. `AGENTS.md` carries the warning.

### ✅ Test suite, mutation-verified (2026-08-10)

40 tests over every extractor, every matcher and the CLI exit codes. Deliberately
pins the behaviour that decides whether a linter can be trusted: which matchers
respect word boundaries and which are substring-permissive, that `heading_N` pins
an exact level, that `mermaid_node` only reads inside its fence.

Then mutation-tested, because a suite that cannot fail is worth less than none:
restore the heading bug, make `mention` always return true, let `mermaid_node`
ignore its fence, loosen the `env_names` pattern, make `check` never exit 1 —
five mutants, five killed.
