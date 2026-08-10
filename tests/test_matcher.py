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
