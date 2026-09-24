"""Make pure addon modules importable without importing the Qt entry point."""

import sys
from pathlib import Path

ADDON_DIR = Path(__file__).parents[1] / "better_check_media_lenient"
sys.path.insert(0, str(ADDON_DIR))
