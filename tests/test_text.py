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
