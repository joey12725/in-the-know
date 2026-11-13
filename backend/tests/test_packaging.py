import tomllib
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _normalize(requirement: str) -> str:
    return requirement.strip().lower().replace("_", "-")


def test_vercel_requirements_match_pyproject() -> None:
    """Vercel installs from requirements.txt; make sure it never drifts from pyproject.toml."""
    pyproject = tomllib.loads((BACKEND / "pyproject.toml").read_text())
    declared = {_normalize(dep) for dep in pyproject["project"]["dependencies"]}
    lines = (BACKEND / "requirements.txt").read_text().splitlines()
    pinned = {_normalize(line) for line in lines if line.strip() and not line.startswith("#")}
    assert pinned == declared
