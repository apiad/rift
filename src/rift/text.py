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


def line_of(text: str, pos: int) -> int:
    """The 1-indexed line containing the character at `pos`."""
    return text.count("\n", 0, pos) + 1


def tokens(text: str) -> list[str]:
    """Maximal runs of Unicode word characters, lowercased. Numbers count.

    `\\w+` with Unicode semantics covers accented Latin and Cyrillic without a
    per-language rule, which is what makes every metric above it work unchanged
    on Spanish. Callers pass already-masked text; this does not mask.
    """
    return [m.group(0).lower() for m in _TOKEN.finditer(text)]


def sentences(text: str) -> list[list[str]]:
    """Sentences, each as a token list.

    Split on terminal punctuation followed by whitespace and an uppercase letter
    or digit, plus end-of-paragraph. Deliberately crude: "Dr. Smith" over-splits.
    That is acceptable because every file in a set is over-split by the same
    rule, so a comparison between files stays valid where the absolute count
    does not. No metric here may depend on the absolute count being right.
    """
    out = []
    for para in paragraphs(text):
        for chunk in _split_sentences(para):
            toks = tokens(chunk)
            if toks:
                out.append(toks)
    return out


def paragraphs(text: str) -> list[str]:
    """Runs of non-empty lines delimited by blank lines, block elements removed."""
    blocks, current = [], []
    for line in text.split("\n"):
        if not line.strip() or _BLOCK.match(line):
            if current:
                blocks.append("\n".join(current))
                current = []
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def _split_sentences(text: str) -> list[str]:
    parts, start = [], 0
    for m in _TERMINATOR.finditer(text):
        nxt = text[m.end():m.end() + 1]
        if nxt and (nxt.isupper() or nxt.isdigit()):
            parts.append(text[start:m.end()])
            start = m.end()
    parts.append(text[start:])
    return [p for p in parts if p.strip()]


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
