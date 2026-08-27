# Zone scoping — implementation plan

**Spec:** `docs/zone-scoping-design.md`
**Status:** not started.
**Target:** `v0.6.0`.

Six slices, cheapest first, each ending with rift able to do something end to end
from a `.rift.yaml`. Slice 0 changes no behaviour and unblocks everything after it.

## Global constraints

- **Every new behaviour ships with a test watched go red.** AGENTS.md,
  non-negotiable.
- **The vacuity rule.** Three features in a row have shipped with a fixture that
  could not distinguish the new behaviour from the old (`sentence_start`
  whitespace, `permit.strip` markers, the `stats` third of a test). For every
  test here, ask: *would this pass against an implementation that ignores the
  feature?* If yes, the fixture is wrong.
- **After touching `matcher.py`, mutation-test.** Break `_matches` to
  `return True` and confirm the suite goes red.
- **An unzoned rule must behave exactly as before.** The existing 238 tests
  passing untouched is the acceptance condition for every slice.
- English everywhere. Conventional commits. One slice per commit.

## One correction to the spec, found while planning

The spec says zone resolution is hoisted into `cli._occurrences`. **`_occurrences`
is `forbid`-only** — `permit` calls `matcher.unpermitted` directly from both
`check_cmd` and `list_cmd`, and `measure` goes through `_values`. Putting
resolution there would leave `permit` and `measure` to duplicate it.

So it goes in a shared helper, `cli._zoned_spans`, used by all three. Everything
else about the hoist stands: it sits above the per-entity loop, and it owns both
resolution and the one-entry-per-file reporting.

## Main stays honest between slices

A well-formed `zone:` that validates but is not yet wired would lint the whole
file and report ✓ — a rule that cannot fail, on `main`, in a repo whose stated
ethos is that such a rule is worse than none. The window is real: `zone_spans`
exists after slice 1 and is consumed only in slices 3 and 4.

So `_validate_zone` **rejects `zone:` on any kind whose slice has not landed**, and
each rejection is deleted as its slice arrives (task 2.1b). That keeps the commits
small and every intermediate state truthful, which squashing slices 1–3 into one
commit would also achieve but at the cost of the review boundaries.

## Slice 0 — prerequisites, no behaviour change

Delivers: the two blockers cleared, with the suite byte-identical.

| # | Task | Verify |
|---|---|---|
| 0.1 | Move `_H2` from `measure.py` to `text.py`; `measure` imports it from there. `text` imports nothing local and is the base of the module graph, so the reverse is a circular import that fails at load. | Full suite passes untouched. `python -c "import rift.cli"` succeeds. |
| 0.2 | `cli.list_cmd`'s `measure` branch wraps `_values`/`_apply_expect` in the same `try/except ConfigError` `check_cmd` uses, exiting 2. | New test: a config with `metric: nonexistent` exits 2 under **both** `check` and `list`. Today `list` tracebacks. |

**Why 0.2 is here and not later:** three new `ConfigError`s arrive in slice 2. Adding
them to a command that has no handler doubles an existing hole rather than using one.

## Slice 1 — zone resolution

Delivers: `text.zone_spans`, unit-tested, wired to nothing.

| # | Task | Verify |
|---|---|---|
| 1.1 | `text.section_spans(text) -> [(start, end)]` using the relocated `_H2`. Text before the first `##` is zone 0. | Hand-computed: a doc with a `#` title, two `##` sections → 3 spans, the first ending at the first `##`. |
| 1.2 | `text.zone_spans(text, zone) -> [(start, end)]`. Structural form dispatches on `unit` to `paragraph_spans`/`section_spans` then applies `index` with Python semantics. | `index: [-1]` on a 3-zone fixture returns the third, not the first. |
| 1.3 | Delimited form: first match of `after` and of `before`, region **excludes** both matches, returns `[]` when either pattern misses or start ≥ end. | Five cases: both bounds, `after` only, `before` only, an inverted pair returning `[]`, and a banned word sitting **inside** the `after` match not falling in the region. |

**Red-first for 1.2:** a three-zone fixture with distinguishable content, asserting
`index: [-1]` returns the third. A single-zone fixture cannot tell an off-by-one
from a correct implementation.

**`zone_spans` returns `[]` for unresolvable** rather than raising — the caller
distinguishes "no zone" from "empty selection" and does the reporting.

## Slice 2 — validation, up front

Delivers: every malformed zone exits 2 before any rule runs.

| # | Task | Verify |
|---|---|---|
| 2.1 | `cli._validate_zone(rule, kind)` raising `ConfigError`, called from `_kinds_or_exit`. Rejects: both forms in one zone; `zone` on `require`; `zone` beside `require.exists`; `metric:` not in the allowlist with a zone; `per:` with a zone; **`expect.vs-siblings` with a zone**. | One test per rejection, each asserting exit 2 **and** that the message names the rule. |
| 2.1b | **Staged rejection:** `_validate_zone` also rejects `zone:` on any kind whose slice has not landed yet, and the rejection for that kind is deleted as its slice arrives. | After slice 2, a well-formed `zone:` on a `forbid` rule exits 2 rather than being silently ignored. |
| 2.4 | `_apply_expect`'s degenerate-set guard counts **distinct files**, not entries. | A 3-file corpus with 5 sections each is 15 zoned values; the guard must still fire, because the set is really three documents. |
| 2.2 | The allowlist is `_ZONE_SAFE_METRICS = {"word-count"}`, plus `pattern:` which is not a metric. | `metric: word-count` + zone is **accepted**; `metric: sentence-length-cv` + zone exits 2; `metric: burrows-delta` + zone exits 2. |
| 2.3 | Validation runs in `_kinds_or_exit`, whose docstring already promises a malformed config fails "before any work". | A config whose **twentieth** rule has a bad zone prints **no** rule results before exiting 2. |

**Two guards, not one, and this was a real hole.** The spec moved the guard from
`vs-siblings` to `metric:` and called that strictly stronger. It is not a superset:
it catches `burrows-delta` and the statistical metrics, and **misses a zoned
`pattern:` count with `vs-siblings`**, because `pattern:` is not a `metric:`. That
config would validate, run, and compare each `(file, zone)` against every other —
mixing "other zones of this file" with "the same zone in other files" into a third
meaning nobody chose, which is the exact ambiguity the spec refuses to resolve
silently. Both rejections are required.

**2.2 is pinned from both sides deliberately.** Asserting only the rejections
passes against a blanket ban, which would silently drop the `word-count` case the
allowlist exists to serve.

**2.3's test is the one that pins the placement.** An exit-code-only test passes
against a mid-run raise; asserting no output precedes it is what proves it validated
up front.

## Slice 3 — `forbid` and `permit`

Delivers: zoned bans reporting `file:line` sites.

| # | Task | Verify |
|---|---|---|
| 3.1 | `cli._zoned_spans(root, docs, zone, include_quotes) -> (dict[Path, list], list[Path])` — resolved spans per file, plus the unresolved files. Masks, resolves, does **not** strip. | A file whose `after:` pattern is absent lands in the unresolved list, not the spans dict. **And**: a rule whose `strip:` targets its own bound pattern still resolves — ordering the strip first makes every zone unresolvable, and that fixture is the only thing that catches it. |
| 3.2 | `matcher.find` and `matcher.unpermitted` take `spans: dict[Path, list] \| None`. `None` means no zone. A site counts only if **fully contained**: `s <= m.start() and m.end() <= e`. Files absent from a non-`None` dict are skipped. | A multi-word entity straddling a zone edge is **not** a site. Start-offset-only containment reports it. |
| 3.3 | **`_occurrences` changes its return type** to `(sites, unresolved: list[Path])`. Both callers render the two separately — sites keep `f"{p}:{line}   {entity}"`, unresolved files render `f"{p}   zone matched nothing"`. The `permit` branches do the same around `_zoned_spans`. | A rule with 3 entities over 2 unresolved files yields **2** failure entries, not 6, and none of them carries a `:0`. |
| 3.4 | In `check_cmd` the unresolved entries join `failures`, so they carry the rule's severity and the kind's existing label. **In `list_cmd` they print as a yellow line and change nothing else** — `list` reports, it never judges, and its `permit` branch renders a frequency worklist with no site list to attach a failure to. | An `error` rule with an unresolvable zone exits 1 under `check`; the same rule under `list` prints the line and exits 0. |

**The return-type change is the point of 3.3, not a side effect.** The spec claimed
`_occurrences` "already builds failures strings directly" and therefore needed no
new channel. It does not: it returns `list[tuple[Path, int, str]]` and both
`check_cmd` and `list_cmd` build the strings themselves, each formatting with
`:{line}`. So without this change the only way to carry an unresolved-zone entry is
a fake `:0` through the site tuple — the thing the spec rejects. Asserted, not
delivered, until here.

**Two things `_zoned_spans` must get right, both easy to "simplify" away:**

- **It must not strip.** `strip_patterns` blanks rather than deletes, so spans
  resolved before it stay valid against `unpermitted`'s stripped text. Folding the
  strip in reintroduces exactly the bug 3.1's fixture exists to catch.
- **An unreadable file is not an unresolvable zone.** Both `find` and
  `_zoned_spans` swallow read errors with `except Exception: continue`, so a file
  that cannot be read would otherwise be reported as `zone matched nothing`. Keep
  the two lists apart.

**Red-first for 3.2, and it is THE test:** a fixture with the banned entity
**outside** the zone only, asserting **zero** sites. A test that only asserts the
in-zone hit passes against an implementation that ignores `zone:` entirely.

**Red-first for 3.3:** the multi-entity fixture above. A single-entity fixture
cannot distinguish one-per-file from one-per-entity, and the failure mode it hides
is 12,330 identical entries burying every real finding.

## Slice 4 — `measure`

Delivers: `bold at most once per section`, and `the opening paragraph is 45–70 words`.

| # | Task | Verify |
|---|---|---|
| 4.1 | `_values` gains a **zoned path only**: mask → resolve zones → slice → `strip_patterns` → count. The unzoned path keeps reading raw text exactly as today. | Unzoned metric values are byte-identical before and after. A zoned `unit: section` does **not** split on a `##` inside a code fence. |
| 4.2 | Zoned keys become `(Path, zone_index)`; unzoned stay `Path`. | Both shapes round-trip through `_apply_expect`. |
| 4.3 | Update every consumer of a `_values` key: `check_cmd:235`, `list_cmd:349`, `stats_cmd:383`, and `_apply_expect`. Rendered as `chapters/ch01.md#3`. | A zoned rule's failure line renders the path **and** the zone in `check` and `list`. |
| 4.4 | Unresolved zones in `_values` report like slice 3's, one entry per file. | Same multi-file assertion. |

**4.1's fence test is the one that would otherwise ship silently.** Resolving on
raw text splits `unit: section` on a `##` inside a fence — the exact failure
`measure.py`'s module docstring says it avoids — and passes any fixture without a
fence, so the fixture must contain one.

**`stats` is unaffected.** `stats_cmd` builds `{"files": files, "strip": list(strip)}`
from CLI flags with no config and no zone key, so it cannot produce a zoned key.
4.3 touches its `relative_to` call for the unzoned shape only; no `stats` test
asserts a zoned key, because none can exist.

## Slice 5 — docs and release

| # | Task | Verify |
|---|---|---|
| 5.1 | README: a `zone:` section under Prose rules — both forms, the exact-counts-vs-statistics rule, the index-less trap, the `include_quotes` interaction, and why `require` is excluded. | `rift check` on rift stays green; the new keys reach the docs. |
| 5.2 | Mutation pass: make the containment filter pass through; make `zone_spans` ignore `index`; make `_values` skip masking. | Suite goes red for each. A gate that cannot fail is the one bug rift cannot ship. |
| 5.3 | CHANGELOG section; bump `pyproject.toml` to `0.6.0`; `uv lock`; update the AGENTS.md Status line. | `uv sync --locked` passes. rift's own version rule catches AGENTS.md if it is missed. |
| 5.4 | **New self-lint rule** in `.rift.yaml`: extract the zone sub-keys from wherever `_validate_zone` names them (`regex: 'zone\.get\("([a-z]+)"'` or equivalent) and `require` each `as: table_cell` in the README. Same shape as the five existing roster rules. | Deleting the `index` row from the README turns `rift check` red. Watch it fail before trusting it. |
| 5.5 | Tag `v0.6.0`. | Release workflow green, including its `rift lints itself` step; verify by installing the published wheel and running a zoned rule through it. |

**5.1's justification in the first draft was false, and I checked all eleven rules.**
rift's self-lint extracts rule kinds, matchers, extractor keys, `expect`
predicates, metric names, CLI commands, module paths, doc paths and the version.
`zone` and its sub-keys match **none** of them, and `_ZONE_SAFE_METRICS` lives in
`cli.py` where the metric rule cannot see it. The README section is, as far as the
build is concerned, genuinely optional — the opposite of what was claimed.

Which is why 5.4 exists. The repo's own rule is that if a check can be a script it
must not be a doc rule, so the fix is a self-lint rule rather than a promise to
remember.

## Not in this plan

- **`per_file:` for `require`**, and therefore `zone:` on `require`. Separate
  feature, separate evidence — see the spec.
- **Sliding windows with a run-length condition.** A different shape wearing a
  zone's clothes.
- **Wiring zones into any book's config.** `enciclopedia`, `books-mhai` and
  `books-codex` all want rules that need this, and all three are their own work.
  Landing the primitive and a book's first config together would make it
  impossible to tell which one broke.
