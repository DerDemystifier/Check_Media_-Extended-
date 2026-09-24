"""Paths used by the lenient media checker."""

from pathlib import Path


def media_trash_directory(media_directory: str) -> str:
    """Return Anki's recoverable trash folder beside ``collection.media``."""

    # Anki's media backend replaces the media directory's name with
    # ``media.trash`` when moving files to recoverable trash.
    return str(Path(media_directory).with_name("media.trash"))
