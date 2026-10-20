"""Self-test de la logique séquence / urgence — SANS hooks Windows.

Exercice :
- séquence correcte → unlock
- mauvaises touches → échecs comptés
- Esc x5 dans la fenêtre → unlock d'urgence
- Esc espacés > 3 s → PAS d'unlock d'urgence

Tourne sous Linux (et Windows) : n'installe aucun hook système.
"""

from __future__ import annotations

import logging
import time
from typing import List

from camera import CameraCapture
from locker import (
    InputLocker,
    _EMERGENCY_ESC_COUNT,
    _EMERGENCY_ESC_WINDOW_S,
    _VK_ESC,
)


class _DummyCamera(CameraCapture):
    """Caméra factice : enregistre les appels, n'ouvre rien."""

    def __init__(self):
        # bypass parent init filesystem needs
        self.capture_dir = "/tmp/pc-lock-selftest-captures"
        self.cooldown_seconds = 0
        self.calls: List[str] = []

    def capture_async(self, reason: str = "failed_unlock") -> None:
        self.calls.append(reason)


def _make_locker(**kwargs) -> InputLocker:
    defaults = dict(
        lock_combo=["ctrl", "alt", "l"],
        unlock_sequence=["u", "n", "l", "o", "c", "k"],
        camera=_DummyCamera(),
        fail_threshold=1,
        overlay_flash=False,
        max_lock_seconds=0,  # désactivé pour les tests synchrone
    )
    defaults.update(kwargs)
    locker = InputLocker(**defaults)
    locker._running = True
    locker._locked = True
    locker._unlock_index = 0
    locker._fail_count = 0
    locker._esc_times = []
    return locker


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def test_correct_sequence_unlocks() -> None:
    unlocked = {"ok": False}

    def on_unlock():
        unlocked["ok"] = True

    locker = _make_locker(on_unlock=on_unlock)
    for ch in "unlock":
        locker._process_locked_key(ch)
    # unlock() est démarré dans un thread daemon — attendre un instant
    deadline = time.time() + 1.0
    while time.time() < deadline and locker.is_locked:
        time.sleep(0.01)
    _assert(not locker.is_locked, "séquence 'unlock' doit déverrouiller")
    _assert(unlocked["ok"], "callback on_unlock doit être appelé")
    print("  OK  séquence correcte → unlock")


def test_wrong_keys_count_fails() -> None:
    cam = _DummyCamera()
    locker = _make_locker(camera=cam, fail_threshold=1)
    locker._process_locked_key("x")  # mauvaise touche
    _assert(locker._unlock_index == 0, "index doit rester à 0")
    _assert(len(cam.calls) == 1, "une capture doit être déclenchée")
    _assert(locker.is_locked, "doit rester verrouillé")
    print("  OK  mauvaises touches → fail + capture")


def test_partial_then_wrong_resets() -> None:
    cam = _DummyCamera()
    locker = _make_locker(camera=cam, fail_threshold=1)
    locker._process_locked_key("u")
    locker._process_locked_key("n")
    _assert(locker._unlock_index == 2, "progression u,n")
    locker._process_locked_key("z")  # casse la séquence
    _assert(locker._unlock_index == 0, "reset après mauvaise touche")
    _assert(len(cam.calls) == 1, "fail enregistré")
    _assert(locker.is_locked, "reste verrouillé")
    print("  OK  progression partielle puis mauvaise touche → reset")


def test_emergency_esc_x5_within_window() -> None:
    unlocked = {"ok": False}

    def on_unlock():
        unlocked["ok"] = True

    locker = _make_locker(on_unlock=on_unlock)
    for _ in range(_EMERGENCY_ESC_COUNT):
        fired = locker._note_emergency_esc()
        if fired:
            locker.unlock(reason="emergency")
            break
        time.sleep(0.05)  # largement < 3 s
    _assert(not locker.is_locked, "Esc x5 dans la fenêtre doit unlock")
    _assert(unlocked["ok"], "callback on_unlock (urgence)")
    print("  OK  Esc x5 rapide → déverrouillage d'urgence")


def test_emergency_esc_spaced_out_does_not_unlock() -> None:
    """Simule des Esc trop espacés en manipulant les timestamps."""
    locker = _make_locker()
    # Injecter 4 Esc "anciens" hors fenêtre, puis 1 récent → jamais 5 dans la fenêtre.
    now = time.monotonic()
    locker._esc_times = [
        now - _EMERGENCY_ESC_WINDOW_S - 1.0,
        now - _EMERGENCY_ESC_WINDOW_S - 0.8,
        now - _EMERGENCY_ESC_WINDOW_S - 0.6,
        now - _EMERGENCY_ESC_WINDOW_S - 0.4,
    ]
    fired = locker._note_emergency_esc()
    _assert(not fired, "Esc espacés ne doivent PAS déclencher l'urgence")
    _assert(locker.is_locked, "doit rester verrouillé")
    _assert(len(locker._esc_times) == 1, "seuls les Esc récents restent")
    print("  OK  Esc espacés (>3s) → PAS d'unlock d'urgence")


def test_esc_does_not_count_as_sequence_fail() -> None:
    cam = _DummyCamera()
    locker = _make_locker(camera=cam)
    locker._process_locked_key("esc")
    _assert(len(cam.calls) == 0, "Esc seul ne doit PAS déclencher de capture")
    _assert(locker._unlock_index == 0, "index inchangé")
    _assert(locker.is_locked, "reste verrouillé")
    print("  OK  Esc seul ne compte pas comme fail de séquence")


def test_handle_key_event_emergency_via_vk() -> None:
    """Simule le chemin Windows via vkCode Esc (0x1B) sans hooks."""
    unlocked = {"ok": False}

    def on_unlock():
        unlocked["ok"] = True

    locker = _make_locker(on_unlock=on_unlock)
    for _ in range(_EMERGENCY_ESC_COUNT):
        # is_down=True, is_up=False — comme un WM_KEYDOWN
        eaten = locker._handle_key_event(_VK_ESC, True, False)
        _assert(eaten is True, "verrouillé → touche avalée")
        if not locker.is_locked:
            break
        time.sleep(0.02)
    deadline = time.time() + 1.0
    while time.time() < deadline and locker.is_locked:
        time.sleep(0.01)
    _assert(not locker.is_locked, "vk Esc x5 doit unlock via _handle_key_event")
    print("  OK  chemin vkCode Esc (0x1B) x5 → unlock")


def test_unlocked_passes_all() -> None:
    locker = _make_locker()
    locker._locked = False
    eaten = locker._handle_key_event(0x55, True, False)  # 'U'
    _assert(eaten is False, "déverrouillé → ne doit PAS avaler")
    print("  OK  déverrouillé → CallNextHookEx (ne bloque rien)")


def run_selftest() -> int:
    logging.basicConfig(level=logging.CRITICAL)
    logging.getLogger("pc-lock.locker").setLevel(logging.CRITICAL)
    print("=" * 60)
    print("  PC Lock — selftest (sans hooks Windows)")
    print("=" * 60)
    tests = [
        test_correct_sequence_unlocks,
        test_wrong_keys_count_fails,
        test_partial_then_wrong_resets,
        test_emergency_esc_x5_within_window,
        test_emergency_esc_spaced_out_does_not_unlock,
        test_esc_does_not_count_as_sequence_fail,
        test_handle_key_event_emergency_via_vk,
        test_unlocked_passes_all,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as exc:
            failed += 1
            print(f"  FAIL {t.__name__}: {exc}")
    print("=" * 60)
    if failed:
        print(f"  RÉSULTAT : {failed}/{len(tests)} échec(s)")
        return 1
    print(f"  RÉSULTAT : {len(tests)}/{len(tests)} OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_selftest())
