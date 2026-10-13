import json
from pathlib import Path

_FILE_KEYS = {"flanges": "actions_file", "submodels": "tensors_file"}


def load_project(path: Path | str) -> dict:
    """Load a project JSON fixture, resolving data file paths relative to it."""
    path = Path(path)
    project = json.loads(path.read_text(encoding="utf-8"))
    for section, key in _FILE_KEYS.items():
        for entry in project.get(section, []):
            if entry.get(key):
                entry[key] = str((path.parent / entry[key]).resolve())
    return project
