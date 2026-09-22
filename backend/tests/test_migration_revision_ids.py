from __future__ import annotations

import re
from pathlib import Path


def test_migration_revision_ids_fit_postgres_version_column() -> None:
    """PostgreSQL's default Alembic version column is VARCHAR(32)."""

    versions_dir = Path(__file__).parents[1] / "alembic" / "versions"
    revision_pattern = re.compile(r'^revision:\s*str\s*=\s*"([^"]+)"', re.MULTILINE)
    revisions: dict[str, int] = {}

    for migration in sorted(versions_dir.glob("*.py")):
        match = revision_pattern.search(migration.read_text(encoding="utf-8"))
        assert match is not None, f"Missing revision id: {migration.name}"
        revisions[match.group(1)] = len(match.group(1))

    too_long = {revision: length for revision, length in revisions.items() if length > 32}
    assert not too_long, f"Alembic revision ids exceed VARCHAR(32): {too_long}"
