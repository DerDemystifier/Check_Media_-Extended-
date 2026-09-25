"""Background orchestration for the extended media scan and trash action."""

from __future__ import annotations

import os
import threading
from collections.abc import Sequence
from concurrent.futures import Future
from pathlib import Path
from typing import Any

from aqt.operations import QueryOp
from aqt.qt import QTimer, qconnect
from aqt.utils import askUser, openFolder, showInfo, showWarning

from .media_paths import (
    discover_media_files,
    empty_media_trash,
    media_trash_directory,
    prepare_media_trash_destination,
)
from .matcher import MatcherConfig, ScanCancelled, ScanResult, scan_collection
from .ui import ResultsDialog


class ExtendedMediaChecker:
    """Owns one scan at a time and keeps all Qt interactions on the UI thread."""

    def __init__(self, mw: Any) -> None:
        self.mw = mw
        self._cancelled = threading.Event()
        self._progress_timer: QTimer | None = None
        self._progress_dialog: object | None = None
        self._dialog: ResultsDialog | None = None

    def start(self) -> None:
        if not self.mw.col:
            showWarning("Open a profile before checking media.", parent=self.mw)
            return
        self._cancelled.clear()
        self._progress_dialog = self.mw.progress.start(label="Preparing extended media check…")
        self._progress_timer = QTimer(self.mw)
        self._progress_timer.setInterval(100)
        qconnect(self._progress_timer.timeout, self._check_for_cancellation)
        self._progress_timer.start()
        self.mw.taskman.run_in_background(self._scan, self._finished, uses_collection=True)

    def _scan(self) -> tuple[ScanResult, str, tuple[str, ...]]:
        media_dir = self.mw.col.media.dir()
        configured = self.mw.addonManager.getConfig(__name__) or {}
        discovery = discover_media_files(
            media_dir, configured.get("additional_paths", [])
        )
        result = scan_collection(
            self.mw.col,
            discovery.filenames,
            config=self._config(configured),
            progress=self._set_progress,
            cancelled=self._cancelled.is_set,
        )
        return result, media_dir, discovery.warnings

    def _set_progress(self, label: str) -> None:
        # TaskManager invokes this worker on a background thread; queue the UI
        # update back to Anki's main thread.
        self.mw.taskman.run_on_main(lambda: self.mw.progress.update(label=label))

    def _check_for_cancellation(self) -> None:
        if getattr(self._progress_dialog, "wantCancel", False):
            self._cancelled.set()

    def _finished(
        self, future: Future[tuple[ScanResult, str, tuple[str, ...]]]
    ) -> None:
        self._finish_progress()
        exception = future.exception()
        if isinstance(exception, ScanCancelled):
            return
        if exception:
            showWarning(str(exception), parent=self.mw)
            return
        result, media_dir, path_warnings = future.result()
        self._dialog = ResultsDialog(
            self.mw,
            result,
            media_dir,
            self.trash_files,
            self.open_media_collection,
            self.open_trash_bin,
            self.empty_trash,
            path_warnings,
        )
        self._dialog.exec()

    def trash_files(self, filenames: Sequence[str]) -> None:
        filenames = list(dict.fromkeys(filenames))
        if not filenames:
            return

        nested_files = [filename for filename in filenames if _is_nested(filename)]
        confirmation = f"Move {len(filenames)} unused file(s) to Anki's media trash?"
        if len(nested_files) < len(filenames):
            confirmation += (
                "\n\nRoot-level files can be restored with Anki's Restore Trash "
                "until the trash is emptied."
            )
        if nested_files:
            confirmation += (
                "\n\nFiles from subfolders will keep their relative paths in the trash. "
                "Anki's Restore Trash does not support nested entries; restore them "
                "manually to their original paths before emptying the trash."
            )
        confirmation += (
            "\n\nThe add-on's Empty Trash permanently deletes everything in the trash."
        )
        if not askUser(confirmation, parent=self.mw, defaultno=True):
            return

        def trash(col: Any) -> tuple[list[str], list[str]]:
            media_directory = col.media.dir()
            moved: list[str] = []
            warnings: list[str] = []
            for filename in filenames:
                try:
                    relative_filename = filename.replace("\\", "/")
                    destination = prepare_media_trash_destination(
                        media_directory, relative_filename
                    )
                    source = Path(media_directory).joinpath(
                        *relative_filename.split("/")
                    )
                    col.media.trash_files([relative_filename])
                    if not source.exists() and destination.is_file():
                        moved.append(filename)
                    else:
                        warnings.append(
                            f"{filename!r}: Anki did not move the file; it may have "
                            "disappeared during the operation."
                        )
                except Exception as error:
                    warnings.append(f"{filename!r}: {error}")
            return moved, warnings

        QueryOp(
            parent=self.mw,
            op=trash,
            success=self._trashed,
        ).with_progress("Moving media to trash…").run_in_background()

    def _trashed(self, result: tuple[list[str], list[str]]) -> None:
        filenames, warnings = result
        if self._dialog and filenames:
            self._dialog.mark_trashed(filenames)
        if filenames:
            message = f"Moved {len(filenames)} file(s) to Anki's media trash."
            if any(_is_nested(filename) for filename in filenames):
                message += (
                    " Nested files keep their relative paths and must be restored "
                    "manually before the trash is emptied."
                )
            showInfo(message, parent=self.mw)
        if warnings:
            showWarning(
                "Some files could not be moved to trash:\n\n" + "\n".join(warnings),
                parent=self.mw,
            )

    def open_media_collection(self) -> None:
        openFolder(self.mw.col.media.dir())

    def open_trash_bin(self) -> None:
        trash_directory = media_trash_directory(self.mw.col.media.dir())
        os.makedirs(trash_directory, exist_ok=True)
        openFolder(trash_directory)

    def empty_trash(self) -> None:
        if not askUser(
            "Permanently delete everything in this profile's media trash, including "
            "nested folders and files from previous checks?\n\n"
            "This cannot be undone.",
            parent=self.mw,
            defaultno=True,
        ):
            return

        QueryOp(
            parent=self.mw,
            op=lambda col: empty_media_trash(col.media.dir()),
            success=lambda _: showInfo("Anki's media trash has been emptied.", parent=self.mw),
        ).with_progress("Emptying media trash…").run_in_background()

    def _finish_progress(self) -> None:
        if self._progress_timer:
            self._progress_timer.stop()
            self._progress_timer.deleteLater()
            self._progress_timer = None
        self.mw.progress.finish()
        self._progress_dialog = None

    def _config(self, configured: dict[str, Any] | None = None) -> MatcherConfig:
        if configured is None:
            configured = self.mw.addonManager.getConfig(__name__) or {}
        return MatcherConfig(
            batch_size=int(configured.get("batch_size", 100)),
            max_regex_length=int(configured.get("max_regex_length", 8_000)),
        )


def _is_nested(filename: str) -> bool:
    return "/" in filename or "\\" in filename
