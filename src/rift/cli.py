import sys
import click
import yaml
from pathlib import Path
from rich.console import Console

from .extractor import extract
from .matcher import check, find

console = Console()

# The rule kinds. A rule carries exactly one; `extract` feeds the first two,
# since where a set of strings comes from is orthogonal to what you assert
# about it.
RULE_KINDS = ("require", "forbid")


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
    sites = []
    for entity in sorted(extract(root, rule["extract"])):
        sites.extend(find(root, entity, rule["forbid"]))
    sites.sort(key=lambda s: (str(s[0]), s[1], s[2]))
    return sites

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

        if kind == "require":
            entities = extract(root, rule["extract"])
            missing = sorted(e for e in entities if not check(root, e, rule["require"]))
            failures = [str(m) for m in missing]
            label = "missing"
        else:
            sites = _occurrences(root, rule)
            failures = [f"{p.relative_to(root)}:{line}   {entity}" for p, line, entity in sites]
            label = "occurrences"

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
        else:
            # A banned entry that appears nowhere is not interesting: for
            # forbid, the occurrences *are* the report.
            sites = _occurrences(root, r)
            console.print(f"\n[bold]{r['name']}[/bold]  ({len(sites)} occurrences)")
            for path, line, entity in sites:
                console.print(f"  [red]✗[/red] {path.relative_to(root)}:{line}   {entity}")


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
