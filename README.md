# rift

A documentation drift linter. You declare facts that live in your code and config —
compose services, env vars, version pins, directory names — and assert that each one
appears in your docs. `rift check` exits 1 when something isn't documented.

It does not read your prose for meaning. It answers one narrow question, mechanically:
**does this thing exist in the codebase but not in the docs?** (Or, inverted: does this
doc name a file that isn't on disk?) That narrowness is the point — it makes the check
cheap enough to run in CI and boring enough to trust.

## Install

```bash
uv sync
uv run rift --help
```

## Quickstart

```bash
rift init          # scaffold a starter .rift.yaml
rift check         # run every rule; exit 1 if any error-severity rule fails
rift list          # per-entity ✓/✗ breakdown — use this to tune a noisy rule
```

`rift check` and `rift list` take an optional project root (default `.`) and
`-c/--config` (default `.rift.yaml`, resolved relative to the root).
`rift list -r <substring>` filters to matching rule names.

**Exit codes:** `0` all rules pass, or only warnings failed · `1` at least one
error-severity rule failed · `2` no config file found.

## Config

`.rift.yaml` is a list of rules. Each rule **extracts** a set of strings from the
codebase and **requires** each one to show up somewhere.

```yaml
rules:
  - name: "compose services → mention in design.md"
    severity: error          # error (default) fails the build; warning only reports
    extract:
      file: "compose*.yml"
      yaml_keys: "services"
    require:
      in: "docs/design.md"
      as: mention
```

### Extractors

Exactly one per rule. `files` and `dirs_with` stand alone; the rest need a `file:` glob.

| Key | Yields |
|---|---|
| `file: <glob>` | Selects the source files for the four extractors below. Globbed from the project root — **not recursive** unless you write `**`. |
| `yaml_keys: <a.b.c>` | The keys of the mapping at that dotted path. `services` on a compose file gives you the service roster. |
| `yaml_values: <a.b.c>` | The values of the mapping, or the items of the list, at that path. |
| `env_names: true` | Variable names matching `^[A-Z_][A-Z0-9_]*=`. Comments, blank lines, indented lines and lowercase names are skipped. |
| `regex: <pattern>` | Capture group 1 if the pattern has one, otherwise the whole match. Compiled with `MULTILINE`, so `^` and `$` anchor per line. |
| `files: <glob>` | The *stem* of each matching file (`apps/one.py` → `one`). Standalone. |
| `dirs_with: <glob>` | The parent directory name of each matching file (`apps/alpha/Dockerfile` → `alpha`). Recursive; skips `.git`, `.venv`, `__pycache__`, `node_modules`, `.playground`. Standalone. |

### Matchers

`require.as` decides what "documented" means. `require.in` is the doc glob
(default `docs/**/*.md`); the entity passes if **any** matching file satisfies it.

| `as:` | Passes when the entity… |
|---|---|
| `mention` (default) | appears anywhere as a **plain substring**. No word boundary — `api` is satisfied by `rapid`. Permissive by design. |
| `heading` | appears in a heading of any level (`#`–`######`). |
| `heading_N` | appears in a heading of exactly level N. `heading_2` matches `##` and rejects `#` and `###`. |
| `table_cell` | appears inside a single `\|` … `\|` cell on one line. |
| `mermaid_node` | appears as a whole word inside a ` ```mermaid ` fence. Occurrences outside the fence don't count. |

`require.exists: true` is the inverse rule and ignores `in`/`as`: it treats each
extracted string as a path relative to the project root and passes if that path
exists. This is how you catch docs that describe files nobody ever wrote.

`require.case_insensitive: true` lowercases both the entity and the document before
matching. (`heading` and `heading_N` are already case-insensitive; the flag is a
no-op for them.)

An unrecognised `as:` value never matches, which surfaces as every entity being
reported missing.

## Known gaps

- **A source file that won't parse makes its rule pass silently.** The extractor
  swallows every exception, so malformed YAML yields zero entities, and zero
  entities is indistinguishable from "everything is documented". Pinned by
  `test_unparseable_yaml_yields_nothing_instead_of_raising`.
- **`mention` has no word-boundary option.** Short entity names produce false
  passes. Use `table_cell` or `heading` where precision matters.

## Development

```bash
uv run pytest -q
```

40 tests covering every extractor, every matcher, and the CLI exit codes.
