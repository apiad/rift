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


def test_an_unknown_metric_is_a_config_error_under_list_too(repo, write):
    """`list` had no ConfigError handler, so a bad metric tracebacked there."""
    chapters(write, ch01=CH3)
    config(write, measure_rule(measure={"files": "chapters/*.md", "metric": "vibes"}))

    result = runner.invoke(main, ["list", str(repo)])
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


# --- permit (slice D) ---

PERMIT_RULE = {
    "name": "accepted vocabulary",
    "severity": "error",
    "extract": {"file": "dict/words.txt", "lines": True},
    "permit": {"in": "chapters/*.md"},
}


def test_check_fails_on_a_token_outside_the_permitted_set(repo, write):
    write("dict/words.txt", "alpha\nbeta\n")
    write("chapters/ch01.md", "alpha beta gamma\n")
    config(write, PERMIT_RULE)

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 1
    assert "gamma" in result.output
    assert "unpermitted" in result.output


def test_check_passes_when_every_token_is_permitted(repo, write):
    write("dict/words.txt", "alpha\nbeta\n")
    write("chapters/ch01.md", "alpha beta\n")
    config(write, PERMIT_RULE)

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 0


def test_list_ranks_unpermitted_tokens_by_frequency(repo, write):
    """The triage surface. `check` reports sites; `list` reports vocabulary,
    because a thousand flat sites is not a worklist and a ranked vocabulary is.
    """
    write("dict/words.txt", "alpha\n")
    write("chapters/ch01.md", "alpha zzz zzz\nzzz qqq alpha\n")
    config(write, PERMIT_RULE)

    result = runner.invoke(main, ["list", str(repo)])
    assert result.exit_code == 0
    assert result.output.index("zzz") < result.output.index("qqq")


def test_check_exits_two_on_a_malformed_of_pattern(repo, write):
    """A typo'd pattern must fail loudly, not make the rule silently green."""
    write("dict/words.txt", "alpha\n")
    write("chapters/ch01.md", "alpha\n")
    config(write, {**PERMIT_RULE, "permit": {"in": "chapters/*.md", "of": "[unclosed"}})

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 2
    # Pin the reason, not just the code: before `permit` had a branch, an
    # unhandled kind fell into `measure` and exited 2 for an unrelated reason.
    assert "malformed of:" in result.output


def test_an_unhandled_rule_kind_fails_loudly_instead_of_being_measured(repo, write):
    """The regression guard for `14ce59e`.

    `check` and `list` dispatched `if require / elif forbid / else measure`, so
    any kind without a branch was silently treated as a measure rule. This pins
    the `else` that replaced that fallback.
    """
    import rift.cli as cli_module

    write("chapters/ch01.md", "alpha\n")
    config(write, {"name": "bogus", "bogus": {"in": "chapters/*.md"}})
    monkey = cli_module.RULE_KINDS
    cli_module.RULE_KINDS = monkey + ("bogus",)
    try:
        result = runner.invoke(main, ["check", str(repo)])
    finally:
        cli_module.RULE_KINDS = monkey
    assert result.exit_code == 2
    assert "no handler" in result.output


def test_a_rule_carrying_permit_and_forbid_is_rejected(repo, write):
    write("dict/words.txt", "alpha\n")
    config(write, {**PERMIT_RULE, "forbid": {"in": "chapters/*.md"}})

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 2
    assert "more than one kind" in result.output


# --- zone validation (slice 2) ---

import pytest

from rift.cli import ConfigError, _validate_zone

PARA_ZONE = {"unit": "paragraph", "index": [0]}


def zoned_forbid(zone=PARA_ZONE, **over):
    rule = {
        "name": "zoned ban",
        "extract": {"list": ["delve"]},
        "forbid": {"in": "chapters/*.md", "as": "word", "zone": zone},
    }
    rule.update(over)
    return rule


def test_a_zone_carrying_both_forms_is_a_config_error(repo, write):
    config(write, zoned_forbid({"unit": "paragraph", "after": "SEP"}))

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 2
    assert "zoned ban" in result.output


def test_a_zone_on_a_require_rule_is_a_config_error(repo, write):
    config(write, {
        "name": "zoned require",
        "extract": {"list": ["promise"]},
        "require": {"in": "chapters/*.md", "as": "word", "zone": PARA_ZONE},
    })

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 2
    assert "zoned require" in result.output
    assert "per_file" in result.output


def test_a_zone_beside_require_exists_is_a_config_error(repo, write):
    config(write, {
        "name": "zoned exists",
        "extract": {"list": ["README.md"]},
        "require": {"exists": True, "zone": PARA_ZONE},
    })

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 2
    assert "zoned exists" in result.output


def test_an_unknown_unit_is_a_config_error(repo, write):
    config(write, zoned_forbid({"unit": "chapter", "index": [0]}))

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 2
    assert "chapter" in result.output


def test_an_unknown_zone_key_is_a_config_error(repo, write):
    config(write, zoned_forbid({"unit": "paragraph", "indices": [0]}))

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 2
    assert "indices" in result.output


def test_an_empty_zone_is_a_config_error(repo, write):
    config(write, zoned_forbid({}))

    assert runner.invoke(main, ["check", str(repo)]).exit_code == 2


def test_a_non_integer_index_is_a_config_error(repo, write):
    config(write, zoned_forbid({"unit": "paragraph", "index": "first"}))

    assert runner.invoke(main, ["check", str(repo)]).exit_code == 2


def test_a_malformed_bound_pattern_is_a_config_error(repo, write):
    """`find` swallows re.error, which would make a typo'd bound silently green."""
    config(write, zoned_forbid({"after": "([unclosed"}))

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 2
    assert "zoned ban" in result.output


def zoned_measure(zone=PARA_ZONE, expect=None, **spec):
    measure = {"files": "chapters/*.md", "zone": zone}
    measure.update(spec)
    rule = {"name": "zoned measure", "measure": measure}
    if expect is not None:
        rule["expect"] = expect
    return rule


def test_a_statistical_metric_with_a_zone_is_a_config_error():
    with pytest.raises(ConfigError):
        _validate_zone(zoned_measure(metric="sentence-length-cv"), "measure")


def test_burrows_delta_with_a_zone_is_a_config_error():
    """The one a `vs-siblings`-only guard would have missed: it is not an
    `expect` predicate and it is not in `METRICS`."""
    with pytest.raises(ConfigError):
        _validate_zone(zoned_measure(metric="burrows-delta"), "measure")


def test_word_count_with_a_zone_is_accepted():
    """Pinned from both sides: asserting only the rejections passes against a
    blanket ban, which would drop the case the allowlist exists to serve."""
    _validate_zone(zoned_measure(metric="word-count"), "measure")


def test_a_raw_pattern_count_with_a_zone_is_accepted():
    _validate_zone(zoned_measure(pattern=r"\*\*"), "measure")


def test_per_with_a_zone_is_a_config_error():
    """`per:` turns an exact count into a ratio, back among the statistics."""
    with pytest.raises(ConfigError):
        _validate_zone(zoned_measure(pattern=r"\*\*", per=1000), "measure")


def test_vs_siblings_with_a_zone_is_a_config_error():
    """`pattern:` is not a `metric:`, so the allowlist guard alone misses this."""
    with pytest.raises(ConfigError):
        _validate_zone(zoned_measure(pattern=r"\*\*", expect={"vs-siblings": 2.0}),
                       "measure")


def test_a_bad_zone_in_the_last_rule_stops_the_run_before_any_output(repo, write):
    """What pins up-front validation. An exit-code-only test passes against a
    mid-run raise."""
    write("chapters/ch01.md", "Aa bb cc.\n")
    good = [{**RULE_OK, "name": f"rule {i}"} for i in range(19)]
    write("compose.yml", "services:\n  api: {}\n")
    write("docs/design.md", "the api service\n")
    config(write, *good, zoned_forbid({"unit": "chapter"}, name="rule 20"))

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 2
    assert "rule 1" not in result.output
    assert "19 rules" not in result.output


def test_a_well_formed_zone_exits_two_until_its_slice_lands(repo, write):
    """Deleted slice by slice. A `zone:` that validates but is wired to nothing
    would lint the whole file and report a green tick — a rule that cannot fail,
    on main, in a repo whose ethos is that such a rule is worse than none."""
    write("chapters/ch01.md", "Delve here.\n")
    config(write, zoned_measure(metric="word-count"))

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 2
    assert "zoned measure" in result.output


def test_the_degenerate_set_guard_counts_files_not_entries():
    """Zoned keys put several entries on one file. Counting entries would judge
    a two-file set against "siblings" that are its own other zones."""
    from pathlib import Path

    from rift.cli import _apply_expect

    values = {(Path("a.md"), i): float(i) for i in range(3)}
    values.update({(Path("b.md"), i): float(i) for i in range(3)})
    _, notes = _apply_expect(values, {"vs-siblings": 2.0})
    assert notes and "set of 2" in notes[0]


# --- zoned forbid and permit (slice 3) ---

# `delve` appears twice: once inside the delimited region, once outside it. A
# fixture with the word only inside cannot tell a working zone from one that is
# ignored entirely.
ZONED_DOC = """\
Opening prose, where we delve early.

\\sep2

Middle prose, where we delve again.

\\sep3

Closing prose, plain.
"""

OUT_OF_ZONE_ONLY = """\
Opening prose, where we delve early.

\\sep2

Middle prose, plain.

\\sep3

Closing prose, plain.
"""


def delimited_forbid(**over):
    forbid = {
        "in": "chapters/*.md",
        "as": "word",
        "zone": {"after": r"\\sep2", "before": r"\\sep3"},
    }
    forbid.update(over)
    return {"name": "zoned ban", "extract": {"list": ["delve"]}, "forbid": forbid}


def test_a_zoned_forbid_ignores_an_occurrence_outside_the_zone(repo, write):
    """THE test. Asserting only the in-zone hit passes against an
    implementation that ignores `zone:` entirely."""
    write("chapters/ch01.md", OUT_OF_ZONE_ONLY)
    config(write, delimited_forbid())

    assert runner.invoke(main, ["check", str(repo)]).exit_code == 0


def test_a_zoned_forbid_still_finds_an_occurrence_inside_the_zone(repo, write):
    write("chapters/ch01.md", ZONED_DOC)
    config(write, delimited_forbid())

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 1
    assert "1 occurrences" in result.output


def test_a_structural_zone_selects_the_section_it_names(repo, write):
    write("chapters/ch01.md",
          "# Title\n\nOpening.\n\n## One\n\nClean here.\n\n## Two\n\nWe delve here.\n")
    config(write, {
        "name": "zoned ban",
        "extract": {"list": ["delve"]},
        "forbid": {"in": "chapters/*.md", "as": "word",
                   "zone": {"unit": "section", "index": [1]}},
    })

    assert runner.invoke(main, ["check", str(repo)]).exit_code == 0


def test_a_match_straddling_the_zone_edge_is_not_a_site(repo, write):
    """`_word_pattern` joins words with `\\s+` and spans a blank line, so
    matches genuinely straddle edges. Filtering on the start offset alone would
    report a match that mostly lies outside."""
    write("chapters/ch01.md", "head\n\nMARK\n\nrich\nhistory here\n")
    config(write, {
        "name": "zoned ban",
        "extract": {"list": ["rich history"]},
        "forbid": {"in": "chapters/*.md", "as": "word",
                   "zone": {"after": "MARK", "before": "history"}},
    })

    assert runner.invoke(main, ["check", str(repo)]).exit_code == 0


def test_a_zoned_forbid_reports_a_file_whose_zone_matched_nothing(repo, write):
    write("chapters/ch01.md", "No separators at all, but we delve here.\n")
    config(write, delimited_forbid())

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 1
    assert "zone matched nothing" in result.output
    assert "chapters/ch01.md" in result.output


def test_one_unresolved_entry_per_file_not_per_entity(repo, write):
    """A single broken bound over a 411-entry glossary would otherwise bury
    every real finding under identical entries."""
    write("chapters/ch01.md", "no bounds here\n")
    write("chapters/ch02.md", "none here either\n")
    config(write, {**delimited_forbid(),
                   "extract": {"list": ["delve", "tapestry", "seamlessly"]}})

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 1
    assert "2 occurrences" in result.output
    assert ":0" not in result.output


def test_an_unreadable_file_is_not_reported_as_an_unresolvable_zone(repo, write):
    """Both `find` and `_zoned_spans` swallow read errors. The two lists stay
    apart, or a file nobody can read is blamed on the zone."""
    write("chapters/ch01.md", ZONED_DOC)
    (repo / "chapters" / "ch02.md").write_bytes(b"\xff\xfe not utf-8 \xff")
    config(write, delimited_forbid())

    result = runner.invoke(main, ["check", str(repo)])
    assert "zone matched nothing" not in result.output


def test_list_prints_an_unresolved_zone_and_still_exits_zero(repo, write):
    """`list` reports, it never judges — including on a rule `check` fails."""
    write("chapters/ch01.md", "no bounds here\n")
    config(write, delimited_forbid())

    result = runner.invoke(main, ["list", str(repo)])
    assert result.exit_code == 0
    assert "zone matched nothing" in result.output


# The motivating delimited bound is a renderer macro, which is exactly what
# `strip:` is for. `permit` is the kind that strips.
# Exactly the tokens of the zoned region — "Middle prose, where we delve again."
# Nothing outside it is listed, so a zone that is ignored flags the whole file.
PERMIT_ALLOWED = ["Middle", "prose", "where", "we", "delve", "again"]


def zoned_permit(**over):
    permit = {
        "in": "chapters/*.md",
        "strip": [r"\\sep\d"],
        "zone": {"after": r"\\sep2", "before": r"\\sep3"},
    }
    permit.update(over)
    return {"name": "zoned permit",
            "extract": {"list": PERMIT_ALLOWED},
            "permit": permit}


def test_a_delimited_zone_survives_a_strip_that_targets_its_own_bound(repo, write):
    """Mask, then resolve zones, then strip. Ordering the strip first blanks
    the bound before any zone can see it, and every zone in the rule becomes
    unresolvable."""
    write("chapters/ch01.md", ZONED_DOC)
    config(write, zoned_permit())

    result = runner.invoke(main, ["check", str(repo)])
    assert "zone matched nothing" not in result.output


def test_a_zoned_permit_ignores_a_token_outside_the_zone(repo, write):
    write("chapters/ch01.md", ZONED_DOC.replace("Opening", "Bogusword"))
    config(write, zoned_permit())

    assert runner.invoke(main, ["check", str(repo)]).exit_code == 0


def test_a_zoned_permit_still_flags_a_token_inside_the_zone(repo, write):
    write("chapters/ch01.md", ZONED_DOC.replace("Middle", "Bogusword"))
    config(write, zoned_permit())

    result = runner.invoke(main, ["check", str(repo)])
    assert result.exit_code == 1
    assert "Bogusword" in result.output
