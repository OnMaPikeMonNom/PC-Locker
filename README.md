# PC Lock 🔒

> A tiny Windows utility that **locks your keyboard and touchpad while keeping the screen on**. Unlock with a secret key sequence. If someone presses the wrong keys, it quietly snaps a **webcam photo**. 100% offline — nothing ever leaves your machine.

*(Version française plus bas — [Section française](#version-française))*

---

## Table of Contents

- [Features](#features)
- [Screenshots](#screenshots)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Default shortcuts](#default-shortcuts)
- [Emergency exits & auto-unlock](#emergency-exits--auto-unlock)
- [Where photos go](#where-photos-go)
- [Run in background / auto-start at login](#run-in-background--auto-start-at-login)
- [Configuration](#configuration)
- [How the lock works](#how-the-lock-works)
- [Windows limitations (honest)](#windows-limitations-honest)
- [Security & privacy](#security--privacy)
- [Project structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Responsible use & consent](#responsible-use--consent)
- [License](#license)
- [Version française](#version-française)

---

## Features

- 🔐 **Blocks keyboard + touchpad/mouse** for all other apps via low-level Windows hooks.
- 🖥️ **Screen stays on** — no sleep, no blanking. Great for leaving a video playing.
- 🔡 **Secret unlock sequence** (default `u-n-l-o-c-k`), matched by virtual-key code so it works on **AZERTY** and other layouts.
- 📸 **Webcam photo on wrong keys**, saved locally to your Desktop.
- 🚪 **Three guaranteed ways out** so you can never get permanently locked out.
- 🛎️ Optional **system-tray icon** (lock now / quit).
- 🚀 **Background mode** (no console) and **auto-start at login** (hidden, elevated).
- 🌐 **No network. No telemetry. No uploads.**

## Screenshots

> _Placeholder — add your own images here._
>
> | Tray icon (ready / locked) | Capture folder |
> |----------------------------|----------------|
> | `docs/tray.png` | `docs/captures.png` |

---

## Requirements

- **Windows 10/11**
- **Python 3.10+** (tick *“Add python.exe to PATH”* during install) — https://www.python.org/downloads/
- A webcam (optional, only for the photo feature)

Python packages (installed automatically by `run.bat`, or `pip install -r requirements.txt`):

```
pynput>=1.7.6
opencv-python>=4.8.0
pystray>=0.19.5
Pillow>=10.0.0
```

---

## Installation

```bat
cd path\to\pc-lock
python -m pip install -r requirements.txt
python main.py
```

Or double-click **`run-admin.bat`** (recommended — it relaunches elevated, so the low-level hooks install reliably).

**Allow camera access** (Windows often blocks desktop apps):
Settings → Privacy & security → Camera → enable *Camera access* **and** *Let desktop apps access your camera*. Test it: `python main.py --setup`.

---

## Usage

```bat
python main.py            :: start (console + tray)
python main.py --setup    :: test the webcam + permission reminders
python main.py --selftest :: test sequence/emergency logic WITHOUT system hooks
python main.py --no-tray  :: no tray icon (console only)
```

Once running:

- **Ctrl+Alt+L** → lock
- type **u n l o c k** → unlock
- **Esc ×5** quickly → emergency unlock
- after ~120 s → automatic unlock
- Tray menu → *Lock now* / *Quit*
- **Ctrl+C** in the console → also quits

After a successful unlock the app stays active (re-armed).

## Default shortcuts

| Action | Keys |
|--------|------|
| **Lock** | `Ctrl` + `Alt` + `L` |
| **Unlock** | type in order: `u` `n` `l` `o` `c` `k` |
| **Emergency** | `Esc` ×5 within 3 seconds |
| **Auto-unlock** | after 120 s (configurable) |

## Emergency exits & auto-unlock

You can **never** get permanently stuck. Three independent escapes:

1. **Secret sequence** — the normal way (`u-n-l-o-c-k`).
2. **Esc ×5 within 3 s** — always unlocks, regardless of sequence or layout. A single Esc never does.
3. **Auto-unlock** — forced release after `max_lock_seconds` (default 120).

On top of that, if an unexpected error happens inside the hook while locked, the app **fails open** (releases input) rather than trapping you.

## Where photos go

Default: **`Desktop\PC-Lock-Captures`** (created automatically).
Filename example: `capture_2026-10-20_22-03-26_wrong_attempt_space.jpg`.
Change the location with `capture_folder` in `config.json`.

---

## Run in background / auto-start at login

### Background now (no console window)

Double-click **`run-hidden.vbs`**. It launches the app with `pythonw.exe`, so there is **no console window** — only the tray icon.
⚠️ Low-level hooks often need **admin rights**. If blocking doesn't take effect, use the Scheduled Task method below (which runs elevated).

### Recommended: auto-start at login, hidden + elevated (Scheduled Task)

This is the reliable option: it starts at logon, runs hidden with `pythonw.exe`, and runs **elevated** so the hooks install.

**Install** — right-click `install-autostart.ps1` → **Run with PowerShell** (accept the UAC prompt), or in an admin PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\install-autostart.ps1
```

It registers a Scheduled Task named **“PC Lock”** (trigger: *At log on*, `-RunLevel Highest`, hidden, working dir = the app folder). To start it immediately without logging out:

```powershell
Start-ScheduledTask -TaskName "PC Lock"
```

**Check it's running:** Task Scheduler → *PC Lock*, or look for `pythonw.exe` in Task Manager → Details, or read `pc-lock.log` in the app folder.

**Stop / uninstall** — right-click `uninstall-autostart.ps1` → **Run with PowerShell**, or:

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall-autostart.ps1
```

It removes the task **and** kills any running `pythonw.exe main.py`. You can also delete the task by hand in Task Scheduler.

### Simple fallback (Startup folder, non-elevated)

Double-click **`install-autostart-startup-folder.bat`**. It drops a shortcut to `run-hidden.vbs` into `shell:startup`, so PC Lock starts at each login **without a console**. It is **not elevated**, so hooks may need admin — prefer the Scheduled Task method for reliable blocking. To remove it, delete the *PC Lock* shortcut from the Startup folder (`shell:startup`).

### Stopping when there's no console

With no console, `Ctrl+C` isn't available — use any of:

- **Tray icon → Quit** (clean shutdown),
- **Esc ×5** or wait for **auto-unlock** to leave the locked state,
- **Task Manager → `pythonw.exe` → End task** (last resort),
- or the uninstall script, which also kills running instances.

The app runs headless: it needs no keyboard input in the console and logs everything to `pc-lock.log`.

---

## Configuration

Edit `config.json` (Notepad), then restart the app.

```json
{
  "lock_combo": ["ctrl", "alt", "l"],
  "unlock_sequence": ["u", "n", "l", "o", "c", "k"],
  "capture_folder": "%USERPROFILE%\\Desktop\\PC-Lock-Captures",
  "fail_threshold": 1,
  "overlay_flash": true,
  "capture_cooldown_seconds": 3,
  "max_lock_seconds": 120
}
```

| Key | Meaning |
|-----|---------|
| `lock_combo` | Keys held together to lock |
| `unlock_sequence` | Keys typed in order to unlock |
| `capture_folder` | Photo folder (absolute, relative, or with `%USERPROFILE%`) |
| `fail_threshold` | Wrong attempts before a photo is taken (1 = immediate) |
| `overlay_flash` | Short beep on each capture (no full-screen window) |
| `capture_cooldown_seconds` | Minimum delay between two photos |
| `max_lock_seconds` | Auto-unlock after N seconds (0 = disabled) |

**Security tip:** change `unlock_sequence` to something personal (and different from `lock_combo`), but keep Esc ×5 and/or `max_lock_seconds` > 0 so you never get stuck.
Recognized key names: `a`–`z`, `0`–`9`, `ctrl`, `alt`, `shift`, `esc`, `enter`, `space`, `tab`, `f1`–`f12`, arrows, etc.

## How the lock works

The lock installs Windows **low-level hooks** `WH_KEYBOARD_LL` and `WH_MOUSE_LL` via `ctypes`/`SetWindowsHookExW`, running in a dedicated thread with a message loop (`GetMessageW`/`TranslateMessage`/`DispatchMessageW`). When **unlocked**, hooks pass everything through (`CallNextHookEx`) and only watch for the lock combo. When **locked**, each key/mouse event is swallowed before reaching other apps; only your sequence / Esc-emergency is handled inside the hook. Keys are matched by **virtual-key code**, so unlocking works on **AZERTY**. The callback stays minimal (camera and beep run in daemon threads); any exception fails **open**.

## Windows limitations (honest)

1. **Ctrl+Alt+Del** (Secure Attention Sequence) always bypasses user hooks — a deliberate Windows protection. The app cannot and should not block it.
2. **Win+L** can still lock the Windows session (OS-level, not controlled here).
3. If camera permission is denied, the lock still works but **without photos** (clearly logged).
4. This is **not** a replacement for Windows session lock (`Win+L`). It's a local deterrent / witness tool (e.g. keep a movie playing while stopping anyone from touching the keyboard).

## Security & privacy

- **No sleep**, no deliberate screen-off.
- **No network traffic**: no telemetry, no uploads.
- Photos are **local only**, in your capture folder.
- The unlock sequence lives in `config.json` in plain text — protect that file if needed.
- Emergency exits are always active (Esc ×5 + auto-unlock + fail-open).

## Project structure

```
pc-lock/
  main.py                              Entry point (headless-friendly)
  config.py                            Reads config.json
  locker.py                            Keyboard/mouse lock + emergency + watchdog
  camera.py                            Webcam capture (separate thread)
  overlay.py                           Safe beep
  tray.py                              System-tray icon
  selftest.py                          Sequence/emergency tests (no hooks)
  config.json                          Your settings
  requirements.txt
  run.bat                              Install deps + run
  run-admin.bat                        Relaunch elevated
  run-hidden.vbs                       Run with no console (pythonw)
  install-autostart.ps1                Scheduled Task: logon, hidden, elevated
  uninstall-autostart.ps1              Remove the Scheduled Task + stop instances
  install-autostart-startup-folder.bat Simple Startup-folder shortcut (non-elevated)
  LICENSE  CONTRIBUTING.md  CHANGELOG.md
  .github/workflows/ci.yml             py_compile + selftest on Linux
  README.md
```

## Troubleshooting

| Problem | Try |
|---------|-----|
| `pip` not found | Reinstall Python, tick “Add to PATH” |
| No photo | `python main.py --setup` + Camera permissions |
| Keys still get through | Run `run-admin.bat` (admin); close exclusive apps |
| Stuck / keyboard dead | Esc ×5 fast, or wait ~120 s (auto-unlock) |
| No tray icon | `pip install pystray Pillow` or use `--no-tray` |
| App won't start | Read `pc-lock.log` in the app folder |
| Background app won't stop | Tray → Quit, or Task Manager → `pythonw.exe`, or `uninstall-autostart.ps1` |
| Verify the logic | `python main.py --selftest` |

## Responsible use & consent

PC Lock can take a webcam photo of whoever is at the keyboard. **Only use it on devices you own or are authorized to manage, and tell people who share the computer that it may photograph them.** Recording or photographing people without consent may be illegal where you live. You are responsible for using this tool lawfully and ethically. The webcam feature can be disabled by denying camera permission or removing the capture logic.

## License

[MIT](LICENSE) © 2026 The PC Lock contributors. Suggested repository name: **`pc-lock`**.

---

# Version française

Application **Windows** qui **verrouille le clavier et le pavé tactile** tout en **gardant l'écran allumé**. Déverrouillage par séquence secrète (`u-n-l-o-c-k`). Une mauvaise touche déclenche une **photo webcam** enregistrée localement. **Aucune donnée réseau.**

## Sortir du verrou (IMPORTANT)

On ne peut **jamais** rester bloqué. Trois sorties :

1. **Séquence secrète** : `u` `n` `l` `o` `c` `k`.
2. **Urgence** : `Échap` ×5 en moins de 3 s — déverrouille toujours (Esc seul ne fait rien).
3. **Auto-unlock** : après `max_lock_seconds` (défaut **120 s**).

En cas d'erreur inattendue dans le hook, l'app **fail-OPEN** (libère les entrées).

## Installation & lancement

```bat
cd chemin\vers\pc-lock
python -m pip install -r requirements.txt
python main.py
```

Ou double-clic sur **`run-admin.bat`** (relance en administrateur — hooks plus fiables).
Caméra : Paramètres → Confidentialité et sécurité → Caméra → activez l'accès et *Autoriser les applications de bureau*. Test : `python main.py --setup`.

Une fois lancée : **Ctrl+Alt+L** verrouille, **u n l o c k** déverrouille, **Esc ×5** = urgence, ~120 s = auto. Menu systray → *Verrouiller* / *Quitter*. **Ctrl+C** quitte aussi.

## Lancer au démarrage / en arrière-plan

### En arrière-plan tout de suite (sans console)

Double-clic sur **`run-hidden.vbs`** : lance l'app avec `pythonw.exe`, **sans fenêtre console** (icône systray seulement).
⚠️ Les hooks bas niveau demandent souvent l'**admin**. Si le blocage ne prend pas, utilisez la Tâche planifiée ci-dessous (élevée).

### Recommandé : démarrage auto à l'ouverture de session, caché + élevé (Tâche planifiée)

**Installer** — clic droit sur `install-autostart.ps1` → **Exécuter avec PowerShell** (acceptez l'UAC), ou en PowerShell admin :

```powershell
powershell -ExecutionPolicy Bypass -File .\install-autostart.ps1
```

Crée une tâche **« PC Lock »** (déclencheur : *À l'ouverture de session*, `-RunLevel Highest`, cachée, dossier de travail = dossier de l'app). Pour la lancer tout de suite :

```powershell
Start-ScheduledTask -TaskName "PC Lock"
```

**Vérifier qu'elle tourne** : Planificateur de tâches → *PC Lock*, ou `pythonw.exe` dans le Gestionnaire des tâches → Détails, ou lisez `pc-lock.log`.

**Arrêter / désinstaller** — clic droit sur `uninstall-autostart.ps1` → **Exécuter avec PowerShell**, ou :

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall-autostart.ps1
```

Supprime la tâche **et** tue les `pythonw.exe main.py` en cours.

### Solution simple (dossier Démarrage, non élevé)

Double-clic sur **`install-autostart-startup-folder.bat`** : dépose un raccourci vers `run-hidden.vbs` dans `shell:startup`. **Non élevé** → les hooks peuvent exiger l'admin ; préférez la Tâche planifiée. Pour retirer : supprimez le raccourci *PC Lock* du dossier Démarrage.

### Arrêter sans console

Sans console, pas de `Ctrl+C`. Utilisez : **systray → Quitter** (arrêt propre), **Esc ×5** ou l'auto-unlock pour sortir du verrou, ou **Gestionnaire des tâches → `pythonw.exe` → Fin de tâche** (dernier recours). L'app est *headless* (aucune saisie console requise) et journalise tout dans `pc-lock.log`.

## Configuration

Éditez `config.json` puis relancez. Clés : `lock_combo`, `unlock_sequence`, `capture_folder` (défaut `%USERPROFILE%\Desktop\PC-Lock-Captures`), `fail_threshold`, `overlay_flash`, `capture_cooldown_seconds`, `max_lock_seconds`. Gardez Esc ×5 et/ou `max_lock_seconds` > 0 pour ne jamais rester coincé.

## Limitations honnêtes (Windows)

1. **Ctrl+Alt+Del** contourne toujours les hooks utilisateur (protection volontaire de Windows).
2. **Win+L** peut encore verrouiller la session (niveau OS).
3. Sans permission caméra, le verrou marche mais **sans photo**.
4. Ce n'est **pas** un substitut au verrouillage de session : c'est un outil de dissuasion / témoin local.

## Usage responsable

PC Lock peut photographier la personne au clavier. **Ne l'utilisez que sur des appareils que vous possédez ou gérez, et prévenez les personnes qui partagent l'ordinateur.** Photographier quelqu'un sans consentement peut être illégal selon votre pays. Vous êtes responsable d'un usage légal et éthique.
