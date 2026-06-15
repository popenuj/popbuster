# Popbuster

Popbuster is a custom Barbie-scale CRT-style home-video appliance prototype. This repository starts with a desktop vertical slice that can run on macOS and later move toward Raspberry Pi OS.

The current slice is intentionally small:

- Python application with native windows
- mocked hardware through keyboard controls
- boot/loading sequence
- app-start intro video
- idle `INSERT TAPE` screen
- PHV / Popbuster Home Video bumper
- local video playback
- play/pause, eject/back, and resume position
- persisted config with opening-jingle and commercial-breaks toggles
- two-window DSI/HDMI simulation with mirrored output for development
- application logic separated from future RFID, IR, GPIO, LED, microswitch, audio, and display integrations

## Architecture

The smallest sensible shape is:

- `popbuster.app`: appliance state machine and user actions
- `popbuster.catalog`: loads tape definitions from local JSON
- `popbuster.config`: loads and saves appliance settings
- `popbuster.resume`: stores playback positions
- `popbuster.ports`: protocols for display/video/hardware-facing adapters
- `popbuster.ui.qt_app`: desktop adapter using Qt windows, keyboard input, and QtMultimedia playback

This keeps the first prototype concrete while leaving a clean replacement point for Raspberry Pi hardware adapters later.

## UI and Playback Stack

Recommended stack: **PySide6 / Qt for Python** with **QtMultimedia**.

Why:

- runs as a local appliance-style app, not a browser app
- supports multiple native windows for HDMI/internal display simulation
- handles keyboard input and media playback in one toolkit
- works on macOS for development and has a realistic Raspberry Pi OS path

Tradeoffs:

- QtMultimedia depends on platform media backends. MP4/H.264 generally works on macOS, but Raspberry Pi OS may require installing the right GStreamer packages.
- PySide6 wheels are not available for every bleeding-edge Python release. Use Python 3.11, 3.12, or 3.13.
- The current adapter is desktop-first. Later Pi display/audio routing may need a dedicated adapter or launch configuration.

Alternatives considered:

- `pygame`: simple input and drawing, but video playback is not a good fit.
- `tkinter`: built in, but no strong native video story.
- VLC bindings: capable playback, but adds a heavier external runtime dependency.
- Browser UI: flexible, but the project goal is a local appliance rather than a web app.

## Setup

From this directory:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m popbuster
```

If `python3.13` is not available, use Python 3.11 or 3.12. Avoid Python 3.14 for now because PySide6 support may lag behind it.

Resume positions are saved in `~/.popbuster/resume_positions.json`. For sandboxed development or tests, override that location:

```bash
POPBUSTER_STATE_DIR=/tmp/popbuster-state python -m popbuster
```

Appliance settings are saved next to the resume file in `config.json`.

## Raspberry Pi Development

On the Raspberry Pi 5 desktop session, activate the virtual environment and run Popbuster against the active Wayland display:

```bash
cd /home/johnp/popbuster
source .venv/bin/activate
XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-0 python -m popbuster
```

The current app still opens normal desktop windows. A later Pi/appliance mode should switch this to fullscreen and eventually systemd autostart.

## Video

The default tape catalog points at `../Content/Movies/ML_tut_area2.mp4` when running inside the current workspace, so this prototype has a local video to play immediately.

For current development, the simulated DSI and HDMI windows mirror the same feed. At application startup, Popbuster plays `assets/videos/app_start.mp4` on both simulated displays before the text boot/loading sequence when the opening jingle setting is on. If that file is missing or the setting is off, the app skips directly to the text boot sequence.

For a real Popbuster test clip, place a video at:

```text
assets/videos/test_video.mp4
```

Then update `assets/tapes.json`.

## Commercials

Future AI-generated Barbie-style commercials should be treated as local video assets, separate from tapes and bumpers. This slice reserves `assets/commercials/` for that content and persists a config flag:

```json
{
  "commercials_enabled": true,
  "opening_jingle_enabled": true
}
```

The current prototype does not insert commercials into playback yet. The setting is exposed now so the later playback planner can skip commercial reels when the flag is off.

## Font

The prototype registers `assets/fonts/Modeseven-L3n5.ttf` at startup and uses it at regular weight for the appliance UI. If the font file is missing or cannot be loaded, Qt falls back to the platform monospace font.

## Controls

Focus either Popbuster window and use:

| Key | Action |
| --- | --- |
| `I` or `1` | Insert the demo tape |
| `M` | Open settings |
| `Up` / `Down` | Move settings selection |
| `Left` / `Right` | Change selected setting immediately |
| `Space` | Play/pause |
| `E`, `Backspace`, or `Escape` | Eject/back |
| `Q` | Quit |

## Implementation Plan

1. Create a plain Python package with minimal dependencies.
2. Define hardware-facing protocols before writing adapters.
3. Implement a small appliance controller with states: boot, idle, bumper, playing, paused.
4. Implement a Qt desktop adapter with two windows.
5. Load a JSON tape catalog and resolve local video paths.
6. Save resume positions in `~/.popbuster/resume_positions.json`.
7. Document setup, controls, and future hardware replacement points.

Future milestones can add RFID readers, IR remote mapping, GPIO status LED/microswitch adapters, systemd unit files, Pi display routing, Setup Tape provisioning, and package download/cache logic.
