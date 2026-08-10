import re
from pathlib import Path


def check(root: Path, entity: str, require: dict) -> bool:
    """Return True if entity satisfies the require condition."""

    if require.get("exists"):
        return (root / entity).exists()

    doc_pattern = require.get("in", "docs/**/*.md")
    doc_files = list(root.glob(doc_pattern))
    as_type = require.get("as", "mention")
    case_insensitive = require.get("case_insensitive", False)
    if case_insensitive:
        entity = entity.lower()

    for doc_file in doc_files:
        try:
            text = doc_file.read_text()
            if case_insensitive:
                text = text.lower()
        except Exception:
            continue
        if _matches(entity, as_type, text):
            return True

    return False


def _matches(entity: str, as_type: str, text: str) -> bool:
    esc = re.escape(entity)

    if as_type == "mention":
        return entity in text

    if as_type == "heading":
        return bool(re.search(rf'^#{1,6}\s+.*{esc}', text, re.MULTILINE | re.IGNORECASE))

    if as_type.startswith("heading"):
        m = re.match(r'heading[_\s]?(\d)', as_type)
        if m:
            prefix = "#" * int(m.group(1))
            return bool(re.search(rf'^{re.escape(prefix)}\s+.*{esc}', text, re.MULTILINE | re.IGNORECASE))

    if as_type == "table_cell":
        return bool(re.search(rf'\|[^|\n]*{esc}[^|\n]*\|', text))

    if as_type == "mermaid_node":
        for block in re.findall(r'```mermaid(.*?)```', text, re.DOTALL):
            if re.search(rf'\b{esc}\b', block):
                return True
        return False

    return False
