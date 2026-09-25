"""Background orchestration for the extended media scan and trash action."""

from __future__ import annotations

import os
import threading
from collections.abc import Sequence
from concurrent.futures import Future
from typing import Any

from aqt.operations import QueryOp
from aqt.qt import QTimer, qconnect
from aqt.utils import askUser, openFolder, showInfo, showWarning

from .media_paths import (
    discover_media_files,
    media_trash_directory,
    root_level_media_filenames,
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
        root_filenames = root_level_media_filenames(filenames)
        if len(root_filenames) != len(filenames):
            showWarning(
                "Files in additional subfolders are report-only and cannot be "
                "moved using Anki's media trash.",
                parent=self.mw,
            )
        filenames = root_filenames
        if not filenames:
            return
        if not askUser(
            f"Move {len(filenames)} file(s) to Anki's media trash?\n\n"
            "They can be restored until the media trash is emptied.",
            parent=self.mw,
            defaultno=True,
        ):
            return

        def trash(col: Any) -> list[str]:
            col.media.trash_files(filenames)
            return filenames

        QueryOp(
            parent=self.mw,
            op=trash,
            success=self._trashed,
        ).with_progress("Moving media to trash…").run_in_background()

    def _trashed(self, filenames: list[str]) -> None:
        if self._dialog:
            self._dialog.mark_trashed(filenames)
        showInfo(
            f"Moved {len(filenames)} file(s) to Anki's media trash. "
            "They are recoverable until the trash is emptied.",
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
            "Permanently delete all files in Anki's media trash?\n\n"
            "This cannot be undone.",
            parent=self.mw,
            defaultno=True,
        ):
            return

        QueryOp(
            parent=self.mw,
            op=lambda col: col.media.empty_trash(),
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
