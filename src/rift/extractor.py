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
                    val = m.group(1) if m.lastindex and m.lastindex >= 1 else m.group(0)
                    results.add(val.strip())
            except Exception:
                pass

    return results


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
