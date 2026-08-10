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
