"""Rules for media that the extended checker must never flag."""

from __future__ import annotations

from collections.abc import Iterable

# Anki itself generates LaTeX assets with the ``latex-`` prefix (see
# aqt.mediacheck's generated-LaTeX check).  ``anki.latex`` intentionally does
# not expose a public filename matcher, so mirroring that upstream convention
# is the most forward-compatible way to identify both PNG and SVG output.
LATEX_GENERATED_PREFIX = "latex-"


def is_exempt(filename: str) -> bool:
    """Return whether *filename* must be excluded from deletion candidates."""

    basename = filename.replace("\\", "/").rsplit("/", maxsplit=1)[-1]
    return basename.startswith("_") or basename.startswith(LATEX_GENERATED_PREFIX)


def filter_candidates(filenames: Iterable[str]) -> list[str]:
    """Return non-exempt filenames, preserving their supplied order."""

    return [filename for filename in filenames if not is_exempt(filename)]
