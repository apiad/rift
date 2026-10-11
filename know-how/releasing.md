---
when: cutting a rift release, or checking that a published tag installs for someone who is not you
---

# Releasing rift

A release is a `vX.Y.Z` tag. Pushing it runs `.github/workflows/release.yml`,
which gates on the suite and on `rift check`, refuses a tag that disagrees with
`pyproject.toml`, builds the sdist and wheel, and publishes a GitHub Release whose
body is the CHANGELOG section for that version. The comments in the workflow say
why each gate is there.

## The steps

1. Bump `version` in `pyproject.toml`.
2. Run `uv lock`. This is the step that gets forgotten. Both workflows run
   `uv sync --locked`, so a stale lock fails the build instead of shipping, but
   v0.2.0 was cut by hand before that existed, with the lock still at `0.1.0`,
   and every local check passed because an editable install never re-resolves.
3. Rename `## [Unreleased]` in `CHANGELOG.md` to `## [vX.Y.Z] - YYYY-MM-DD` and
   open a fresh empty `## [Unreleased]` above it. The workflow finds the notes by
   that exact heading and falls back to generated notes, with a warning, when it
   is missing.
4. Run `uv run pytest -q` and `uv run rift check .`, then commit the three files
   on `main` as `chore(release): vX.Y.Z`.
5. `git tag -a vX.Y.Z -m vX.Y.Z`, then push `main` and the tag.

## Where it is published

GitHub Releases only. rift is not on PyPI (`tasks.md` holds that open question),
so anyone installing it pins the git tag:

```bash
uvx --from git+https://github.com/apiad/rift@vX.Y.Z rift check .
```

## Verify the artifact, not the run

A green workflow and an installable release are different claims. After the run:

```bash
gh release view vX.Y.Z --json isDraft,assets
```

Then install from the tag the way a stranger would: no GitHub token, no SSH
agent, no uv cache, no git config that could rewrite the URL.

```bash
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME="$(mktemp -d)" \
  GIT_TERMINAL_PROMPT=0 GIT_CONFIG_NOSYSTEM=1 \
  uvx --from git+https://github.com/apiad/rift@vX.Y.Z rift check .
```

Run it in a scratch project whose `.rift.yaml` exercises what the release added.
Check that uv's "Built rift @ git+…@<sha>" line names the tagged commit. Then
break the project on purpose and confirm the exit code turns 1. v0.9.0 was
checked this way: one pass, three deliberate breaks that each exited 1 and named
the missing value, and a malformed pattern that exited 2.
