from logging import debug, error
from traceback import format_exc
from typing import Optional
from vspreview import set_timecodes

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem

from vssource import Title

__all__ = [
    'ISOTreeManager',
]


class ISOTreeManager:
    """Manages the tree widget for ISO browsing."""

    def __init__(self, parent) -> None:
        self.parent = parent
        self.tree = QTreeWidget()
        self.chapters_tree = QTreeWidget()
        self._setup_tree()
        self._setup_chapters_tree()

    def _setup_tree(self) -> None:
        """Configure tree widget."""
        self.tree.setHeaderLabels(["Titles"])
        self.tree.itemClicked.connect(self._on_tree_item_selected)

    def _setup_chapters_tree(self) -> None:
        """Configure chapters tree widget."""

        self.chapters_tree.setHeaderLabels(["Chapters"])
        self.chapters_tree.itemClicked.connect(self._on_chapter_selected)
        self.chapters_tree.setVisible(False)
        self.chapters_tree.setMinimumHeight(300)
        self.chapters_tree.setContentsMargins(0, 50, 0, 50)

    def populate_tree(self) -> None:
        """Populate the tree widget with titles and angles."""

        self.tree.clear()
        self.chapters_tree.clear()
        self.chapters_tree.setVisible(False)
        self.parent.title_info.clear()

        if not self.parent.iso_file:
            debug('No DVD loaded')
            return

        try:
            self._add_titles_to_tree()
            self.tree.expandAll()

            if not self.parent.iso_path.suffix.lower() == '.ifo':
                self.parent.dump_all_titles_button.setEnabled(self.parent.iso_file.title_count > 0)
        except Exception as e:
            error(f'Failed to populate tree: {e}\n{format_exc()}')
            self.parent._reset_iso_state()
            raise

    def _add_titles_to_tree(self) -> None:
        """Add all titles to the tree."""

        debug(f'Populating tree with {self.parent.iso_file.title_count} titles')

        for title_idx in range(1, self.parent.iso_file.title_count + 1):
            debug(f'Adding title {title_idx}')

            try:
                self._add_title_to_tree(title_idx)
            except Exception as e:
                error(f'Failed to add title {title_idx}: {e}\n{format_exc()}')
                continue

    def _add_title_to_tree(self, title_idx: int) -> None:
        """Add a title and its details to the tree widget."""

        tt_srpt = self.parent.iso_file.ifo0.tt_srpt[title_idx - 1]
        angle_count = tt_srpt.nr_of_angles

        debug(f'Title {title_idx} has {angle_count} angle(s)')

        if angle_count == 1:
            # Single angle title
            if self._load_title(title_idx, None) is None:
                error(f'Failed to load base title {title_idx}')
                return None

            debug(f'Getting title info for title {title_idx} (no angle)')
            title_info = self.parent.title_info.get((title_idx, None))
            if title_info is None:
                error(f'Title info not found for title {title_idx}')
                return None
            debug(f'Title info found: {title_info is not None}')

            duration_str = self._format_duration(title_info['duration']) if title_info else ""
            debug(f'Formatted duration: {duration_str}')

            debug(f'Creating tree item for title {title_idx}')
            title_item = QTreeWidgetItem(self.tree, [f"Title {title_idx} ({duration_str})"])
            title_item.setData(0, Qt.ItemDataRole.UserRole, {'title': title_idx, 'angle': None})
            debug(f'Tree item created with label: Title {title_idx} ({duration_str})')
            return

        # Multi-angle title
        title_item = QTreeWidgetItem(self.tree, [f"Title {title_idx} (Multi-Angle)"])
        title_item.setFlags(title_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)

        # Add all angles as sub-items
        for angle in range(1, angle_count + 1):
            debug(f'Loading angle {angle} for title {title_idx}')
            if self._load_title(title_idx, angle) is None:
                continue

            angle_info = self.parent.title_info.get((title_idx, angle))
            angle_duration = self._format_duration(angle_info['duration']) if angle_info else ""
            angle_item = QTreeWidgetItem(title_item, [f"Angle {angle} ({angle_duration})"])
            angle_item.setData(0, Qt.ItemDataRole.UserRole, {'title': title_idx, 'angle': angle})

    def _load_title(self, title_idx: int, angle: Optional[int]) -> Optional[Title]:
        """Load title and store its info."""

        try:
            debug(f'Attempting to get title {title_idx} angle {angle}')

            if not (title := self.parent.iso_file.get_title(title_idx, angle)):
                debug(f'Title {title_idx} angle {angle} not found')
                return None

            debug(f'Getting video stream for title {title_idx} angle {angle}')
            video = title.video

            if not video:
                debug(f'No video stream found for title {title_idx} angle {angle}')
                return None

            debug(f'Getting title info from tt_srpt for title {title_idx}')
            tt_srpt = self.parent.iso_file.ifo0.tt_srpt[title_idx - 1]

            # Get audio tracks
            debug(f'Getting audio tracks for title {title_idx} angle {angle}')
            audio_tracks = self._get_audio_tracks(title, title_idx, angle)

            debug(f'Creating title info dict for title {title_idx} angle {angle}')

            title_info = {
                'title_idx': title_idx,
                'angle': angle,
                'chapter_count': len(title.chapters),
                'chapters': title.chapters,
                'audio_tracks': audio_tracks,
                'angle_count': tt_srpt.nr_of_angles,
                'width': video.width,
                'height': video.height,
                'fps': float(video.fps),
                'duration': float(video.num_frames / video.fps),
                'frame_count': video.num_frames,
                'vts': title._vts
            }

            debug(f'Storing title info for title {title_idx} angle {angle}')
            self.parent.title_info[(title_idx, angle)] = title_info

            debug(f'Successfully loaded title {title_idx} angle {angle}')
            return title

        except Exception as e:
            error(f'Failed to load title {title_idx} angle {angle}: {e}\n{format_exc()}')
            return None

    def _get_audio_tracks(self, title: Title, title_idx: int, angle: Optional[int]) -> list[str]:
        """Get audio tracks safely."""

        audio_tracks = []

        try:
            debug(f'Getting audio tracks for title {title_idx} angle {angle}')

            try:
                debug('Getting info for audio track')

                for track in title._audios:
                    if track and track.lower() != 'none':
                        audio_tracks.append(track)

            except Exception:
                debug('Failed to get info for audio track, using fallback name')
                audio_tracks.append("Unknown Codec")

        except Exception as e:
            debug(f'Failed to get audio tracks for title {title_idx} angle {angle}: {e}')

        debug(f'Found {len(audio_tracks)} audio tracks')

        return audio_tracks

    def _on_tree_item_selected(self, item: QTreeWidgetItem) -> None:
        """Handle tree item selection."""

        if not item:
            self.chapters_tree.setVisible(False)
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)

        if not data:
            self.chapters_tree.setVisible(False)
            return

        title_idx = data['title']
        angle = data['angle']

        try:
            debug(f'Loading title {title_idx} ({angle=})')
            self._load_selected_title(title_idx, angle)
            self.parent.copy_script_button.setEnabled(True)
        except Exception as e:
            error(f'Failed to load title: {e}\n{format_exc()}')
            raise

    def _load_selected_title(self, title_idx: int, angle: Optional[int]) -> None:
        """Load and display the selected title."""

        if not (info := self.parent.title_info.get((title_idx, angle))):
            debug(f'No info found for title {title_idx} angle {angle}')
            return

        self.parent.current_title = self.parent.iso_file.get_title(title_idx, angle)
        self.parent.current_node = self.parent.current_title.video

        # Update chapter spinboxes
        chapter_count = info['chapter_count']
        has_chapters = chapter_count > 0

        self.parent.chapter_label.setEnabled(has_chapters)
        self.parent.chapter_start_spin.setEnabled(has_chapters)
        self.parent.chapter_end_spin.setEnabled(has_chapters)
        self.parent.chapter_to_label.setEnabled(has_chapters)
        self.parent.chapter_dump_label.setEnabled(has_chapters)

        if has_chapters:
            self.parent.chapter_start_spin.setMaximum(chapter_count)
            self.parent.chapter_end_spin.setMaximum(chapter_count)
            self.parent.chapter_end_spin.setValue(chapter_count)

        # Update FFmpeg handler chapter values
        self.parent.ffmpeg_handler.chapter_start = self.parent.chapter_start_spin.value() if has_chapters else None
        self.parent.ffmpeg_handler.chapter_end = self.parent.chapter_end_spin.value() if has_chapters else None

        if not self.parent.iso_path.suffix.lower() == '.ifo':
            self.parent.dump_title_button.setEnabled(bool(info['audio_tracks']))

        self._update_info_label(info)
        self._update_outputs(title_idx, angle)
        self._populate_chapters_tree(info)

    def _update_outputs(self, title_idx: int, angle: Optional[int]) -> None:
        """Update the outputs with the new video and audio nodes and load chapters as scenechanges."""

        main = self.parent.plugin.main
        current_output_idx = main.current_output.index

        video_output = main.outputs[current_output_idx].with_node(self.parent.current_node)
        video_output.name = f"Title {title_idx}" + (f" Angle {angle}" if angle is not None else "") + " (Video)"

        # TODO: Add audio outputs

        if (info := self.parent.title_info.get((title_idx, angle))) and info['chapters']:
            debug(f'Loading {len(info["chapters"])} chapters as scenechanges')

            try:
                chapter_frames = [
                    int(frame) for frame in info['chapters']
                    if frame > 0
                ]

                set_timecodes(video_output, chapter_frames)
                debug(f'Added {len(chapter_frames)} chapter frames as scenechanges')
            except Exception as e:
                error(f'Failed to load chapters as scenechanges: {e}\n{format_exc()}')

        main.outputs.items.clear()
        main.outputs.items.append(video_output)
        video_output.index = -1

        main.refresh_video_outputs()
        main.switch_output(0)

    def _update_info_label(self, info: dict) -> None:
        """Update info label with title details."""

        info_text = [
            f"Angle: {info['angle'] if info['angle'] is not None else 1}/{info['angle_count']}",
            f"Duration: {self._format_duration(info['duration'])}",
            f"Resolution: {info['width']}x{info['height']}",
            f"Chapters: {info['chapter_count']}",
            f"Frame Count: {info['frame_count']}",
            f"VTS: {info['vts']}"
        ]

        if info.get('audio_tracks', None):
            info_text += ["Audio Track(s):"]

            for i, track in enumerate(info['audio_tracks'], 1):
                info_text += [f"  {i}. {track}"]
        else:
            info_text += ["Audio Track(s): None"]

        self.parent.info_label.setText("\n".join(info_text))

    def _format_duration(self, duration_secs: float) -> str:
        """Format duration in seconds to HH:MM:SS format."""

        hours = int(duration_secs // 3600)
        minutes = int((duration_secs % 3600) // 60)
        seconds = int(duration_secs % 60)

        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _populate_chapters_tree(self, info: dict) -> None:
        """Populate chapters tree with chapter information."""

        self.chapters_tree.clear()
        chapters = info.get('chapters', [])

        # Update chapter spinbox visibility and values based on chapter availability
        has_chapters = bool(chapters)

        # Show/hide chapter controls
        self.chapters_tree.setVisible(has_chapters)
        self.parent.chapter_widget.setVisible(has_chapters)

        if not has_chapters:
            return

        # Set spinbox ranges
        chapter_count = len(chapters)
        self.parent.chapter_start_spin.setMaximum(chapter_count)
        self.parent.chapter_end_spin.setMaximum(chapter_count)
        self.parent.chapter_end_spin.setValue(chapter_count)

        # Connect value changed signals to ensure valid ranges
        self.parent.chapter_start_spin.valueChanged.connect(self._on_chapter_start_changed)
        self.parent.chapter_end_spin.valueChanged.connect(self._on_chapter_end_changed)

        # Update FFmpeg handler chapter values
        self.parent.ffmpeg_handler.chapter_start = self.parent.chapter_start_spin.value()
        self.parent.ffmpeg_handler.chapter_end = self.parent.chapter_end_spin.value()

        # Populate chapter tree
        fps = info['fps']
        for i, frame in enumerate(chapters, 1):
            timestamp = self._format_duration(frame / fps)
            chapter_item = QTreeWidgetItem(self.chapters_tree, [f"Chapter {i} - Frame {frame} - {timestamp}"])
            chapter_item.setData(0, Qt.ItemDataRole.UserRole, {'frame': frame})

    def _on_chapter_start_changed(self, value: int) -> None:
        """Ensure start chapter doesn't exceed end chapter."""
        if value > self.parent.chapter_end_spin.value():
            self.parent.chapter_end_spin.setValue(value)

        # Store chapter values in title info
        title_idx = self.parent.current_title._title + 1
        angle = getattr(self.parent.current_title, 'angle', None)
        title_key = (title_idx, angle)

        debug(f'Updating chapter start: title_key={title_key}, value={value}')
        if title_key in self.parent.title_info:
            debug(f'Current title_info before update: {self.parent.title_info[title_key]}')
            self.parent.title_info[title_key]['chapter_start'] = value
            self.parent.ffmpeg_handler.chapter_start = value
            debug(f'Updated title_info: {self.parent.title_info[title_key]}')

    def _on_chapter_end_changed(self, value: int) -> None:
        """Ensure end chapter isn't less than start chapter."""
        if value < self.parent.chapter_start_spin.value():
            self.parent.chapter_start_spin.setValue(value)

        # Store chapter values in title info
        title_idx = self.parent.current_title._title + 1
        angle = getattr(self.parent.current_title, 'angle', None)
        title_key = (title_idx, angle)

        debug(f'Updating chapter end: title_key={title_key}, value={value}')
        if title_key in self.parent.title_info:
            debug(f'Current title_info before update: {self.parent.title_info[title_key]}')
            self.parent.title_info[title_key]['chapter_end'] = value
            self.parent.ffmpeg_handler.chapter_end = value
            debug(f'Updated title_info: {self.parent.title_info[title_key]}')

    def _on_chapter_selected(self, item: QTreeWidgetItem) -> None:
        """Handle chapter selection by jumping to the chapter frame."""

        if not item:
            return

        if not (data := item.data(0, Qt.ItemDataRole.UserRole)) or 'frame' not in data:
            return

        # TODO: Figure out why this is not working
        main = self.parent.plugin.main
        main.current_output.frame = data['frame']

    def clear(self) -> None:
        """Clear the tree widgets."""
        self.tree.clear()
        self.chapters_tree.clear()
        self.chapters_tree.setVisible(False)
        self.parent.chapter_widget.setVisible(False)  # Hide chapter controls when clearing
