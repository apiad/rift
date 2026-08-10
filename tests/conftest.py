import pytest


@pytest.fixture
def repo(tmp_path):
    """A throwaway project root."""
    return tmp_path


@pytest.fixture
def write(repo):
    """write("docs/design.md", "...") -> Path, creating parent dirs."""

    def _write(relpath: str, content: str):
        target = repo / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return target

    return _write
