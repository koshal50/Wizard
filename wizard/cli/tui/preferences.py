"""Local display choices only. No credentials or project state."""
import json
import os
from pathlib import Path
import tempfile

from platformdirs import user_config_dir


PREFERENCES = Path(user_config_dir("wizard")) / "interface.json"
KEYS = {"intro_seen", "motion", "guide"}


def load_preferences(path=PREFERENCES):
    try:
        if path.stat().st_size > 4096:
            return {}
        value = json.loads(path.read_text(encoding="utf-8"))
        return {key: item for key, item in value.items() if key in KEYS and isinstance(item, bool)} if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save_preferences(value, path=PREFERENCES):
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = stream.name
            json.dump({key: item for key, item in value.items() if key in KEYS and isinstance(item, bool)}, stream)
        os.replace(temporary, path)
        return True
    except OSError:
        return False  # An unwritable display preference must not stop the CLI.
    finally:
        if temporary and os.path.exists(temporary):
            try:
                os.unlink(temporary)
            except OSError:
                pass
