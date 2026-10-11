# rift

A documentation drift linter. Rules in `.rift.yaml` extract strings from code and
config (compose service names, env var names, version pins, directory names, tool
names) and assert each one is documented, or banned, or measured. `rift check`
exits 1 when one isn't. It is for any repo whose docs make claims about its own
code, and for the CI job and the agent that keep those claims true.

This file changes when the goals change. Nothing in it should be made false by a
commit that adds code or content.

## What done means

- `uv run pytest -q` and `uv run rift check .` both pass. CI runs both on every
  push and PR, and the release workflow runs them again before publishing.
- A change to what a rule can say (a rule kind, matcher, extractor key, `expect`
  predicate, metric or `zone` sub-key) updates `README.md`, the rule reference.
  rift's own rules fail until it does.
- New behaviour ships with a test you watched fail without it. `DESIGN.md` says
  why that rule is not negotiable here.
- English everywhere: code, comments, error strings, CLI help, commits, tests and
  docs.

## Where everything lives

| What | Where |
|---|---|
| What rift does for a user, every key and matcher | `README.md` |
| How the modules divide the work, their contracts, the rules and their reasons | `DESIGN.md` |
| One procedure per job, with its traps | `know-how/` |
| Every mechanical check, each with its reason in a comment | `.rift.yaml`, `.github/workflows/` |
| What changed in each release | `CHANGELOG.md` |
| Open work and its analysis | `tasks.md`, GitHub issues |
| Dated design specs and plans from earlier features | `docs/` |

## Working here

```bash
uv run pytest -q                       # the suite
uv run rift check .                    # rift lints its own docs
grep -m1 -H '^when:' know-how/*.md     # the know-how menu
```

Read the know-how doc whose `when:` matches the job before starting it.
