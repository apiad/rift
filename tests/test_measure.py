"""Every expected value here is hand-computed from the spec's definitions.

A test whose expected value came from running the code under test asserts
nothing. Each metric also gets a discrimination test: two fixtures that differ
in the property the metric claims to measure, asserting it separates them in the
right direction. That is what catches a metric which computes *something* but
not the thing.
"""

import pytest

from rift import measure

# Three sentences of three tokens each.
UNIFORM = "Aa bb cc. Dd ee ff. Gg hh ii."
# One 1-token sentence and one 7-token sentence.
VARIED = "A. Bb cc dd ee ff gg hh."


# --- rhythm ---


def test_mean_sentence_length():
    assert measure.mean_sentence_length("One two three. Four five six.") == 3.0


def test_sentence_length_cv_is_zero_for_identical_lengths():
    assert measure.sentence_length_cv(UNIFORM) == 0.0


def test_sentence_length_cv_hand_computed():
    # lengths [1, 7]; mean 4; population sd 3; cv = 3/4
    assert measure.sentence_length_cv(VARIED) == pytest.approx(0.75)


def test_sentence_length_cv_separates_uniform_from_varied():
    assert measure.sentence_length_cv(UNIFORM) < measure.sentence_length_cv(VARIED)


def test_short_sentence_ratio_hand_computed():
    # lengths [1, 7]; one of two is under 6
    assert measure.short_sentence_ratio(VARIED) == pytest.approx(0.5)


def test_short_sentence_ratio_is_zero_when_every_sentence_is_long():
    assert measure.short_sentence_ratio("Aa bb cc dd ee ff gg hh ii jj kk.") == 0.0


def test_sentence_length_autocorr_hand_computed():
    # lengths [1, 5, 1, 5]; mean 3; numerator -12; denominator 16
    src = "A. Bb cc dd ee ff. Gg. Hh ii jj kk ll."
    assert measure.sentence_length_autocorr(src) == pytest.approx(-0.75)


def test_sentence_length_autocorr_is_negative_when_lengths_alternate():
    src = "A. Bb cc dd ee ff. Gg. Hh ii jj kk ll."
    assert measure.sentence_length_autocorr(src) < 0


def test_sentence_length_autocorr_is_positive_when_lengths_run():
    """Humans write in runs — several long, then several short."""
    src = "Aa bb cc dd ee. Ff gg hh ii jj. Kk. Ll. Mm. Nn."
    assert measure.sentence_length_autocorr(src) > 0


# --- texture ---


def test_mattr_hand_computed_for_a_document_shorter_than_the_window():
    # 3 tokens, 2 types
    assert measure.mattr("aa bb aa") == pytest.approx(2 / 3)


def test_mattr_separates_repetitive_from_diverse():
    repetitive = " ".join(["aa bb"] * 40)
    diverse = " ".join(f"w{i}" for i in range(80))
    assert measure.mattr(repetitive) < measure.mattr(diverse)


def test_hapax_ratio_hand_computed():
    # tokens [aa, bb, aa, cc]; exactly-once types: bb, cc
    assert measure.hapax_ratio("aa bb aa cc") == pytest.approx(0.5)


def test_hapax_ratio_is_zero_when_everything_repeats():
    assert measure.hapax_ratio("aa aa bb bb") == 0.0


def test_self_repetition_hand_computed():
    # 8 tokens -> 5 four-grams; (a,b,c,d) occurs twice
    assert measure.self_repetition("a b c d a b c d") == pytest.approx(0.4)


def test_self_repetition_is_zero_when_nothing_repeats():
    assert measure.self_repetition("a b c d e f g h") == 0.0


# --- structure ---


def test_mean_paragraph_length_hand_computed():
    assert measure.mean_paragraph_length("aa bb\n\ncc dd\n") == 2.0


def test_paragraph_length_cv_is_zero_for_equal_paragraphs():
    assert measure.paragraph_length_cv("aa bb\n\ncc dd\n") == 0.0


def test_paragraph_length_cv_separates_uniform_from_varied():
    uniform = "aa bb\n\ncc dd\n"
    varied = "aa\n\nbb cc dd ee ff gg\n"
    assert measure.paragraph_length_cv(uniform) < measure.paragraph_length_cv(varied)


def test_sections_counts_level_two_headings():
    assert measure.sections("# T\n\n## A\n\n## B\n") == 2.0


def test_sections_ignores_level_three():
    assert measure.sections("# T\n\n## A\n\n### Sub\n") == 1.0


def test_mean_heading_length_hand_computed():
    # "# One two" -> 2 tokens; "## Three" -> 1 token
    assert measure.mean_heading_length("# One two\n\n## Three\n") == pytest.approx(1.5)


def test_words_per_section_hand_computed():
    # tokens: t a aa bb b cc dd = 7; sections = 2
    src = "# T\n\n## A\n\naa bb\n\n## B\n\ncc dd\n"
    assert measure.words_per_section(src) == pytest.approx(3.5)


def test_words_per_section_is_zero_without_sections():
    assert measure.words_per_section("just prose here\n") == 0.0


def test_opening_paragraphs_counts_blocks_before_the_first_section():
    src = "# T\n\npara one\n\npara two\n\n## A\n\nbody\n"
    assert measure.opening_paragraphs(src) == 2.0


def test_opening_paragraphs_is_zero_when_a_section_follows_the_title():
    assert measure.opening_paragraphs("# T\n\n## A\n\nbody\n") == 0.0


# --- masking applies to metrics ---


def test_metrics_ignore_fenced_code():
    plain = "Aa bb cc. Dd ee ff.\n"
    fenced = "Aa bb cc. Dd ee ff.\n\n```\nxx yy zz qq ww\n```\n"
    assert measure.mean_sentence_length(plain) == measure.mean_sentence_length(fenced)


def test_metrics_ignore_quoted_prose():
    plain = "Aa bb cc. Dd ee ff.\n"
    quoted = "Aa bb cc. Dd ee ff.\n\n> someone else wrote this bit\n"
    assert measure.mean_paragraph_length(plain) == measure.mean_paragraph_length(quoted)


# --- pattern ---


def test_pattern_counts_matches():
    assert measure.pattern_count("a {~x} b {~y}", r'\{~[a-z]+\}') == 2.0


def test_pattern_normalises_per_n_tokens_excluding_the_markers():
    # markers blanked before tokenising -> denominator is [a, b] = 2 tokens
    assert measure.pattern_count("a {~x} b {~y}", r'\{~[a-z]+\}', per=1000) == pytest.approx(1000.0)


def test_pattern_does_not_count_inside_a_code_fence():
    src = "a {~x}\n\n```\n{~y} {~z}\n```\n"
    assert measure.pattern_count(src, r'\{~[a-z]+\}') == 1.0


# --- burrows's delta ---


def test_burrows_delta_ranks_the_odd_document_highest():
    """Known-answer on ranking, not on absolute value — ranking is what the
    design relies on, and absolute Delta is noisy at chapter length."""
    same = "the cat of the house and the dog of the garden and the bird of the tree"
    odd = "a cat in a house to a dog in a garden to a bird in a tree"
    deltas = measure.burrows_delta({"a": same, "b": same, "c": same, "d": odd})
    assert deltas["d"] > deltas["a"]
    assert deltas["d"] > deltas["b"]
    assert deltas["d"] > deltas["c"]


def test_burrows_delta_is_zero_for_identical_documents():
    same = "the cat and the dog and the bird"
    deltas = measure.burrows_delta({"a": same, "b": same, "c": same})
    assert all(v == 0.0 for v in deltas.values())


def test_burrows_delta_returns_a_value_per_document():
    deltas = measure.burrows_delta({"a": "one two", "b": "three four"})
    assert set(deltas) == {"a", "b"}


# --- registry ---


def test_every_catalogued_metric_is_registered():
    catalogue = {
        "sentence-length-cv", "short-sentence-ratio", "sentence-length-autocorr",
        "mean-sentence-length", "mattr", "hapax-ratio", "self-repetition",
        "paragraph-length-cv", "mean-paragraph-length", "sections",
        "words-per-section", "mean-heading-length", "opening-paragraphs",
    }
    assert catalogue <= set(measure.METRICS)


def test_empty_document_yields_zero_not_a_crash():
    for name, fn in measure.METRICS.items():
        assert fn("") == 0.0, name


# --- word-count ---


def test_word_count_hand_computed():
    assert measure.word_count("one two three") == 3.0


def test_word_count_excludes_masked_regions():
    assert measure.word_count("one two\n\n```\nthree four five\n```\n") == 2.0


def test_word_count_is_registered():
    assert "word-count" in measure.METRICS


# --- repeated sentence openers (slice B) ---

# Four sentences, twelve tokens. Openers: the, the, a, the.
# Consecutive repeats: only the pair (1, 2). 1 / 12 * 1000 = 83.333...
OPENERS_ONE_REPEAT = "The cat sat. The dog ran. A bird flew. The fish swam."
# Same twelve tokens, openers: the, the, the, the. Three consecutive pairs.
# 3 / 12 * 1000 = 250.0
OPENERS_ALL_REPEAT = "The cat sat. The dog ran. The bird flew. The fish swam."
# Same shape, every opener distinct. Zero pairs.
OPENERS_NONE = "Alpha runs fast. Beta walks slow. Gamma flies high. Delta swims deep."


def test_repeated_sentence_openers_hand_computed():
    assert measure.repeated_sentence_openers(OPENERS_ONE_REPEAT) == pytest.approx(1 / 12 * 1000)


def test_repeated_sentence_openers_is_zero_when_every_opener_differs():
    assert measure.repeated_sentence_openers(OPENERS_NONE) == 0.0


def test_repeated_sentence_openers_discriminates():
    """The tic is consecutive repetition, not vocabulary: all three fixtures
    share a sentence count, and two share their token count exactly."""
    none = measure.repeated_sentence_openers(OPENERS_NONE)
    one = measure.repeated_sentence_openers(OPENERS_ONE_REPEAT)
    every = measure.repeated_sentence_openers(OPENERS_ALL_REPEAT)
    assert none < one < every
    assert every == pytest.approx(250.0)


def test_repeated_sentence_openers_counts_consecutive_pairs_not_totals():
    """A word that opens two sentences with another between them is not the tic.

    Openers: the, a, the. No adjacent pair repeats, though "the" opens twice.
    A count of distinct-opener frequency would report 1 here.
    """
    assert measure.repeated_sentence_openers("The cat sat. A dog ran. The bird flew.") == 0.0


def test_repeated_sentence_openers_ignores_a_code_fence():
    """Masked like every metric: a fence is not prose."""
    fenced = "```\nThe x. The y. The z.\n```\n\nAlpha runs. Beta walks."
    assert measure.repeated_sentence_openers(fenced) == 0.0


def test_repeated_sentence_openers_is_registered():
    assert "repeated-sentence-openers" in measure.METRICS
