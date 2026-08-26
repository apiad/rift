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
