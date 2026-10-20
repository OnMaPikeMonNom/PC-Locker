# Changelog

All notable changes to PC Lock are documented here.
This project loosely follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- **Background mode (no console):** `run-hidden.vbs` launches the app with
  `pythonw.exe` so there is no console window (systray only).
- **Auto-start at login:** `install-autostart.ps1` registers a Scheduled Task
  that runs at user logon, hidden, elevated (`RunLevel Highest`) so low-level
  hooks install; `uninstall-autostart.ps1` removes it and stops running
  instances.
- **Simple fallback auto-start:** `install-autostart-startup-folder.bat` drops
  a shortcut to `run-hidden.vbs` into the Startup folder (non-elevated).
- **GitHub packaging:** `LICENSE` (MIT), `.gitignore`, `CONTRIBUTING.md`,
  `CHANGELOG.md`, and a minimal GitHub Actions workflow (`.github/workflows/ci.yml`)
  that compiles all `.py` and runs the self-test on Linux.
- Bilingual (English + French) README with a table of contents.

## Earlier iterations

### Desktop captures + sticky-modifier fix
- Webcam photos now save to `Desktop\PC-Lock-Captures` (created automatically).
- Fixed the keyboard staying "stuck" after unlock: modifier KEYUP events
  (Ctrl/Alt) are now let through, and modifiers are force-released on every
  lock/unlock. Fixed a missing `_cleanup_modifiers_after_lock` method.

### Anti-lockout failsafes
- Three guaranteed ways out of the lock: secret sequence, **Esc ×5** within
  3 seconds, and **auto-unlock** after `max_lock_seconds` (default 120s).
- Hook callback fails **open** (releases input) on unexpected errors.
- Replaced the full-screen flash with a short beep (the overlay was suspected
  of interfering with the lock).

### Low-level hooks fix
- Fixed hook installation failing on 64-bit Python (a pointer/handle was being
  truncated), which previously prevented keyboard/mouse blocking.
- Switched from `pynput suppress=True` to Windows `WH_KEYBOARD_LL` /
  `WH_MOUSE_LL` hooks via `ctypes`, with a dedicated message-loop thread.
  Keys are matched by virtual-key code, so unlocking works on AZERTY.

### Initial build
- Lock keyboard + touchpad on `Ctrl+Alt+L`, screen stays on.
- Unlock by typing the secret sequence `u-n-l-o-c-k`.
- Webcam photo captured on wrong keys.
- Optional systray icon, configurable via `config.json`, French README,
  `--setup`, `--selftest`, and `--no-tray` options.
