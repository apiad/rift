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

### 🔵 Repo is private — decide whether to publish (2026-08-10)

Created private on 2026-08-10 as the cautious default. There is nothing
Alex-specific in it: no credentials, no domain knowledge. If it goes
public, it wants a PyPI release too, since installing a linter from a git URL is
most of the friction in adopting one.

## Done

### ✅ rift lints rift (2026-08-27)

`.rift.yaml`, eleven rules, wired into CI beside the suite. Nine are `error`
(mechanical facts about this repo), two stay `warning` (prose taste).

Five of them extract a **roster the code dispatches on** — rule kinds from
`kind == "..."`, matchers from `as_type == "..."`, extractor keys, `expect`
predicates, metric names from `METRICS` — so adding one and forgetting the README
fails the build. Functions are deliberately not rostered: they are wiring, and
`know-how/writing-rules.md` says check the roster.

**Writing the config found two real bugs, which is the argument for dogfooding
that the books-tsoc pilot already made once.**

1. **`regex:` silently truncated a roster.** It took `group(1)` unconditionally,
   so an alternation — the normal way to extract a roster a codebase spells two
   ways — handed `None` to `.strip()` on the unmatched branch, and the
   `except Exception` around the per-file loop discarded every *remaining* match
   in that file. Not zero entities, which looks suspicious, but a partial roster
   reporting pass. The `expect` predicate rule needs exactly that alternation and
   could not have been written before the fix.
2. **`permit` had no `strip:`.** `[Enigma]{~encryption}` reported `encryption`,
   and a marker whose slug repeats its display text reported the name four times.
   Slug fragments are apparatus no dictionary should absorb.

**Two features are deliberately unused, and the config says why.**
`measure`/`vs-siblings` needs four files in a set and there are two know-how docs,
so the rule would sit permanently yellow. `permit` reads *masked* prose, so inline
code and fences are blank to it — every identifier in the README is in backticks,
which makes it structurally unable to see what it would be asked about. `require`
is the tool for API coverage, and that is exactly why `require` alone reads
unmasked. Forcing either one on would be a config that lies.

**Every rule was watched to fail before being trusted.** Dropping a matcher row,
dropping an `expect` predicate, renaming a module and falsifying the version each
turn their rule red; dropping one metric row turns CI red with exit 1. Nine green
on a first run is the shape of a config that asserts nothing.

The path-existence rule matches **backtick-delimited** paths only, because
`require` reads unmasked and an unscoped pattern also picks up illustrative paths
inside config examples. It found a dangling reference on its first run.

### ✅ CI, and releases gated on it (2026-08-26)

`ci.yml` on push/PR across 3.11 and 3.13; `release.yml` on a `v*` tag. The release
job runs the suite **before** publishing — a release workflow that skips the tests
would happily ship a red tag — then checks the tag matches `pyproject.toml`, builds
sdist+wheel, and publishes using the hand-written CHANGELOG section, falling back
to generated notes only when the section is missing. Idempotent on re-run.

Two things worth keeping:

- **`uv sync --locked` in both jobs is not housekeeping.** v0.2.0 was tagged by
  hand with `uv.lock` still pinned at `0.1.0`, so `uv sync --locked` was broken on
  the released tag and nothing noticed. The lock check is what makes the release
  reproducible.
- **The version guard was proven to fail before being trusted**, by running its
  script locally with a mismatched tag. So was the notes extractor, against the
  real CHANGELOG and against a tag with no section. A gate nobody has watched go
  red is not a gate.

Verified end to end by cutting v0.2.1 through the pipeline: run green, release
published, both artifacts attached, body taken from the CHANGELOG.

### ✅ Prose linting shipped and proven on a real consumer (2026-08-26)

`forbid` and `measure`/`expect` implemented (see the entry below for the design
notes), then taken to `repos/books-tsoc`, where eight rules replaced three
hand-written Python test files. Parity was proven before deleting anything: every
defect the old suite caught was injected into a throwaway copy and both suites
run. rift caught all nine and two the old suite missed.

**Writing the first real config found four bugs that unit tests had not.** This is
the argument for having a consumer, and it is worth repeating on the next feature:

1. `find()` compiled without `MULTILINE` while the `regex:` extractor used it, so
   `^---$` matched only at start-of-file. `check()` had the same gap one branch
   over.
2. `files:` yields bare *stems*, so four different `index.md` collapsed into one
   entity — dropping one from the build declaration still passed. Fixed with
   `paths:`.
3. `in:` accepted only one glob, and a real document set is several.
4. **Renderer markup was being measured as prose.** `[Tony Hoare]{~hoare-tony}`
   tokenised as "tony hoare hoare tony". The spec had called for stripping it;
   only `pattern_count` did. Fixed with `strip:`, and written up in
   `know-how/measuring-prose.md` because the failure is silent and plausible.

### ✅ Prose linting: `forbid` and `measure` rule kinds (2026-08-26)

rift went from one rule kind to three. `forbid` reports `file:line` for banned
words, phrases and regexes; `measure`/`expect` runs 14 stylometric metrics with
`min`/`max`/`vs-siblings` thresholds; `rift stats` reports the whole table and
never judges.

Design in `docs/prose-linting-design.md`, execution in
`docs/prose-linting-plan.md`. Two things worth remembering:

- **Masking blanks, it never deletes.** `forbid` reports line numbers, so an
  offset into the masked text has to still index the original file. A deleting
  stripper shifts every line after a code fence and silently reports the wrong
  one. Pinned by `test_masking_does_not_shift_line_numbers_of_later_prose`.
- **Masking applies to `forbid` and `measure`, never to `require`.** `require`
  asks whether something is *documented* and a code fence is documentation.

This closes the old word-boundary item: it shipped as `as: word`, a matcher
alongside `mention` rather than a flag on it, because `forbid` needs boundaries
by default rather than by opt-in. `mention` stays permissive — existing rules
depend on it.

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
