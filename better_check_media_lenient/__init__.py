"""Entry point for the Check Media (Lenient) Anki addon."""

from aqt import mw
from aqt.qt import QAction, qconnect

from .controller import LenientMediaChecker


def open_lenient_media_check() -> None:
    LenientMediaChecker(mw).start()


action = QAction("Check Media (Lenient)", mw)
qconnect(action.triggered, open_lenient_media_check)
mw.form.menuTools.addAction(action)
