# Writing rift rules

**When to reach for it:** you are authoring or tuning a `.rift.yaml` for a repo,
or a rule is reporting noise and you need to decide whether to narrow it or drop it.

## The bar a rule has to clear

A rule earns its place only if a failure means *someone must edit a document*. If
the honest response to a red line is "yeah, that's fine actually", the rule is
noise, and noise in a linter is worse than a missing check — it trains everyone to
run `check` and skim past the red.

So: **start with `severity: warning`, run `rift list` over the real repo, read
every ✗, and only promote to `error` once the list is empty for reasons you agree
with.** `rift list` is the tuning tool; `rift check` is the gate.

## Rules that carried their weight

Validated against the AInBox monorepo (2026-08-09 pilot, 5 rules, ~9 services).

**Roster rules.** Extract the keys of a mapping that *is* the roster — compose
`services`, a workspace member list — and require a `mention`. When someone adds a
service and forgets the docs, this is the rule that catches it. Highest signal of
anything tried.

**Inverse existence rules.** Extract file paths *out of the prose* with a `regex`
and require `exists: true`. This catches the opposite and more embarrassing drift:
docs describing files nobody ever wrote. In the pilot this found five compose
overlay files documented in `design.md` with none of them on disk — the single
most valuable finding of the run.

**Env-var coverage.** `env_names` from `.env.example` against `docs/**/*.md`. Ten
of fifteen variables were documented nowhere at all. This one tends to fail loudly
on first run because the doc it wants usually doesn't exist yet; that *is* the
finding.

**Version-pin coverage.** A `regex` capture over a `versions.env`-style file
against the BOM table, with `case_insensitive: true` (the file shouts in
`UPPER_SNAKE`, the table is prose). Catches components added to the build but not
to the bill of materials.

## Rules that looked good and weren't

**Ports.** Tempting and wrong. A compose file's `ports:` are *host* mappings,
while a doc's port table almost always describes the *internal* network — a repo
that exposes almost nothing to the host will fail a structural port rule on every
single row while its docs are perfectly correct. If you want port coverage at all,
extract from the docs and check a mention, never the reverse.

**Make targets.** Too many, too low-level, and they churn. A repo with forty
targets produces forty rows of noise to catch the two that matter.

The pattern behind both: **check the roster, not the wiring.** Rosters are small,
stable, and semantically meaningful; wiring is numerous, volatile, and its meaning
depends on context the linter cannot see.

## Choosing a matcher

`mention` is a plain substring with no word boundary, so short entity names
(`api`, `db`, `ui`) will pass against unrelated prose and give you a false green.
When the entity name is short, reach for `table_cell` — a BOM or roster table is
usually where you actually wanted it documented anyway, and the pipe delimiters
make the match precise.

Use `heading` / `heading_N` when your standard is "this thing has its own section",
not merely "this thing is named somewhere". That is a much stronger claim; expect
it to fail on things that are genuinely documented inside a table, and decide
which standard you meant.

## Where a rule's blind spot is

If the source file fails to parse, the extractor yields zero entities and the rule
reports **pass**. A rule pointed at a file that has been renamed or deleted is
therefore permanently, silently green. When you add a rule, confirm it fails first:
delete a line from the doc it checks and watch it go red. A rule you have never
seen fail is a rule you cannot trust.
