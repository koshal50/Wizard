"""pytest configuration — makes src/ importable without editable install."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
