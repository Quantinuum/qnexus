"""Utilities for qnexus-filesystem interactions."""

import json
from pathlib import Path

from qnexus.models.references import Ref, deserialize_nexus_ref


def save(ref: Ref, path: Path, mkdir: bool = False) -> None:
    """Save a Nexus Ref to a file.

    Examples:
        >>> import qnexus as qnx
        >>> from pathlib import Path
        >>> project_ref = qnx.projects.get(name="my-project")
        >>> qnx.filesystem.save(project_ref, Path("my_project.json"))

        >>> qnx.filesystem.save(project_ref, Path("data/refs/project.json"), mkdir=True)
    """
    if mkdir:
        path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(ref.model_dump_json())


def load(path: Path) -> Ref:
    """Load a Nexus Ref from a file.

    Examples:
        >>> import qnexus as qnx
        >>> from pathlib import Path
        >>> project_ref = qnx.filesystem.load(Path("my_project.json"))
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return deserialize_nexus_ref(data)
