from rift.extractor import extract

COMPOSE = """\
services:
  api:
    image: api:1
  worker:
    image: worker:1
volumes:
  data: {}
"""


def test_yaml_keys_reads_the_named_mapping(repo, write):
    write("compose.yml", COMPOSE)
    assert extract(repo, {"file": "compose*.yml", "yaml_keys": "services"}) == {"api", "worker"}


def test_yaml_keys_navigates_a_dotted_path(repo, write):
    write("stack.yml", "a:\n  b:\n    leaf: 1\n    other: 2\n")
    assert extract(repo, {"file": "stack.yml", "yaml_keys": "a.b"}) == {"leaf", "other"}


def test_yaml_keys_unions_across_every_glob_match(repo, write):
    write("compose.yml", COMPOSE)
    write("compose.prod.yml", "services:\n  cron:\n    image: cron:1\n")
    got = extract(repo, {"file": "compose*.yml", "yaml_keys": "services"})
    assert got == {"api", "worker", "cron"}


def test_yaml_keys_on_a_missing_path_yields_nothing(repo, write):
    write("compose.yml", COMPOSE)
    assert extract(repo, {"file": "compose.yml", "yaml_keys": "nope.nothere"}) == set()


def test_yaml_values_of_a_mapping(repo, write):
    write("compose.yml", COMPOSE)
    assert extract(repo, {"file": "compose.yml", "yaml_values": "services.api"}) == {"api:1"}


def test_yaml_values_of_a_list(repo, write):
    write("stack.yml", "targets:\n  - alpha\n  - beta\n")
    assert extract(repo, {"file": "stack.yml", "yaml_values": "targets"}) == {"alpha", "beta"}


def test_env_names_skips_comments_and_blanks(repo, write):
    write(
        ".env.example",
        "# a comment\nAPI_URL=http://x\n\nDB_PASSWORD=\n  INDENTED=1\nlowercase=1\n",
    )
    assert extract(repo, {"file": ".env.example", "env_names": True}) == {"API_URL", "DB_PASSWORD"}


def test_regex_returns_the_first_capture_group_when_there_is_one(repo, write):
    write("release/versions.env", "API_VERSION=1.2\nSANDBOX_BASE_VERSION=0.9\n")
    got = extract(
        repo,
        {"file": "release/versions.env", "regex": r"^([A-Z]+(?:_[A-Z]+)*)_VERSION="},
    )
    assert got == {"API", "SANDBOX_BASE"}


def test_regex_returns_the_whole_match_when_there_is_no_group(repo, write):
    write("docs/design.md", "see compose.devmount.yml and compose.localhost.yml\n")
    got = extract(repo, {"file": "docs/design.md", "regex": r"compose\.\w+\.ya?ml"})
    assert got == {"compose.devmount.yml", "compose.localhost.yml"}


def test_files_extractor_returns_stems(repo, write):
    write("apps/one.py", "")
    write("apps/two.py", "")
    assert extract(repo, {"files": "apps/*.py"}) == {"one", "two"}


def test_dirs_with_returns_the_parent_directory_name(repo, write):
    write("apps/alpha/Dockerfile", "FROM x")
    write("apps/beta/Dockerfile", "FROM y")
    assert extract(repo, {"dirs_with": "**/Dockerfile"}) == {"alpha", "beta"}


def test_dirs_with_skips_vendored_and_build_directories(repo, write):
    write("apps/alpha/Dockerfile", "FROM x")
    write("node_modules/pkg/Dockerfile", "FROM z")
    write(".venv/thing/Dockerfile", "FROM z")
    assert extract(repo, {"dirs_with": "**/Dockerfile"}) == {"alpha"}


def test_a_file_pattern_matching_nothing_yields_nothing(repo):
    assert extract(repo, {"file": "compose*.yml", "yaml_keys": "services"}) == set()


def test_unparseable_yaml_yields_nothing_instead_of_raising(repo, write):
    """Known gap: a broken source file makes its rule pass vacuously.

    extractor.extract swallows every exception, so a rule whose source file is
    malformed reports zero entities — and zero entities is indistinguishable
    from "everything is documented". Pinned here so the behaviour is a
    deliberate, visible choice rather than a silent one.
    """
    write("compose.yml", "services:\n  api:\n   - bad\n  : : :\n")
    assert extract(repo, {"file": "compose.yml", "yaml_keys": "services"}) == set()


# --- list: and lines: (prose-linting slice 1) ---


def test_list_yields_its_literal_entries(repo):
    assert extract(repo, {"list": ["delve", "tapestry"]}) == {"delve", "tapestry"}


def test_list_is_standalone_and_ignores_a_file_key(repo, write):
    write("data/other.yaml", "a: b\n")
    assert extract(repo, {"list": ["delve"], "file": "data/other.yaml"}) == {"delve"}


def test_list_preserves_multi_word_phrases(repo):
    assert extract(repo, {"list": ["rich history of"]}) == {"rich history of"}


def test_list_coerces_non_strings(repo):
    assert extract(repo, {"list": [42]}) == {"42"}


def test_lines_yields_each_non_empty_line(repo, write):
    write("prose/banned.txt", "delve\ntapestry\n")
    assert extract(repo, {"file": "prose/banned.txt", "lines": True}) == {"delve", "tapestry"}


def test_lines_skips_comments_and_blanks(repo, write):
    write("prose/banned.txt", "# AI-tic phrases\n\ndelve\n\n#another\ntapestry\n")
    assert extract(repo, {"file": "prose/banned.txt", "lines": True}) == {"delve", "tapestry"}


def test_lines_strips_surrounding_whitespace(repo, write):
    write("prose/banned.txt", "  delve  \n")
    assert extract(repo, {"file": "prose/banned.txt", "lines": True}) == {"delve"}


def test_lines_keeps_internal_spaces_so_phrases_survive(repo, write):
    write("prose/banned.txt", "rich history of\n")
    assert extract(repo, {"file": "prose/banned.txt", "lines": True}) == {"rich history of"}


# --- paths: (the non-lossy sibling of files:) ---


def test_paths_yields_the_relative_path_not_the_stem(repo, write):
    write("a/one.md", "x")
    assert extract(repo, {"paths": "a/*.md"}) == {"a/one.md"}


def test_paths_keeps_same_named_files_in_different_dirs_distinct(repo, write):
    """`files:` collapses these to one stem; that hides an orphaned file."""
    write("a/index.md", "x")
    write("b/index.md", "x")
    assert extract(repo, {"files": "*/index.md"}) == {"index"}
    assert extract(repo, {"paths": "*/index.md"}) == {"a/index.md", "b/index.md"}


def test_paths_accepts_a_list_of_globs(repo, write):
    write("a/one.md", "x")
    write("b/two.md", "x")
    assert extract(repo, {"paths": ["a/*.md", "b/*.md"]}) == {"a/one.md", "b/two.md"}


def test_paths_ignores_directories(repo, write):
    write("a/one.md", "x")
    (repo / "a" / "sub.md").mkdir(parents=True)
    assert extract(repo, {"paths": "a/*"}) == {"a/one.md"}


def test_file_accepts_a_list_of_globs(repo, write):
    write("a/one.md", "KEY_A=1\n")
    write("b/two.md", "KEY_B=1\n")
    assert extract(repo, {"file": ["a/*.md", "b/*.md"], "env_names": True}) == {"KEY_A", "KEY_B"}


def test_file_as_a_list_works_for_regex_too(repo, write):
    write("a/one.md", "[~alpha]\n")
    write("b/two.md", "[~beta]\n")
    got = extract(repo, {"file": ["a/*.md", "b/*.md"], "regex": r'\[~([a-z]+)\]'})
    assert got == {"alpha", "beta"}
