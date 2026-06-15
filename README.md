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

Deploy the current project from macOS to the Pi:

```bash
scripts/deploy-pi
```

Defaults:

```text
PI_HOST=popbuster.local
PI_USER=johnp
PI_PATH=/home/johnp/popbuster
```

Override any of those environment variables if needed.

On the Raspberry Pi 5 desktop session, run Popbuster against the active Wayland display:

```bash
cd /home/johnp/popbuster
source .venv/bin/activate
XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-0 python -m popbuster
```

For the current DSI appliance-style test mode, use:

```bash
scripts/run-pi
```

That wraps:

```bash
XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-0 python -m popbuster --single-display --fullscreen
```

To compare against the windowed desktop path while debugging Pi video rendering:

```bash
POPBUSTER_FULLSCREEN=0 scripts/run-pi
POPBUSTER_FULLSCREEN=0 POPBUSTER_SINGLE_DISPLAY=0 scripts/run-pi
```

The default macOS/development mode still opens two mirrored windows. Pi mode uses one fullscreen window on the active 800x480 DSI display, hides the cursor, and uses tighter text padding for the smaller screen.

### Pi DSI Display

The Waveshare 4.3-inch 800x480 non-touch DSI display should be configured explicitly instead of relying on Raspberry Pi OS display auto-detection. Auto-detect worked intermittently after kernel/initramfs updates, and warm reboots could come back headless.

Edit `/boot/firmware/config.txt` on the Pi:

```bash
sudo nano /boot/firmware/config.txt
```

Use this display section:

```text
# Automatically load overlays for detected DSI displays
display_auto_detect=0

# Automatically load initramfs files, if found
auto_initramfs=1

# Enable Waveshare 4.3" 800x480 non-touch DSI display on Pi DSI0
dtoverlay=vc4-kms-dsi-waveshare-800x480,dsi0,disable_touch

# Enable DRM VC4 V3D driver
dtoverlay=vc4-kms-v3d
max_framebuffers=2
```

After saving, reboot and verify that the desktop sees the real panel:

```bash
wlr-randr
ls -la /sys/class/drm
```

Expected output includes an enabled `DSI` connector at `800x480`. If `wlr-randr` shows `NOOP-1 "Headless output"`, the OS is running but did not detect the display.

### Pi Autostart

The current autostart path is a user-level systemd service that runs after the Pi desktop session starts. This assumes the Pi is configured to log into the desktop automatically, because Popbuster currently renders into that Wayland session.

After deploying to the Pi, install the service on the Pi:

```bash
cd /home/johnp/popbuster
scripts/install-pi-autostart
```

Start it immediately without rebooting:

```bash
systemctl --user start popbuster.service
```

Useful service commands:

```bash
systemctl --user status popbuster.service
journalctl --user -u popbuster.service -f
systemctl --user restart popbuster.service
systemctl --user stop popbuster.service
systemctl --user disable popbuster.service
```

The installed unit lives at `~/.config/systemd/user/popbuster.service`. It runs `scripts/run-pi`, so the same `POPBUSTER_FULLSCREEN`, `POPBUSTER_SINGLE_DISPLAY`, and `WAYLAND_DISPLAY` overrides still apply through the service file.

### Pi Kiosk Session

Kiosk mode is an experiment to remove the brief desktop flash before Popbuster launches. It uses a minimal `labwc` Wayland session and configures LightDM autologin to start `popbuster-kiosk` instead of the normal desktop. The regular desktop is not deleted.

Install the compositor dependency on the Pi:

```bash
sudo apt install labwc x11-apps
```

After deploying Popbuster, install kiosk mode:

```bash
cd /home/johnp/popbuster
scripts/install-pi-kiosk
sudo reboot
```

Expected boot path:

```text
Plymouth spinner
Popbuster fullscreen
```

A brief black screen with a blinking text cursor between Plymouth and Popbuster is the Linux virtual terminal showing during session handoff. It is separate from the mouse pointer inside Popbuster. If it becomes distracting, try hiding the kernel console cursor later with `vt.global_cursor_default=0` in `/boot/firmware/cmdline.txt`; keep that as a separate boot-polish experiment.

The kiosk installer creates a transparent cursor theme at `~/.icons/popbuster-blank` and starts the kiosk compositor with that cursor theme. This hides the compositor-level mouse pointer before Qt has a chance to draw Popbuster.

If kiosk mode fails, recover over SSH:

```bash
ssh johnp@192.168.0.18
cd ~/popbuster
scripts/restore-pi-desktop
sudo reboot
```

If the normal desktop still appears instead of Popbuster, verify that LightDM can read the kiosk session file:

```bash
ls -la /usr/share/wayland-sessions/popbuster-kiosk.desktop
cat /etc/lightdm/lightdm.conf.d/90-popbuster-kiosk.conf
lightdm --show-config
```

The session file should be readable by everyone, for example `-rw-r--r--`. Raspberry Pi OS may load `/etc/lightdm/lightdm.conf` after the `conf.d` file, so `scripts/install-pi-kiosk` also backs up and patches the main config at `/etc/lightdm/lightdm.conf.before-popbuster-kiosk`. The kiosk session should live in `/usr/share/wayland-sessions`, not `/usr/share/xsessions`; an X session launches Cage nested under Xorg and can produce a black screen.

After returning to the normal desktop, reinstall desktop-session autostart if desired:

```bash
cd ~/popbuster
scripts/install-pi-autostart
```

### Plymouth Boot Splash

The current stable boot splash uses Plymouth's stock `spinner` theme:

```bash
sudo plymouth-set-default-theme -R spinner
sudo reboot
```

The Pi 5 boots quickly enough that this is a reasonable prototype baseline, and it avoids Plymouth/display handoff flicker while Popbuster is still running inside the desktop session.

Popbuster also includes an experimental custom Plymouth theme. It currently holds a single frame until the OS hands off to the desktop session and Popbuster autostarts. In testing, Plymouth could briefly show the frame, go black during display handoff, show it again, then hand off to the desktop. Keep it as an experiment until kiosk-session work is stable.

Bundled splash sequences:

- `ken_tv_unboxing`
- `antenna_fixing`

The default install uses `ken_tv_unboxing`:

```bash
cd /home/johnp/popbuster
scripts/install-pi-plymouth
sudo reboot
```

To install the antenna sequence instead:

```bash
POPBUSTER_SPLASH_SEQUENCE=antenna_fixing scripts/install-pi-plymouth
sudo reboot
```

The installer copies the selected sequence into `/usr/share/plymouth/themes/popbuster`, sets it as the default Plymouth theme, and rebuilds the boot image with `plymouth-set-default-theme -R popbuster`. The static theme displays the selected sequence's first frame. Plymouth starts after the earliest firmware/kernel phase, so a tiny amount of Raspberry Pi boot output may still appear before the custom splash. The brief desktop flash is handled separately by the future kiosk-session work.

## Video

The default tape catalog points at `../Content/Movies/ML_tut_area2.mp4` when running inside the current workspace, so this prototype has a local video to play immediately.

For current development, the simulated DSI and HDMI windows mirror the same feed. At application startup, Popbuster plays `assets/videos/app_start.mp4` before the text boot/loading sequence when the opening jingle setting is on. If that file is missing or the setting is off, the app skips directly to the text boot sequence.

For a real Popbuster test clip, place a video at:

```text
assets/videos/test_video.mp4
```

Then update `assets/tapes.json`.

Pi playback is most reliable with 800x480 H.264 MP4 files. The app decodes videos with QtMultimedia, then renders decoded frames into normal Qt image widgets instead of using `QVideoWidget`; this has been more reliable on the Pi DSI/Wayland path. Normalize generated or captured clips before adding them:

```bash
scripts/transcode-video input.mov assets/videos/test_video.mp4
```

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
