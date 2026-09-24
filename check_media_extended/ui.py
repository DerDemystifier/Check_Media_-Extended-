"""Qt results window for the extended media checker."""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence

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
    ) -> None:
        super().__init__(parent)
        self._on_trash = on_trash
        self._filenames = list(result.unused)
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

        self._unused_bytes = sum(
            os.path.getsize(os.path.join(media_dir, filename))
            for filename in self._filenames
            if os.path.isfile(os.path.join(media_dir, filename))
        )
        self.summary = QLabel(
            "<b>Sweep summary</b><br>"
            f"Media files scanned: {result.media_file_count}<br>"
            f"Exempted: {result.exempted_count} (_-prefixed or generated LaTeX)<br>"
            f"Candidates checked: {len(result.candidates)}<br>"
            f"Notes referencing media in the collection: {result.matched_note_count}<br>"
            f"Unused: {len(self._filenames)} ({_format_size(self._unused_bytes)})"
        )
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        self.report.setPlainText("\n".join(self._filenames))
        layout.addWidget(self.report)

        buttons = QDialogButtonBox()
        self.delete_unused = QPushButton("Delete Unused")
        self.open_media = QPushButton("Open Media Collection")
        self.open_trash = QPushButton("Open Trash Bin")
        self.empty_trash = QPushButton("Empty Trash")
        buttons.addButton(QDialogButtonBox.StandardButton.Close)
        buttons.addButton(self.delete_unused, QDialogButtonBox.ButtonRole.DestructiveRole)
        buttons.addButton(self.open_media, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(self.open_trash, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(self.empty_trash, QDialogButtonBox.ButtonRole.ActionRole)
        layout.addWidget(buttons)

        qconnect(self.delete_unused.clicked, lambda: self._on_trash(self._filenames))
        qconnect(self.open_media.clicked, on_open_media)
        qconnect(self.open_trash.clicked, on_open_trash)
        qconnect(self.empty_trash.clicked, on_empty_trash)
        qconnect(buttons.rejected, self.reject)
        self._update_delete_button()

    def mark_trashed(self, filenames: Sequence[str]) -> None:
        moved = set(filenames)
        self._filenames = [filename for filename in self._filenames if filename not in moved]
        self.report.setPlainText("\n".join(self._filenames))
        self.summary.setText(
            f"Moved {len(moved)} file(s) to Anki's media trash. "
            "They remain recoverable until the trash is emptied."
        )

        self._update_delete_button()

    def _update_delete_button(self) -> None:
        self.delete_unused.setEnabled(bool(self._filenames))


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    raise AssertionError("unreachable")
