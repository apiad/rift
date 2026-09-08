"""Tests for the `contain` rule kind.

`contain` is the universal-over-zones claim rift can make: every zone must
match a required pattern. It is the shape a per-file `require` would have
if `check` were not existential over the file set.
"""

import yaml
from click.testing import CliRunner

from rift.matcher import contain_gaps
from rift.cli import main


runner = CliRunner()


def config(write, *rules):
    write(".rift.yaml", yaml.safe_dump({"rules": list(rules)}))


SECTION_ZONE = {"unit": "section"}


# ------------------------------------------------------ contain_gaps ----

def test_a_section_with_the_required_pattern_is_not_flagged(repo, write):
    a = write("chapters/01.md", "## What is truth?\n\nquestion · What is truth, really?\n\nbody\n")
    offenders, unresolved = contain_gaps(repo, {
        "in": "chapters/*.md",
        "zone": SECTION_ZONE,
        "matches": r"^question · \S",
    })
    assert offenders == []
    assert unresolved == []


def test_a_section_missing_the_pattern_is_flagged(repo, write):
    a = write("chapters/01.md", "## What is truth?\n\nbody without a brief\n")
    offenders, unresolved = contain_gaps(repo, {
        "in": "chapters/*.md",
        "zone": SECTION_ZONE,
        "matches": r"^question · \S",
    })
    assert len(offenders) == 1
    path, idx, heading = offenders[0]
    assert path == a
    assert idx == 1  # zone 0 is the preamble; the ## opens zone 1
    assert "What is truth?" in heading


def test_where_heading_not_skips_apparatus_sections(repo, write):
    """Suggested Reading and Further Reading are apparatus — they should be
    excluded from the "every section carries a brief" check by matching a
    heading regex, not by listing them one by one at the call site."""
    write("chapters/01.md",
          "## What is truth?\n\nquestion · Real question?\n\n"
          "## Suggested Reading\n\nno brief here\n")
    offenders, _ = contain_gaps(repo, {
        "in": "chapters/*.md",
        "zone": SECTION_ZONE,
        "matches": r"^question · \S",
        "where_heading_not": r"^(Suggested Reading|Further Reading)",
    })
    assert offenders == []


def test_where_heading_not_still_flags_non_matching_sections(repo, write):
    """The exclusion is a filter, not an override — non-apparatus sections
    without a brief still fail."""
    write("chapters/01.md",
          "## What is truth?\n\nno brief\n\n"
          "## Suggested Reading\n\nno brief here either\n")
    offenders, _ = contain_gaps(repo, {
        "in": "chapters/*.md",
        "zone": SECTION_ZONE,
        "matches": r"^question · \S",
        "where_heading_not": r"^Suggested Reading",
    })
    assert len(offenders) == 1
    assert "What is truth?" in offenders[0][2]


def test_an_empty_preamble_is_skipped_not_flagged(repo, write):
    """The preamble (zone 0) is empty when a file opens on `##`; every
    contain rule over sections would otherwise trip on it in every such file."""
    write("chapters/01.md",
          "## What is truth?\n\nquestion · yes\n")
    offenders, _ = contain_gaps(repo, {
        "in": "chapters/*.md",
        "zone": SECTION_ZONE,
        "matches": r"^question · \S",
    })
    assert offenders == []


def test_a_preamble_with_content_is_still_skipped(repo, write):
    """Under `unit: section`, zone 0 is preamble by definition — whatever it
    carries (an H1 title, a chapter brief, nothing) is not a section, and a
    "every section contains X" claim must not judge it. The chapter file that
    opens `# Title\\npreamble\\n## Section` would otherwise report the preamble
    as a section missing its brief."""
    write("chapters/01.md",
          "# What is truth?\n\npreamble text, no brief here\n\n"
          "## What kinds of things are true?\n\nquestion · yes\n")
    offenders, _ = contain_gaps(repo, {
        "in": "chapters/*.md",
        "zone": SECTION_ZONE,
        "matches": r"^question · \S",
    })
    assert offenders == []


def test_a_zone_that_matches_nothing_is_reported_as_unresolved(repo, write):
    """The same convention as forbid/measure: an unresolvable zone is a broken
    rule, not a passed one — a rule that cannot fail is worse than none."""
    write("chapters/01.md", "no sections here\n")
    offenders, unresolved = contain_gaps(repo, {
        "in": "chapters/*.md",
        "zone": {"after": r"NOT_IN_FILE", "before": r"ALSO_NOT"},
        "matches": r"anything",
    })
    assert offenders == []
    assert len(unresolved) == 1


def test_first_heading_line_strips_markdown_chrome():
    """The report shows the section title, not its markup — a `##` prefix
    is how the line was written, not what the line says."""
    from rift.matcher import _first_heading_line
    assert _first_heading_line("## Hello\nbody") == "Hello"
    assert _first_heading_line("### Hello\nbody") == "Hello"
    assert _first_heading_line("\n\n## Hello\nbody") == "Hello"
    assert _first_heading_line("- item\nbody") == "item"
    assert _first_heading_line("") == ""


# ------------------------------------------------------- CLI: check ----

BRIEF_RULE = {
    "name": "every section has a brief",
    "contain": {
        "in": "chapters/*.md",
        "zone": SECTION_ZONE,
        "matches": r"^question · \S",
    },
}


def test_check_passes_when_every_zone_has_the_pattern(repo, write):
    write("chapters/01.md",
          "## What is truth?\n\nquestion · yes\n\n"
          "## What is knowledge?\n\nquestion · also yes\n")
    config(write, BRIEF_RULE)
    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 0, result.output


def test_check_fails_and_names_the_zone_that_lacks_the_pattern(repo, write):
    write("chapters/01.md",
          "## What is truth?\n\nquestion · yes\n\n"
          "## What is knowledge?\n\nno brief here\n")
    config(write, BRIEF_RULE)
    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 1
    # The failing zone is reported by (file#zone_index) so a reader can find it,
    # and by heading text so they know what it says.
    assert "chapters/01.md#2" in result.output
    assert "What is knowledge?" in result.output
    # The passing zone must not be listed as a failure.
    assert "chapters/01.md#1" not in result.output.split("What is knowledge?")[0]


def test_check_rejects_a_rule_without_matches(repo, write):
    config(write, {
        "name": "broken",
        "contain": {"in": "chapters/*.md", "zone": SECTION_ZONE},
    })
    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 2
    assert "matches" in result.output


def test_check_rejects_a_malformed_matches_regex(repo, write):
    write("chapters/01.md", "## x\n")
    config(write, {**BRIEF_RULE, "contain": {**BRIEF_RULE["contain"],
                                              "matches": r"[unclosed"}})
    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 2
    assert "malformed" in result.output


def test_check_with_where_heading_not_skips_apparatus(repo, write):
    write("chapters/01.md",
          "## Q1\n\nquestion · yes\n\n"
          "## Suggested Reading\n\nno brief needed here\n")
    config(write, {**BRIEF_RULE, "contain": {
        **BRIEF_RULE["contain"],
        "where_heading_not": r"^Suggested Reading",
    }})
    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 0, result.output


def test_check_reports_zone_matched_nothing_before_the_sites(repo, write):
    """Per the same convention forbid uses: a broken bound is a broken rule,
    not a finding, and belongs before the finding list where truncation can't
    push it out of view."""
    write("chapters/01.md", "no sections at all\n")
    config(write, {**BRIEF_RULE, "contain": {
        **BRIEF_RULE["contain"],
        "zone": {"after": r"NOTHING", "before": r"NOTHING"},
    }})
    result = runner.invoke(main, ["check", str(repo)])
    assert "zone matched nothing" in result.output


def test_check_zone_validation_still_applies(repo, write):
    """`contain` reuses the standard zone shape rules — a zone with both
    forms must fail up-front like every other kind."""
    write("chapters/01.md", "## x\nq\n")
    config(write, {**BRIEF_RULE, "contain": {
        **BRIEF_RULE["contain"],
        "zone": {"unit": "section", "after": r"anything"},
    }})
    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 2
    assert "both forms" in result.output


# ------------------------------------------------------- CLI: list ----

def test_list_shows_every_scoped_zone_and_marks_the_offenders(repo, write):
    write("chapters/01.md",
          "## Q1\n\nquestion · yes\n\n"
          "## Q2\n\nno brief\n\n"
          "## Suggested Reading\n\nnothing\n")
    config(write, {**BRIEF_RULE, "contain": {
        **BRIEF_RULE["contain"],
        "where_heading_not": r"^Suggested Reading",
    }})
    result = runner.invoke(main, ["list", str(repo)])
    assert result.exit_code == 0
    assert "Q1" in result.output
    assert "Q2" in result.output
    # Skipped by where_heading_not — not shown as pass or fail.
    assert "Suggested Reading" not in result.output
