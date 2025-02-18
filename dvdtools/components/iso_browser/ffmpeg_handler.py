from logging import warning, DEBUG, debug, error, getLogger
from traceback import format_exc
import subprocess
from typing import List

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

    def dump_all_titles(self) -> None:
        """Dump all titles to files using ffmpeg."""

        debug('Dumping all titles')

        if not self.parent.iso_file:
            error('No ISO file loaded')
            return

        output_dir = QFileDialog.getExistingDirectory(
            self.parent,
            "Select Output Directory",
            str(self.parent.iso_path.parent if self.parent.iso_path else '.')
        )

        if not output_dir:
            debug('User cancelled directory selection')
            return

        output_dir = SPath(output_dir)
        title_count = self.parent.iso_file.title_count

        progress = QProgressDialog("Dumping all titles...", "Cancel", 0, title_count, self.parent)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setWindowTitle("Dumping All Titles")
        progress.show()

        successful_dumps = 0
        failed_dumps = []

        # TODO: Async?
        try:
            for title_idx in range(1, title_count + 1):
                if progress.wasCanceled():
                    debug('User cancelled dump all titles')
                    break

                tt_srpt = self.parent.iso_file.ifo0.tt_srpt[title_idx - 1]
                angle_count = tt_srpt.nr_of_angles

                for angle in range(1, angle_count + 1):
                    progress.setLabelText(
                        f"Dumping title {title_idx}/{title_count}"
                        + (f" angle {angle}/{angle_count}" if angle_count > 1 else "")
                    )
                    progress.setValue(title_idx - 1)
                    QApplication.processEvents()

                    try:
                        self.parent.current_title = self.parent.iso_file.get_title(title_idx, angle if angle_count > 1 else None)
                        output_name = self._get_title_filename(title_idx, angle if angle_count > 1 else None)
                        output_path = output_dir / output_name

                        if output_path.exists():
                            debug(f'Deleting existing file: {output_path}')
                            output_path.unlink()

                        cmd = self._build_ffmpeg_command(self.parent.iso_path.to_str(), output_path.to_str(), angle)
                        debug(f'FFmpeg command built for title {title_idx}/{angle_count} angle {angle}/{angle_count}: {" ".join(cmd)}')

                        self._run_ffmpeg_process(cmd, show_progress=False)
                        successful_dumps += 1

                    except Exception as e:
                        error(f'Failed to dump title {title_idx} angle {angle}: {e}\n{format_exc()}')
                        failed_dumps.append(f"{title_idx} (angle {angle})")

            progress.setValue(title_count)

            if successful_dumps > 0:
                summary = f"Successfully dumped {successful_dumps} titles to: {output_dir}"

                if failed_dumps:
                    summary += f"\n\nFailed to dump titles: {', '.join(map(str, failed_dumps))}"

                QMessageBox.information(self.parent, "Dump Complete", summary)
            else:
                QMessageBox.critical(self.parent, "Error", "Failed to dump any titles!")

        except Exception as e:
            error(f'Failed to dump all titles: {e}\n{format_exc()}')
            QMessageBox.critical(self.parent, "Error", f"Failed to dump all titles: {str(e)}")
        finally:
            progress.close()

    def dump_title(self) -> None:
        """Dump video and all audio tracks to file using ffmpeg."""

        debug('Dumping title')

        if not self._check_ffmpeg_support():
            error('FFmpeg support check failed')
            return

        if not self.parent.iso_path:
            error('No ISO file loaded')
            return

        if not self.parent.current_title:
            error('No title selected')
            return

        title_idx = self.parent.current_title._title + 1
        angle = getattr(self.parent.current_title, 'angle', 1)
        debug(f'Dumping title {title_idx} (angle {angle})')

        # Try both with and without angle if lookup fails
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

        output_path = self._get_save_path()

        if not output_path:
            debug('User cancelled save dialog')
            return

        cmd = self._build_ffmpeg_command(self.parent.iso_path.to_str(), output_path)
        debug(f'FFmpeg command built: {" ".join(cmd)}')

        self._run_ffmpeg_process(cmd)

    def _check_ffmpeg_support(self) -> bool:
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

    def _get_title_filename(self, title_idx: int, angle: int | None) -> str:
        """Generate filename for a title."""

        name = f"{self.parent.iso_path.stem}_title_{title_idx:02d}"

        if angle is not None:
            name += f"_angle_{angle:02d}"

        return name + ".mkv"

    def _get_save_path(self) -> str | None:
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

        suggested_name = self._get_title_filename(title_idx, angle)
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

    def _build_ffmpeg_command(self, file_path: str, output_path: str, angle: int | None) -> List[str]:
        """Build the ffmpeg command for video and all audio extraction."""

        title_idx = self.parent.current_title._title + 1

        cmd = [
            'ffmpeg', '-hide_banner',
            '-f', 'dvdvideo',
            '-preindex', 'True',
            '-title', str(title_idx)
        ]

        if angle is not None:
            cmd.extend(['-angle', str(angle)])

        cmd.extend(['-i', file_path])

        # Add video stream
        cmd.extend([
            '-map', '0:v:0',
            '-c:v', 'copy'
        ])

        # Try both with and without angle for title info lookup
        title_key = (title_idx, angle)
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

        cmd.append(output_path)
        return cmd

    def _run_ffmpeg_process(self, cmd: List[str], show_progress: bool = True) -> None:
        """Run the ffmpeg process with progress dialog."""

        if (output_file := SPath(cmd[-1])).exists():
            debug(f'Deleting existing output file: {output_file}')
            output_file.unlink(missing_ok=True)

        progress = None

        if show_progress:
            progress = QProgressDialog("Starting dump process...", "Cancel", 0, 100, self.parent)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setWindowTitle("FFmpeg Progress")
            progress.show()

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1
            )

            duration = None
            time = 0

            while process.poll() is None:
                if progress and progress.wasCanceled():
                    debug('User cancelled FFmpeg process')
                    process.terminate()
                    process.wait()
                    break

                if not process.stderr:
                    QApplication.processEvents()
                    continue

                line = process.stderr.readline()

                if self.log_level <= DEBUG:
                    print(line, end='')

                if 'already exists. Overwrite?' in line:
                    process.stdin.write('y\n')
                    process.stdin.flush()
                    continue

                if not progress:
                    continue

                if 'Duration:' in line and not duration:
                    try:
                        duration_str = line.split('Duration: ')[1].split(',')[0]
                        h, m, s = map(float, duration_str.split(':'))
                        duration = h * 3600 + m * 60 + s
                    except Exception as e:
                        error(f'Failed to parse duration: {e}\n{format_exc()}')
                    continue

                if 'time=' not in line:
                    continue

                try:
                    time_str = line.split('time=')[1].split()[0]
                    h, m, s = map(float, time_str.split(':'))
                    time = h * 3600 + m * 60 + s

                    if duration:
                        progress.setValue(int(time / duration * 100))
                        progress.setLabelText(f"Time: {time_str} / {duration_str}")
                except Exception as e:
                    error(f'Failed to parse time: {e}\n{format_exc()}')

                QApplication.processEvents()

            if process.returncode != 0:
                error_output = process.stderr.read() if process.stderr else "Unknown error"
                if 'ffmpeg version' in error_output:
                    error_output = '\n'.join(
                        line for line in error_output.splitlines()
                        if not line.startswith('  ')
                        and 'ffmpeg version' not in line
                        and 'configuration:' not in line
                        and 'lib' not in line
                    )
                error(f'FFmpeg process failed: {error_output}')
                raise RuntimeError(f"Failed to dump titles:\n\n{error_output}")

        except Exception as e:
            error(f'Failed to dump titles: {e}\n{format_exc()}')
            raise
        finally:
            if progress:
                progress.close()
