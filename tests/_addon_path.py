"""Make pure addon modules importable without importing the Qt entry point."""

import sys
from pathlib import Path

ADDON_DIR = Path(__file__).parents[1] / "check_media_extended"
sys.path.insert(0, str(ADDON_DIR))
