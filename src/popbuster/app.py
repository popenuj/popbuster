from __future__ import annotations

import random
from enum import Enum, auto

from popbuster.catalog import Tape, TapeCatalog
from popbuster.config import AppConfig, ConfigStore
from popbuster.ports import DisplayPort, VideoPort
from popbuster.resume import ResumeStore


class ApplianceState(Enum):
    BOOTING = auto()
    IDLE = auto()
    BUMPER = auto()
    PLAYING = auto()
    PAUSED = auto()
    SETTINGS = auto()
    ERROR = auto()


BOOT_MESSAGES = (
    "POPBUSTER BIOS 0.1",
    "CHECKING TAPE BAY...",
    "SPINNING UP PHV DECK...",
    "RETICULATING SPLINES...",
    "READY.",
)

SETTINGS_COUNT = 2
OPENING_JINGLE_SETTING = 0
COMMERCIALS_SETTING = 1


class PopbusterController:
    def __init__(
        self,
        catalog: TapeCatalog,
        resume_store: ResumeStore,
        config_store: ConfigStore,
        display: DisplayPort,
        video: VideoPort,
    ) -> None:
        self.catalog = catalog
        self.resume_store = resume_store
        self.config_store = config_store
        self.config: AppConfig = config_store.load()
        self.display = display
        self.video = video
        self.state = ApplianceState.BOOTING
        self.current_tape: Tape | None = None
        self.playback_queue: list[Tape] = []
        self.previous_state = ApplianceState.IDLE
        self.selected_setting = 0

    def boot_message(self, index: int) -> bool:
        if index >= len(BOOT_MESSAGES):
            self.state = ApplianceState.IDLE
            self.display.show_idle()
            return False
        self.display.show_boot(BOOT_MESSAGES[index])
        return True

    def insert_default_tape(self) -> None:
        tape = self.catalog.first_available()
        if tape is None:
            self._error("NO TAPES CONFIGURED")
            return
        self.insert_tape(tape.id)

    def insert_tape(self, tape_id: str) -> None:
        if self.state not in {ApplianceState.IDLE, ApplianceState.ERROR}:
            return

        tape = self.catalog.get(tape_id)
        if tape is None:
            self._error(f"UNKNOWN TAPE: {tape_id}")
            return
        if not tape.video_path.exists():
            self._error(f"VIDEO NOT FOUND: {tape.video_path}")
            return

        self.current_tape = tape
        self.playback_queue = []
        self.state = ApplianceState.BUMPER
        self.display.show_bumper()

    def start_shuffle_playback(self) -> None:
        if self.state not in {ApplianceState.IDLE, ApplianceState.ERROR}:
            return

        tapes = self.catalog.available()
        if not tapes:
            self._error("NO LOCAL VIDEOS FOUND")
            return

        random.shuffle(tapes)
        self.current_tape = tapes[0]
        self.playback_queue = tapes[1:]
        self.state = ApplianceState.BUMPER
        self.display.show_bumper()

    def bumper_finished(self) -> None:
        if self.state != ApplianceState.BUMPER or self.current_tape is None:
            return

        tape = self.current_tape
        resume_position = self.resume_store.load_ms(tape.id)
        self.video.load(tape.video_path)
        if resume_position > 0:
            self.video.seek_ms(resume_position)
        self.video.play()
        self.state = ApplianceState.PLAYING
        self.display.show_playing(tape, resumed=resume_position > 0)

    def toggle_play_pause(self) -> None:
        if self.current_tape is None:
            return
        if self.state == ApplianceState.PLAYING:
            self.video.pause()
            self.resume_store.save_ms(self.current_tape.id, self.video.position_ms())
            self.state = ApplianceState.PAUSED
            self.display.show_paused(self.current_tape)
        elif self.state == ApplianceState.PAUSED:
            self.video.play()
            self.state = ApplianceState.PLAYING
            self.display.show_playing(self.current_tape, resumed=True)

    def open_settings(self) -> None:
        if self.state not in {ApplianceState.IDLE, ApplianceState.PAUSED, ApplianceState.ERROR}:
            return
        self.previous_state = self.state
        self.state = ApplianceState.SETTINGS
        self.display.show_settings(self.config, self.selected_setting)

    def close_settings(self) -> None:
        if self.state != ApplianceState.SETTINGS:
            return
        self.state = self.previous_state
        if self.state == ApplianceState.PAUSED and self.current_tape is not None:
            self.display.show_paused(self.current_tape)
        elif self.state == ApplianceState.ERROR:
            self.display.show_idle()
            self.state = ApplianceState.IDLE
        else:
            self.display.show_idle()

    def toggle_commercials(self) -> None:
        if self.state != ApplianceState.SETTINGS:
            return
        self.config.commercials_enabled = not self.config.commercials_enabled
        self.config_store.save(self.config)
        self.display.show_settings(self.config, self.selected_setting)

    def toggle_opening_jingle(self) -> None:
        if self.state != ApplianceState.SETTINGS:
            return
        self.config.opening_jingle_enabled = not self.config.opening_jingle_enabled
        self.config_store.save(self.config)
        self.display.show_settings(self.config, self.selected_setting)

    def move_settings_selection(self, direction: int) -> None:
        if self.state != ApplianceState.SETTINGS:
            return
        self.selected_setting = (self.selected_setting + direction) % SETTINGS_COUNT
        self.display.show_settings(self.config, self.selected_setting)

    def adjust_selected_setting(self, direction: int) -> None:
        if self.state != ApplianceState.SETTINGS:
            return
        if self.selected_setting == OPENING_JINGLE_SETTING:
            self.config.opening_jingle_enabled = not self.config.opening_jingle_enabled
        elif self.selected_setting == COMMERCIALS_SETTING:
            self.config.commercials_enabled = not self.config.commercials_enabled
        self.config_store.save(self.config)
        self.display.show_settings(self.config, self.selected_setting)

    def eject(self) -> None:
        if self.state == ApplianceState.SETTINGS:
            self.close_settings()
            return
        if self.current_tape is not None:
            self.resume_store.save_ms(self.current_tape.id, self.video.position_ms())
        self.video.stop()
        self.current_tape = None
        self.playback_queue = []
        self.state = ApplianceState.IDLE
        self.display.show_idle()

    def playback_finished(self) -> None:
        if self.current_tape is not None:
            self.resume_store.clear(self.current_tape.id)
        if self.playback_queue:
            self.current_tape = self.playback_queue.pop(0)
            self.video.load(self.current_tape.video_path)
            self.video.play()
            self.state = ApplianceState.PLAYING
            self.display.show_playing(self.current_tape, resumed=False)
            return
        self.video.stop()
        self.current_tape = None
        self.playback_queue = []
        self.state = ApplianceState.IDLE
        self.display.show_idle()

    def _error(self, message: str) -> None:
        self.state = ApplianceState.ERROR
        self.display.show_error(message)
