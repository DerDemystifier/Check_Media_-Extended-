"""Qt results window for the extended media checker."""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from html import escape

from aqt.qt import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTextOption,
    QWidget,
    QVBoxLayout,
    qconnect,
)

from .media_paths import root_level_media_filenames
from .matcher import ScanResult


class ResultsDialog(QDialog):
    """Shows a copyable report and collection-level media actions."""

    def __init__(
        self,
        parent: QWidget,
        result: ScanResult,
        media_dir: str,
        on_trash: Callable[[list[str]], None],
        on_open_media: Callable[[], None],
        on_open_trash: Callable[[], None],
        on_empty_trash: Callable[[], None],
        path_warnings: Sequence[str] = (),
    ) -> None:
        super().__init__(parent)
        self._on_trash = on_trash
        self._filenames = list(result.unused)
        self._result = result
        self._media_dir = media_dir
        self._path_warnings = tuple(path_warnings)
        self._trashed_count = 0
        self._set_up_ui(result, media_dir, on_open_media, on_open_trash, on_empty_trash)

    def _set_up_ui(
        self,
        result: ScanResult,
        media_dir: str,
        on_open_media: Callable[[], None],
        on_open_trash: Callable[[], None],
        on_empty_trash: Callable[[], None],
    ) -> None:
        self.setWindowTitle("Check Media (Extended)")
        self.setMinimumSize(600, 420)
        layout = QVBoxLayout(self)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self._update_summary()
        layout.addWidget(self.summary)

        if self._path_warnings:
            self.path_warnings = QLabel(
                "<b>Some additional paths were skipped:</b><br>"
                + "<br>".join(escape(warning) for warning in self._path_warnings)
            )
            self.path_warnings.setWordWrap(True)
            layout.addWidget(self.path_warnings)

        if any(_is_nested(filename) for filename in self._filenames):
            self.nested_notice = QLabel(
                "Nested-folder results are report-only. Anki's media trash "
                "supports root-level files only."
            )
            self.nested_notice.setWordWrap(True)
            layout.addWidget(self.nested_notice)

        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        self.report.setPlainText("\n".join(self._filenames))
        layout.addWidget(self.report)

        buttons = QDialogButtonBox()
        self.delete_unused = QPushButton("Move Root Files to Trash")
        self.open_media = QPushButton("Open Media Collection")
        self.open_trash = QPushButton("Open Trash Bin")
        self.empty_trash = QPushButton("Empty Trash")
        buttons.addButton(QDialogButtonBox.StandardButton.Close)
        buttons.addButton(self.delete_unused, QDialogButtonBox.ButtonRole.DestructiveRole)
        buttons.addButton(self.open_media, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(self.open_trash, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(self.empty_trash, QDialogButtonBox.ButtonRole.ActionRole)
        layout.addWidget(buttons)

        qconnect(
            self.delete_unused.clicked,
            lambda: self._on_trash(self._trashable_filenames()),
        )
        qconnect(self.open_media.clicked, on_open_media)
        qconnect(self.open_trash.clicked, on_open_trash)
        qconnect(self.empty_trash.clicked, on_empty_trash)
        qconnect(buttons.rejected, self.reject)
        self._update_delete_button()

    def mark_trashed(self, filenames: Sequence[str]) -> None:
        moved = {filename for filename in filenames if not _is_nested(filename)}
        self._filenames = [filename for filename in self._filenames if filename not in moved]
        self._trashed_count += len(moved)
        self.report.setPlainText("\n".join(self._filenames))
        self._update_summary()
        self._update_delete_button()

    def _update_delete_button(self) -> None:
        self.delete_unused.setEnabled(bool(self._trashable_filenames()))

    def _trashable_filenames(self) -> list[str]:
        return root_level_media_filenames(self._filenames)

    def _update_summary(self) -> None:
        listed_bytes = sum(
            _file_size(self._media_dir, filename) for filename in self._filenames
        )
        parts = [
            "<b>Sweep summary</b>",
            f"Media files scanned: {self._result.media_file_count}",
            f"Exempted: {self._result.exempted_count} (_-prefixed or generated LaTeX)",
            f"Candidates checked: {len(self._result.candidates)}",
            "Notes referencing media in the collection: "
            f"{self._result.matched_note_count}",
            f"Still listed as unused: {len(self._filenames)} "
            f"({_format_size(listed_bytes)})",
        ]
        if self._trashed_count:
            parts.append(
                f"Moved to Anki's recoverable media trash: {self._trashed_count}"
            )
        self.summary.setText("<br>".join(parts))


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    raise AssertionError("unreachable")


def _is_nested(filename: str) -> bool:
    return "/" in filename or "\\" in filename


def _file_size(media_directory: str, filename: str) -> int:
    path = os.path.join(media_directory, filename)
    try:
        return os.path.getsize(path) if os.path.isfile(path) else 0
    except OSError:
        return 0
