import re
from pathlib import Path

from .text import line_of, mask


def check(root: Path, entity: str, require: dict) -> bool:
    """Return True if entity satisfies the require condition.

    Answers *is it anywhere?* and returns as soon as it knows. Deliberately
    reads the document unmasked: `require` asks whether something is
    **documented**, and a code fence is documentation.
    """

    if require.get("exists"):
        return (root / entity).exists()

    doc_pattern = require.get("in", "docs/**/*.md")
    doc_files = list(root.glob(doc_pattern))
    as_type = require.get("as", "mention")
    case_insensitive = require.get("case_insensitive", False)

    # A regex entity is a pattern, not a string: lowercasing it would rewrite
    # character classes. It gets the IGNORECASE flag instead.
    fold = case_insensitive and as_type != "regex"
    if fold:
        entity = entity.lower()

    for doc_file in doc_files:
        try:
            text = doc_file.read_text()
        except Exception:
            continue
        if fold:
            text = text.lower()
        if _matches(entity, as_type, text, case_insensitive):
            return True

    return False


def find(root: Path, entity: str, forbid: dict) -> list[tuple[Path, int, str]]:
    """Every site where entity appears in the prose, as (path, line, entity).

    Answers *where is it?*, so unlike `check` it must visit every file and every
    occurrence — there is no early return. Reads the document **masked**:
    `forbid` asks whether something is in your prose, and a code fence, a link
    URL and a quotation of someone else are not your prose.
    """
    doc_pattern = forbid.get("in", "docs/**/*.md")
    as_type = forbid.get("as", "word")
    case_insensitive = forbid.get("case_insensitive", False)
    include_quotes = forbid.get("include_quotes", False)

    pattern = _pattern_for(entity, as_type)
    if pattern is None:
        return []
    flags = re.IGNORECASE if case_insensitive else 0
    try:
        compiled = re.compile(pattern, flags)
    except re.error:
        return []

    sites = []
    for doc_file in sorted(root.glob(doc_pattern)):
        if not doc_file.is_file():
            continue
        try:
            text = mask(doc_file.read_text(), include_quotes)
        except Exception:
            continue
        for m in compiled.finditer(text):
            sites.append((doc_file, line_of(text, m.start()), entity))
    return sites


def _pattern_for(entity: str, as_type: str) -> str | None:
    """The regex source for a literal-or-pattern entity, or None if unsupported."""
    if as_type == "word":
        return rf'\b{re.escape(entity)}\b'
    if as_type == "regex":
        return entity
    if as_type == "mention":
        return re.escape(entity)
    return None


def _matches(entity: str, as_type: str, text: str, case_insensitive: bool = False) -> bool:
    esc = re.escape(entity)

    if as_type == "mention":
        return entity in text

    if as_type == "word":
        return bool(re.search(rf'\b{esc}\b', text))

    if as_type == "regex":
        try:
            return bool(re.search(entity, text, re.IGNORECASE if case_insensitive else 0))
        except re.error:
            return False

    if as_type == "heading":
        return bool(re.search(rf'^#{{1,6}}\s+.*{esc}', text, re.MULTILINE | re.IGNORECASE))

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
