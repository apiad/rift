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
