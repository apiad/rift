import sys
import click
import yaml
from pathlib import Path
from rich.console import Console

from .extractor import extract
from .matcher import check

console = Console()

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
    errors = warnings = 0

    console.print(f"\n[bold]rift check[/bold] — {root}\n")

    for rule in rules:
        severity = rule.get("severity", "error")
        entities = extract(root, rule["extract"])
        require = rule["require"]
        missing = sorted(e for e in entities if not check(root, e, require))

        if missing:
            color = "red" if severity == "error" else "yellow"
            icon = "✗" if severity == "error" else "⚠"
            console.print(f"[{color}]{icon}[/{color}]  {rule['name']}  [{color}][{len(missing)} missing][/{color}]")
            for m in missing[:6]:
                console.print(f"   {m}")
            if len(missing) > 6:
                console.print(f"   ... (+{len(missing) - 6} more)")
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

    for r in rules:
        if rule and rule.lower() not in r["name"].lower():
            continue
        entities = extract(root, r["extract"])
        require = r["require"]
        console.print(f"\n[bold]{r['name']}[/bold]  ({len(entities)} entities)")
        for e in sorted(entities):
            ok = check(root, e, require)
            icon = "[green]✓[/green]" if ok else "[red]✗[/red]"
            console.print(f"  {icon} {e}")


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
