from rift.matcher import check

MENTION = {"in": "docs/**/*.md", "as": "mention"}


def test_mention_finds_the_entity_anywhere_in_the_prose(repo, write):
    write("docs/design.md", "The worker service consumes the queue.\n")
    assert check(repo, "worker", MENTION) is True


def test_mention_reports_a_missing_entity(repo, write):
    write("docs/design.md", "The worker service consumes the queue.\n")
    assert check(repo, "sandbox", MENTION) is False


def test_mention_is_a_plain_substring_so_short_names_match_inside_words(repo, write):
    """Documented permissiveness: `mention` does not respect word boundaries."""
    write("docs/design.md", "rapid iteration\n")
    assert check(repo, "api", MENTION) is True


def test_mention_only_searches_files_the_in_glob_selects(repo, write):
    write("docs/design.md", "nothing here\n")
    write("notes/scratch.md", "worker\n")
    assert check(repo, "worker", MENTION) is False


def test_mention_searches_nested_docs(repo, write):
    write("docs/ref/env.md", "SANDBOX_VERSION pins the image.\n")
    assert check(repo, "SANDBOX_VERSION", MENTION) is True


def test_case_insensitive_lets_a_lowercase_doc_satisfy_an_uppercase_entity(repo, write):
    write("docs/design.md", "the sandbox component\n")
    assert check(repo, "SANDBOX", MENTION) is False
    assert check(repo, "SANDBOX", {**MENTION, "case_insensitive": True}) is True


def test_heading_matches_any_level(repo, write):
    write("docs/design.md", "### The worker service\n\nbody\n")
    assert check(repo, "worker", {"in": "docs/**/*.md", "as": "heading"}) is True


def test_heading_does_not_match_body_prose(repo, write):
    write("docs/design.md", "# Overview\n\nthe worker service\n")
    assert check(repo, "worker", {"in": "docs/**/*.md", "as": "heading"}) is False


def test_heading_n_pins_the_exact_level(repo, write):
    write("docs/design.md", "## worker\n")
    req = {"in": "docs/**/*.md", "as": "heading_2"}
    assert check(repo, "worker", req) is True

    write("docs/design.md", "### worker\n")
    assert check(repo, "worker", req) is False

    write("docs/design.md", "# worker\n")
    assert check(repo, "worker", req) is False


def test_table_cell_matches_inside_a_pipe_delimited_cell(repo, write):
    write("docs/design.md", "| component | image |\n| --- | --- |\n| worker | worker:1 |\n")
    assert check(repo, "worker", {"in": "docs/**/*.md", "as": "table_cell"}) is True


def test_table_cell_does_not_match_prose_outside_a_table(repo, write):
    write("docs/design.md", "the worker service\n")
    assert check(repo, "worker", {"in": "docs/**/*.md", "as": "table_cell"}) is False


def test_mermaid_node_only_looks_inside_a_mermaid_fence(repo, write):
    write("docs/design.md", "```mermaid\ngraph TD\n  api --> worker\n```\n")
    assert check(repo, "worker", {"in": "docs/**/*.md", "as": "mermaid_node"}) is True


def test_mermaid_node_ignores_the_same_word_outside_the_fence(repo, write):
    write("docs/design.md", "worker is important\n\n```mermaid\ngraph TD\n  api\n```\n")
    assert check(repo, "worker", {"in": "docs/**/*.md", "as": "mermaid_node"}) is False


def test_exists_checks_the_path_relative_to_the_project_root(repo, write):
    write("compose.devmount.yml", "services: {}\n")
    assert check(repo, "compose.devmount.yml", {"exists": True}) is True
    assert check(repo, "compose.localhost.yml", {"exists": True}) is False


def test_an_unknown_matcher_never_satisfies_a_rule(repo, write):
    write("docs/design.md", "worker\n")
    assert check(repo, "worker", {"in": "docs/**/*.md", "as": "no_such_matcher"}) is False


def test_no_docs_at_all_means_nothing_is_documented(repo):
    assert check(repo, "worker", MENTION) is False


# --- as: word / as: regex / find() (prose-linting slice 1) ---

from rift.matcher import find

WORD = {"in": "docs/**/*.md", "as": "word"}
FORBID = {"in": "docs/**/*.md", "as": "word"}


def test_word_does_not_match_inside_a_longer_word(repo, write):
    """The opposite of `mention`, pinned with equal force."""
    write("docs/design.md", "adjusted rapid sandbox-dbg\n")
    assert check(repo, "just", WORD) is False
    assert check(repo, "api", WORD) is False
    assert check(repo, "db", WORD) is False


def test_word_matches_a_standalone_word(repo, write):
    write("docs/design.md", "we just ship it\n")
    assert check(repo, "just", WORD) is True


def test_word_matches_a_multi_word_phrase(repo, write):
    write("docs/design.md", "the rich history of computing\n")
    assert check(repo, "rich history of", WORD) is True


def test_word_is_literal_not_a_pattern(repo, write):
    write("docs/design.md", "a.c\n")
    assert check(repo, "abc", WORD) is False


def test_regex_treats_the_entity_as_a_pattern(repo, write):
    write("docs/design.md", "very quickly indeed\n")
    assert check(repo, r"\bvery\s+\w+ly\b", {"in": "docs/**/*.md", "as": "regex"}) is True


def test_regex_reports_no_match(repo, write):
    write("docs/design.md", "slowly and surely\n")
    assert check(repo, r"\bvery\s+\w+ly\b", {"in": "docs/**/*.md", "as": "regex"}) is False


def test_find_reports_every_occurrence_not_just_the_first(repo, write):
    """A find() that early-returned like check() would pass any non-empty test."""
    write("docs/a.md", "delve here\nand delve again\n")
    write("docs/b.md", "delve once more\n")
    sites = find(repo, "delve", FORBID)
    assert len(sites) == 3


def test_find_reports_the_correct_line_numbers(repo, write):
    write("docs/a.md", "one\ntwo\ndelve\n")
    assert [line for _, line, _ in find(repo, "delve", FORBID)] == [3]


def test_find_skips_masked_regions(repo, write):
    write("docs/a.md", "prose\n```\ndelve\n```\n> quoted delve\n")
    assert find(repo, "delve", FORBID) == []


def test_find_counts_a_site_outside_the_fence_with_the_right_line(repo, write):
    write("docs/a.md", "one\n```\ndelve\n```\nfive delve\n")
    sites = find(repo, "delve", FORBID)
    assert [line for _, line, _ in sites] == [5]


def test_find_respects_include_quotes(repo, write):
    write("docs/a.md", "> quoted delve\n")
    assert find(repo, "delve", FORBID) == []
    assert len(find(repo, "delve", {**FORBID, "include_quotes": True})) == 1


def test_find_defaults_to_word_boundaries(repo, write):
    write("docs/a.md", "adjusted\n")
    assert find(repo, "just", {"in": "docs/**/*.md"}) == []


def test_find_is_case_insensitive_on_request(repo, write):
    write("docs/a.md", "Delve here\n")
    assert find(repo, "delve", FORBID) == []
    assert len(find(repo, "delve", {**FORBID, "case_insensitive": True})) == 1


def test_find_returns_nothing_when_clean(repo, write):
    write("docs/a.md", "perfectly ordinary prose\n")
    assert find(repo, "delve", FORBID) == []


# --- exclude: declared exceptions to an otherwise-good ban ---

EXCLUDE = {**FORBID, "exclude": ["delve deeper into the archive"]}


def test_exclude_skips_an_occurrence_inside_a_declared_phrase(repo, write):
    write("docs/a.md", "we delve deeper into the archive\n")
    assert find(repo, "delve", EXCLUDE) == []


def test_exclude_still_reports_the_same_word_elsewhere(repo, write):
    write("docs/a.md", "we delve deeper into the archive\nand we delve again\n")
    assert [line for _, line, _ in find(repo, "delve", EXCLUDE)] == [2]


def test_exclude_honours_the_rules_own_case_sensitivity(repo, write):
    write("docs/a.md", "we Delve Deeper Into The Archive\n")
    forbid = {**FORBID, "case_insensitive": True, "exclude": ["delve deeper into the archive"]}
    assert find(repo, "delve", forbid) == []
    # ...and a case-sensitive rule does not silently extend the exemption
    assert len(find(repo, "Delve", EXCLUDE)) == 1


# --- multi-glob `in:` and MULTILINE regex (needed by real configs) ---


def test_in_accepts_a_list_of_globs(repo, write):
    write("a/one.md", "worker\n")
    write("b/two.md", "sandbox\n")
    req = {"in": ["a/*.md", "b/*.md"], "as": "word"}
    assert check(repo, "worker", req) is True
    assert check(repo, "sandbox", req) is True


def test_in_as_a_list_excludes_what_it_does_not_name(repo, write):
    write("a/one.md", "worker\n")
    write("c/three.md", "sandbox\n")
    req = {"in": ["a/*.md", "b/*.md"], "as": "word"}
    assert check(repo, "sandbox", req) is False


def test_find_accepts_a_list_of_globs(repo, write):
    write("a/one.md", "delve\n")
    write("b/two.md", "delve\n")
    write("c/three.md", "delve\n")
    sites = find(repo, "delve", {"in": ["a/*.md", "b/*.md"], "as": "word"})
    assert len(sites) == 2


def test_find_does_not_double_report_overlapping_globs(repo, write):
    write("a/one.md", "delve\n")
    sites = find(repo, "delve", {"in": ["a/*.md", "a/one.md"], "as": "word"})
    assert len(sites) == 1


def test_find_compiles_regex_multiline_so_caret_anchors_per_line(repo, write):
    """`^---$` is the shape a real banned-pattern rule needs."""
    write("a/one.md", "prose\n---\nmore prose\n")
    sites = find(repo, r"^---$", {"in": "a/*.md", "as": "regex"})
    assert [line for _, line, _ in sites] == [2]


def test_multiline_regex_does_not_match_a_rule_inside_a_fence(repo, write):
    write("a/one.md", "prose\n```\n---\n```\n")
    assert find(repo, r"^---$", {"in": "a/*.md", "as": "regex"}) == []


def test_check_regex_is_multiline_like_find(repo, write):
    """One meaning of `^` across a config, in check as well as find."""
    write("docs/a.md", "prose\n---\nmore\n")
    assert check(repo, r"^---$", {"in": "docs/*.md", "as": "regex"}) is True


# --- wrap: the entity is substituted into a pattern ---

WRAP = {"in": "docs/**/*.md", "wrap": r'[\[{]~${entity}[\]}]'}


def test_wrap_matches_the_entity_inside_its_marker(repo, write):
    write("docs/a.md", "text [~cpu] more\n")
    assert check(repo, "cpu", WRAP) is True


def test_wrap_does_not_match_the_bare_word(repo, write):
    """The point: `abstraction` in prose must not satisfy the marker `[~abstraction]`."""
    write("docs/a.md", "a discussion of abstraction in general\n")
    assert check(repo, "abstraction", WRAP) is False


def test_wrap_accepts_either_marker_form(repo, write):
    write("docs/a.md", "one [~cpu] two\n")
    write("docs/b.md", "three {~alu} four\n")
    assert check(repo, "cpu", WRAP) is True
    assert check(repo, "alu", WRAP) is True


def test_wrap_escapes_the_entity(repo, write):
    """An entity carrying a regex metachar must match literally, not as a pattern.
    Unescaped, the key `a.c` would match the marker `[~abc]`."""
    write("docs/a.md", "[~abc]\n")
    assert check(repo, "a.c", WRAP) is False
    write("docs/b.md", "[~a.c]\n")
    assert check(repo, "a.c", WRAP) is True


def test_wrap_does_not_match_a_longer_key(repo, write):
    write("docs/a.md", "[~cpu-cache]\n")
    assert check(repo, "cpu", WRAP) is False


def test_wrap_works_in_find_and_reports_sites(repo, write):
    write("docs/a.md", "one [~cpu]\ntwo {~cpu}\n")
    sites = find(repo, "cpu", {"in": "docs/*.md", "wrap": r'[\[{]~${entity}[\]}]'})
    assert [line for _, line, _ in sites] == [1, 2]


# --- whitespace-tolerant literal matching (slice A) ---


def test_word_matches_a_phrase_broken_across_a_line(repo, write):
    """A hard-wrapped document must not hide a banned phrase.

    `books-tsoc` writes one paragraph per line and was never bitten by this;
    `enciclopedia` is hard-wrapped and would be.
    """
    write("docs/a.md", "the claim is not\nmerely that it is hard\n")
    sites = find(repo, "not merely", FORBID)
    assert [line for _, line, _ in sites] == [1]


def test_require_word_also_matches_across_a_line(repo, write):
    """The same fix, at the second site.

    `find` reads `_pattern_for`; `check` has its own `as: word` branch. Fixing
    one leaves the other broken in exactly the same way.
    """
    write("docs/design.md", "a rich\nhistory of computing\n")
    assert check(repo, "rich history of", WORD) is True


def test_word_still_respects_boundaries_across_a_line(repo, write):
    """Tolerating the wrap must not loosen the ends of the phrase."""
    write("docs/a.md", "the claim is not\nmerelyish and vague\n")
    assert find(repo, "not merely", FORBID) == []


# --- as: sentence_start (slice C) ---

SENTENCE_START = {"in": "docs/*.md", "as": "sentence_start"}


def test_sentence_start_ignores_a_mid_sentence_occurrence(repo, write):
    """THE test for this feature.

    A test that only asserts the sentence-initial site is found would pass
    against a plain `as: word` implementation and prove nothing.
    """
    write("docs/a.md", "The result was however quite different.\n")
    assert find(repo, "however", SENTENCE_START) == []


def test_sentence_start_finds_a_sentence_that_does_not_open_a_line(repo, write):
    """Not expressible as a regex: `^` anchors per line, and this one is mid-line."""
    write("docs/a.md", "Alpha runs fast. However, beta walks slow.\n")
    sites = find(repo, "However", SENTENCE_START)
    assert [line for _, line, _ in sites] == [1]


def test_sentence_start_reports_both_kinds_of_site_once_each(repo, write):
    write("docs/a.md", "However it began.\n\nIt ended. However it began again.\n")
    sites = find(repo, "however", {**SENTENCE_START, "case_insensitive": True})
    assert [line for _, line, _ in sites] == [1, 3]


def test_sentence_start_is_masked_like_any_forbid(repo, write):
    write("docs/a.md", "```\nHowever this is code.\n```\n\nHowever this is prose.\n")
    sites = find(repo, "However", SENTENCE_START)
    assert [line for _, line, _ in sites] == [5]


def test_require_sentence_start_survives_case_insensitive(repo, write):
    """Folding the document to lowercase would destroy every sentence boundary,
    since splitting keys on the following capital. The flag must not fold."""
    write("docs/a.md", "Alpha runs fast. However, beta walks slow.\n")
    assert check(repo, "however", {**SENTENCE_START, "case_insensitive": True}) is True
    assert check(repo, "beta", {**SENTENCE_START, "case_insensitive": True}) is False


def test_sentence_start_finds_an_indented_paragraph_opener(repo, write):
    """The site is the word, not the whitespace the paragraph span opens on."""
    write("docs/a.md", "   However it began.\n")
    sites = find(repo, "However", SENTENCE_START)
    assert [line for _, line, _ in sites] == [1]
