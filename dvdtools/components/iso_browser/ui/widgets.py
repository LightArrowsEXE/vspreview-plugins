from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QLabel
from PyQt6.QtGui import QDesktopServices
from vspreview.core.abstracts import PushButton

__all__ = [
    'create_widgets',
]


def create_widgets(parent) -> None:
    """Create and initialize all widgets."""

    parent.file_label = QLabel("No ISO loaded")

    parent.load_button = PushButton("Load ISO", parent, clicked=parent._on_load_iso)
    parent.load_button.setFixedWidth(150)
    parent.load_button.setToolTip("Load a DVD ISO file")

    parent.dump_title_button = PushButton("Dump Title", parent, clicked=parent.ffmpeg_handler.dump_title)
    parent.dump_title_button.setFixedWidth(150)
    parent.dump_title_button.setEnabled(False)
    parent.dump_title_button.setToolTip("Extract the selected title and angle to a file")

    parent.dump_all_titles_button = PushButton("Dump All Titles", parent, clicked=parent.ffmpeg_handler.dump_all_titles)
    parent.dump_all_titles_button.setFixedWidth(150)
    parent.dump_all_titles_button.setEnabled(False)
    parent.dump_all_titles_button.setToolTip("Extract all titles from the ISO to separate files")

    parent.copy_script_button = PushButton("⎘", parent, clicked=parent._on_copy_script)
    parent.copy_script_button.setFixedWidth(20)
    parent.copy_script_button.setEnabled(False)
    parent.copy_script_button.setToolTip("Copy an IsoFile code snippet to clipboard")

    parent.info_button = PushButton("🛈", parent)
    parent.info_button.setFixedWidth(20)
    parent.info_button.setToolTip("Click to learn more about remuxing DVDISO files (opens in browser)")
    parent.info_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(
        "https://jaded-encoding-thaumaturgy.github.io/JET-guide/dvd-remux/sources/dvd-remux"
    )))

    parent.info_label = QLabel("Select a title to view details")
