from __future__ import annotations

import argparse
import sys
import os
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import QCursor, QFont, QFontDatabase, QKeyEvent, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoFrame, QVideoSink
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from popbuster.app import PopbusterController
from popbuster.catalog import Tape, TapeCatalog
from popbuster.config import AppConfig, ConfigStore
from popbuster.resume import ResumeStore


PROJECT_ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = PROJECT_ROOT / "assets" / "tapes.json"
FONT_PATH = PROJECT_ROOT / "assets" / "fonts" / "Modeseven-L3n5.ttf"
APP_START_VIDEO_PATH = PROJECT_ROOT / "assets" / "videos" / "app_start.mp4"
STATE_DIR = Path(os.environ.get("POPBUSTER_STATE_DIR", Path.home() / ".popbuster"))
RESUME_PATH = STATE_DIR / "resume_positions.json"
CONFIG_PATH = STATE_DIR / "config.json"
APP_FONT_FAMILY = "Menlo"
DSI_SIZE = (800, 480)


def register_application_fonts() -> None:
    global APP_FONT_FAMILY

    if not FONT_PATH.exists():
        return

    font_id = QFontDatabase.addApplicationFont(str(FONT_PATH))
    if font_id < 0:
        return

    families = QFontDatabase.applicationFontFamilies(font_id)
    if families:
        APP_FONT_FAMILY = families[0]


def appliance_font(size: int, bold: bool = False) -> QFont:
    font = QFont(APP_FONT_FAMILY)
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSize(size)
    font.setBold(bold)
    return font


class KeyWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.key_handler = None

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self.key_handler is not None:
            self.key_handler(event)
            return
        super().keyPressEvent(event)


class OutputWindow(KeyWindow):
    def __init__(self, *, appliance_layout: bool = False) -> None:
        super().__init__()
        self.setWindowTitle("Popbuster Output / TV")
        self.appliance_layout = appliance_layout
        self.resize(*DSI_SIZE if self.appliance_layout else (960, 540))
        self.message_padding = 18 if self.appliance_layout else 28

        self.stack = QStackedWidget()
        self.message = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.message.setWordWrap(True)
        self.message.setFont(appliance_font(24 if self.appliance_layout else 28))
        self.message.setStyleSheet(
            f"background: #000; color: #f7f7f7; padding: {self.message_padding}px;"
        )

        self.current_image: QPixmap | None = None
        self.image = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.image.setStyleSheet("background: #000;")

        self.stack.addWidget(self.message)
        self.stack.addWidget(self.image)
        self.setCentralWidget(self.stack)

    def show_message(self, text: str, blue: bool = False) -> None:
        color = "#8eb6ff" if blue else "#f7f7f7"
        self.message.setStyleSheet(
            f"background: #000; color: {color}; padding: {self.message_padding}px;"
        )
        self.message.setText(text)
        self.stack.setCurrentWidget(self.message)

    def show_video(self) -> None:
        self.stack.setCurrentWidget(self.image)

    def show_image(self, pixmap: QPixmap) -> None:
        self.current_image = pixmap
        self._refresh_image()
        self.stack.setCurrentWidget(self.image)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_image()

    def _refresh_image(self) -> None:
        if self.current_image is None:
            return
        self.image.setPixmap(
            self.current_image.scaled(
                self.image.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class InternalWindow(KeyWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Popbuster Internal Display")
        self.resize(480, 288)

        self.stack = QStackedWidget()
        self.logo = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.logo.setWordWrap(True)
        self.logo.setFont(appliance_font(22))
        self.logo.setStyleSheet("background: #000; color: #f7f7f7; padding: 20px;")

        self.current_image: QPixmap | None = None
        self.image = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.image.setStyleSheet("background: #000;")

        self.stack.addWidget(self.logo)
        self.stack.addWidget(self.image)

        root = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stack)
        root.setLayout(layout)
        self.setCentralWidget(root)

    def show_status(self, text: str, blue: bool = False) -> None:
        color = "#8eb6ff" if blue else "#f7f7f7"
        self.logo.setStyleSheet(f"background: #000; color: {color}; padding: 20px;")
        self.logo.setText(text)
        self.stack.setCurrentWidget(self.logo)

    def show_video(self) -> None:
        self.stack.setCurrentWidget(self.image)

    def show_image(self, pixmap: QPixmap) -> None:
        self.current_image = pixmap
        self._refresh_image()
        self.stack.setCurrentWidget(self.image)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_image()

    def _refresh_image(self) -> None:
        if self.current_image is None:
            return
        self.image.setPixmap(
            self.current_image.scaled(
                self.image.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class QtDisplayVideoAdapter:
    def __init__(
        self,
        output: OutputWindow,
        internal: InternalWindow,
        mirror_enabled: bool,
    ) -> None:
        self.output = output
        self.internal = internal
        self.mirror_enabled = mirror_enabled
        self.player = QMediaPlayer()
        self.audio = QAudioOutput()
        self.video_sink = QVideoSink()
        self.audio.setVolume(0.7)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoSink(self.video_sink)
        self.video_sink.videoFrameChanged.connect(self._video_frame_changed)

    def show_boot(self, message: str) -> None:
        self.output.show_message(message)
        self.internal.show_status(message)

    def show_idle(self) -> None:
        self.output.show_message("INSERT TAPE", blue=True)
        self.internal.show_status("INSERT TAPE", blue=True)

    def show_bumper(self) -> None:
        self.output.show_message("PHV\nPOPBUSTER HOME VIDEO", blue=True)
        self.internal.show_status("PHV\nPOPBUSTER HOME VIDEO", blue=True)

    def show_playing(self, tape: Tape, resumed: bool) -> None:
        self.output.show_video()
        self.internal.show_video()

    def show_paused(self, tape: Tape) -> None:
        self.output.show_video()
        self.internal.show_video()

    def show_status(self, message: str) -> None:
        self.output.show_message(message)
        self.internal.show_status(message)

    def show_error(self, message: str) -> None:
        self.output.show_message(message)
        self.internal.show_status(message)

    def show_settings(self, config: AppConfig, selected_index: int) -> None:
        commercials = "On" if config.commercials_enabled else "Off"
        opening_jingle = "On" if config.opening_jingle_enabled else "Off"
        rows = (
            f"{'>' if selected_index == 0 else ' '} Opening jingle   {opening_jingle}",
            f"{'>' if selected_index == 1 else ' '} Commercials      {commercials}",
        )
        self.show_status(
            "\n".join(
                (
                    "Settings",
                    *rows,
                )
            )
        )

    def load(self, path: Path) -> None:
        source = QUrl.fromLocalFile(str(path))
        self.player.setSource(source)

    def play(self) -> None:
        self.player.play()

    def pause(self) -> None:
        self.player.pause()

    def stop(self) -> None:
        self.player.stop()

    def seek_ms(self, position_ms: int) -> None:
        self.player.setPosition(position_ms)

    def position_ms(self) -> int:
        return self.player.position()

    def _video_frame_changed(self, frame: QVideoFrame) -> None:
        image = frame.toImage()
        if image.isNull():
            return

        pixmap = QPixmap.fromImage(image)
        self.output.show_image(pixmap)
        if self.mirror_enabled:
            self.internal.show_image(pixmap)


class DesktopApp:
    def __init__(self, *, fullscreen: bool = False, single_display: bool = False) -> None:
        self.qt = QApplication(sys.argv)
        register_application_fonts()
        self.fullscreen = fullscreen
        self.single_display = single_display
        self.output = OutputWindow(appliance_layout=self.single_display)
        self.internal = InternalWindow()
        self.adapter = QtDisplayVideoAdapter(
            self.output,
            self.internal,
            mirror_enabled=not self.single_display,
        )
        self.playing_app_start_video = False
        self.controller = PopbusterController(
            catalog=TapeCatalog.from_json(CATALOG_PATH),
            resume_store=ResumeStore(RESUME_PATH),
            config_store=ConfigStore(CONFIG_PATH),
            display=self.adapter,
            video=self.adapter,
        )

        self.boot_index = 0
        self.boot_timer = QTimer()
        self.boot_timer.setInterval(850)
        self.boot_timer.timeout.connect(self._boot_tick)

        self.bumper_timer = QTimer()
        self.bumper_timer.setSingleShot(True)
        self.bumper_timer.setInterval(1800)
        self.bumper_timer.timeout.connect(self.controller.bumper_finished)

        self.adapter.player.mediaStatusChanged.connect(self._media_status_changed)
        self.adapter.player.errorOccurred.connect(self._media_error)
        self.output.key_handler = self._handle_key
        self.internal.key_handler = self._handle_key

    def run(self) -> int:
        if self.fullscreen:
            self.output.setCursor(QCursor(Qt.CursorShape.BlankCursor))
            self.output.showFullScreen()
        else:
            self.output.show()

        if not self.single_display:
            self.internal.show()
        QTimer.singleShot(250, self._start_app_intro)
        return self.qt.exec()

    def _start_app_intro(self) -> None:
        if (
            not self.controller.config.opening_jingle_enabled
            or not APP_START_VIDEO_PATH.exists()
        ):
            self._start_boot_sequence()
            return

        self.playing_app_start_video = True
        self.output.show_video()
        self.internal.show_video()
        self.adapter.load(APP_START_VIDEO_PATH)
        self.adapter.play()

    def _start_boot_sequence(self) -> None:
        self.playing_app_start_video = False
        self.adapter.stop()
        self._boot_tick()
        self.boot_timer.start()

    def _boot_tick(self) -> None:
        if self.controller.boot_message(self.boot_index):
            self.boot_index += 1
        else:
            self.boot_timer.stop()

    def _handle_key(self, event: QKeyEvent) -> None:
        key = event.key()
        if key in (Qt.Key.Key_I, Qt.Key.Key_1):
            self.controller.insert_default_tape()
            if self.controller.current_tape is not None:
                self.bumper_timer.start()
        elif key == Qt.Key.Key_M:
            self.controller.open_settings()
        elif key == Qt.Key.Key_Up:
            self.controller.move_settings_selection(-1)
        elif key == Qt.Key.Key_Down:
            self.controller.move_settings_selection(1)
        elif key == Qt.Key.Key_Left:
            self.controller.adjust_selected_setting(-1)
        elif key == Qt.Key.Key_Right:
            self.controller.adjust_selected_setting(1)
        elif key == Qt.Key.Key_Space:
            self.controller.toggle_play_pause()
        elif key in (Qt.Key.Key_E, Qt.Key.Key_Backspace, Qt.Key.Key_Escape):
            self.bumper_timer.stop()
            self.controller.eject()
        elif key == Qt.Key.Key_Q:
            self.controller.eject()
            self.qt.quit()

    def _media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if self.playing_app_start_video and status in {
            QMediaPlayer.MediaStatus.EndOfMedia,
            QMediaPlayer.MediaStatus.InvalidMedia,
        }:
            print(f"popbuster: app-start media finished ({status.name})")
            self._start_boot_sequence()
            return

        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.controller.playback_finished()

    def _media_error(self, error: QMediaPlayer.Error, message: str) -> None:
        if error != QMediaPlayer.Error.NoError:
            print(f"popbuster: media error ({error.name}): {message}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Popbuster prototype.")
    parser.add_argument(
        "--fullscreen",
        action="store_true",
        help="Open the main output window fullscreen.",
    )
    parser.add_argument(
        "--single-display",
        action="store_true",
        help="Use one display window instead of the mirrored development pair.",
    )
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return DesktopApp(
        fullscreen=args.fullscreen,
        single_display=args.single_display,
    ).run()
