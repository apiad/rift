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
