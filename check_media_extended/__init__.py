"""Entry point for the Check Media (Extended) Anki add-on."""

from aqt import mw
from aqt.qt import QAction, qconnect

from .controller import ExtendedMediaChecker


def open_extended_media_check() -> None:
    ExtendedMediaChecker(mw).start()


action = QAction("Check Media (Extended)", mw)
qconnect(action.triggered, open_extended_media_check)
mw.form.menuTools.addAction(action)
