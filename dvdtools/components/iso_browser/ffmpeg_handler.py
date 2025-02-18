from logging import warning, DEBUG, debug, error, getLogger
from traceback import format_exc
import subprocess
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox, QProgressDialog
from vstools import SPath

__all__ = [
    'FFmpegHandler',
]


class FFmpegHandler:
    """Handles FFmpeg-related operations for ISO dumping."""

    def __init__(self, parent) -> None:
        self.parent = parent
        self.log_level = getLogger().getEffectiveLevel()
        # Add default chapter values
        self.chapter_start = None
        self.chapter_end = None

    def dump_all_titles(self) -> None:
        """Dump all titles from the ISO."""

        if not self._check_ffmpeg():
            return

        # Get save directory
        save_dir = QFileDialog.getExistingDirectory(
            self.parent, "Select output directory", str(self.parent.iso_path.parent)
        )

        if not save_dir:
            return

        save_dir = SPath(save_dir)

        # Get all unique titles and their info
        unique_titles = {}

        for i, ((title_idx, _), info) in enumerate(self.parent.title_info.items()):
            if title_idx not in {k[0] for k in list(self.parent.title_info.keys())[:i]}:
                unique_titles[title_idx] = info

        total_titles = len(unique_titles)
        debug(f'Found {total_titles} unique titles')

        # Create progress dialog
        progress = QProgressDialog("Dumping titles...", "Cancel", 0, total_titles, self.parent)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setWindowTitle("Dumping Titles")

        titles_processed = 0

        try:
            for title_idx, info in sorted(unique_titles.items()):
                if progress.wasCanceled():
                    break

                # Set full chapter range for this title
                chapter_count = info.get('chapter_count', 1)
                self.chapter_start = 1
                self.chapter_end = chapter_count

                angle_count = info.get('angle_count', 1)
                debug(f'Processing title {title_idx} with {angle_count} angles')

                try:
                    output_path = save_dir / self._get_suggested_filename(title_idx, info)

                    if angle_count == 1:
                        progress.setLabelText(f"Processing title {title_idx}/{total_titles}")
                        debug(f'Dumping title {title_idx} to {output_path}')
                        self._dump_title(title_idx, str(output_path))
                        continue

                    # Process titles with multiple angles
                    for angle in range(1, angle_count + 1):
                        # Replace the last digits in the filename with the current angle
                        # TODO: Use regular substitution here, but that requires rewriting a bunch of other stuff.
                        output_path = output_path.with_name(
                            output_path.name.rsplit('_', 1)[0] + f'_{angle:02d}.mkv'
                        )

                        progress.setLabelText(
                            f"Processing title {title_idx}/{total_titles} - Angle {angle}/{angle_count}"
                        )

                        debug(f'Dumping title {title_idx} angle {angle} to {output_path}')

                        try:
                            self._dump_title(title_idx, str(output_path), angle)
                        except RuntimeError as e:
                            warning(f'Failed to dump title {title_idx} angle {angle}: {str(e)}')
                            continue

                except RuntimeError as e:
                    warning(f'Failed to dump title {title_idx}: {str(e)}')
                    continue
                except Exception as e:
                    error(f'Unexpected error dumping title {title_idx}: {str(e)}\n{format_exc()}')
                    continue

                titles_processed += 1
                progress.setValue(titles_processed)
                QApplication.processEvents()

        finally:
            progress.close()

    def dump_title(self) -> None:
        """Dump currently selected title."""

        debug('Dumping title')

        if not self._check_ffmpeg():
            return

        selected_item = self.parent.tree_manager.tree.currentItem()
        data = selected_item.data(0, Qt.ItemDataRole.UserRole)

        title_idx = data['title']
        angle = data.get('angle')
        title_info = self.parent.title_info.get((title_idx, angle), {})

        debug(f'Dumping title {title_idx} (angle {angle})')

        # Get save path
        debug('Getting save path for title dump')
        suggested_name = self._get_suggested_filename(title_idx, title_info)
        debug(f'Suggested filename: {suggested_name}')

        output_path = self._get_save_path(suggested_name)

        if not output_path:
            debug('User cancelled save dialog')
            return

        self._dump_title(title_idx, output_path, angle)

    def _check_ffmpeg(self) -> bool:
        """Check if ffmpeg is available and supports DVD video."""
        debug('Checking FFmpeg installation and DVD video support')

        try:
            result = subprocess.run(
                ['ffmpeg', '-hide_banner', '-h', 'demuxer=dvdvideo'],
                capture_output=True, text=True, check=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            error(f'FFmpeg check failed: {e}\n{format_exc()}')
            QMessageBox.critical(
                self.parent, "Error",
                "FFmpeg not found. Please install FFmpeg and make sure it's in your PATH."
            )

            return False

        if 'dvdvideo' not in result.stdout:
            error('FFmpeg installation does not support DVD video demuxing!')
            QMessageBox.critical(
                self.parent, "Error",
                "FFmpeg installation does not support DVD video demuxing. "
                "Please ensure FFmpeg was built with GPL library support "
                "and the configure switches --enable-libdvdnav and --enable-libdvdread."
            )

            return False

        return True

    def _get_suggested_filename(self, title_idx: int, title_info: dict[str, Any] | int) -> str:
        """Get suggested filename for title dump."""

        # Normalize title_info and angle
        if isinstance(title_info, int):
            angle = title_info
            title_info = (
                self.parent.title_info.get((title_idx, angle)) or
                self.parent.title_info.get((title_idx, None), {})
            )
            if angle is not None and title_info:
                title_info = {**title_info, 'angle': angle}
        else:
            angle = title_info.get('angle', 1)  # Default to angle 1 if not specified

        # Build filename components
        base_name = self.parent.iso_path.stem
        title_str = f"title_{title_idx:02d}"

        angle_str = ""
        chapter_str = ""

        # Add angle if title has multiple angles
        has_multiple_angles = title_info.get('angle_count', 1) > 1

        if has_multiple_angles:
            print('xxxxxxxxxxxxxxxxxxxxx', angle)
            angle_str = f"_angle_{angle:02d}"

        # Add chapter range if not using full range
        if hasattr(self, 'chapter_start') and hasattr(self, 'chapter_end'):
            chapter_count = title_info.get('chapter_count', 1)

            if not (self.chapter_start == 1 and self.chapter_end == chapter_count):
                chapter_str = (
                    f"_ch{self.chapter_start:02d}"
                    if self.chapter_start == self.chapter_end
                    else f"_ch{self.chapter_start:02d}-{self.chapter_end:02d}"
                )

        return f"{base_name}_{title_str}{angle_str}{chapter_str}.mkv"

    def _get_save_path(self, filename: str = '') -> str | None:
        """Get the save path for the video/audio output."""

        debug('Getting save path for title dump')

        title_idx = self.parent.current_title._title + 1
        angle = getattr(self.parent.current_title, 'angle', 1)
        title_key = (title_idx, angle)

        if title_key not in self.parent.title_info:
            title_key = (title_idx, None)

            if title_key not in self.parent.title_info:
                error(
                    f'Title info lookup failed:\n'
                    f'Title key: {title_key}\n'
                    f'Title info keys: {list(self.parent.title_info.keys())}\n'
                    f'Title number: {title_idx}\n'
                    f'Title angle: {angle}'
                )
                QMessageBox.critical(self.parent, "Error", "Title information not found!")
                return

        suggested_name = filename or self._get_suggested_filename(title_idx, angle)
        debug(f'Suggested filename: {suggested_name}')

        output_path, _ = QFileDialog.getSaveFileName(
            self.parent,
            "Save Title",
            str(self.parent.iso_path.parent / suggested_name),
            "Matroska Video (*.mkv);;All files (*.*)"
        )

        if output_path:
            debug(f'Selected output path: {output_path}')

        return output_path

    def _build_ffmpeg_command(self, file_path: str, output_path: str | SPath, angle: int | None, title_idx: int | None = None) -> list[str]:
        """Build the ffmpeg command for video and all audio extraction."""

        if title_idx is None:
            title_idx = self.parent.current_title._title + 1

        # Try both with and without angle for title info lookup
        title_key = (title_idx, angle)
        title_info = self.parent.title_info.get(title_key, {})

        if not title_info:
            title_key = (title_idx, None)
            title_info = self.parent.title_info.get(title_key, {})

        debug(f'Building FFmpeg command for title_key={title_key}')
        debug(f'Title info: {title_info}')

        cmd = [
            'ffmpeg', '-hide_banner',
            '-f', 'dvdvideo',
            '-preindex', 'True',
        ]

        # Add chapter trimming parameters if available and needed
        if 'chapters' in title_info:
            chapter_count = title_info.get('chapter_count', 0)

            # Only add chapter_start if it's not the first chapter
            if self.chapter_start is not None:
                if self.chapter_start > 1:
                    debug(f'Adding chapter start: {self.chapter_start}')
                    cmd.extend(['-chapter_start', str(self.chapter_start)])

            # Only add chapter_end if it's not the last chapter
            if self.chapter_end is not None:
                if self.chapter_end < chapter_count:
                    debug(f'Adding chapter end: {self.chapter_end}')
                    cmd.extend(['-chapter_end', str(self.chapter_end)])
        else:
            debug('No chapters available in title info')

        cmd.extend(['-title', str(title_idx)])

        if angle is not None:
            cmd.extend(['-angle', str(angle)])

        # Properly quote the input path
        quoted_input = f'"{file_path}"'
        cmd.extend(['-i', quoted_input])

        cmd.extend([
            '-map', '0:v:0',
            '-c:v', 'copy'
        ])

        if title_key not in self.parent.title_info:
            title_key = (title_idx, None)
            if title_key not in self.parent.title_info:
                error(f'Title info not found for {title_key}')
                return cmd

        title_info = self.parent.title_info[title_key]
        audio_tracks = title_info['audio_tracks']

        for idx, audio_info in enumerate(audio_tracks):
            cmd.extend(['-map', f'0:a:{idx}'])

            if 'pcm' in audio_info.lower():
                warning(f'PCM audio detected for track {idx}, re-encoding to FLAC')
                cmd.extend([f'-c:a:{idx}', 'flac', '-compression_level', '8'])
            else:
                debug(f'{audio_info} audio detected for track {idx}, copying stream')
                cmd.extend([f'-c:a:{idx}', 'copy'])

            if lang_info := title_info.get('audio_langs', [])[idx] if 'audio_langs' in title_info else None:
                debug(f'Setting language metadata for audio track {idx}: {lang_info}')
                cmd.extend([
                    f'-metadata:s:a:{idx}', f'language={lang_info}',
                    f'-metadata:s:a:{idx}', f'title=Audio Track {idx+1} ({lang_info.upper()})'
                ])

        # Properly quote the output path
        if isinstance(output_path, SPath):
            output_path = str(output_path)

        quoted_output = f'"{output_path}"'
        cmd.append(quoted_output)
        return cmd

    def _run_ffmpeg_process(self, cmd: list[str]) -> None:
        """Run FFmpeg process and handle output."""

        # Get input and output paths from command
        input_idx = cmd.index('-i') + 1
        input_path = cmd[input_idx].strip('"')
        output_path = cmd[-1].strip('"')

        # Delete output file if it exists (ffmpeg will hang if it's there, even with -y)
        if SPath(output_path).exists():
            debug(f'Deleting existing output file: {output_path}')
            SPath(output_path).unlink()

        # Properly escape paths for subprocess
        cmd[input_idx] = SPath(input_path).as_posix()
        cmd[-1] = SPath(output_path).as_posix()

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )

        error_output = ''

        while True:
            output = process.stderr.readline()
            if output == '' and process.poll() is not None:
                break

            if output:
                error_output += output

                if 'time=' in output:
                    if self.log_level == DEBUG:
                        print(output.strip())

        if process.returncode != 0:
            if 'looks empty (may consist of padding cells)' in error_output:
                warning('Skipping empty title (padding cells)')
                return

            error(f'FFmpeg process failed:\n{error_output}')
            raise RuntimeError(f"Failed to dump titles:\n\n{error_output}")

    def _dump_title(self, title_idx: int, output_path: str, angle: int | None = None) -> None:
        """Dump a single title."""

        cmd = self._build_ffmpeg_command(self.parent.iso_path.to_str(), output_path, angle, title_idx)

        self._run_ffmpeg_process(cmd)
