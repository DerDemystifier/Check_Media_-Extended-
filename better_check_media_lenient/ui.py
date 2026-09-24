"""Qt results window for the lenient media checker."""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence

from aqt.qt import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QWidget,
    QVBoxLayout,
    Qt,
    qconnect,
)


class ResultsDialog(QDialog):
    """Shows flagged media and lets the user choose what to trash."""

    def __init__(
        self,
        parent: QWidget,
        filenames: Sequence[str],
        media_dir: str,
        on_trash: Callable[[list[str]], None],
    ) -> None:
        super().__init__(parent)
        self._on_trash = on_trash
        self._set_up_ui(filenames, media_dir)

    def _set_up_ui(self, filenames: Sequence[str], media_dir: str) -> None:
        self.setWindowTitle("Check Media (Lenient)")
        self.setMinimumSize(600, 420)
        layout = QVBoxLayout(self)

        total_bytes = sum(
            os.path.getsize(os.path.join(media_dir, filename))
            for filename in filenames
            if os.path.isfile(os.path.join(media_dir, filename))
        )
        self.summary = QLabel(
            f"{len(filenames)} candidate file(s), {_format_size(total_bytes)}. "
            "Review before moving files to Anki's recoverable media trash."
        )
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.files = QListWidget()
        self.files.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        for filename in filenames:
            item = QListWidgetItem(filename)
            item.setData(Qt.ItemDataRole.UserRole, filename)
            self.files.addItem(item)
        layout.addWidget(self.files)

        buttons = QDialogButtonBox()
        self.trash_selected = QPushButton("Move Selected to Trash")
        self.trash_all = QPushButton("Move All to Trash")
        close = buttons.addButton(QDialogButtonBox.StandardButton.Close)
        buttons.addButton(self.trash_selected, QDialogButtonBox.ButtonRole.DestructiveRole)
        buttons.addButton(self.trash_all, QDialogButtonBox.ButtonRole.DestructiveRole)
        layout.addWidget(buttons)

        qconnect(self.trash_selected.clicked, self._trash_selected)
        qconnect(self.trash_all.clicked, lambda: self._on_trash(self.filenames()))
        qconnect(close.clicked, self.reject)
        self._update_buttons()
        qconnect(self.files.itemSelectionChanged, self._update_buttons)

    def filenames(self) -> list[str]:
        return [
            self.files.item(index).data(Qt.ItemDataRole.UserRole)
            for index in range(self.files.count())
        ]

    def mark_trashed(self, filenames: Sequence[str]) -> None:
        moved = set(filenames)
        for index in reversed(range(self.files.count())):
            if self.files.item(index).data(Qt.ItemDataRole.UserRole) in moved:
                self.files.takeItem(index)
        self.summary.setText(
            f"Moved {len(moved)} file(s) to Anki's media trash. "
            "They remain recoverable until the trash is emptied."
        )
        self._update_buttons()

    def _trash_selected(self) -> None:
        self._on_trash(
            [item.data(Qt.ItemDataRole.UserRole) for item in self.files.selectedItems()]
        )

    def _update_buttons(self) -> None:
        self.trash_selected.setEnabled(bool(self.files.selectedItems()))
        self.trash_all.setEnabled(self.files.count() > 0)


def _format_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
        size /= 1024
    raise AssertionError("unreachable")
