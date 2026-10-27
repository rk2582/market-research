"""Milestone 2 smoke tests: the environment is set up as the plan says."""

import subprocess  # nosec B404 - used only to call git with fixed arguments
import sys
from importlib.metadata import version
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_python_version_is_312():
    assert sys.version_info[:2] == (3, 12)


def test_agno_is_pinned_to_reference_version():
    assert version("agno") == "2.9.0"


def test_core_packages_import():
    import agno.agent  # noqa: F401
    import agno.os  # noqa: F401
    import agno.workflow  # noqa: F401
    import fastapi  # noqa: F401
    import sqlalchemy.ext.asyncio  # noqa: F401


def test_no_real_env_files_are_tracked_by_git():
    """Guard against committing secrets (this happened in the reference repo)."""
    result = subprocess.run(  # nosec B603 B607 - fixed command, no user input
        ["git", "ls-files"],  # noqa: S607
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:  # not a git checkout (e.g. unzipped copy) — nothing to check
        return
    tracked = [Path(p).name for p in result.stdout.splitlines()]
    leaked = [n for n in tracked if n.startswith(".env") and not n.endswith(".example")]
    assert leaked == [], f"Real env files are tracked by git: {leaked}"


def test_env_example_lists_required_keys():
    text = (REPO_ROOT / "backend" / ".env.example").read_text()
    for key in ("DATABASE_URL", "OPENAI_API_KEY", "TAVILY_API_KEY", "DEFAULT_MODEL"):
        assert f"{key}=" in text
