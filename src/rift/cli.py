import math
import re
import sys
import click
import yaml
from collections import Counter
from pathlib import Path
from statistics import mean, pstdev
from rich.console import Console
from rich.table import Table

from . import measure
from .extractor import extract
from .text import strip_patterns
from .matcher import check, find, resolve_globs, unpermitted

console = Console()

# The rule kinds. A rule carries exactly one; `extract` feeds all but `measure`,
# since where a set of strings comes from is orthogonal to what you assert
# about it.
RULE_KINDS = ("require", "forbid", "permit", "measure")


class ConfigError(Exception):
    """A rule that is malformed rather than failing."""


def _rule_kind(rule: dict) -> str:
    name = rule.get("name", "<unnamed>")
    present = [k for k in RULE_KINDS if k in rule]
    if not present:
        raise ConfigError(f"rule {name!r} carries none of: {', '.join(RULE_KINDS)}")
    if len(present) > 1:
        raise ConfigError(f"rule {name!r} carries more than one kind: {', '.join(present)}")
    return present[0]


def _kinds_or_exit(rules: list[dict]) -> list[str]:
    """Validate every rule up front, so a malformed config fails before any work."""
    try:
        return [_rule_kind(r) for r in rules]
    except ConfigError as e:
        console.print(f"[red]Config error:[/red] {e}")
        sys.exit(2)


def _occurrences(root: Path, rule: dict) -> list[tuple[Path, int, str]]:
    """The sites that violate a forbid rule.

    Plain `forbid` means zero tolerance. Two optional allowances generalise it
    without turning it into a counting rule — the report is still occurrences:

    - `max_per_file: N` — the first N in each file are allowed; report the rest.
      "Mark a glossary term only on first use in a chapter."
    - `max_files: N` — the entity may appear in at most N files; report the
      occurrences in the excess ones. "Never define a footnote label twice."

    Setting only `max_files` must not silently apply the zero-tolerance default
    per file, so the per-file cap goes to infinity unless it was asked for.
    """
    forbid = rule["forbid"]
    max_files = forbid.get("max_files")
    max_per_file = forbid.get("max_per_file")
    if max_per_file is None:
        max_per_file = math.inf if max_files is not None else 0

    sites = []
    for entity in sorted(extract(root, rule["extract"])):
        found = find(root, entity, forbid)

        by_file: dict[Path, list] = {}
        for site in found:
            by_file.setdefault(site[0], []).append(site)

        excess_files = set()
        if max_files is not None and len(by_file) > max_files:
            excess_files = set(sorted(by_file)[max_files:])

        for path, group in by_file.items():
            if path in excess_files:
                sites.extend(group)
            else:
                sites.extend(group[max_per_file:] if max_per_file != math.inf else [])

    sites.sort(key=lambda s: (str(s[0]), s[1], s[2]))
    return sites


def _values(root: Path, spec: dict) -> dict:
    """The metric value per file for a measure spec."""
    texts = {}
    for f in resolve_globs(root, spec.get("files", [])):
        try:
            texts[f] = f.read_text()
        except Exception:
            continue

    # Renderer markers are apparatus, not prose. Stripped before every metric,
    # so a chapter is not measured as different when only its markup differs.
    strip = spec.get("strip")
    if strip:
        texts = {f: strip_patterns(t, strip) for f, t in texts.items()}

    if "pattern" in spec:
        return {f: measure.pattern_count(t, spec["pattern"], spec.get("per")) for f, t in texts.items()}

    metric = spec.get("metric")
    if metric == "burrows-delta":
        return measure.burrows_delta(texts)
    fn = measure.METRICS.get(metric)
    if fn is None:
        raise ConfigError(f"unknown metric {metric!r}")
    return {f: fn(t) for f, t in texts.items()}


def _apply_expect(values: dict, expect: dict) -> tuple[list[tuple], list[str]]:
    """Return (failures, notes) where a failure is (path, value, why).

    No expect means report the number and pass — principle 2.
    """
    failures: list[tuple] = []
    notes: list[str] = []
    if not expect:
        return failures, notes

    for f, v in sorted(values.items()):
        if "min" in expect and v < expect["min"]:
            failures.append((f, v, f"below min {expect['min']}"))
        if "max" in expect and v > expect["max"]:
            failures.append((f, v, f"above max {expect['max']}"))

    k = expect.get("vs-siblings")
    if k is None:
        return failures, notes

    # Degenerate sets must not silently pass and must not fail — either would be
    # a lie about what was checked.
    if len(values) < 4:
        notes.append(
            f"set of {len(values)} is too small to judge against siblings "
            "(needs 4); reported, not judged"
        )
        return failures, notes

    for f, v in sorted(values.items()):
        others = [w for g, w in values.items() if g != f]
        m = mean(others)
        s = pstdev(others)
        if s == 0:
            # Siblings are identical. If this file matches them there is no
            # outlier; if it does not, it is maximally outlying — which is the
            # case the check most needs to catch, not a division to skip.
            if v != m:
                failures.append((f, v, f"differs from identical siblings ({m:.2f})"))
            continue
        z = abs(v - m) / s
        if z > k:
            failures.append((f, v, f"{z:.2f} sd from siblings (max {k})"))

    return failures, notes

STARTER_CONFIG = """\
rules:
  - name: "compose services → mention in docs"
    severity: error
    extract:
      file: "compose*.yml"
      yaml_keys: "services"
    require:
      in: "docs/**/*.md"
      as: mention
"""


@click.group()
def main():
    """rift — documentation linter"""


@main.command("check")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--config", "-c", default=".rift.yaml", help="Config file")
def check_cmd(path, config):
    """Run all rules and exit 1 on errors."""
    root = Path(path).resolve()
    config_path = Path(config) if Path(config).is_absolute() else root / config

    if not config_path.exists():
        console.print(f"[red]No config found at {config_path}[/red]")
        console.print("Run [bold]rift init[/bold] to scaffold one.")
        sys.exit(2)

    rules = yaml.safe_load(config_path.read_text()).get("rules", [])
    kinds = _kinds_or_exit(rules)
    errors = warnings = 0

    console.print(f"\n[bold]rift check[/bold] — {root}\n")

    for rule, kind in zip(rules, kinds):
        severity = rule.get("severity", "error")
        color = "red" if severity == "error" else "yellow"
        icon = "✗" if severity == "error" else "⚠"

        notes: list[str] = []
        if kind == "require":
            entities = extract(root, rule["extract"])
            missing = sorted(e for e in entities if not check(root, e, rule["require"]))
            failures = [str(m) for m in missing]
            label = "missing"
        elif kind == "forbid":
            sites = _occurrences(root, rule)
            failures = [f"{p.relative_to(root)}:{line}   {entity}" for p, line, entity in sites]
            label = "occurrences"
        elif kind == "permit":
            entities = extract(root, rule["extract"])
            try:
                sites = unpermitted(root, entities, rule["permit"])
            except re.error as e:
                console.print(
                    f"[red]Config error:[/red] in rule {rule['name']!r}: "
                    f"malformed of: pattern — {e}"
                )
                sys.exit(2)
            failures = [f"{p.relative_to(root)}:{line}   {token}" for p, line, token in sites]
            label = "unpermitted"
        elif kind == "measure":
            try:
                values = _values(root, rule["measure"])
            except ConfigError as e:
                console.print(f"[red]Config error:[/red] in rule {rule['name']!r}: {e}")
                sys.exit(2)
            out_of_bounds, notes = _apply_expect(values, rule.get("expect", {}))
            failures = [
                f"{path.relative_to(root)}   {value:.2f}   {why}"
                for path, value, why in out_of_bounds
            ]
            label = "out of bounds"
        else:
            # Unreachable while every kind in RULE_KINDS has a branch above, and
            # that is the point: `if/elif/else` with `measure` as the fallback is
            # how `list` came to raise KeyError on every measure rule. A fifth
            # kind must fail here, loudly, rather than be silently measured.
            console.print(
                f"[red]Config error:[/red] rule {rule['name']!r} has kind "
                f"{kind!r}, which has no handler"
            )
            sys.exit(2)

        for note in notes:
            console.print(f"[yellow]⚠[/yellow]  {rule['name']}  [yellow]{note}[/yellow]")

        if failures:
            console.print(
                f"[{color}]{icon}[/{color}]  {rule['name']}  "
                f"[{color}][{len(failures)} {label}][/{color}]"
            )
            for f in failures[:6]:
                console.print(f"   {f}")
            if len(failures) > 6:
                console.print(f"   ... (+{len(failures) - 6} more)")
            console.print()
            if severity == "error":
                errors += 1
            else:
                warnings += 1
        else:
            console.print(f"[green]✓[/green]  {rule['name']}")

    console.print()
    passes = len(rules) - errors - warnings
    console.print(
        f"{len(rules)} rules: [red]{errors} errors[/red] · "
        f"[yellow]{warnings} warnings[/yellow] · [green]{passes} pass[/green]"
    )

    if errors:
        sys.exit(1)


@main.command("list")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--config", "-c", default=".rift.yaml")
@click.option("--rule", "-r", default=None, help="Filter by rule name (substring)")
def list_cmd(path, config, rule):
    """Show extracted entities and their doc coverage."""
    root = Path(path).resolve()
    config_path = Path(config) if Path(config).is_absolute() else root / config

    if not config_path.exists():
        console.print(f"[red]No config found at {config_path}[/red]")
        sys.exit(2)

    rules = yaml.safe_load(config_path.read_text()).get("rules", [])
    kinds = _kinds_or_exit(rules)

    for r, kind in zip(rules, kinds):
        if rule and rule.lower() not in r["name"].lower():
            continue

        if kind == "require":
            entities = extract(root, r["extract"])
            console.print(f"\n[bold]{r['name']}[/bold]  ({len(entities)} entities)")
            for e in sorted(entities):
                ok = check(root, e, r["require"])
                icon = "[green]✓[/green]" if ok else "[red]✗[/red]"
                console.print(f"  {icon} {e}")
        elif kind == "forbid":
            # A banned entry that appears nowhere is not interesting: for
            # forbid, the occurrences *are* the report.
            sites = _occurrences(root, r)
            console.print(f"\n[bold]{r['name']}[/bold]  ({len(sites)} occurrences)")
            for path, line, entity in sites:
                console.print(f"  [red]✗[/red] {path.relative_to(root)}:{line}   {entity}")
        elif kind == "permit":
            # `check` reports sites; `list` reports vocabulary. The asymmetry is
            # the whole point: a first run against a real book emits sites in the
            # thousands, and a flat site list is untriageable where a
            # frequency-ranked vocabulary is a worklist.
            entities = extract(root, r["extract"])
            try:
                sites = unpermitted(root, entities, r["permit"])
            except re.error as e:
                console.print(f"[red]Config error:[/red] in rule {r['name']!r}: {e}")
                sys.exit(2)
            counts = Counter(token for _, _, token in sites)
            console.print(
                f"\n[bold]{r['name']}[/bold]  "
                f"({len(counts)} unpermitted, {len(sites)} occurrences)"
            )
            for token, n in counts.most_common():
                console.print(f"  [red]✗[/red] {token}   ({n})")
        elif kind == "measure":
            # For a measure rule the measured files are the entities, so the
            # per-entity report is every file's value — passing ones included,
            # since a number you can see beats a number you have to infer.
            values = _values(root, r["measure"])
            out_of_bounds, notes = _apply_expect(values, r.get("expect", {}))
            why: dict = {}
            for path, _, reason in out_of_bounds:
                why.setdefault(path, []).append(reason)

            console.print(f"\n[bold]{r['name']}[/bold]  ({len(values)} files)")
            for note in notes:
                console.print(f"  [yellow]{note}[/yellow]")
            for f, v in sorted(values.items()):
                icon = "[red]✗[/red]" if f in why else "[green]✓[/green]"
                reason = f"   {'; '.join(why[f])}" if f in why else ""
                console.print(f"  {icon} {f.relative_to(root)}   {v:.2f}{reason}")


@main.command("stats")
@click.argument("files")
@click.option("--path", "-p", default=".", type=click.Path(exists=True), help="Project root")
@click.option("--metric", "-m", default=None, help="Filter to metrics matching a substring")
@click.option("--strip", "-s", multiple=True, help="Regex of renderer markup to blank before measuring (repeatable)")
def stats_cmd(files, path, metric, strip):
    """Report the metric table for a file set.

    Never judges and always exits 0. This is the agent-facing surface: it is how
    you ask whether a chapter is unlike its siblings without anyone having
    written a rule first.
    """
    root = Path(path).resolve()
    spec = {"files": files, "strip": list(strip)}

    names = [n for n in measure.METRICS if not metric or metric in n]
    if not metric or metric in "burrows-delta":
        names.append("burrows-delta")

    columns = {}
    for name in names:
        columns[name] = _values(root, {**spec, "metric": name})

    paths = sorted({p for col in columns.values() for p in col})
    if not paths:
        console.print(f"[yellow]No files matched {files!r} under {root}[/yellow]")
        return

    table = Table(title=f"rift stats — {files}")
    table.add_column("metric", style="bold")
    for p in paths:
        table.add_column(p.relative_to(root).stem, justify="right")

    for name in names:
        table.add_row(name, *(f"{columns[name].get(p, 0.0):.3f}" for p in paths))

    console.print(table)


@main.command("init")
@click.argument("path", default=".", type=click.Path(exists=True))
def init_cmd(path):
    """Scaffold a starter .rift.yaml."""
    target = Path(path) / ".rift.yaml"
    if target.exists():
        console.print(f"[yellow]{target} already exists[/yellow]")
        return
    target.write_text(STARTER_CONFIG)
    console.print(f"[green]Created {target}[/green]")
