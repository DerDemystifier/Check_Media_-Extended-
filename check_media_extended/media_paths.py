"""Paths used by the extended media checker."""

from __future__ import annotations

import os
import stat
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from pathlib import PureWindowsPath


@dataclass(frozen=True)
class MediaFileDiscovery:
    """Media filenames discovered for a scan and any non-fatal warnings."""

    filenames: tuple[str, ...]
    warnings: tuple[str, ...]


def discover_media_files(media_directory: str, additional_paths: object = ()) -> MediaFileDiscovery:
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
                warnings.add(f"Skipped media file outside collection.media: {entry.name}.")
                continue
            filenames.add(entry.name)

    if isinstance(additional_paths, Sequence) and not isinstance(additional_paths, (str, bytes)):
        configured_paths = additional_paths
    else:
        configured_paths = ()
        warnings.add("The additional_paths setting must be a list of relative directories.")

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
                        _path_warning(configured_path, "symbolic-link paths are not scanned")
                    )
                    invalid_directory = True
                    break
                resolved_directory = directory.resolve()
                if not _is_within(resolved_directory, media_root):
                    warnings.add(
                        _path_warning(configured_path, "it resolves outside collection.media")
                    )
                    invalid_directory = True
                    break
                if not directory.exists():
                    warnings.add(_path_warning(configured_path, "the directory does not exist"))
                    invalid_directory = True
                    break
                if not directory.is_dir():
                    warnings.add(_path_warning(configured_path, "the path is not a directory"))
                    invalid_directory = True
                    break
            except (OSError, RuntimeError) as error:
                warnings.add(_path_warning(configured_path, f"it could not be inspected: {error}"))
                invalid_directory = True
                break

        if invalid_directory:
            continue

        def report_walk_error(error: OSError) -> None:
            relative_error_path = _relative_to_media(error.filename or str(directory), media_root)
            warnings.add(f"Could not inspect {relative_error_path}: {error.strerror or error}.")

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
        return None, _path_warning(configured_path, "parent-directory traversal is not allowed")
    parts = tuple(part for part in raw_parts if part not in ("", "."))
    if not parts:
        return None, _path_warning(configured_path, "the media root itself cannot be scanned")
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
    """Return Anki's media trash folder beside ``collection.media``."""

    # Anki's media backend replaces the media directory's name with
    # ``media.trash`` when moving files to recoverable trash.
    return str(Path(media_directory).with_name("media.trash"))


def prepare_media_trash_destination(media_directory: str, filename: str) -> Path:
    """Validate a media-relative file and prepare its mirrored trash path.

    Anki's trash operation creates the trash root, but not nested destination
    folders. This helper creates the required folders and refuses unsafe paths,
    symlinks/junctions, missing sources, and destinations that already exist.
    It does not move the file.
    """

    parts = _media_relative_path_parts(filename)
    media_root = Path(media_directory)
    resolved_media_root = media_root.resolve()
    if not media_root.is_dir():
        raise NotADirectoryError(f"Media directory is unavailable: {media_root}")

    source_path = media_root
    for index, part in enumerate(parts):
        source_path /= part
        if _is_link_or_junction(source_path):
            raise ValueError(f"Media path contains a symlink or junction: {filename!r}")
        if not _is_within(source_path.resolve(), resolved_media_root):
            raise ValueError(f"Media path escapes collection.media: {filename!r}")
        if index < len(parts) - 1:
            if not source_path.is_dir():
                raise FileNotFoundError(f"Media directory does not exist: {source_path}")
        elif not source_path.is_file():
            raise FileNotFoundError(f"Media file does not exist: {source_path}")

    trash_root = Path(media_trash_directory(media_directory))
    _ensure_trash_directory(trash_root, trash_root.parent.resolve())
    resolved_trash_root = trash_root.resolve()
    destination_parent = trash_root
    for part in parts[:-1]:
        destination_parent /= part
        _ensure_trash_directory(destination_parent, resolved_trash_root)

    destination = destination_parent / parts[-1]
    if os.path.lexists(destination):
        raise FileExistsError(f"Trash destination already exists: {destination}")
    return destination


def empty_media_trash(media_directory: str) -> None:
    """Remove all trash contents recursively without following links.

    The ``media.trash`` directory itself is retained. A linked or non-directory
    trash root is refused rather than traversed.
    """

    trash_root = Path(media_trash_directory(media_directory))
    if not os.path.lexists(trash_root):
        return
    if _is_link_or_junction(trash_root):
        raise ValueError(f"Refusing to empty linked media trash: {trash_root}")
    if not trash_root.is_dir():
        raise NotADirectoryError(f"Media trash is not a directory: {trash_root}")

    with os.scandir(trash_root) as entries:
        children = [Path(entry.path) for entry in entries]
    for child in children:
        _remove_trash_entry(child)


def _media_relative_path_parts(filename: object) -> tuple[str, ...]:
    if not isinstance(filename, str):
        raise ValueError("Media filename must be a relative path string")

    normalized = filename.replace("\\", "/")
    if (
        not normalized
        or normalized.startswith("/")
        or PureWindowsPath(filename).drive
        or "\x00" in normalized
        or ":" in normalized
    ):
        raise ValueError(f"Unsafe media-relative path: {filename!r}")

    parts = tuple(normalized.split("/"))
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"Unsafe media-relative path: {filename!r}")
    return parts


def _ensure_trash_directory(directory: Path, allowed_root: Path) -> None:
    if _is_link_or_junction(directory):
        raise ValueError(f"Trash path contains a symlink or junction: {directory}")
    if not os.path.lexists(directory):
        directory.mkdir()
    elif not directory.is_dir():
        raise NotADirectoryError(f"Trash path is not a directory: {directory}")

    if not _is_within(directory.resolve(), allowed_root):
        raise ValueError(f"Trash path escapes its allowed directory: {directory}")


def _remove_trash_entry(path: Path) -> None:
    if _is_link_or_junction(path):
        # Windows requires rmdir for directory symlinks/junctions; on POSIX,
        # unlink removes the link itself without touching its target.
        if os.name == "nt" and path.is_dir():
            os.rmdir(path)
        else:
            path.unlink()
        return

    if path.is_dir():
        with os.scandir(path) as entries:
            children = [Path(entry.path) for entry in entries]
        for child in children:
            _remove_trash_entry(child)
        path.rmdir()
    else:
        path.unlink()
