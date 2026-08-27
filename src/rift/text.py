"""Text normalisation shared by the matcher and the measurement engine.

The one rule that matters here: masking **blanks** a region, it never deletes it.
`forbid` rules report `file:line` for every site they find, so an offset into the
masked text has to still index the original file. Deleting a code fence shifts
every line number after it and makes the report wrong.
"""

import re

_FENCE = re.compile(r'^[ \t]*(?:```|~~~)')
_INLINE_CODE = re.compile(r'`[^`\n]*`')
_HTML_TAG = re.compile(r'<[^>\n]*>')
_LINK_URL = re.compile(r'(?<=\])\([^)\n]*\)')
_QUOTE = re.compile(r'^[ \t]*>.*$', re.MULTILINE)

# `##` only, excluding `###`. Lives here rather than in `measure` because both
# the `sections` metric and `section_spans` need it, and `text` is the base of
# the module graph — `measure` imports from here, so the reverse would be a
# circular import. A config has one definition of "section", not two.
_H2 = re.compile(r'^[ \t]*##(?!#)[ \t]+', re.MULTILINE)

_TOKEN = re.compile(r'\w+')
_TERMINATOR = re.compile(r'[.!?…]+\s+')
# Characters a sentence may open with *before* its first letter. `¿` and `¡` are
# the ones that matter — Spanish puts them in front of the capital — and opening
# quotes are the same shape of problem in every language.
#
# Brackets are deliberately absent. `[`, `(` and `{` are markdown and marker
# syntax far more often than they are sentence punctuation, and including them
# split a run of `[Tony Hoare]{~hoare-tony}` markers into new sentences, moving
# a metric that had a test pinning its value.
_OPENERS = '¿¡"\'«‹“‘'
_BLOCK = re.compile(r'^[ \t]*(?:#|>|[-*+][ \t]|\d+\.[ \t]|\||```|~~~)')


def mask(text: str, include_quotes: bool = False) -> str:
    """Blank the regions that are not the author's prose, preserving offsets.

    Fenced code, inline code, HTML tags and link URLs are never prose.
    Blockquotes are someone else's prose, which is why they go too unless the
    caller asks for them back.
    """
    out = _mask_fences(text)
    out = _INLINE_CODE.sub(_blank, out)
    out = _HTML_TAG.sub(_blank, out)
    out = _LINK_URL.sub(_blank, out)
    if not include_quotes:
        out = _QUOTE.sub(_blank, out)
    return out


def strip_patterns(text: str, patterns) -> str:
    """Blank caller-supplied markers before measuring.

    Renderer syntax is not prose. `[Tony Hoare]{~hoare-tony}` tokenises as
    "tony hoare hoare tony" and a timeline label leaks its whole caption into the
    sentence stream, so a chapter carrying more markers than its neighbour is
    measured as having different prose when only its apparatus differs.

    rift knows no renderer: the patterns come from the config. Blanks rather
    than deletes, for the same reason `mask` does.
    """
    if not patterns:
        return text
    if isinstance(patterns, str):
        patterns = [patterns]
    for pattern in patterns:
        try:
            text = re.sub(pattern, _blank, text, flags=re.MULTILINE)
        except re.error:
            continue
    return text


def line_of(text: str, pos: int) -> int:
    """The 1-indexed line containing the character at `pos`."""
    return text.count("\n", 0, pos) + 1


def tokens(text: str) -> list[str]:
    """Maximal runs of Unicode word characters, lowercased. Numbers count.

    `\\w+` with Unicode semantics covers accented Latin and Cyrillic without a
    per-language rule, which is what makes every metric above it work unchanged
    on Spanish. Callers pass already-masked text; this does not mask.
    """
    return [t.lower() for _, t in token_spans(text)]


def token_spans(text: str) -> list[tuple[int, str]]:
    """The same tokens as `tokens`, as (offset, source form).

    `tokens` lowercases and throws the offsets away, which is right for every
    metric and wrong for `permit`: an allowlist has to report a line, which
    needs the offset, and has to judge `of:` against the form the author wrote,
    which needs the token unfolded.
    """
    return [(m.start(), m.group(0)) for m in _TOKEN.finditer(text)]


def sentences(text: str) -> list[list[str]]:
    """Sentences, each as a token list.

    Split on terminal punctuation followed by whitespace and an uppercase letter
    or digit, plus end-of-paragraph. Deliberately crude: "Dr. Smith" over-splits.
    That is acceptable because every file in a set is over-split by the same
    rule, so a comparison between files stays valid where the absolute count
    does not. No metric here may depend on the absolute count being right.
    """
    out = []
    for start, end in sentence_spans(text):
        toks = tokens(text[start:end])
        if toks:
            out.append(toks)
    return out


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """The same sentences as `sentences`, as offsets into `text`.

    Offsets are what `forbid` needs and token lists cannot give: a site has to
    report a line, and a line comes from an offset.
    """
    out = []
    for para_start, para_end in paragraph_spans(text):
        out.extend(_split_sentence_spans(text[para_start:para_end], para_start))
    return out


def sentence_start_offsets(text: str) -> set[int]:
    """The offset of the first word character of each sentence.

    Not the offset of the span, which may open on whitespace — "Alpha runs.
    Beta walks." puts a space in front of "Beta", and a matcher comparing
    against the span start would never fire.
    """
    starts = set()
    for start, end in sentence_spans(text):
        m = _TOKEN.search(text, start, end)
        if m:
            starts.add(m.start())
    return starts


def paragraphs(text: str) -> list[str]:
    """Runs of non-empty lines delimited by blank lines, block elements removed."""
    return [text[start:end] for start, end in paragraph_spans(text)]


def paragraph_spans(text: str) -> list[tuple[int, int]]:
    """The same runs as `paragraphs`, as offsets into `text`."""
    spans: list[tuple[int, int]] = []
    start = end = None
    pos = 0
    for line in text.split("\n"):
        line_start, line_end = pos, pos + len(line)
        pos = line_end + 1  # the "\n" that split() consumed
        if not line.strip() or _BLOCK.match(line):
            if start is not None:
                spans.append((start, end))
                start = None
            continue
        if start is None:
            start = line_start
        end = line_end
    if start is not None:
        spans.append((start, end))
    return spans


def section_spans(text: str) -> list[tuple[int, int]]:
    """The text split at every `##`, as offsets. Contiguous and gapless.

    The text before the first `##` is zone 0, which is what makes "the chapter
    opening" addressable in a file whose first heading is its title. It is
    emitted even when empty, so `index: [1]` means the same thing in a file
    that opens on a `##` as in one that does not — a zone index that shifted
    with the presence of a preamble would make a rule confidently wrong about
    where it looked.

    A section owns its own heading line: the span starts at the `##`.
    """
    starts = [m.start() for m in _H2.finditer(text)]
    bounds = [0] + starts + [len(text)]
    return [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]


def zone_spans(text: str, zone: dict) -> list[tuple[int, int]]:
    """The regions of `text` a rule's `zone:` selects.

    Callers pass **already-masked** text: resolving on raw text would split
    `unit: section` on a `##` inside a code fence.

    Returns `[]` for a zone that cannot be resolved in this document — a
    missing bound, an inverted pair, an index past the end. The empty list is
    the signal, not an exception, because the caller has to tell "no zone" from
    "empty selection" and owns the reporting either way.
    """
    if "after" in zone or "before" in zone:
        return _delimited_spans(text, zone.get("after"), zone.get("before"))

    unit = zone.get("unit")
    spans = paragraph_spans(text) if unit == "paragraph" else section_spans(text)

    index = zone.get("index")
    if index is None:
        return spans
    picked = []
    for i in index:
        if -len(spans) <= i < len(spans):
            picked.append(spans[i])
    return sorted(set(picked))


def _delimited_spans(text: str, after, before) -> list[tuple[int, int]]:
    """The one region between the **first** match of each bound, bounds excluded.

    One region per file, no nesting, no overlap resolution. A region selector
    that resolves ambiguity is a parser, and a zone that silently lands on the
    wrong span produces a rule that is confidently wrong about where it looked.
    """
    start, end = 0, len(text)
    if after is not None:
        m = re.search(after, text, re.MULTILINE)
        if m is None:
            return []
        start = m.end()
    if before is not None:
        m = re.search(before, text, re.MULTILINE)
        if m is None:
            return []
        end = m.start()
    if start >= end:
        return []
    return [(start, end)]


def _split_sentence_spans(text: str, base: int = 0) -> list[tuple[int, int]]:
    parts, start = [], 0
    for m in _TERMINATOR.finditer(text):
        if _opens_a_sentence(text, m.end()):
            parts.append((start, m.end()))
            start = m.end()
    parts.append((start, len(text)))
    return [(base + s, base + e) for s, e in parts if text[s:e].strip()]


def _opens_a_sentence(text: str, pos: int) -> bool:
    """Does a new sentence begin at `pos`?

    Opening punctuation is skipped before the test, which is what makes this
    work on Spanish: `¿` and `¡` sit *in front of* the capital, so requiring an
    uppercase letter immediately after the terminator merged every question and
    exclamation into its neighbour. The same passage split into five sentences
    in English and three in Spanish, and every sentence metric read wrong on a
    dialogue-heavy Spanish chapter.

    The uppercase-or-digit requirement itself is unchanged, so this only ever
    finds *more* boundaries, never looser ones: `e.g. "foo"` still does not
    split, because `foo` is lowercase once the quote is skipped.
    """
    while pos < len(text) and text[pos] in _OPENERS:
        pos += 1
    nxt = text[pos:pos + 1]
    return bool(nxt) and (nxt.isupper() or nxt.isdigit())


def _blank(match: re.Match) -> str:
    return re.sub(r'[^\n]', ' ', match.group(0))


def _mask_fences(text: str) -> str:
    """Line-based rather than regex, so an unterminated fence blanks to EOF."""
    out = []
    in_fence = False
    for line in text.split("\n"):
        if _FENCE.match(line):
            in_fence = not in_fence
            out.append(" " * len(line))
        elif in_fence:
            out.append(" " * len(line))
        else:
            out.append(line)
    return "\n".join(out)
