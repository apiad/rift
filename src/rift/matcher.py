import re
from pathlib import Path

from .extractor import resolve_globs
from .text import line_of, mask, sentence_start_offsets, token_spans


def check(root: Path, entity: str, require: dict) -> bool:
    """Return True if entity satisfies the require condition.

    Answers *is it anywhere?* and returns as soon as it knows. Deliberately
    reads the document unmasked: `require` asks whether something is
    **documented**, and a code fence is documentation.
    """

    if require.get("exists"):
        return (root / entity).exists()

    doc_files = resolve_globs(root, require.get("in", "docs/**/*.md"))
    as_type = require.get("as", "mention")
    case_insensitive = require.get("case_insensitive", False)

    # A regex entity is a pattern, not a string: lowercasing it would rewrite
    # character classes. It gets the IGNORECASE flag instead.
    #
    # `sentence_start` is excluded for a different reason: sentence splitting
    # keys on the capital that follows the terminator, so folding the document
    # to lowercase erases every boundary in it and the matcher finds nothing.
    # It gets IGNORECASE too.
    wrap = require.get("wrap")
    fold = case_insensitive and as_type not in ("regex", "sentence_start") and not wrap
    if fold:
        entity = entity.lower()

    for doc_file in doc_files:
        try:
            text = doc_file.read_text()
        except Exception:
            continue
        if fold:
            text = text.lower()
        if _matches(entity, as_type, text, case_insensitive, wrap):
            return True

    return False


def find(root: Path, entity: str, forbid: dict) -> list[tuple[Path, int, str]]:
    """Every site where entity appears in the prose, as (path, line, entity).

    Answers *where is it?*, so unlike `check` it must visit every file and every
    occurrence — there is no early return. Reads the document **masked**:
    `forbid` asks whether something is in your prose, and a code fence, a link
    URL and a quotation of someone else are not your prose.
    """
    as_type = forbid.get("as", "word")
    case_insensitive = forbid.get("case_insensitive", False)
    include_quotes = forbid.get("include_quotes", False)

    pattern = _pattern_for(entity, as_type, forbid.get("wrap"))
    if pattern is None:
        return []
    # MULTILINE to match the extractor and pattern counting: a real banned
    # pattern is line-anchored (`^---$`), and three different meanings of `^`
    # across one config would be a trap.
    flags = re.MULTILINE | (re.IGNORECASE if case_insensitive else 0)
    try:
        compiled = re.compile(pattern, flags)
    except re.error:
        return []

    exclusions = _exclusions(forbid.get("exclude"), flags)

    sites = []
    for doc_file in resolve_globs(root, forbid.get("in", "docs/**/*.md")):
        try:
            text = mask(doc_file.read_text(), include_quotes)
        except Exception:
            continue
        exempt = [span for e in exclusions for span in (m.span() for m in e.finditer(text))]
        starts = sentence_start_offsets(text) if as_type == "sentence_start" else None
        for m in compiled.finditer(text):
            if any(s <= m.start() and m.end() <= e for s, e in exempt):
                continue
            if starts is not None and m.start() not in starts:
                continue
            sites.append((doc_file, line_of(text, m.start()), entity))
    return sites


def unpermitted(root: Path, allowed: set[str], permit: dict) -> list[tuple[Path, int, str]]:
    """Every prose token *outside* the permitted set, as (path, line, token).

    The mirror of `find`: where `forbid` bans the extracted set, `permit` bans
    everything but it. Spelling is one instance — "no proper noun outside the
    roster" and "no acronym outside the glossary" are the others, and on a book
    with a large glossary they are worth more.

    Structurally unlike `check` and `find`, which take one entity and are called
    once per extracted string: this takes the whole set and walks the document
    once, because the question is about the document's vocabulary rather than
    about any one word.

    A malformed `of:` pattern raises rather than returning nothing. `find`
    swallows `re.error`, which means a typo'd pattern makes a rule silently
    green — the repo's documented blind spot, and the one failure mode a linter
    cannot afford. A new rule kind is not bound by that choice.
    """
    of = permit.get("of")
    of_pattern = re.compile(of) if of else None
    case_insensitive = permit.get("case_insensitive", False)
    include_quotes = permit.get("include_quotes", False)

    allow = {a.lower() for a in allowed} if case_insensitive else set(allowed)

    sites = []
    for doc_file in resolve_globs(root, permit.get("in", "docs/**/*.md")):
        try:
            text = mask(doc_file.read_text(), include_quotes)
        except Exception:
            continue
        for pos, raw in token_spans(text):
            # A year is not a spelling. This is the only judgment built in, and
            # it is a fact about tokens rather than a taste about prose.
            if raw.isdigit():
                continue
            if of_pattern is not None and not of_pattern.search(raw):
                continue
            if (raw.lower() if case_insensitive else raw) in allow:
                continue
            sites.append((doc_file, line_of(text, pos), raw))
    return sites


def _exclusions(phrases, flags: int) -> list[re.Pattern]:
    """Declared exceptions: literal phrases whose occurrences are exempt.

    A banned word is sometimes unavoidable — inside a quotation of someone
    else, or as a letter of an acronym. Naming the phrase keeps the ban intact
    everywhere else, which weakening the pattern would not: the exemption is
    visible in the config instead of hidden in a looser regex.

    Literal, not regex, and matched with the rule's own flags — a
    case-sensitive rule must not acquire a case-insensitive exemption.
    """
    if not phrases:
        return []
    if isinstance(phrases, str):
        phrases = [phrases]
    return [re.compile(re.escape(p), flags) for p in phrases]


def _word_pattern(entity: str) -> str | None:
    """A literal phrase, `\\b`-wrapped, tolerating any whitespace run inside it.

    The single space in "not merely" was a literal space, so the phrase was
    invisible the moment a renderer or an author wrapped the line between its
    two words. Whitespace inside the entity becomes `\\s+`; the boundaries stay
    exact, so "not merely" still does not match "not merelyish".

    `\\s+` spans a blank line too, so a phrase whose first word ends a paragraph
    and whose second opens the next reports a site. Rare, and narrowing it costs
    a pattern nobody can read — documented in the README instead.
    """
    parts = entity.split()
    if not parts:
        return None
    return r'\b' + r'\s+'.join(re.escape(p) for p in parts) + r'\b'


def _pattern_for(entity: str, as_type: str, wrap: str | None = None) -> str | None:
    """The regex source for a literal-or-pattern entity, or None if unsupported.

    `wrap` substitutes the escaped entity into a caller-supplied pattern via
    `${entity}`. It is what lets a rule ask about a *marked* term rather than a
    bare word — `[~abstraction]`, not the word "abstraction" — without rift
    knowing anything about the marker syntax.
    """
    if wrap:
        return wrap.replace("${entity}", re.escape(entity))
    if as_type in ("word", "sentence_start"):
        # `sentence_start` is a literal match plus a filter, not a pattern of its
        # own: sentence position needs segmentation, which no regex over the raw
        # text can express. `find` applies the filter.
        return _word_pattern(entity)
    if as_type == "regex":
        return entity
    if as_type == "mention":
        return re.escape(entity)
    return None


def _matches(entity: str, as_type: str, text: str, case_insensitive: bool = False,
             wrap: str | None = None) -> bool:
    esc = re.escape(entity)

    if wrap:
        flags = re.MULTILINE | (re.IGNORECASE if case_insensitive else 0)
        try:
            return bool(re.search(_pattern_for(entity, as_type, wrap), text, flags))
        except re.error:
            return False

    if as_type == "mention":
        return entity in text

    if as_type == "word":
        pattern = _word_pattern(entity)
        return bool(pattern) and bool(re.search(pattern, text))

    if as_type == "sentence_start":
        pattern = _word_pattern(entity)
        if not pattern:
            return False
        flags = re.MULTILINE | (re.IGNORECASE if case_insensitive else 0)
        starts = sentence_start_offsets(text)
        return any(m.start() in starts for m in re.finditer(pattern, text, flags))

    if as_type == "regex":
        try:
            flags = re.MULTILINE | (re.IGNORECASE if case_insensitive else 0)
            return bool(re.search(entity, text, flags))
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
