"""Paths used by the extended media checker."""

from __future__ import annotations

import os
import stat
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from pathlib import PureWindowsPath


@dataclass(frozen=True)
class MediaFileDiscovery:
    """Media filenames discovered for a scan and any non-fatal warnings."""

    filenames: tuple[str, ...]
    warnings: tuple[str, ...]


def root_level_media_filenames(filenames: Iterable[str]) -> list[str]:
    """Return unique root-level names safe to pass to Anki's media trash."""

    return list(
        dict.fromkeys(
            filename
            for filename in filenames
            if "/" not in filename and "\\" not in filename
        )
    )


def discover_media_files(
    media_directory: str, additional_paths: object = ()
) -> MediaFileDiscovery:
    """List root files plus files below configured media-relative directories.

    Additional directories are traversed recursively, but symlinked directories
    and files resolving outside the media directory are skipped.
    """

    media_root = Path(media_directory).resolve()
    warnings: set[str] = set()
    filenames: set[str] = set()

    with os.scandir(media_root) as entries:
        for entry in entries:
            try:
                if not entry.is_file():
                    continue
                resolved_file = Path(entry.path).resolve()
            except (OSError, RuntimeError) as error:
                warnings.add(f"Could not inspect {entry.name}: {error}.")
                continue
            if not _is_within(resolved_file, media_root):
                warnings.add(
                    f"Skipped media file outside collection.media: {entry.name}."
                )
                continue
            filenames.add(entry.name)

    if isinstance(additional_paths, Sequence) and not isinstance(
        additional_paths, (str, bytes)
    ):
        configured_paths = additional_paths
    else:
        configured_paths = ()
        warnings.add(
            "The additional_paths setting must be a list of relative directories."
        )

    for configured_path in configured_paths:
        parts, warning = _relative_directory_parts(configured_path)
        if warning:
            warnings.add(warning)
            continue
        assert parts is not None

        directory = media_root
        invalid_directory = False
        for part in parts:
            directory /= part
            try:
                if _is_link_or_junction(directory):
                    warnings.add(
                        _path_warning(
                            configured_path, "symbolic-link paths are not scanned"
                        )
                    )
                    invalid_directory = True
                    break
                resolved_directory = directory.resolve()
                if not _is_within(resolved_directory, media_root):
                    warnings.add(
                        _path_warning(
                            configured_path, "it resolves outside collection.media"
                        )
                    )
                    invalid_directory = True
                    break
                if not directory.exists():
                    warnings.add(
                        _path_warning(configured_path, "the directory does not exist")
                    )
                    invalid_directory = True
                    break
                if not directory.is_dir():
                    warnings.add(
                        _path_warning(configured_path, "the path is not a directory")
                    )
                    invalid_directory = True
                    break
            except (OSError, RuntimeError) as error:
                warnings.add(
                    _path_warning(configured_path, f"it could not be inspected: {error}")
                )
                invalid_directory = True
                break

        if invalid_directory:
            continue

        def report_walk_error(error: OSError) -> None:
            relative_error_path = _relative_to_media(
                error.filename or str(directory), media_root
            )
            warnings.add(
                f"Could not inspect {relative_error_path}: {error.strerror or error}."
            )

        for current_directory, directory_names, file_names in os.walk(
            directory,
            topdown=True,
            onerror=report_walk_error,
            followlinks=False,
        ):
            current_path = Path(current_directory)
            safe_directory_names: list[str] = []
            for directory_name in directory_names:
                child_directory = current_path / directory_name
                try:
                    if _is_link_or_junction(child_directory):
                        warnings.add(
                            f"Skipped symlinked media directory "
                            f"{_relative_to_media(child_directory, media_root)}."
                        )
                        continue
                    resolved_child = child_directory.resolve()
                except (OSError, RuntimeError) as error:
                    warnings.add(
                        f"Could not inspect "
                        f"{_relative_to_media(child_directory, media_root)}: {error}."
                    )
                    continue
                if not _is_within(resolved_child, media_root):
                    warnings.add(
                        f"Skipped media directory outside collection.media: "
                        f"{_relative_to_media(child_directory, media_root)}."
                    )
                    continue
                safe_directory_names.append(directory_name)
            directory_names[:] = sorted(safe_directory_names)

            for file_name in file_names:
                media_file = current_path / file_name
                try:
                    if not media_file.is_file():
                        continue
                    resolved_file = media_file.resolve()
                except (OSError, RuntimeError) as error:
                    warnings.add(
                        f"Could not inspect "
                        f"{_relative_to_media(media_file, media_root)}: {error}."
                    )
                    continue
                if not _is_within(resolved_file, media_root):
                    warnings.add(
                        f"Skipped media file outside collection.media: "
                        f"{_relative_to_media(media_file, media_root)}."
                    )
                    continue
                filenames.add(_relative_to_media(media_file, media_root))

    return MediaFileDiscovery(tuple(sorted(filenames)), tuple(sorted(warnings)))


def _relative_directory_parts(
    configured_path: object,
) -> tuple[tuple[str, ...] | None, str | None]:
    if not isinstance(configured_path, str):
        return None, _path_warning(configured_path, "it must be a relative path string")

    normalized = configured_path.strip().replace("\\", "/")
    windows_path = PureWindowsPath(configured_path.strip())
    if not normalized:
        return None, _path_warning(configured_path, "the path is empty")
    if normalized.startswith("/") or windows_path.drive:
        return None, _path_warning(configured_path, "absolute paths are not allowed")
    if "\x00" in normalized or ":" in normalized:
        return None, _path_warning(configured_path, "the path contains an invalid character")

    raw_parts = normalized.split("/")
    if ".." in raw_parts:
        return None, _path_warning(
            configured_path, "parent-directory traversal is not allowed"
        )
    parts = tuple(part for part in raw_parts if part not in ("", "."))
    if not parts:
        return None, _path_warning(
            configured_path, "the media root itself cannot be scanned"
        )
    return parts, None


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    if os.name == "nt":
        try:
            attributes = os.lstat(path).st_file_attributes
        except (AttributeError, OSError):
            return False
        reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        return bool(attributes & reparse_point)
    return False


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _relative_to_media(path: str | Path, media_root: Path) -> str:
    try:
        return Path(path).relative_to(media_root).as_posix()
    except ValueError:
        return Path(path).name


def _path_warning(configured_path: object, reason: str) -> str:
    return f"Skipped additional media path {configured_path!r}: {reason}."


def media_trash_directory(media_directory: str) -> str:
    """Return Anki's recoverable trash folder beside ``collection.media``."""

    # Anki's media backend replaces the media directory's name with
    # ``media.trash`` when moving files to recoverable trash.
    return str(Path(media_directory).with_name("media.trash"))
