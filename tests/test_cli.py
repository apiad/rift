import yaml
from click.testing import CliRunner

from rift.cli import main

runner = CliRunner()

RULE_OK = {
    "name": "documented",
    "severity": "error",
    "extract": {"file": "compose.yml", "yaml_keys": "services"},
    "require": {"in": "docs/**/*.md", "as": "mention"},
}


def config(write, *rules):
    write(".rift.yaml", yaml.safe_dump({"rules": list(rules)}))


def test_check_exits_zero_when_every_rule_passes(repo, write):
    write("compose.yml", "services:\n  api: {}\n")
    write("docs/design.md", "the api service\n")
    config(write, RULE_OK)

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 0


def test_check_exits_one_when_an_error_rule_has_a_missing_entity(repo, write):
    write("compose.yml", "services:\n  api: {}\n  sandbox: {}\n")
    write("docs/design.md", "the api service\n")
    config(write, RULE_OK)

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 1
    assert "sandbox" in result.output


def test_check_exits_zero_when_only_warning_rules_fail(repo, write):
    write("compose.yml", "services:\n  api: {}\n  sandbox: {}\n")
    write("docs/design.md", "the api service\n")
    config(write, {**RULE_OK, "severity": "warning"})

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 0
    assert "sandbox" in result.output


def test_check_counts_rules_not_entities(repo, write):
    write("compose.yml", "services:\n  api: {}\n  sandbox: {}\n  cron: {}\n")
    write("docs/design.md", "nothing documented here\n")
    config(write, RULE_OK, {**RULE_OK, "name": "second", "severity": "warning"})

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 1
    assert "1 errors" in result.output
    assert "1 warnings" in result.output
    assert "0 pass" in result.output


def test_check_exits_two_when_there_is_no_config(repo):
    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 2
    assert "No config" in result.output


def test_check_truncates_long_missing_lists(repo, write):
    services = {f"svc{i}": {} for i in range(10)}
    write("compose.yml", yaml.safe_dump({"services": services}))
    write("docs/design.md", "nothing\n")
    config(write, RULE_OK)

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 1
    assert "4 more" in result.output


def test_list_marks_each_entity_documented_or_not(repo, write):
    write("compose.yml", "services:\n  api: {}\n  sandbox: {}\n")
    write("docs/design.md", "the api service\n")
    config(write, RULE_OK)

    result = runner.invoke(main, ["list", str(repo)])
    assert result.exit_code == 0
    assert "api" in result.output and "sandbox" in result.output


def test_list_filters_by_rule_substring(repo, write):
    write("compose.yml", "services:\n  api: {}\n")
    write("docs/design.md", "the api service\n")
    config(write, RULE_OK, {**RULE_OK, "name": "other rule"})

    result = runner.invoke(main, ["list", str(repo), "--rule", "other"])
    assert result.exit_code == 0
    assert "other rule" in result.output
    assert "documented" not in result.output


def test_init_scaffolds_a_config(repo):
    result = runner.invoke(main, ["init", str(repo)])
    assert result.exit_code == 0
    written = (repo / ".rift.yaml").read_text()
    assert yaml.safe_load(written)["rules"]


def test_init_refuses_to_clobber_an_existing_config(repo, write):
    write(".rift.yaml", "rules: []\n")
    result = runner.invoke(main, ["init", str(repo)])
    assert result.exit_code == 0
    assert (repo / ".rift.yaml").read_text() == "rules: []\n"
    assert "already exists" in result.output


# --- forbid rules (prose-linting slice 1) ---

RULE_FORBID = {
    "name": "no AI-tic phrasing",
    "severity": "error",
    "extract": {"list": ["delve", "tapestry"]},
    "forbid": {"in": "chapters/*.md", "as": "word"},
}


def test_forbid_exits_zero_on_clean_prose(repo, write):
    write("chapters/ch01.md", "Perfectly ordinary prose.\n")
    config(write, RULE_FORBID)

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 0


def test_forbid_exits_one_when_a_banned_phrase_appears(repo, write):
    write("chapters/ch01.md", "Let us delve in.\n")
    config(write, RULE_FORBID)

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 1


def test_forbid_reports_the_file_and_line_of_each_site(repo, write):
    write("chapters/ch01.md", "one\ntwo\nLet us delve in.\n")
    config(write, RULE_FORBID)

    result = runner.invoke(main, ["check", str(repo)])
    assert "chapters/ch01.md:3" in result.output
    assert "delve" in result.output


def test_forbid_says_occurrences_not_missing(repo, write):
    """The whole reason forbid exists: the report must not lie about what happened."""
    write("chapters/ch01.md", "delve\n")
    config(write, RULE_FORBID)

    result = runner.invoke(main, ["check", str(repo)])
    assert "occurrence" in result.output
    assert "missing" not in result.output


def test_forbid_counts_every_occurrence(repo, write):
    write("chapters/ch01.md", "delve and delve\n")
    write("chapters/ch02.md", "tapestry\n")
    config(write, RULE_FORBID)

    result = runner.invoke(main, ["check", str(repo)])
    assert "3 occurrences" in result.output


def test_forbid_ignores_a_banned_word_inside_a_code_fence(repo, write):
    write("chapters/ch01.md", "prose\n```\ndelve\n```\n")
    config(write, RULE_FORBID)

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 0


def test_forbid_ignores_a_banned_word_inside_a_quotation(repo, write):
    write("chapters/ch01.md", "> as Knuth put it, delve deeper\n")
    config(write, RULE_FORBID)

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 0


def test_forbid_at_warning_severity_does_not_fail_the_build(repo, write):
    write("chapters/ch01.md", "delve\n")
    config(write, {**RULE_FORBID, "severity": "warning"})

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 0


def test_summary_counts_rules_not_occurrences(repo, write):
    """One noisy chapter must not drown the roster rules in the summary line."""
    write("chapters/ch01.md", "delve delve delve delve\n")
    config(write, RULE_FORBID)

    result = runner.invoke(main, ["check", str(repo)])
    assert "1 rules" in result.output
    assert "1 errors" in result.output


def test_a_rule_with_two_kinds_is_a_config_error(repo, write):
    write("chapters/ch01.md", "prose\n")
    config(write, {**RULE_FORBID, "require": {"in": "chapters/*.md"}})

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 2
    assert "no AI-tic phrasing" in result.output


def test_a_rule_with_no_kind_is_a_config_error(repo, write):
    config(write, {"name": "shapeless", "extract": {"list": ["x"]}})

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 2
    assert "shapeless" in result.output


def test_list_shows_forbid_occurrences(repo, write):
    write("chapters/ch01.md", "one\ndelve\n")
    config(write, RULE_FORBID)

    result = runner.invoke(main, ["list", str(repo)])
    assert "chapters/ch01.md:2" in result.output


def test_list_omits_banned_entries_that_appear_nowhere(repo, write):
    write("chapters/ch01.md", "delve\n")
    config(write, RULE_FORBID)

    result = runner.invoke(main, ["list", str(repo)])
    assert "tapestry" not in result.output


# --- measure / expect rules (prose-linting slice 2) ---


def chapters(write, **bodies):
    for name, body in bodies.items():
        write(f"chapters/{name}.md", body)


# mean-sentence-length of 3.0, 4.0, 5.0 and 30.0 respectively
CH3 = "Aa bb cc. Dd ee ff.\n"
CH4 = "Aa bb cc dd. Ee ff gg hh.\n"
CH5 = "Aa bb cc dd ee. Ff gg hh ii jj.\n"
CH30 = "Zz " + " ".join(f"w{i}" for i in range(29)) + ".\n"


def measure_rule(**over):
    rule = {
        "name": "sentence rhythm",
        "measure": {"files": "chapters/*.md", "metric": "mean-sentence-length"},
    }
    rule.update(over)
    return rule


def test_measure_with_no_expect_reports_and_passes(repo, write):
    """Principle 2: rift ships no thresholds, so an absent expect always passes."""
    chapters(write, ch01=CH3)
    config(write, measure_rule())

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 0


def test_measure_min_fails_a_file_below_the_floor(repo, write):
    chapters(write, ch01=CH3)
    config(write, measure_rule(expect={"min": 4.0}))

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 1
    assert "ch01.md" in result.output


def test_measure_min_passes_a_file_above_the_floor(repo, write):
    chapters(write, ch01=CH5)
    config(write, measure_rule(expect={"min": 4.0}))

    assert runner.invoke(main, ["check", str(repo)]).exit_code == 0


def test_measure_max_fails_a_file_above_the_ceiling(repo, write):
    chapters(write, ch01=CH30)
    config(write, measure_rule(expect={"max": 10.0}))

    assert runner.invoke(main, ["check", str(repo)]).exit_code == 1


def test_measure_reports_the_number_and_the_threshold(repo, write):
    """rift reports a distance and what it was measured against — never a verdict."""
    chapters(write, ch01=CH3)
    config(write, measure_rule(expect={"min": 4.0}))

    output = runner.invoke(main, ["check", str(repo)]).output
    assert "3.00" in output
    assert "4.0" in output


def test_vs_siblings_fails_the_outlier(repo, write):
    chapters(write, ch01=CH3, ch02=CH4, ch03=CH5, ch04=CH30)
    config(write, measure_rule(expect={"vs-siblings": 2.0}))

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 1
    assert "ch04.md" in result.output


def test_vs_siblings_does_not_fail_the_conforming_files(repo, write):
    chapters(write, ch01=CH3, ch02=CH4, ch03=CH5, ch04=CH30)
    config(write, measure_rule(expect={"vs-siblings": 2.0}))

    output = runner.invoke(main, ["check", str(repo)]).output
    assert "ch01.md" not in output
    assert "ch02.md" not in output


def test_vs_siblings_flags_a_file_that_differs_from_identical_siblings(repo, write):
    """Leave-one-out sd is 0 here, but the held-out file is maximally outlying —
    the case the check most needs to catch, not a division to skip."""
    chapters(write, ch01=CH3, ch02=CH3, ch03=CH3, ch04=CH30)
    config(write, measure_rule(expect={"vs-siblings": 2.0}))

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 1
    assert "ch04.md" in result.output


def test_vs_siblings_passes_when_every_file_is_identical(repo, write):
    chapters(write, ch01=CH3, ch02=CH3, ch03=CH3, ch04=CH3)
    config(write, measure_rule(expect={"vs-siblings": 2.0}))

    assert runner.invoke(main, ["check", str(repo)]).exit_code == 0


def test_vs_siblings_on_a_small_set_warns_and_passes(repo, write):
    """It must not silently pass, and it must not fail — either would be a lie."""
    chapters(write, ch01=CH3, ch02=CH30)
    config(write, measure_rule(expect={"vs-siblings": 2.0}))

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 0
    assert "too small" in result.output


def test_list_shows_every_measured_file_with_its_value(repo, write):
    """`list` is the per-entity surface; for a measure rule the files are the
    entities. It used to crash on any measure rule, which made the whole
    command unusable in a config that mixes kinds."""
    chapters(write, ch01=CH3, ch02=CH5)
    config(write, measure_rule(expect={"min": 4.0}))

    result = runner.invoke(main, ["list", str(repo)])
    assert result.exit_code == 0
    assert "ch01.md" in result.output and "3.00" in result.output
    assert "ch02.md" in result.output and "5.00" in result.output
    assert "below min 4.0" in result.output


def test_measure_pattern_counts_a_caller_supplied_regex(repo, write):
    chapters(write, ch01="a {~one} b {~two}\n")
    config(write, {
        "name": "glossary markers",
        "measure": {"files": "chapters/*.md", "pattern": r'\{~[a-z]+\}'},
        "expect": {"max": 1},
    })

    assert runner.invoke(main, ["check", str(repo)]).exit_code == 1


def test_measure_burrows_delta_runs_over_the_set(repo, write):
    same = "the cat of the house and the dog of the garden and the bird of the tree\n"
    odd = "a cat in a house to a dog in a garden to a bird in a tree\n"
    chapters(write, ch01=same, ch02=same, ch03=same, ch04=odd)
    config(write, {
        "name": "voice",
        "measure": {"files": "chapters/*.md", "metric": "burrows-delta"},
        "expect": {"vs-siblings": 2.0},
    })

    result = runner.invoke(main, ["check", str(repo)])
    assert "ch04.md" in result.output


def test_an_unknown_metric_is_a_config_error(repo, write):
    chapters(write, ch01=CH3)
    config(write, measure_rule(measure={"files": "chapters/*.md", "metric": "vibes"}))

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 2
    assert "vibes" in result.output


def test_measure_counts_as_a_kind_for_the_multiplicity_check(repo, write):
    config(write, {**measure_rule(), "forbid": {"in": "chapters/*.md"}})

    assert runner.invoke(main, ["check", str(repo)]).exit_code == 2


# --- stats ---


def test_stats_exits_zero_with_no_config_file(repo, write):
    chapters(write, ch01=CH3)

    result = runner.invoke(main, ["stats", "chapters/*.md", "-p", str(repo)])
    assert result.exit_code == 0


def test_stats_reports_metric_names_and_files(repo, write):
    chapters(write, ch01=CH3, ch02=CH5)

    output = runner.invoke(main, ["stats", "chapters/*.md", "-p", str(repo)]).output
    assert "mean-sentence-length" in output
    assert "ch01" in output
    assert "ch02" in output


def test_stats_includes_burrows_delta(repo, write):
    chapters(write, ch01=CH3, ch02=CH5)

    output = runner.invoke(main, ["stats", "chapters/*.md", "-p", str(repo)]).output
    assert "burrows-delta" in output


def test_stats_never_judges_even_when_a_value_is_extreme(repo, write):
    chapters(write, ch01=CH30)

    result = runner.invoke(main, ["stats", "chapters/*.md", "-p", str(repo)])
    assert result.exit_code == 0
    assert "✗" not in result.output


def test_stats_on_an_empty_set_exits_zero(repo, write):
    result = runner.invoke(main, ["stats", "nothing/*.md", "-p", str(repo)])
    assert result.exit_code == 0


def test_measure_files_accepts_a_list_of_globs(repo, write):
    write("a/ch01.md", CH3)
    write("b/ch02.md", CH30)
    config(write, {
        "name": "rhythm across two dirs",
        "measure": {"files": ["a/*.md", "b/*.md"], "metric": "mean-sentence-length"},
        "expect": {"max": 10.0},
    })
    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 1
    assert "ch02.md" in result.output


def test_strip_changes_a_metric_by_removing_marker_text(repo, write):
    """Marker text inflates token counts and merges sentences; strip removes it."""
    body = "Short one. " + "[Tony Hoare]{~hoare-tony} " * 30 + "And a close.\n"
    write("chapters/ch01.md", body)
    config(write, {
        "name": "with markers",
        "measure": {"files": "chapters/*.md", "metric": "mean-sentence-length"},
        "expect": {"max": 100},
    })
    assert runner.invoke(main, ["check", str(repo)]).exit_code == 1

    config(write, {
        "name": "markers stripped",
        "measure": {"files": "chapters/*.md", "metric": "mean-sentence-length",
                    "strip": [r'\{~[^}]*\}']},
        "expect": {"max": 100},
    })
    assert runner.invoke(main, ["check", str(repo)]).exit_code == 0


def test_stats_accepts_repeatable_strip(repo, write):
    write("chapters/ch01.md", "Prose here. [X]{~key} More prose.\n")
    result = runner.invoke(main, ["stats", "chapters/*.md", "-p", str(repo),
                                  "-s", r'\{~[^}]*\}'])
    assert result.exit_code == 0


# --- forbid allowances: max_per_file and max_files ---

RULE_MARKERS = {
    "name": "markers",
    "extract": {"list": ["{~cpu}"]},
    "forbid": {"in": "chapters/*.md", "as": "mention", "max_per_file": 1},
}


def test_max_per_file_allows_the_first_occurrence(repo, write):
    write("chapters/ch01.md", "a {~cpu} b\n")
    config(write, RULE_MARKERS)
    assert runner.invoke(main, ["check", str(repo)]).exit_code == 0


def test_max_per_file_flags_only_the_excess(repo, write):
    write("chapters/ch01.md", "one {~cpu}\ntwo {~cpu}\nthree {~cpu}\n")
    config(write, RULE_MARKERS)
    out = runner.invoke(main, ["check", str(repo)])
    assert out.exit_code == 1
    assert "2 occurrences" in out.output      # the 2nd and 3rd, not all three
    assert "ch01.md:2" in out.output and "ch01.md:3" in out.output
    assert "ch01.md:1" not in out.output


def test_max_per_file_counts_per_file_not_across_the_set(repo, write):
    write("chapters/ch01.md", "{~cpu}\n")
    write("chapters/ch02.md", "{~cpu}\n")
    config(write, RULE_MARKERS)
    assert runner.invoke(main, ["check", str(repo)]).exit_code == 0


def test_default_is_still_zero_tolerance(repo, write):
    """Absent both keys, forbid means what it always meant."""
    write("chapters/ch01.md", "{~cpu}\n")
    config(write, {**RULE_MARKERS, "forbid": {"in": "chapters/*.md", "as": "mention"}})
    assert runner.invoke(main, ["check", str(repo)]).exit_code == 1


RULE_LABELS = {
    "name": "footnote labels",
    "extract": {"list": ["[^brooks]:"]},
    "forbid": {"in": "chapters/*.md", "as": "mention", "max_files": 1},
}


def test_max_files_allows_one_file(repo, write):
    write("chapters/ch01.md", "[^brooks]: A citation.\n")
    config(write, RULE_LABELS)
    assert runner.invoke(main, ["check", str(repo)]).exit_code == 0


def test_max_files_flags_the_second_file(repo, write):
    write("chapters/ch01.md", "[^brooks]: A citation.\n")
    write("chapters/ch02.md", "[^brooks]: A different citation.\n")
    config(write, RULE_LABELS)
    out = runner.invoke(main, ["check", str(repo)])
    assert out.exit_code == 1
    assert "ch02.md" in out.output
    assert "ch01.md" not in out.output


def test_max_files_does_not_apply_the_zero_default_per_file(repo, write):
    """Setting only max_files must not make every occurrence a violation."""
    write("chapters/ch01.md", "[^brooks]: One.\nand again [^brooks]:\n")
    config(write, RULE_LABELS)
    assert runner.invoke(main, ["check", str(repo)]).exit_code == 0
