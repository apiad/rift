"""Text in, numbers out. Pure functions — no YAML, no rules, no filesystem.

Knows nothing about rift, which is what makes it testable against hand-computed
fixtures with no repo fixture at all. Every function takes raw file text and
masks it here, so callers cannot forget to.

Structure metrics (`sections`, `mean-heading-length`, `opening-paragraphs`) are
about markdown structure rather than prose, but they read masked text too:
`mask` leaves headings alone and blanks fences and blockquotes, which is exactly
right — a `##` inside a code fence is not a section.
"""

import re
from collections import Counter
from statistics import mean, pstdev

from .text import mask, paragraphs, sentences, tokens

_HEADING = re.compile(r'^[ \t]*(#{1,6})[ \t]+(.*)$', re.MULTILINE)
_H2 = re.compile(r'^[ \t]*##(?!#)[ \t]+', re.MULTILINE)
_H1 = re.compile(r'^[ \t]*#(?!#)[ \t]+')


# --- rhythm ---


def mean_sentence_length(text: str) -> float:
    lengths = _sentence_lengths(text)
    return mean(lengths) if lengths else 0.0


def sentence_length_cv(text: str) -> float:
    """Burstiness. Human prose runs high; generated prose runs low."""
    return _cv(_sentence_lengths(text))


def short_sentence_ratio(text: str) -> float:
    """Humans use short sentences for emphasis; uniform prose has almost none."""
    lengths = _sentence_lengths(text)
    if not lengths:
        return 0.0
    return sum(1 for n in lengths if n < 6) / len(lengths)


def sentence_length_autocorr(text: str) -> float:
    """Lag-1 autocorrelation. Humans write in runs; uniform-random sits near zero."""
    lengths = _sentence_lengths(text)
    if len(lengths) < 3:
        return 0.0
    m = mean(lengths)
    denominator = sum((x - m) ** 2 for x in lengths)
    if denominator == 0:
        return 0.0
    numerator = sum((lengths[i] - m) * (lengths[i + 1] - m) for i in range(len(lengths) - 1))
    return numerator / denominator


# --- texture ---


def mattr(text: str, window: int = 200) -> float:
    """Moving-average type-token ratio. Length-independent, unlike raw TTR."""
    toks = tokens(mask(text))
    if not toks:
        return 0.0
    if len(toks) <= window:
        return len(set(toks)) / len(toks)
    ratios = [len(set(toks[i:i + window])) / window for i in range(len(toks) - window + 1)]
    return mean(ratios)


def hapax_ratio(text: str) -> float:
    """Proportion of tokens appearing exactly once."""
    toks = tokens(mask(text))
    if not toks:
        return 0.0
    counts = Counter(toks)
    return sum(1 for c in counts.values() if c == 1) / len(toks)


def self_repetition(text: str, n: int = 4) -> float:
    """Proportion of n-grams that occur more than once."""
    toks = tokens(mask(text))
    if len(toks) < n:
        return 0.0
    grams = [tuple(toks[i:i + n]) for i in range(len(toks) - n + 1)]
    counts = Counter(grams)
    return sum(c for c in counts.values() if c > 1) / len(grams)


# --- structure ---


def mean_paragraph_length(text: str) -> float:
    lengths = _paragraph_lengths(text)
    return mean(lengths) if lengths else 0.0


def paragraph_length_cv(text: str) -> float:
    return _cv(_paragraph_lengths(text))


def sections(text: str) -> float:
    return float(len(_H2.findall(mask(text))))


def words_per_section(text: str) -> float:
    n = sections(text)
    if not n:
        return 0.0
    return len(tokens(mask(text))) / n


def mean_heading_length(text: str) -> float:
    lengths = [len(tokens(body)) for _, body in _HEADING.findall(mask(text))]
    lengths = [n for n in lengths if n]
    return mean(lengths) if lengths else 0.0


def opening_paragraphs(text: str) -> float:
    """Blocks between the `#` title and the first `##`."""
    lines = mask(text).split("\n")
    start = 0
    for i, line in enumerate(lines):
        if _H1.match(line):
            start = i + 1
            break
    end = len(lines)
    for i in range(start, len(lines)):
        if _H2.match(lines[i]):
            end = i
            break
    return float(len(paragraphs("\n".join(lines[start:end]))))


# --- apparatus ---


def pattern_count(text: str, pattern: str, per: int | None = None) -> float:
    """Occurrences of a caller-supplied regex, optionally per N tokens.

    The markers are blanked before the denominator is tokenised, so a chapter is
    not penalised in the ratio for carrying more of them than its neighbour.
    """
    masked = mask(text)
    compiled = re.compile(pattern, re.MULTILINE)
    count = len(compiled.findall(masked))
    if not per:
        return float(count)
    body = compiled.sub(lambda m: " " * len(m.group(0)), masked)
    denominator = len(tokens(body)) or 1
    return count * per / denominator


# --- voice ---


def burrows_delta(texts: dict, top_n: int = 150) -> dict:
    """Mean absolute z-score over the top-N frequent tokens, against the centroid.

    The most frequent tokens in any language are function words, whose rates are
    an authorial fingerprint writers do not consciously control — so this needs
    no dictionary, no stopword list and no knowledge of the language.

    Noisy at chapter length. Rank the results; do not trust the absolute value.
    """
    docs = {name: tokens(mask(t)) for name, t in texts.items()}
    if not docs:
        return {}

    corpus = Counter()
    for toks in docs.values():
        corpus.update(toks)
    vocab = [w for w, _ in corpus.most_common(top_n)]
    if not vocab:
        return {name: 0.0 for name in docs}

    names = list(docs)
    freqs = {}
    for name in names:
        toks = docs[name]
        total = len(toks) or 1
        counts = Counter(toks)
        freqs[name] = [counts[w] / total for w in vocab]

    z = {name: [] for name in names}
    for j in range(len(vocab)):
        column = [freqs[name][j] for name in names]
        m = mean(column)
        s = pstdev(column)
        for name in names:
            z[name].append(0.0 if s == 0 else (freqs[name][j] - m) / s)

    return {name: mean(abs(v) for v in z[name]) for name in names}


# --- helpers ---


def _sentence_lengths(text: str) -> list[int]:
    return [len(s) for s in sentences(mask(text))]


def _paragraph_lengths(text: str) -> list[int]:
    return [len(tokens(p)) for p in paragraphs(mask(text))]


def _cv(values: list[int]) -> float:
    """Coefficient of variation, σ/μ. Zero variance is zero, not undefined."""
    if not values:
        return 0.0
    m = mean(values)
    if m == 0:
        return 0.0
    return pstdev(values) / m


METRICS = {
    "sentence-length-cv": sentence_length_cv,
    "short-sentence-ratio": short_sentence_ratio,
    "sentence-length-autocorr": sentence_length_autocorr,
    "mean-sentence-length": mean_sentence_length,
    "mattr": mattr,
    "hapax-ratio": hapax_ratio,
    "self-repetition": self_repetition,
    "paragraph-length-cv": paragraph_length_cv,
    "mean-paragraph-length": mean_paragraph_length,
    "sections": sections,
    "words-per-section": words_per_section,
    "mean-heading-length": mean_heading_length,
    "opening-paragraphs": opening_paragraphs,
}
