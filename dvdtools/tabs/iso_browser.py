from __future__ import annotations

from logging import debug, error
from traceback import format_exc
from typing import Any, TypedDict

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout,
                             QInputDialog, QLabel, QMessageBox, QTreeWidget,
                             QTreeWidgetItem, QWidget)
from vspreview import set_output
from vspreview.core import Frame
from vspreview.core.abstracts import AbstractSettingsWidget, PushButton
from vspreview.plugins import AbstractPlugin
from vssource import IsoFile, Title
from vssource.formats.dvd.IsoFileCore import IsoFileCore
from vstools import CustomNotImplementedError, SPath, core, vs

from ..utils.dump_pcm import dump_pcm

__all__ = [
    'IsoBrowserTab'
]


class TitleInfo(TypedDict):
    """Information about a title."""

    title_num: int
    """Number of the title."""

    angle: int | None
    """Angle number if multi-angle, None otherwise."""

    chapter_count: int
    """Number of chapters in the title."""

    chapters: list[int]
    """List of chapter start frames."""

    audio_tracks: list[str]
    """List of audio track descriptions."""

    angle_count: int
    """Total number of angles available."""

    width: int
    """Video width in pixels."""

    height: int
    """Video height in pixels."""

    fps: float
    """Video framerate."""

    duration: float
    """Duration in seconds."""


class IsoBrowserTab(AbstractSettingsWidget):
    """Tab for browsing DVD/BD ISO files and their titles/angles."""

    __slots__ = ('file_label', 'load_button', 'tree', 'info_label', 'dump_audio_button')

    def __init__(self, plugin: AbstractPlugin) -> None:
        super().__init__()

        self.plugin = plugin
        self._init_state()

    def _init_state(self) -> None:
        """Initialize internal state variables."""

        self.iso_path: SPath | None = None
        self.iso_file: type[IsoFileCore] | None = None
        self.current_node: vs.VideoNode | None = None
        self.title_info: dict[tuple[int, int | None], TitleInfo] = {}
        self.current_title: Title | None = None

    def setup_ui(self) -> None:
        """Set up the user interface."""

        super().setup_ui()

        self.file_label = QLabel("No ISO loaded")
        self.load_button = PushButton("Load ISO", self, clicked=self._on_load_iso)
        self.dump_audio_button = PushButton("Dump Audio", self, clicked=self._on_dump_audio)
        self.dump_audio_button.setEnabled(False)
        self.tree = QTreeWidget()
        self.tree.clear()
        self.info_label = QLabel()

        self._setup_tree()
        self._setup_layout()
        self.info_label.setText("Select a title to view details")

    def _setup_tree(self) -> None:
        """Configure tree widget."""

        self.tree.setHeaderLabels(["Titles"])
        self.tree.itemClicked.connect(self._on_tree_item_selected)

    def _setup_layout(self) -> None:
        """Set up widget layout."""

        file_widget = QWidget()
        file_layout = QHBoxLayout(file_widget)
        file_layout.addWidget(self.file_label)
        file_layout.addWidget(self.load_button)
        file_layout.addWidget(self.dump_audio_button)

        self.vlayout.addWidget(file_widget)
        self.vlayout.addWidget(self.tree)
        self.vlayout.addWidget(self.info_label)

    def _reset_iso_state(self) -> None:
        """Reset the ISO state and UI elements."""

        debug('Resetting ISO state')
        self.file_label.setText("No ISO loaded")
        self._init_state()
        self.tree.clear()
        self.dump_audio_button.setEnabled(False)
        self.info_label.setText("Select a title to view details")

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
            self.iso_file = IsoFile(self.iso_path)
            self.file_label.setText(self.iso_path.name)
            self.info_label.setText("Select a title to view details")
            self._populate_tree()
        except Exception as e:
            error(f'Failed to load ISO: {e}\n{format_exc()}')
            self._reset_iso_state()
            QMessageBox.critical(self, "Error", f"Failed to load ISO: {str(e)}")

    def _on_dump_audio(self) -> None:
        """Handle audio track dumping."""

        if not self._validate_title_for_audio():
            return

        if not (audio_tracks := self._get_audio_tracks()):
            QMessageBox.warning(self, "Warning", "No audio tracks found in this title.")
            return

        if (track_idx := self._select_audio_track(audio_tracks)) is None:
            return

        if not (file_path := self._get_audio_save_path(track_idx, audio_tracks[track_idx][1])):
            return

        self._dump_audio_to_file(file_path, track_idx)

    def _validate_title_for_audio(self) -> bool:
        """Check if current title is valid for audio dumping."""

        return bool(self.current_title and hasattr(self.current_title, '_audios'))

    def _get_audio_tracks(self) -> list[tuple[int, str]]:
        """Get list of audio tracks from current title."""

        return [
            (i, audio) for i, audio in enumerate(self.current_title._audios)
            if audio.startswith(('ac3', 'lpcm', 'pcm'))
        ]

    def _select_audio_track(self, audio_tracks: list[tuple[int, str]]) -> int | None:
        """Handle audio track selection dialog if multiple tracks exist."""

        if len(audio_tracks) == 1:
            return audio_tracks[0][0]

        track_items = [f"Track {i}: {audio}" for i, audio in audio_tracks]

        track, ok = QInputDialog.getItem(
            self, "Select Audio Track",
            "Multiple audio tracks found. Please select one:",
            track_items, 0, False
        )

        if not ok:
            return None

        return audio_tracks[track_items.index(track)][0]

    def _dump_audio_to_file(self, file_path: str, track_idx: int) -> None:
        """Dump audio track to specified file."""

        try:
            if self.current_title._audios[track_idx].startswith('ac3'):
                debug(f'Dumping AC3 for title {self.current_title._title} track {track_idx}')
                self.current_title.dump_ac3(self.iso_path / file_path, track_idx)
            elif self.current_title._audios[track_idx].startswith(('lpcm', 'pcm')):
                debug(f'Dumping PCM for title {self.current_title._title} track {track_idx}')
                self._dump_pcm(self.iso_path / file_path, track_idx)
            else:
                raise CustomNotImplementedError(
                    f"Unsupported audio format: {self.current_title._audios[track_idx]}",
                    self._dump_audio_to_file
                )
        except Exception as e:
            error(f'Failed to dump audio: {e}\n{format_exc()}')
            QMessageBox.critical(self, "Error", f"Failed to dump audio: {str(e)}")

    def _dump_pcm(self, file_path: str, track_idx: int) -> None:
        """Dump PCM audio track to WAV file."""

        try:
            self.current_title._assert_dvdsrc2(self._dump_pcm)
        except Exception as e:
            error(f'Failed to dump PCM: {e}\n{format_exc()}')
            QMessageBox.critical(self, "Error", f"Failed to dump PCM: {str(e)}")
            return

        # TODO: Figure out why the audio is so sped up for this wtf?
        pcm_node = core.dvdsrc2.FullVtsLpcm(
            self.current_title._core.iso_path.to_str(),
            self.current_title._vts,
            track_idx,
            self.current_title._dvdsrc_ranges
        )

        dump_pcm(pcm_node, file_path)

    def _get_audio_save_path(self, track_idx: int, audio_type: str) -> str | None:
        """Get save path for audio dump."""

        title_item = self.tree.currentItem()
        title_text = title_item.text(0)
        title_idx = int(title_text.split()[1])

        filename = f"{self.iso_path.stem}_"
        filename += f"title_{title_idx:02d}"
        filename += f"_track_{track_idx}"

        if (angle := getattr(self.current_title, 'angle', None)) is not None:
            filename += f"_angle_{angle}"

        extension = '.ac3' if audio_type.startswith('ac3') else '.wav'
        filename += extension
        filter_text = "AC3 files (*.ac3)" if extension == '.ac3' else "WAV files (*.wav)"

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Audio", filename, filter_text
        )

        return file_path

    def _populate_tree(self) -> None:
        """Populate the tree widget with titles and angles."""

        self.tree.clear()
        self.title_info.clear()

        if not self.iso_file:
            debug('No ISO file loaded')
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        try:
            self._add_titles_to_tree()
            self.tree.expandAll()
        except Exception as e:
            error(f'Failed to populate tree: {e}\n{format_exc()}')
            self._reset_iso_state()
            QMessageBox.critical(self, "Error", f"Failed to load titles: {str(e)}")
        finally:
            QApplication.restoreOverrideCursor()

    def _add_titles_to_tree(self) -> None:
        """Add all titles to the tree."""

        debug(f'Populating tree with {self.iso_file.title_count} titles')

        for title_idx in range(1, self.iso_file.title_count + 1):
            try:
                self._add_title_to_tree(title_idx)
            except Exception as e:
                error(f'Failed to add title {title_idx}: {e}\n{format_exc()}')
                continue

    def _add_title_to_tree(self, title_idx: int) -> None:
        """Add a title and its details to the tree widget."""

        tt_srpt = self.iso_file.ifo0.tt_srpt[title_idx - 1]
        angle_count = tt_srpt.nr_of_angles

        if self._load_title(title_idx, angle_count) is None:
            error(f'Failed to load any angles for title {title_idx}')
            return

        title_item = QTreeWidgetItem(self.tree, [f"Title {title_idx}"])

        self._add_angles_to_item(title_item, title_idx, angle_count)

    def _load_title(self, title_idx: int, angle_count: int) -> Title | None:
        """Load title and store its info."""

        angles = range(1, angle_count + 1) if angle_count > 1 else [None]

        for angle in angles:
            try:
                title = self.iso_file.get_title(title_idx, angle)

                self._store_title_info(title_idx, angle, title, title.video, angle_count)

                return title
            except Exception as e:
                error(f'Failed to load title {title_idx} angle {angle}: {e}\n{format_exc()}')
                continue

        return None

    def _store_title_info(
        self, title_idx: int, angle: int | None, title: Title, video: vs.VideoNode, angle_count: int
    ) -> None:
        """Store information about a title in title_info."""

        audio_tracks = [
            track for track in getattr(title, '_audios', [])
            if track and track.lower() != 'none'
        ]

        self.title_info[(title_idx, angle)] = {
            'title_idx': title_idx,
            'angle': angle,
            'chapter_count': len(title.chapters),
            'chapters': title.chapters,
            'audio_tracks': audio_tracks,
            'angle_count': angle_count,
            'width': video.width,
            'height': video.height,
            'fps': video.fps,
            'duration': len(video) / video.fps
        }

    def _add_angles_to_item(self, parent_item: QTreeWidgetItem, title_idx: int, angle_count: int) -> None:
        """Add angle information to a tree item."""

        if angle_count > 1:
            for angle in range(1, angle_count + 1):
                angle_item = QTreeWidgetItem(parent_item, [f"Angle {angle}"])
                angle_item.setData(0, 100, ("title", title_idx, angle))
        else:
            parent_item.setData(0, 100, ("title", title_idx, None))

    def _on_tree_item_selected(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle title/angle selection."""

        if not self.iso_file or not (data := item.data(0, 100)):
            debug('No valid item data or ISO file')
            return

        item_type, title_idx, angle = data

        if item_type != "title":
            debug(f'Ignoring non-title item type: {item_type}')
            return

        try:
            debug(f'Loading title {title_idx} ({angle=})')
            self._load_selected_title(title_idx, angle)
        except Exception as e:
            error(f'Failed to load title: {e}\n{format_exc()}')
            QMessageBox.critical(self, "Error", f"Failed to load title: {str(e)}")

    def _load_selected_title(self, title_idx: int, angle: int | None) -> None:
        """Load and display the selected title."""

        if not (info := self.title_info.get((title_idx, angle))):
            debug(f'No info found for title {title_idx} angle {angle}')
            return

        self.current_title = self.iso_file.get_title(title_idx, angle)
        self.current_node = self.current_title.video

        self.dump_audio_button.setEnabled(bool(info['audio_tracks']))
        self._update_info_label(info)

        self._update_outputs(title_idx, angle)

    def _update_outputs(self, title_idx: int, angle: int | None) -> None:
        """Update the outputs with the new video node."""

        new_output = self.plugin.main.outputs[self.plugin.main.current_output.index].with_node(self.current_node)
        new_output.name = f"Title {title_idx}" + (f" Angle {angle}" if angle else "")

        self.plugin.main.outputs.items.clear()
        self.plugin.main.outputs.items.append(new_output)
        new_output.index = -1

        self.plugin.main.refresh_video_outputs()
        self.plugin.main.switch_output(0)

    def _update_info_label(self, info: TitleInfo) -> None:
        """Update info label with title details."""

        info_text = [
            f"Angle: {info['angle'] if info['angle'] else 1}/{info['angle_count']}",
            self._format_duration(info['duration']),
            f"Resolution: {info['width']}x{info['height']}",
            f"Chapters: {info['chapter_count']}"
        ]

        if info.get('audio_tracks', None):
            info_text += ["Audio Track(s):"]

            for i, track in enumerate(info['audio_tracks'], 1):
                info_text += [f"  {i}. {track}"]
        else:
            info_text += ["Audio Track(s): None"]

        self.info_label.setText("\n".join(info_text))

    def _format_duration(self, duration_secs: float) -> str:
        """Format duration in seconds to HH:MM:SS.mmm format."""

        hours = int(duration_secs // 3600)
        minutes = int((duration_secs % 3600) // 60)
        seconds = int(duration_secs % 60)
        milliseconds = int((duration_secs % 1) * 1000)

        return f"Duration: {hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

    def _check_current_title(self) -> bool:
        """Check if current title exists and is valid."""

        if not hasattr(self, 'current_title'):
            return False

        if self.current_title is None:
            return False

        return True

    def on_current_frame_changed(self, frame: Frame) -> None:
        if not self._check_current_title():
            return

        try:
            self.current_title.frame = frame.value
        except AttributeError as e:
            debug(f'Failed to update frame in on_current_frame_changed: {e}\n{format_exc()}')
            pass

    def on_current_output_changed(self, index: int, prev_index: int) -> None:
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
        return {
            'iso_path': str(self.iso_path) if self.iso_path else None
        }

    def __setstate__(self, state: dict[str, Any]) -> None:
        if (iso_path := state.get('iso_path')) is None:
            return

        self.iso_path = SPath(iso_path)

        try:
            debug(f'Loading saved ISO state: {iso_path}')
            self.iso_file = IsoFile(self.iso_path)
            self.file_label.setText(self.iso_path.name)
            self._populate_tree()
        except Exception as e:
            error(f'Failed to load saved ISO state: {e}\n{format_exc()}')
            self._reset_iso_state()
            QMessageBox.critical(self, "Error", f"Failed to load ISO: {str(e)}")
