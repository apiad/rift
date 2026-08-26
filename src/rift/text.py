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
