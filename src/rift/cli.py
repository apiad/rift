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
from .text import mask, strip_patterns, zone_spans
from .matcher import check, find, resolve_globs, unpermitted

console = Console()

# The rule kinds. A rule carries exactly one; `extract` feeds all but `measure`,
# since where a set of strings comes from is orthogonal to what you assert
# about it.
RULE_KINDS = ("require", "forbid", "permit", "measure")

# A zoned `measure` takes exact counts, not statistics. The line is that a count
# over a span is as correct as a count over a file, where a ratio, a coefficient
# of variation, an autocorrelation or a mean all go wrong at zone length. Other
# exact counts (`sections`, `opening-paragraphs`) join this set when a real rule
# needs them — not before. `pattern:` is exact too, and is not a metric.
_ZONE_SAFE_METRICS = {"word-count"}

_ZONE_UNITS = ("paragraph", "section")


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


def _validate_zone(rule: dict, kind: str) -> None:
    """Reject a malformed or unsupported `zone:` before any rule runs.

    Shape first, then the three semantic bans the design argued for: `require`
    cannot take a zone at all, a zoned `measure` takes exact counts only, and a
    zoned count may not be compared against siblings.
    """
    name = rule.get("name", "<unnamed>")
    spec = rule.get(kind)
    if not isinstance(spec, dict) or "zone" not in spec:
        return
    zone = spec["zone"]
    if not isinstance(zone, dict):
        raise ConfigError(f"rule {name!r}: zone: must be a mapping")

    # `check` returns a bool and early-returns on the first file that matches:
    # it is existential over the document set. A zone narrows *where in a file*
    # the search happens, so it cannot turn any of the per-file claims that
    # wanted it into something `require` can answer.
    if kind == "require":
        raise ConfigError(
            f"rule {name!r}: zone: is not available on require — `check` is "
            "existential over the file set, so a zone cannot express a per-file "
            "claim; it unlocks when per_file: does"
        )

    unknown = set(zone) - {"unit", "index", "after", "before"}
    if unknown:
        raise ConfigError(
            f"rule {name!r}: unknown zone key(s) {', '.join(sorted(unknown))}"
        )

    structural = "unit" in zone or "index" in zone
    delimited = "after" in zone or "before" in zone
    if structural and delimited:
        raise ConfigError(
            f"rule {name!r}: zone: carries both forms — use unit/index or "
            "after/before, not both"
        )
    if not structural and not delimited:
        raise ConfigError(
            f"rule {name!r}: zone: needs a unit: or a bound (after:/before:)"
        )

    if structural:
        unit = zone.get("unit")
        if unit not in _ZONE_UNITS:
            raise ConfigError(
                f"rule {name!r}: zone unit {unit!r} is not one of: "
                f"{', '.join(_ZONE_UNITS)}"
            )
        index = zone.get("index")
        if index is not None and (
            not isinstance(index, list) or not all(isinstance(i, int) for i in index)
        ):
            raise ConfigError(f"rule {name!r}: zone index: must be a list of integers")
    else:
        # A malformed bound would otherwise be swallowed by `find`'s
        # `except re.error`, which makes a typo'd pattern silently green.
        for key in ("after", "before"):
            if key in zone:
                try:
                    re.compile(zone[key])
                except re.error as e:
                    raise ConfigError(
                        f"rule {name!r}: malformed zone {key}: pattern — {e}"
                    ) from None

    if kind == "measure":
        if "pattern" not in spec:
            metric = spec.get("metric")
            if metric not in _ZONE_SAFE_METRICS:
                raise ConfigError(
                    f"rule {name!r}: metric {metric!r} cannot take a zone — a "
                    "zoned measure takes exact counts only "
                    f"({', '.join(sorted(_ZONE_SAFE_METRICS))}, or pattern:)"
                )
        if spec.get("per"):
            raise ConfigError(
                f"rule {name!r}: per: turns a zoned count into a ratio, which "
                "is a statistic — drop one of the two"
            )
        # Not caught by the metric guard above: `pattern:` is not a `metric:`,
        # so a zoned pattern count with vs-siblings would otherwise validate and
        # compare each (file, zone) against every other — mixing "the other
        # zones of this file" with "the same zone in other files".
        if rule.get("expect", {}).get("vs-siblings") is not None:
            raise ConfigError(
                f"rule {name!r}: vs-siblings cannot take a zone — with zones "
                "\"the siblings\" is ambiguous between the other zones of this "
                "file and the same zone in other files"
            )


def _kinds_or_exit(rules: list[dict]) -> list[str]:
    """Validate every rule up front, so a malformed config fails before any work."""
    try:
        kinds = []
        for r in rules:
            kind = _rule_kind(r)
            _validate_zone(r, kind)
            kinds.append(kind)
        return kinds
    except ConfigError as e:
        console.print(f"[red]Config error:[/red] {e}")
        sys.exit(2)


def _zoned_spans(root: Path, spec: dict) -> tuple[dict[Path, list] | None, list[Path]]:
    """The rule's zone resolved per file, plus the files it matched nothing in.

    `(None, [])` when the rule has no zone, so the matchers can tell "no zone"
    from "empty selection".

    Hoisted above the entity loop deliberately: `find` runs once per extracted
    string, so producing an unresolved-zone entry inside it would emit one per
    entity per file — 411 glossary terms over 30 chapters is 12,330 identical
    failures from a single broken bound, of which six print. One entry per
    (rule, file) instead.

    **Masks and resolves; does not strip.** The motivating delimited bound is a
    renderer macro, which is exactly what `strip:` is for, so stripping first
    would blank the bound before any zone could see it and make every zone in
    that rule unresolvable. `strip_patterns` blanks rather than deletes, so
    spans resolved before it still index the stripped text.

    An unreadable file is **not** an unresolvable zone: it is skipped entirely,
    the same way `find` skips it, rather than being blamed on the bound.
    """
    zone = spec.get("zone")
    if zone is None:
        return None, []

    spans: dict[Path, list] = {}
    unresolved: list[Path] = []
    for doc_file in resolve_globs(root, spec.get("in", "docs/**/*.md")):
        try:
            text = mask(doc_file.read_text(), spec.get("include_quotes", False))
        except Exception:
            continue
        found = zone_spans(text, zone)
        if found:
            spans[doc_file] = found
        else:
            unresolved.append(doc_file)
    return spans, unresolved


def _occurrences(root: Path, rule: dict) -> tuple[list[tuple[Path, int, str]], list[Path]]:
    """The sites that violate a forbid rule, and the files whose zone missed.

    Plain `forbid` means zero tolerance. Two optional allowances generalise it
    without turning it into a counting rule — the report is still occurrences:

    - `max_per_file: N` — the first N in each file are allowed; report the rest.
      "Mark a glossary term only on first use in a chapter."
    - `max_files: N` — the entity may appear in at most N files; report the
      occurrences in the excess ones. "Never define a footnote label twice."

    Setting only `max_files` must not silently apply the zero-tolerance default
    per file, so the per-file cap goes to infinity unless it was asked for.

    Returns two lists rather than one because an unresolvable zone has no line
    to report: smuggling it through the `(Path, int, str)` site tuple would mean
    inventing a fake `:0`, and both callers format that tuple as `{path}:{line}`.
    """
    forbid = rule["forbid"]
    max_files = forbid.get("max_files")
    max_per_file = forbid.get("max_per_file")
    if max_per_file is None:
        max_per_file = math.inf if max_files is not None else 0

    spans, unresolved = _zoned_spans(root, forbid)

    sites = []
    for entity in sorted(extract(root, rule["extract"])):
        found = find(root, entity, forbid, spans)

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
    return sites, unresolved


def _values(root: Path, spec: dict) -> tuple[dict, list[Path]]:
    """The metric value per key for a measure spec, and the files whose zone missed.

    Keys are `Path` for an unzoned spec and `(Path, zone_index)` for a zoned
    one, where the index is the position in the rule's own selection.

    The zoned path is a **separate** path on purpose. `_values` holds raw text
    and never masks — each metric masks its own input — so resolving a zone
    needs a masking pass this function does not otherwise have, and resolving
    on the raw text would split `unit: section` on a `##` inside a code fence.
    Confining the mask to zoned specs makes "an unzoned rule behaves exactly as
    before" true by construction rather than by luck. A zoned slice is masked
    twice, which is safe because `mask` only ever replaces with spaces and
    every one of its patterns needs a literal delimiter the first pass has
    already blanked.
    """
    zone = spec.get("zone")
    texts: dict = {}
    unresolved: list[Path] = []
    for f in resolve_globs(root, spec.get("files", [])):
        try:
            raw = f.read_text()
        except Exception:
            continue
        if zone is None:
            texts[f] = raw
            continue
        masked = mask(raw)
        spans = zone_spans(masked, zone)
        if not spans:
            unresolved.append(f)
            continue
        for i, (s, e) in enumerate(spans):
            texts[(f, i)] = masked[s:e]

    # Renderer markers are apparatus, not prose. Stripped before every metric,
    # so a chapter is not measured as different when only its markup differs.
    # After the zone, never before it: the bound is often a marker itself.
    strip = spec.get("strip")
    if strip:
        texts = {f: strip_patterns(t, strip) for f, t in texts.items()}

    if "pattern" in spec:
        values = {f: measure.pattern_count(t, spec["pattern"], spec.get("per"))
                  for f, t in texts.items()}
        return values, unresolved

    metric = spec.get("metric")
    if metric == "burrows-delta":
        return measure.burrows_delta(texts), unresolved
    fn = measure.METRICS.get(metric)
    if fn is None:
        raise ConfigError(f"unknown metric {metric!r}")
    return {f: fn(t) for f, t in texts.items()}, unresolved


def _print_unresolved(root: Path, unresolved: list[Path]) -> None:
    """`list`'s half of an unresolved zone: a yellow line and nothing else.

    Not a failure, because `list` reports and never judges — and its `permit`
    branch renders a frequency worklist with no site list to attach one to.
    """
    for p in unresolved:
        console.print(f"  [yellow]⚠[/yellow] {p.relative_to(root)}   zone matched nothing")


def _zone_failures(root: Path, unresolved: list[Path]) -> list[str]:
    """One entry per file whose zone matched nothing.

    Placed **before** the sites in the failure list: a declared zone that does
    not exist is a broken rule rather than a finding, and six sites would push
    it past the truncation and out of the report.
    """
    return [f"{p.relative_to(root)}   zone matched nothing" for p in unresolved]


def _key_path(key) -> Path:
    """The file a `_values` key names. Zoned keys are `(Path, zone_index)`."""
    return key[0] if isinstance(key, tuple) else key


def _render_key(root: Path, key) -> str:
    """`chapters/ch01.md`, or `chapters/ch01.md#2` for a zoned key.

    A value out of bounds in one section of a forty-section chapter is not a
    fact about the chapter, so the report has to say which zone it was.
    """
    rendered = str(_key_path(key).relative_to(root))
    return f"{rendered}#{key[1]}" if isinstance(key, tuple) else rendered


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
    # a lie about what was checked. Counted over **distinct files**: a zoned key
    # puts several entries on one file, and counting entries would judge a
    # two-file set against "siblings" that are its own other zones.
    files = {_key_path(f) for f in values}
    if len(files) < 4:
        notes.append(
            f"set of {len(files)} is too small to judge against siblings "
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
            sites, unresolved = _occurrences(root, rule)
            failures = _zone_failures(root, unresolved) + [
                f"{p.relative_to(root)}:{line}   {entity}" for p, line, entity in sites
            ]
            label = "occurrences"
        elif kind == "permit":
            entities = extract(root, rule["extract"])
            spans, unresolved = _zoned_spans(root, rule["permit"])
            try:
                sites = unpermitted(root, entities, rule["permit"], spans)
            except re.error as e:
                console.print(
                    f"[red]Config error:[/red] in rule {rule['name']!r}: "
                    f"malformed of: pattern — {e}"
                )
                sys.exit(2)
            failures = _zone_failures(root, unresolved) + [
                f"{p.relative_to(root)}:{line}   {token}" for p, line, token in sites
            ]
            label = "unpermitted"
        elif kind == "measure":
            try:
                values, unresolved = _values(root, rule["measure"])
            except ConfigError as e:
                console.print(f"[red]Config error:[/red] in rule {rule['name']!r}: {e}")
                sys.exit(2)
            out_of_bounds, notes = _apply_expect(values, rule.get("expect", {}))
            failures = _zone_failures(root, unresolved) + [
                f"{_render_key(root, key)}   {value:.2f}   {why}"
                for key, value, why in out_of_bounds
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
            sites, unresolved = _occurrences(root, r)
            console.print(f"\n[bold]{r['name']}[/bold]  ({len(sites)} occurrences)")
            _print_unresolved(root, unresolved)
            for path, line, entity in sites:
                console.print(f"  [red]✗[/red] {path.relative_to(root)}:{line}   {entity}")
        elif kind == "permit":
            # `check` reports sites; `list` reports vocabulary. The asymmetry is
            # the whole point: a first run against a real book emits sites in the
            # thousands, and a flat site list is untriageable where a
            # frequency-ranked vocabulary is a worklist.
            entities = extract(root, r["extract"])
            spans, unresolved = _zoned_spans(root, r["permit"])
            try:
                sites = unpermitted(root, entities, r["permit"], spans)
            except re.error as e:
                console.print(f"[red]Config error:[/red] in rule {r['name']!r}: {e}")
                sys.exit(2)
            counts = Counter(token for _, _, token in sites)
            console.print(
                f"\n[bold]{r['name']}[/bold]  "
                f"({len(counts)} unpermitted, {len(sites)} occurrences)"
            )
            _print_unresolved(root, unresolved)
            for token, n in counts.most_common():
                console.print(f"  [red]✗[/red] {token}   ({n})")
        elif kind == "measure":
            # For a measure rule the measured files are the entities, so the
            # per-entity report is every file's value — passing ones included,
            # since a number you can see beats a number you have to infer.
            try:
                values, unresolved = _values(root, r["measure"])
                out_of_bounds, notes = _apply_expect(values, r.get("expect", {}))
            except ConfigError as e:
                console.print(f"[red]Config error:[/red] in rule {r['name']!r}: {e}")
                sys.exit(2)
            why: dict = {}
            for key, _, reason in out_of_bounds:
                why.setdefault(key, []).append(reason)

            console.print(f"\n[bold]{r['name']}[/bold]  ({len(values)} files)")
            for note in notes:
                console.print(f"  [yellow]{note}[/yellow]")
            _print_unresolved(root, unresolved)
            for f, v in sorted(values.items()):
                icon = "[red]✗[/red]" if f in why else "[green]✓[/green]"
                reason = f"   {'; '.join(why[f])}" if f in why else ""
                console.print(f"  {icon} {_render_key(root, f)}   {v:.2f}{reason}")


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
        # `stats` builds its whole spec from CLI flags, so it has no config and
        # no zone key: the unresolved list here is always empty and the keys are
        # always bare paths.
        columns[name], _ = _values(root, {**spec, "metric": name})

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
