from __future__ import annotations

from logging import debug, error
from traceback import format_exc
from typing import Any

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWidgets import QApplication, QFileDialog, QLabel, QMessageBox, QWidget, QHBoxLayout, QProgressDialog
from PyQt6.QtGui import QDesktopServices
from vspreview.core import Frame
from vspreview.core.abstracts import AbstractSettingsWidget, PushButton
from vspreview.plugins import AbstractPlugin
from vssource import IsoFile, Title
from vstools import SPath, vs

from .tree_manager import ISOTreeManager
from .ffmpeg_handler import FFmpegHandler
from .types import TitleInfo
from .ui import setup_layout, create_widgets


class IsoBrowserTab(AbstractSettingsWidget):
    """Tab for browsing DVD/BD ISO files and their titles/angles."""

    __slots__ = (
        'file_label', 'load_button', 'info_label', 'dump_title_button', 'tree_manager', 'ffmpeg_handler'
    )

    def __init__(self, plugin: AbstractPlugin) -> None:
        self.plugin = plugin

        self.tree_manager = ISOTreeManager(self)
        self.ffmpeg_handler = FFmpegHandler(self)

        super().__init__()
        self._init_state()

    def _init_state(self) -> None:
        """Initialize internal state variables."""

        self.iso_path: SPath | None = None
        self.iso_file: IsoFile | None = None  # type:ignore

        self.title_info: dict[tuple[int, int | None], TitleInfo] = {}

        self.current_node: vs.VideoNode | None = None
        self.current_title: Title | None = None

    def setup_ui(self) -> None:
        """Set up the user interface."""

        super().setup_ui()
        create_widgets(self)
        setup_layout(self)

    def _on_load_iso(self) -> None:
        """Handle ISO file loading."""

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select ISO file", "", "ISO files (*.iso);;All files (*.*)"
        )

        if not file_path:
            debug('No file selected')
            return

        try:
            debug(f'Loading ISO file: {file_path}')
            self.iso_path = SPath(file_path)

            # Create progress dialog
            progress = QProgressDialog("Loading ISO file...", "Cancel", 0, 100, self)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setWindowTitle("Loading ISO")
            progress.setValue(0)
            progress.show()

            QApplication.processEvents()

            progress.setLabelText("Parsing ISO structure...")
            self.iso_file = IsoFile(self.iso_path)

            if progress.wasCanceled():
                raise Exception("Operation cancelled by user")

            progress.setLabelText("Loading titles...")
            self.file_label.setText(self.iso_path.name)
            self.info_label.setText("Select a title to view details")

            if progress.wasCanceled():
                raise Exception("Operation cancelled by user")

            total_titles = self.iso_file.title_count
            total_items = 0

            for title_idx in range(1, total_titles + 1):
                tt_srpt = self.iso_file.ifo0.tt_srpt[title_idx - 1]
                total_items += max(1, tt_srpt.nr_of_angles)

            items_processed = 0
            progress_per_item = 100 / total_items

            # Clear existing data
            self.tree_manager.clear()
            self.title_info.clear()

            # Process each title
            for title_idx in range(1, total_titles + 1):
                if progress.wasCanceled():
                    raise Exception("Operation cancelled by user")

                progress.setLabelText(f"Loading title {title_idx + 1} of {total_titles}...")

                try:
                    self.tree_manager._add_title_to_tree(title_idx)
                except Exception as e:
                    error(f'Failed to add title {title_idx}: {e}\n{format_exc()}')
                    continue

                items_processed += 1
                progress.setValue(min(int(items_processed * progress_per_item), 100))

            # Finish up
            self.tree_manager.tree.expandAll()
            self.dump_all_titles_button.setEnabled(total_titles > 0)
            progress.setValue(100)

        except Exception as e:
            error(f'Failed to load ISO: {e}\n{format_exc()}')
            self._reset_iso_state()
            QMessageBox.critical(self, "Error", f"Failed to load ISO: {str(e)}")
        finally:
            if 'progress' in locals():
                progress.close()

    def _reset_iso_state(self) -> None:
        """Reset the ISO state and UI elements."""

        debug('Resetting ISO state')

        self.file_label.setText("No ISO loaded")
        self._init_state()
        self.tree_manager.clear()
        self.dump_title_button.setEnabled(False)
        self.dump_all_titles_button.setEnabled(False)
        self.info_label.setText("Select a title to view details")

    def _check_current_title(self) -> bool:
        """Check if current title exists and is valid."""

        if not hasattr(self, 'current_title'):
            return False

        return self.current_title is not None

    def on_current_frame_changed(self, frame: Frame) -> None:
        """Handle frame change events."""

        if not self._check_current_title():
            return

        try:
            self.current_title.frame = frame.value
        except AttributeError as e:
            debug(f'Failed to update frame in on_current_frame_changed: {e}\n{format_exc()}')
            pass

    def on_current_output_changed(self, index: int, prev_index: int) -> None:
        """Handle output change events."""

        if not self._check_current_title():
            return

        try:
            current_frame = self.plugin.main.current_frame
            if current_frame is None:
                return

            if self.plugin.main.current_output.node is not self.current_title.video:
                main = self.plugin.main
                new_output = main.outputs[index].with_node(self.current_title.video)
                new_output.name = (
                    f"Title {self.current_title._title}"
                    + (f" Angle {self.current_title.angle}" if hasattr(self.current_title, 'angle') else "")
                )
                new_output.index = index
                main.outputs.items[index] = new_output
                main.refresh_video_outputs()
                return

            self.current_title.frame = current_frame.value
        except AttributeError as e:
            debug(f'Failed to update frame in on_current_output_changed: {e}\n{format_exc()}')
            pass

    def __getstate__(self) -> dict[str, Any]:
        """Get state for serialization."""

        return {}

    def __setstate__(self, state: dict[str, Any]) -> None:
        """Restore state from serialization."""

        self._reset_iso_state()

        if (iso_path := state.get('iso_path')) is None:
            return

        if not (iso_path := SPath(iso_path)).exists():
            debug(f'Previously saved ISO file no longer exists: {iso_path}')

            return

        try:
            debug(f'Loading saved ISO state: {iso_path}')

            self.iso_path = iso_path
            self.iso_file = IsoFile(self.iso_path)
            self.file_label.setText(self.iso_path.name)
            self.tree_manager.populate_tree()
        except Exception as e:
            error(f'Failed to load saved ISO state: {e}\n{format_exc()}')
            self._reset_iso_state()
            QMessageBox.critical(self, "Error", f"Failed to load ISO: {str(e)}")
