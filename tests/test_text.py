from rift.text import line_of, mask


def test_mask_preserves_length_so_offsets_survive():
    src = "before\n```\nfenced\n```\nafter\n"
    assert len(mask(src)) == len(src)


def test_mask_preserves_newlines_so_line_numbers_survive():
    src = "one\n```\ntwo\nthree\n```\nfour\n"
    assert mask(src).count("\n") == src.count("\n")


def test_mask_blanks_a_fenced_code_block():
    src = "prose\n```\ndelve\n```\n"
    assert "delve" not in mask(src)
    assert "prose" in mask(src)


def test_mask_blanks_inline_code():
    assert "delve" not in mask("call `delve` here")
    assert "call" in mask("call `delve` here")


def test_mask_blanks_a_link_url_but_keeps_the_link_text():
    masked = mask("see [the docs](https://delve.example.com/x)")
    assert "delve" not in masked
    assert "the docs" in masked


def test_mask_blanks_html_tags():
    assert "delve" not in mask('<a class="delve">text</a>')
    assert "text" in mask('<a class="delve">text</a>')


def test_mask_blanks_blockquotes_by_default():
    src = "my prose\n\n> quoted delve here\n\nmore prose\n"
    masked = mask(src)
    assert "delve" not in masked
    assert "my prose" in masked
    assert "more prose" in masked


def test_include_quotes_puts_blockquotes_back_in_play():
    src = "my prose\n\n> quoted delve here\n"
    assert "delve" in mask(src, include_quotes=True)


def test_prose_is_untouched():
    src = "Plain prose with no markup at all.\n"
    assert mask(src) == src


def test_line_of_is_one_indexed():
    assert line_of("a\nb\nc", 0) == 1
    assert line_of("a\nb\nc", 2) == 2
    assert line_of("a\nb\nc", 4) == 3


def test_masking_does_not_shift_line_numbers_of_later_prose():
    """The assertion that catches a stripper which deletes instead of masks."""
    src = "one\n```\ndelve\nand\nmore\nlines\nhere\n```\nnine: delve\n"
    masked = mask(src)
    pos = masked.index("delve")
    assert line_of(masked, pos) == 9


# --- tokens / sentences / paragraphs (prose-linting slice 2) ---

from rift.text import paragraphs, sentences, tokens


def test_tokens_lowercases_and_drops_punctuation():
    assert tokens("Hello, World!") == ["hello", "world"]


def test_tokens_are_unicode_so_spanish_works_unchanged():
    assert tokens("El niño comió") == ["el", "niño", "comió"]


def test_tokens_count_numbers():
    assert tokens("in 1936 Turing") == ["in", "1936", "turing"]


def test_sentences_split_on_terminal_punctuation():
    assert sentences("One two three. Four five six.") == [
        ["one", "two", "three"],
        ["four", "five", "six"],
    ]


def test_sentences_do_not_split_without_a_capital_or_digit_after():
    """`3.14` and `e.g. thing` must not split."""
    assert len(sentences("The value is 3.14 exactly.")) == 1


def test_sentences_over_split_on_abbreviations_by_design():
    """Documented crudeness: every file in a set is over-split by the same rule."""
    assert len(sentences("Dr. Smith wrote it.")) == 2


def test_sentences_treat_end_of_paragraph_as_a_boundary():
    assert sentences("No terminator here") == [["no", "terminator", "here"]]


def test_sentences_do_not_run_across_paragraphs():
    assert len(sentences("First para\n\nSecond para")) == 2


def test_paragraphs_are_blank_line_delimited():
    assert paragraphs("one one\n\ntwo two\n") == ["one one", "two two"]


def test_paragraphs_drop_headings():
    assert paragraphs("# Title\n\nbody text\n") == ["body text"]


def test_paragraphs_drop_list_blocks_and_tables():
    src = "body\n\n- item one\n- item two\n\n| a | b |\n|---|---|\n\nmore body\n"
    assert paragraphs(src) == ["body", "more body"]


def test_paragraphs_join_wrapped_lines():
    assert paragraphs("one\ntwo\n") == ["one\ntwo"]


# --- strip_patterns: caller-supplied markers are not prose ---

from rift.text import strip_patterns


def test_strip_patterns_blanks_a_match_preserving_length():
    src = "a [Tony Hoare]{~hoare-tony} b"
    out = strip_patterns(src, [r'\{~[^}]*\}'])
    assert len(out) == len(src)
    assert "hoare-tony" not in out
    assert "Tony Hoare" in out


def test_strip_patterns_preserves_line_numbers():
    src = "one\ntwo {~key}\nthree"
    assert strip_patterns(src, [r'\{~[^}]*\}']).count("\n") == 2


def test_strip_patterns_accepts_several_patterns():
    src = "x {~a} y [>1969: Label here] z"
    out = strip_patterns(src, [r'\{~[^}]*\}', r'\[>[^\]]*\]'])
    assert "Label" not in out
    assert "x" in out and "z" in out


def test_strip_patterns_with_no_patterns_is_identity():
    assert strip_patterns("unchanged", []) == "unchanged"
    assert strip_patterns("unchanged", None) == "unchanged"


def test_strip_ignores_an_invalid_regex_rather_than_crashing():
    assert strip_patterns("text", ["([unclosed"]) == "text"


# --- spans (slice C) ---

from rift.text import (
    paragraph_spans,
    paragraphs,
    sentence_spans,
    sentence_start_offsets,
    sentences,
    token_spans,
    tokens,
)


def test_paragraph_spans_slice_back_to_the_paragraphs():
    """The span API and the string API must not drift apart."""
    doc = "# Heading\n\nOne line.\nAnd another.\n\n- a list item\n\nLast para.\n"
    assert [doc[s:e] for s, e in paragraph_spans(doc)] == paragraphs(doc)


def test_sentence_spans_slice_back_to_the_sentences():
    doc = "One two three. Four five six.\n\nSeven eight.\n"
    assert [tokens(doc[s:e]) for s, e in sentence_spans(doc)] == sentences(doc)


def test_sentence_start_offsets_finds_a_sentence_beginning_mid_line():
    """The reason `as: sentence_start` cannot be a regex.

    Every pattern in a rift config anchors `^` per line, and the second
    sentence here does not begin one.
    """
    doc = "Alpha runs fast. Beta walks slow.\n"
    assert sentence_start_offsets(doc) == {0, doc.index("Beta")}


def test_sentence_start_offsets_skips_leading_whitespace():
    """An indented paragraph opens its span on whitespace, not on its first word.

    The gap *between* sentences is not the case to test: `_TERMINATOR` is
    `[.!?...]+\\s+`, so it already consumes the spaces after a full stop and the
    second span starts at the word either way. A fixture built on that gap
    passes against a matcher that returns raw span starts, and this one does
    not.
    """
    doc = "   Alpha runs fast.\n"
    assert sentence_start_offsets(doc) == {doc.index("Alpha")}
    assert 0 not in sentence_start_offsets(doc)


def test_token_spans_carry_the_offset_and_the_source_form():
    """`tokens()` lowercases and discards offsets; `permit` needs both back —
    the offset to report a line, the source form to judge `of:`."""
    doc = "Alpha and BETA.\n"
    assert token_spans(doc) == [(0, "Alpha"), (6, "and"), (10, "BETA")]


def test_tokens_is_the_lowercased_projection_of_token_spans():
    doc = "# Heading\n\nAlpha and BETA, 1936.\n"
    assert tokens(doc) == [t.lower() for _, t in token_spans(doc)]


# --- sentence splitting across languages ---

# The same five sentences, English and Spanish. Spanish opens questions and
# exclamations with ¿ / ¡ *before* the capital, so a splitter that requires an
# uppercase letter immediately after the terminator silently merges them.
EN_FIVE = ("Elizabeth looked at the map. Why does the river stop here? "
           "Katherine said nothing. Look at that! The bridge was gone.")
ES_FIVE = ("Elizabeth miró el mapa. ¿Por qué el río se detiene aquí? "
           "Katherine no respondió. ¡Mira eso! El puente había desaparecido.")


def test_english_and_spanish_split_the_same_passage_alike():
    """rift claims every metric works on Spanish unchanged. This is that claim."""
    assert len(sentences(EN_FIVE)) == 5
    assert len(sentences(ES_FIVE)) == 5


def test_sentence_start_sees_the_word_after_inverted_punctuation():
    """The site is the word, not the ¿ — otherwise `as: sentence_start` cannot
    fire on any Spanish question or exclamation."""
    starts = sentence_start_offsets(ES_FIVE)
    assert ES_FIVE.index("Por") in starts
    assert ES_FIVE.index("Mira") in starts


def test_an_opening_quote_does_not_split_before_a_lowercase_word():
    """Skipping opening punctuation must not loosen the uppercase requirement:
    an abbreviation followed by a quoted lowercase word is not a new sentence."""
    assert len(sentences('Use a shim, e.g. "foo" in the config.')) == 1


# --- zones ---

from rift.text import section_spans, zone_spans

# A `#` title, an opening paragraph, then two `##` sections. Three zones, and
# the content of each is distinguishable — a fixture whose zones read alike
# cannot tell an off-by-one from a correct implementation.
THREE_ZONES = """\
# The Title

Opening prose here.

## First

Alpha content.

## Second

Beta content.
"""


def test_section_spans_treats_the_text_before_the_first_h2_as_zone_zero():
    spans = section_spans(THREE_ZONES)
    assert len(spans) == 3
    assert spans[0] == (0, THREE_ZONES.index("## First"))
    assert "The Title" in THREE_ZONES[spans[0][0]:spans[0][1]]
    assert "Opening prose" in THREE_ZONES[spans[0][0]:spans[0][1]]


def test_section_spans_cover_the_whole_text_without_gaps():
    spans = section_spans(THREE_ZONES)
    assert spans[0][0] == 0
    assert spans[-1][1] == len(THREE_ZONES)
    assert all(a[1] == b[0] for a, b in zip(spans, spans[1:]))


def test_section_spans_ignores_h3():
    doc = "Intro.\n\n## One\n\n### Deeper\n\nBody.\n"
    assert len(section_spans(doc)) == 2


def test_a_document_with_no_h2_is_a_single_zone():
    doc = "# Title\n\nJust prose.\n"
    assert section_spans(doc) == [(0, len(doc))]


def test_zone_spans_selects_a_section_by_index():
    [(s, e)] = zone_spans(THREE_ZONES, {"unit": "section", "index": [1]})
    assert "Alpha" in THREE_ZONES[s:e]
    assert "Beta" not in THREE_ZONES[s:e]


def test_zone_spans_index_minus_one_selects_the_last_zone_not_the_first():
    """The off-by-one that passes any single-zone fixture."""
    [(s, e)] = zone_spans(THREE_ZONES, {"unit": "section", "index": [-1]})
    assert "Beta" in THREE_ZONES[s:e]
    assert "Alpha" not in THREE_ZONES[s:e]
    assert "The Title" not in THREE_ZONES[s:e]


def test_zone_spans_takes_several_indices():
    spans = zone_spans(THREE_ZONES, {"unit": "paragraph", "index": [0, -1]})
    picked = [THREE_ZONES[s:e] for s, e in spans]
    assert picked == ["Opening prose here.", "Beta content."]


def test_zone_spans_with_no_index_is_the_union_of_the_units():
    spans = zone_spans(THREE_ZONES, {"unit": "section"})
    assert spans == section_spans(THREE_ZONES)


def test_an_out_of_range_index_yields_no_span_rather_than_raising():
    assert zone_spans(THREE_ZONES, {"unit": "section", "index": [7]}) == []


# --- delimited zones ---

DELIMITED = "Head alpha.\n\n\\sep2\n\nBody beta.\n\n\\sep3\n\nTail gamma.\n"


def test_a_delimited_zone_runs_between_the_two_bounds():
    [(s, e)] = zone_spans(DELIMITED, {"after": r"\\sep2", "before": r"\\sep3"})
    assert "beta" in DELIMITED[s:e]
    assert "alpha" not in DELIMITED[s:e]
    assert "gamma" not in DELIMITED[s:e]


def test_after_alone_runs_to_end_of_file():
    [(s, e)] = zone_spans(DELIMITED, {"after": r"\\sep2"})
    assert e == len(DELIMITED)
    assert "alpha" not in DELIMITED[s:e]
    assert "gamma" in DELIMITED[s:e]


def test_before_alone_runs_from_start_of_file():
    [(s, e)] = zone_spans(DELIMITED, {"before": r"\\sep3"})
    assert s == 0
    assert "alpha" in DELIMITED[s:e]
    assert "gamma" not in DELIMITED[s:e]


def test_an_inverted_pair_resolves_to_nothing():
    """Right way round in one chapter and wrong in another must not go quietly
    green on the second."""
    assert zone_spans(DELIMITED, {"after": r"\\sep3", "before": r"\\sep2"}) == []


def test_a_missing_bound_resolves_to_nothing():
    assert zone_spans(DELIMITED, {"after": r"\\sep9"}) == []
    assert zone_spans(DELIMITED, {"before": r"\\sep9"}) == []


def test_the_region_excludes_the_bound_matches_themselves():
    doc = "before\n\nMARK delve MARK\n\nbody\n\nEND\n"
    [(s, e)] = zone_spans(doc, {"after": "MARK delve MARK", "before": "END"})
    assert "delve" not in doc[s:e]
    assert "body" in doc[s:e]


def test_the_first_match_wins_for_each_bound():
    doc = "a\n\nSEP\n\nb\n\nSEP\n\nc\n\nEND\n\nd\n\nEND\n"
    [(s, e)] = zone_spans(doc, {"after": "SEP", "before": "END"})
    assert doc[s:e].split() == ["b", "SEP", "c"]
