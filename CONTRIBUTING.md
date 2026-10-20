# Contributing

Thanks for your interest in PC Lock! This is a small, focused Windows utility.

## Ground rules

- **Keep the safety nets.** Never remove or weaken the emergency exits
  (Esc ×5, auto-unlock, fail-open on hook errors). The user must never be
  able to get permanently locked out.
- **Don't break AZERTY/French support.** Keys are matched by virtual-key
  code, and the UI/logs are in French. Keep it that way.
- **No network calls.** The app is 100% offline. Photos stay local.

## Workflow

1. Fork and create a branch.
2. Make your change.
3. Run the checks locally (these also run in CI on Linux):
   ```bash
   python -m py_compile *.py
   python main.py --selftest
   ```
   `selftest.py` runs without Windows hooks, so it works on any OS.
4. Open a pull request describing the change and how you tested it
   (especially on real Windows, since hooks can't be tested in CI).

## Reporting bugs

Open an issue with your OS version, Python version, and the relevant lines
from `pc-lock.log`.
