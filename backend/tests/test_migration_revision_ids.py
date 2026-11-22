from __future__ import annotations

import ast
import re
from pathlib import Path

VERSIONS_DIR = Path(__file__).parents[1] / "alembic" / "versions"


def _migration_graph() -> dict[str, str | None]:
    graph: dict[str, str | None] = {}
    for migration in sorted(VERSIONS_DIR.glob("*.py")):
        tree = ast.parse(migration.read_text(encoding="utf-8"), filename=migration.name)
        values: dict[str, object] = {}
        for node in tree.body:
            if (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id in {"revision", "down_revision"}
                and node.value is not None
            ):
                values[node.target.id] = ast.literal_eval(node.value)

        revision = values.get("revision")
        down_revision = values.get("down_revision")
        assert isinstance(revision, str), f"Missing revision id: {migration.name}"
        assert down_revision is None or isinstance(down_revision, str), (
            f"Unsupported down_revision in {migration.name}: {down_revision!r}"
        )
        assert revision not in graph, f"Duplicate revision id: {revision}"
        graph[revision] = down_revision
    return graph


def test_migration_revision_ids_fit_postgres_version_column() -> None:
    """PostgreSQL's default Alembic version column is VARCHAR(32)."""

    revision_pattern = re.compile(r'^revision:\s*str\s*=\s*"([^"]+)"', re.MULTILINE)
    revisions: dict[str, int] = {}

    for migration in sorted(VERSIONS_DIR.glob("*.py")):
        match = revision_pattern.search(migration.read_text(encoding="utf-8"))
        assert match is not None, f"Missing revision id: {migration.name}"
        revisions[match.group(1)] = len(match.group(1))

    too_long = {revision: length for revision, length in revisions.items() if length > 32}
    assert not too_long, f"Alembic revision ids exceed VARCHAR(32): {too_long}"


def test_migration_graph_has_one_root_one_head_and_no_missing_parent() -> None:
    """A blank database must have one unambiguous upgrade path to the current head."""

    graph = _migration_graph()
    roots = {revision for revision, parent in graph.items() if parent is None}
    referenced_parents = {parent for parent in graph.values() if parent is not None}
    missing_parents = referenced_parents - graph.keys()
    heads = graph.keys() - referenced_parents

    assert roots == {"0001_line_foundation"}
    assert not missing_parents, f"Missing migration parents: {sorted(missing_parents)}"
    assert len(heads) == 1, f"Expected one Alembic head, found: {sorted(heads)}"


def test_every_migration_is_reachable_from_the_single_head() -> None:
    """Catch an accidentally detached migration before it reaches a blank DB rebuild."""

    graph = _migration_graph()
    referenced_parents = {parent for parent in graph.values() if parent is not None}
    head = next(iter(graph.keys() - referenced_parents))
    visited: set[str] = set()
    current: str | None = head

    while current is not None:
        assert current not in visited, f"Migration cycle detected at {current}"
        visited.add(current)
        current = graph[current]

    assert visited == graph.keys(), f"Detached migrations: {sorted(graph.keys() - visited)}"
