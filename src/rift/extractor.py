import re
import yaml
from pathlib import Path


def resolve_globs(root: Path, patterns) -> list[Path]:
    """Files matching one glob or a list of them, deduplicated and ordered.

    A single document set is often several globs — the chapter directories plus
    a couple of named top-level files — and there is no glob that spells that.
    """
    if isinstance(patterns, str):
        patterns = [patterns]
    found = []
    for pattern in patterns:
        found.extend(root.glob(pattern))
    return sorted({f for f in found if f.is_file()})


def extract(root: Path, config: dict) -> set[str]:
    """Extract a set of entity strings from the codebase."""
    results = set()

    if "list" in config:
        return {str(x) for x in config["list"]}

    if "paths" in config:
        return {str(p.relative_to(root)) for p in resolve_globs(root, config["paths"])}

    if "files" in config:
        for path in root.glob(config["files"]):
            results.add(path.stem if path.is_file() else path.name)
        return results

    if "dirs_with" in config:
        for match in root.rglob(config["dirs_with"]):
            if match.is_file() and not _is_ignored(match):
                results.add(match.parent.name)
        return results

    # `file:` takes one glob or a list, like `in:` — a source set is often
    # several directories and no single glob spells that.
    matching_files = resolve_globs(root, config.get("file", []))

    if "yaml_keys" in config:
        for f in matching_files:
            try:
                node = _navigate_yaml(yaml.safe_load(f.read_text()), config["yaml_keys"])
                if isinstance(node, dict):
                    results.update(str(k) for k in node.keys())
            except Exception:
                pass

    elif "yaml_values" in config:
        for f in matching_files:
            try:
                node = _navigate_yaml(yaml.safe_load(f.read_text()), config["yaml_values"])
                if isinstance(node, dict):
                    results.update(str(v) for v in node.values())
                elif isinstance(node, list):
                    results.update(str(v) for v in node)
            except Exception:
                pass

    elif config.get("lines"):
        for f in matching_files:
            try:
                for line in f.read_text().splitlines():
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#"):
                        results.add(stripped)
            except Exception:
                pass

    elif config.get("env_names"):
        for f in matching_files:
            try:
                for line in f.read_text().splitlines():
                    m = re.match(r'^([A-Z_][A-Z0-9_]*)=', line)
                    if m:
                        results.add(m.group(1))
            except Exception:
                pass

    elif "regex" in config:
        pattern = re.compile(config["regex"], re.MULTILINE)
        for f in matching_files:
            try:
                for m in pattern.finditer(f.read_text()):
                    results.add(_captured(m).strip())
            except Exception:
                pass

    return results


def extract_with_sites(root: Path, config: dict) -> list[tuple[str, Path, int]]:
    """Same extractors as `extract`, but yields (value, path, line) triples.

    `unique` reports every site of a duplicated value, not just the value, so
    each occurrence has to carry its provenance through the pipeline. Line is
    1-indexed. For extractors whose entity is the file itself (`paths`,
    `files`, `dirs_with`) or whose value has no natural line (`yaml_keys`,
    `yaml_values`), line is 1 — a duplicated file is already located by its
    path. For `regex`, `lines` and `env_names`, the line is the match's.

    `list:` has no source file and is rejected at CLI validation time. It
    yields `[]` here rather than raising, because the extractor is a pure
    dispatch and the caller decides which kinds it makes sense to feed.
    """
    if "list" in config:
        return []

    if "paths" in config:
        return [(str(p.relative_to(root)), p, 1)
                for p in resolve_globs(root, config["paths"])]

    if "files" in config:
        results = []
        for path in sorted(root.glob(config["files"])):
            results.append((path.stem if path.is_file() else path.name, path, 1))
        return results

    if "dirs_with" in config:
        results = []
        for match in sorted(root.rglob(config["dirs_with"])):
            if match.is_file() and not _is_ignored(match):
                results.append((match.parent.name, match, 1))
        return results

    matching_files = resolve_globs(root, config.get("file", []))
    results: list[tuple[str, Path, int]] = []

    if "yaml_keys" in config:
        for f in matching_files:
            try:
                node = _navigate_yaml(yaml.safe_load(f.read_text()), config["yaml_keys"])
                if isinstance(node, dict):
                    results.extend((str(k), f, 1) for k in node.keys())
            except Exception:
                pass

    elif "yaml_values" in config:
        for f in matching_files:
            try:
                node = _navigate_yaml(yaml.safe_load(f.read_text()), config["yaml_values"])
                if isinstance(node, dict):
                    results.extend((str(v), f, 1) for v in node.values())
                elif isinstance(node, list):
                    results.extend((str(v), f, 1) for v in node)
            except Exception:
                pass

    elif config.get("lines"):
        for f in matching_files:
            try:
                for i, line in enumerate(f.read_text().splitlines(), 1):
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#"):
                        results.append((stripped, f, i))
            except Exception:
                pass

    elif config.get("env_names"):
        for f in matching_files:
            try:
                for i, line in enumerate(f.read_text().splitlines(), 1):
                    m = re.match(r'^([A-Z_][A-Z0-9_]*)=', line)
                    if m:
                        results.append((m.group(1), f, i))
            except Exception:
                pass

    elif "regex" in config:
        pattern = re.compile(config["regex"], re.MULTILINE)
        for f in matching_files:
            try:
                text = f.read_text()
                for m in pattern.finditer(text):
                    value = _captured(m).strip()
                    line = text.count("\n", 0, m.start()) + 1
                    results.append((value, f, line))
            except Exception:
                pass

    return results


def _captured(m: re.Match) -> str:
    """The first group that actually matched, or the whole match if there are none.

    A roster written in two idioms needs an alternation, and an unmatched branch
    leaves its group `None`. Returning `group(1)` unconditionally handed `None`
    to `.strip()`, and the `except Exception` around the per-file loop swallowed
    the error — dropping every *remaining* match in that file. The result was not
    zero entities, which would look suspicious, but a silently partial roster
    that reports pass.
    """
    for value in m.groups():
        if value is not None:
            return value
    return m.group(0)


def _navigate_yaml(data, path: str):
    if not path or path == ".":
        return data
    for key in path.split("."):
        if isinstance(data, dict):
            data = data.get(key)
        else:
            return None
    return data


def _is_ignored(path: Path) -> bool:
    ignored = {".venv", "__pycache__", "node_modules", ".git", ".playground"}
    return any(part in ignored for part in path.parts)
