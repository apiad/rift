"""Tests for the `unique` rule kind and its extractor path.

`extract_with_sites` mirrors `extract` and adds provenance — every test here
asserts on the (value, path, line) triple, because a duplicate that cannot
be located is a duplicate the report cannot describe.
"""

import yaml
from click.testing import CliRunner

from rift.extractor import extract_with_sites
from rift.matcher import duplicates
from rift.cli import main


runner = CliRunner()


def config(write, *rules):
    write(".rift.yaml", yaml.safe_dump({"rules": list(rules)}))


# ---------------------------------------------------- extract_with_sites ----

def test_regex_extraction_reports_line_of_each_match(repo, write):
    """Line number is the extraction primitive — without it a duplicate cannot
    be located, and a report that names only a value is a report a reader
    cannot act on."""
    f = write("chapters/01.md", "top\n[a](https://x)\n\n[b](https://y)\n")
    sites = extract_with_sites(repo, {
        "file": "chapters/*.md",
        "regex": r"\((https?://[^)]+)\)",
    })
    assert sites == [("https://x", f, 2), ("https://y", f, 4)]


def test_regex_preserves_multiplicity_within_one_file(repo, write):
    """A value that appears twice in one file is two sites, not one — the set
    view of `extract` would swallow the second."""
    f = write("chapters/01.md", "[a](https://x)\n[b](https://x)\n")
    sites = extract_with_sites(repo, {
        "file": "chapters/*.md",
        "regex": r"\((https?://[^)]+)\)",
    })
    assert sites == [("https://x", f, 1), ("https://x", f, 2)]


def test_paths_extractor_returns_files_at_line_one(repo, write):
    a = write("chapters/01.md", "x")
    b = write("chapters/02.md", "y")
    sites = extract_with_sites(repo, {"paths": "chapters/*.md"})
    assert sorted(sites) == sorted([("chapters/01.md", a, 1),
                                    ("chapters/02.md", b, 1)])


def test_list_extractor_yields_nothing_since_it_has_no_source(repo):
    """`list:` yields the config's own strings and has no file to point at.
    Silently returning `[]` is the honest answer — the CLI rejects the shape."""
    assert extract_with_sites(repo, {"list": ["a", "b"]}) == []


def test_yaml_keys_are_reported_at_line_one(repo, write):
    """The file locates the duplicate; the exact key line inside the YAML is
    not what a duplicate check needs — two `services.api` keys means the
    file is malformed, not just non-unique."""
    f = write("compose.yml", "services:\n  api: {}\n  worker: {}\n")
    sites = extract_with_sites(repo, {"file": "compose.yml",
                                       "yaml_keys": "services"})
    assert sorted(sites) == sorted([("api", f, 1), ("worker", f, 1)])


# ------------------------------------------------------------ duplicates ----

def test_across_files_flags_a_value_that_appears_in_two_files(repo, write):
    """The URL-per-chapter case: a link shared across chapters breaks the
    per-chapter reading budget."""
    a = write("chapters/01.md", "")
    b = write("chapters/02.md", "")
    sites = [("https://x", a, 3), ("https://x", b, 5), ("https://y", a, 7)]
    groups = duplicates(sites, "across-files")
    assert groups == [[("https://x", a, 3), ("https://x", b, 5)]]


def test_across_files_does_not_flag_repeats_within_one_file(repo, write):
    """A chapter linking the same URL twice is a fact about the chapter, not
    a duplication across the set — the "one week's reading" claim survives."""
    a = write("chapters/01.md", "")
    sites = [("https://x", a, 3), ("https://x", a, 5)]
    assert duplicates(sites, "across-files") == []


def test_within_file_flags_repeats_inside_one_file(repo, write):
    """Footnote labels: `[^a]` defined twice in one file is a broken document,
    even if no other file uses the label at all."""
    a = write("chapters/01.md", "")
    sites = [("a", a, 3), ("a", a, 8)]
    assert duplicates(sites, "within-file") == [[("a", a, 3), ("a", a, 8)]]


def test_within_file_does_not_flag_repeats_across_files(repo, write):
    """`[^a]` defined once in each of two chapters is fine: footnote scope is
    per-file. `across-files` is the shape that flags it if needed."""
    a = write("chapters/01.md", "")
    b = write("chapters/02.md", "")
    sites = [("a", a, 3), ("a", b, 5)]
    assert duplicates(sites, "within-file") == []


def test_duplicates_rejects_unknown_scope():
    import pytest
    with pytest.raises(ValueError, match="unknown scope"):
        duplicates([], "everywhere")


# ---------------------------------------------------------- CLI: check ----

UNIQ = {
    "name": "no reading in two chapters",
    "extract": {"file": "chapters/*.md",
                "regex": r"\((https?://[^)]+)\)"},
    "unique": {},
}


def test_check_passes_when_every_value_is_unique(repo, write):
    write("chapters/01.md", "[a](https://x)\n")
    write("chapters/02.md", "[b](https://y)\n")
    config(write, UNIQ)
    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 0
    assert "0 errors" in result.output


def test_check_fails_when_a_url_is_shared_across_two_chapters(repo, write):
    write("chapters/01.md", "[a](https://x)\n")
    write("chapters/02.md", "[b](https://x)\n")
    config(write, UNIQ)
    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 1
    assert "https://x" in result.output
    # Both sites must be reported — a duplicate is not a single-site claim.
    assert "chapters/01.md" in result.output
    assert "chapters/02.md" in result.output


def test_check_rejects_list_extractor_because_there_is_no_source(repo, write):
    config(write, {**UNIQ, "extract": {"list": ["a", "b"]}})
    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 2
    assert "list" in result.output


def test_check_rejects_an_unknown_scope(repo, write):
    write("chapters/01.md", "[a](https://x)\n")
    config(write, {**UNIQ, "unique": {"scope": "everywhere"}})
    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 2
    assert "everywhere" in result.output


def test_check_supports_within_file_scope(repo, write):
    write("chapters/01.md", "[a](https://x)\n[b](https://x)\n")
    config(write, {**UNIQ, "unique": {"scope": "within-file"}})
    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 1
    assert "https://x" in result.output


def test_unique_cannot_take_a_zone(repo, write):
    """A zoned unique would silently narrow the extraction stream — the whole
    surprise the kind is meant to prevent."""
    write("chapters/01.md", "[a](https://x)\n")
    config(write, {**UNIQ, "unique": {"zone": {"unit": "paragraph"}}})
    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 2
    assert "zone" in result.output


# ------------------------------------------------------------ CLI: list ----

def test_list_shows_every_site_and_marks_the_colliding_ones(repo, write):
    write("chapters/01.md", "[a](https://x)\n[b](https://y)\n")
    write("chapters/02.md", "[c](https://x)\n")
    config(write, UNIQ)
    result = runner.invoke(main, ["list", str(repo)])
    assert result.exit_code == 0
    assert "https://x" in result.output
    assert "https://y" in result.output
