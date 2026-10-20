"""Verrouillage clavier / souris (pavé tactile) sans mise en veille.

Principe (Windows) :
- On installe des hooks bas niveau (Low-Level) via l'API Win32 :
  WH_KEYBOARD_LL (13) et WH_MOUSE_LL (14) avec SetWindowsHookExW, dans un
  thread dédié qui fait tourner une boucle de messages (GetMessageW /
  TranslateMessage / DispatchMessageW) — indispensable pour que ces hooks
  se déclenchent.
- Déverrouillé : les hooks laissent TOUT passer (CallNextHookEx) ; ils se
  contentent de détecter la combinaison de verrouillage.
- Verrouillé : chaque touche / évènement souris est **toujours avalé**
  (return 1) donc rien n'atteint les autres applications. Seule la séquence
  de déverrouillage (reconnue par code de touche virtuelle « vk », compatible
  AZERTY) est traitée à l'intérieur du hook.
- L'écran reste allumé (SetThreadExecutionState).

SORTIES DE SECOURS (priorité anti-blocage) :
1. Séquence configurée (défaut : u n l o c k)
2. Esc x5 en moins de 3 secondes → déverrouillage d'urgence IMMÉDIAT
3. Timer max_lock_seconds (défaut 120 s) → déverrouillage automatique
4. Toute exception inattendue dans le hook verrouillé → fail-OPEN (unlock)

Limitation Windows connue : Ctrl+Alt+Del (Secure Attention Sequence) contourne
TOUJOURS les hooks utilisateur. Documentée dans le README. Si l'installation
des hooks échoue, relancez en administrateur (run-admin.bat).
"""

from __future__ import annotations

import logging
import platform
import threading
import time
from typing import Callable, List, Optional, Set

from camera import CameraCapture
from overlay import flash_async

logger = logging.getLogger("pc-lock.locker")

_IS_WINDOWS = platform.system() == "Windows"

# Esc (vk 0x1B) x5 dans cette fenêtre → déverrouillage d'urgence.
_EMERGENCY_ESC_COUNT = 5
_EMERGENCY_ESC_WINDOW_S = 3.0
_VK_ESC = 0x1B

# ---------------------------------------------------------------------------
# Maintien écran / système éveillé (Windows uniquement)
# ---------------------------------------------------------------------------

if _IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    ES_DISPLAY_REQUIRED = 0x00000002


def _keep_awake(enable: bool) -> None:
    """Empêche la mise en veille et l'extinction de l'écran pendant le verrou."""
    if not _IS_WINDOWS:
        return
    try:
        if enable:
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
            )
        else:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
    except Exception as exc:  # pragma: no cover
        logger.warning("SetThreadExecutionState a échoué: %s", exc)



# Modifiers dont le KEYUP doit passer même verrouillé, sinon Windows croit
# qu'ils restent enfoncés (Ctrl/Alt "collés" après Ctrl+Alt+L → clavier mort).
_MODIFIER_VKS = {
    0x10, 0xA0, 0xA1,  # shift
    0x11, 0xA2, 0xA3,  # ctrl
    0x12, 0xA4, 0xA5,  # alt / altgr
    0x5B, 0x5C,        # win
}


def _release_stuck_modifiers() -> None:
    """Envoie un KEYUP synthétique pour tous les modifiers (nettoie l'état OS)."""
    if not _IS_WINDOWS:
        return
    try:
        INPUT_KEYBOARD = 1
        KEYEVENTF_KEYUP = 0x0002

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t),
            ]

        class INPUT(ctypes.Structure):
            class _U(ctypes.Union):
                _fields_ = [("ki", KEYBDINPUT)]
            _anonymous_ = ("u",)
            _fields_ = [("type", wintypes.DWORD), ("u", _U)]

        # Ordre : gauche/droite pour chaque modifier.
        vks = (0xA2, 0xA3, 0xA4, 0xA5, 0xA0, 0xA1, 0x5B, 0x5C, 0x11, 0x12, 0x10)
        arr = (INPUT * len(vks))()
        for i, vk in enumerate(vks):
            arr[i].type = INPUT_KEYBOARD
            arr[i].ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP, 0, 0)
        ctypes.windll.user32.SendInput(len(vks), ctypes.byref(arr), ctypes.sizeof(INPUT))
        logger.info("Modifiers OS relâchés (anti-collage Ctrl/Alt).")
    except Exception as exc:
        logger.warning("Impossible de relâcher les modifiers: %s", exc)


# ---------------------------------------------------------------------------
# Mapping des codes de touches virtuelles (vk) -> nom canonique config
# (compatible AZERTY : le vk reflète la lettre LOGIQUE, pas la position
#  physique ; la touche qui tape 'u' renvoie vk 0x55 quel que soit le clavier)
# ---------------------------------------------------------------------------

_VK_SPECIAL = {
    0x10: "shift", 0xA0: "shift", 0xA1: "shift",
    0x11: "ctrl", 0xA2: "ctrl", 0xA3: "ctrl",
    0x12: "alt", 0xA4: "alt", 0xA5: "alt",
    0x5B: "cmd", 0x5C: "cmd",
    0x1B: "esc",
    0x0D: "enter",
    0x20: "space",
    0x09: "tab",
    0x08: "backspace",
    0x2E: "delete",
    0x2D: "insert",
    0x25: "left", 0x26: "up", 0x27: "right", 0x28: "down",
    0x24: "home", 0x23: "end",
    0x21: "page_up", 0x22: "page_down",
    0x14: "caps_lock",
}
# F1..F12 = 0x70..0x7B
for _i in range(12):
    _VK_SPECIAL[0x70 + _i] = "f%d" % (_i + 1)


def _vk_to_name(vk: int) -> Optional[str]:
    """Convertit un code de touche virtuelle Windows en nom de config."""
    if vk is None:
        return None
    if 0x41 <= vk <= 0x5A:            # A-Z
        return chr(vk).lower()
    if 0x30 <= vk <= 0x39:            # 0-9 (rangée du haut)
        return chr(vk)
    if 0x60 <= vk <= 0x69:            # pavé numérique 0-9
        return chr(ord("0") + (vk - 0x60))
    return _VK_SPECIAL.get(vk)


# ---------------------------------------------------------------------------
# Structures ctypes pour les hooks bas niveau
# ---------------------------------------------------------------------------

if _IS_WINDOWS:
    ULONG_PTR = ctypes.c_size_t
    LRESULT = ctypes.c_ssize_t

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("vkCode", wintypes.DWORD),
            ("scanCode", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class POINTSTRUCT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

    class MSLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("pt", POINTSTRUCT),
            ("mouseData", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    # Les callbacks Windows sont en convention stdcall -> WINFUNCTYPE (pas CFUNCTYPE).
    HOOKPROC = ctypes.WINFUNCTYPE(
        LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
    )

    WH_KEYBOARD_LL = 13
    WH_MOUSE_LL = 14
    HC_ACTION = 0
    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    WM_SYSKEYDOWN = 0x0104
    WM_SYSKEYUP = 0x0105
    WM_QUIT = 0x0012


# ---------------------------------------------------------------------------
# Locker
# ---------------------------------------------------------------------------


class InputLocker:
    """Gère l'état verrouillé / déverrouillé.

    Sur Windows : hooks bas niveau ctypes (toujours installés tant que l'app
    tourne ; ils n'avalent les évènements que lorsque c'est verrouillé).
    Sur les autres OS : repli pynput (suppress) — surtout pour dev/tests.
    """

    def __init__(
        self,
        lock_combo: list,
        unlock_sequence: list,
        camera: CameraCapture,
        fail_threshold: int = 1,
        overlay_flash: bool = True,
        max_lock_seconds: int = 120,
        on_lock: Optional[Callable[[], None]] = None,
        on_unlock: Optional[Callable[[], None]] = None,
    ):
        self.lock_combo = [k.lower() for k in lock_combo]
        self.unlock_sequence = [k.lower() for k in unlock_sequence]
        self.camera = camera
        self.fail_threshold = max(1, int(fail_threshold))
        self.overlay_flash = bool(overlay_flash)
        self.max_lock_seconds = max(0, int(max_lock_seconds))
        self.on_lock = on_lock
        self.on_unlock = on_unlock

        self._locked = False
        self._running = False
        self._state_lock = threading.RLock()

        self._pressed: Set[str] = set()
        self._unlock_index = 0
        self._fail_count = 0

        # Esc x5 d'urgence : liste glissante de timestamps (monotonic).
        self._esc_times: List[float] = []

        # Watchdog anti-blocage.
        self._auto_unlock_timer: Optional[threading.Timer] = None

        # Windows : état des hooks
        self._hook_thread: Optional[threading.Thread] = None
        self._hook_thread_id = 0
        self._kb_hook = None
        self._mouse_hook = None
        self._kb_proc_ref = None     # garder une référence (anti-GC)
        self._mouse_proc_ref = None
        self._hooks_installed = threading.Event()
        self._hooks_failed = False

        # Non-Windows : listeners pynput
        self._kb_listener = None
        self._mouse_listener = None
        # "hooks" | "pynput" | None — None = mode test (pas de backend actif)
        self._backend = None

    # -- état public --------------------------------------------------------

    @property
    def is_locked(self) -> bool:
        return self._locked

    @property
    def hooks_failed(self) -> bool:
        return self._hooks_failed

    # -- cycle de vie -------------------------------------------------------

    def start(self) -> None:
        with self._state_lock:
            if self._running:
                return
            self._running = True
        if _IS_WINDOWS:
            self._backend = "hooks"
            self._start_hook_thread()
        else:
            self._backend = "pynput"
            self._start_pynput_unlocked()
        logger.info(
            "Locker démarré. Verrouiller: %s | Déverrouiller: %s | "
            "Urgence: Esc x%d / %.0fs | Auto: %ss",
            "+".join(self.lock_combo).upper(),
            " puis ".join(self.unlock_sequence),
            _EMERGENCY_ESC_COUNT,
            _EMERGENCY_ESC_WINDOW_S,
            self.max_lock_seconds if self.max_lock_seconds else "off",
        )

    def stop(self) -> None:
        with self._state_lock:
            self._running = False
            was_locked = self._locked
            self._locked = False
        self._cancel_auto_unlock()
        if self._backend == "hooks":
            self._stop_hook_thread()
        elif self._backend == "pynput":
            self._stop_pynput()
        self._backend = None
        if was_locked:
            _keep_awake(False)
        _keep_awake(False)
        logger.info("Locker arrêté.")

    def ensure_alive(self) -> None:
        """Relance le thread de hooks s'il est mort de façon inattendue."""
        if not self._running:
            return
        if self._backend == "hooks":
            t = self._hook_thread
            if t is not None and not t.is_alive() and not self._hooks_failed:
                logger.warning("Thread de hooks arrêté — redémarrage.")
                self._start_hook_thread()
        elif self._backend == "pynput":
            lst = self._kb_listener
            if lst is not None and not getattr(lst, "running", False):
                logger.warning("Listener clavier arrêté — redémarrage.")
                if self._locked:
                    self._start_pynput_locked()
                else:
                    self._start_pynput_unlocked()

    # -- verrouillage / déverrouillage --------------------------------------

    def lock(self) -> None:
        with self._state_lock:
            if not self._running or self._locked:
                return
            logger.info("VERROUILLAGE — clavier et souris bloqués, écran reste allumé.")
            self._locked = True
            self._unlock_index = 0
            self._fail_count = 0
            self._pressed.clear()
            self._esc_times.clear()
            if self._backend == "pynput":
                self._stop_pynput()
                self._start_pynput_locked()
            _keep_awake(True)
        # Laisse remonter les KEYUP physiques, puis force un nettoyage OS.
        threading.Thread(target=self._cleanup_modifiers_after_lock, daemon=True).start()
        self._arm_auto_unlock()
        if self._hooks_failed:
            logger.error(
                "ATTENTION : les hooks Windows ne sont PAS installés — le blocage "
                "ne sera PAS effectif. Relancez via run-admin.bat (administrateur)."
            )
        if self.on_lock:
            try:
                self.on_lock()
            except Exception:
                logger.exception("on_lock a échoué")

    def _cleanup_modifiers_after_lock(self) -> None:
        """Après verrouillage : attendre le relâchement physique puis forcer KEYUP."""
        time.sleep(0.25)
        _release_stuck_modifiers()

    def unlock(self, reason: str = "sequence") -> None:

        with self._state_lock:
            if not self._running or not self._locked:
                return
            if reason == "emergency":
                logger.info("Déverrouillage d'urgence (Esc x%d).", _EMERGENCY_ESC_COUNT)
            elif reason == "auto":
                logger.info("Déverrouillage automatique (sécurité anti-blocage).")
            elif reason == "fail_open":
                logger.error(
                    "DÉVERROUILLAGE FAIL-OPEN — exception dans le hook ; "
                    "entrées restaurées pour éviter un blocage permanent."
                )
            else:
                logger.info("DÉVERROUILLAGE — entrées restaurées.")
            self._locked = False
            self._unlock_index = 0
            self._fail_count = 0
            self._pressed.clear()
            self._esc_times.clear()
            if self._backend == "pynput":
                self._stop_pynput()
                self._start_pynput_unlocked()
            _keep_awake(False)
        self._cancel_auto_unlock()
        # Nettoie d'éventuels modifiers collés avant de rendre le clavier.
        try:
            _release_stuck_modifiers()
        except Exception:
            pass
        if self.on_unlock:
            try:
                self.on_unlock()
            except Exception:
                logger.exception("on_unlock a échoué")

    # -- watchdog anti-blocage ----------------------------------------------

    def _arm_auto_unlock(self) -> None:
        self._cancel_auto_unlock()
        if self.max_lock_seconds <= 0:
            return
        t = threading.Timer(self.max_lock_seconds, self._auto_unlock_fire)
        t.daemon = True
        t.name = "pc-lock-auto-unlock"
        self._auto_unlock_timer = t
        t.start()
        logger.info(
            "Watchdog anti-blocage armé : déverrouillage auto dans %ss.",
            self.max_lock_seconds,
        )

    def _cancel_auto_unlock(self) -> None:
        t = self._auto_unlock_timer
        self._auto_unlock_timer = None
        if t is not None:
            try:
                t.cancel()
            except Exception:
                pass

    def _auto_unlock_fire(self) -> None:
        if self._locked:
            self.unlock(reason="auto")

    # ======================================================================
    # Backend Windows : hooks bas niveau
    # ======================================================================

    def _start_hook_thread(self) -> None:
        self._hooks_installed.clear()
        self._hook_thread = threading.Thread(
            target=self._hook_thread_main, name="pc-lock-hooks", daemon=True
        )
        self._hook_thread.start()
        # Attendre l'installation (ou l'échec) pour pouvoir prévenir l'utilisateur.
        if not self._hooks_installed.wait(timeout=5.0) and not self._hooks_failed:
            logger.warning("Installation des hooks : délai dépassé.")

    def _hook_thread_main(self) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        user32.SetWindowsHookExW.restype = wintypes.HHOOK
        user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD
        ]
        user32.CallNextHookEx.restype = LRESULT
        user32.CallNextHookEx.argtypes = [
            wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
        ]
        user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
        user32.GetMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT
        ]

        # IMPORTANT (64 bits) : sans restype explicite, le HANDLE est tronque
        # a 32 bits -> hmod invalide -> SetWindowsHookExW echoue (code 0).
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]

        self._hook_thread_id = kernel32.GetCurrentThreadId()
        hmod = kernel32.GetModuleHandleW(None)

        # Garder les références aux callbacks (sinon GC -> crash).
        self._kb_proc_ref = HOOKPROC(self._ll_keyboard_proc)
        self._mouse_proc_ref = HOOKPROC(self._ll_mouse_proc)

        def _install(hook_id, proc):
            # Essai avec le module courant, puis repli sur NULL (autorise
            # pour les hooks bas niveau WH_*_LL).
            h = user32.SetWindowsHookExW(hook_id, proc, hmod, 0)
            if not h:
                h = user32.SetWindowsHookExW(hook_id, proc, None, 0)
            return h

        self._kb_hook = _install(WH_KEYBOARD_LL, self._kb_proc_ref)
        self._mouse_hook = _install(WH_MOUSE_LL, self._mouse_proc_ref)

        if not self._kb_hook or not self._mouse_hook:
            err = ctypes.get_last_error()
            self._hooks_failed = True
            logger.error(
                "ÉCHEC installation des hooks bas niveau (code=%s). "
                "Le blocage clavier/souris ne fonctionnera PAS.", err,
            )
            print("")
            print("=" * 64)
            print("  ERREUR : impossible d'installer le verrou clavier/souris.")
            print("  Veuillez RELANCER l'application EN ADMINISTRATEUR :")
            print("     -> double-cliquez sur  run-admin.bat")
            print("  (clic droit > Exécuter en tant qu'administrateur si besoin)")
            print("=" * 64)
            print("")
            # Nettoyer le hook éventuellement installé.
            if self._kb_hook:
                user32.UnhookWindowsHookEx(self._kb_hook)
            if self._mouse_hook:
                user32.UnhookWindowsHookEx(self._mouse_hook)
            self._kb_hook = None
            self._mouse_hook = None
            self._hooks_installed.set()
            return

        logger.info("Hooks bas niveau installés (clavier + souris).")
        self._hooks_failed = False
        self._hooks_installed.set()

        # Boucle de messages : OBLIGATOIRE pour que les hooks LL se déclenchent.
        msg = wintypes.MSG()
        while self._running:
            ret = user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
            if ret == 0 or ret == -1:  # WM_QUIT ou erreur
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        # Désinstallation propre.
        if self._kb_hook:
            user32.UnhookWindowsHookEx(self._kb_hook)
        if self._mouse_hook:
            user32.UnhookWindowsHookEx(self._mouse_hook)
        self._kb_hook = None
        self._mouse_hook = None
        logger.info("Hooks bas niveau désinstallés.")

    def _stop_hook_thread(self) -> None:
        tid = self._hook_thread_id
        if tid:
            try:
                ctypes.windll.user32.PostThreadMessageW(tid, WM_QUIT, 0, 0)
            except Exception:
                pass
        t = self._hook_thread
        if t is not None:
            t.join(timeout=3.0)
        self._hook_thread = None
        self._hook_thread_id = 0

    def _ll_keyboard_proc(self, nCode, wParam, lParam):
        """Callback hook clavier — DOIT rester ultra-rapide et jamais planter.

        Sur exception inattendue alors que verrouillé : fail-OPEN (unlock)
        pour ne jamais laisser l'utilisateur sans entrée.
        """
        try:
            if nCode == HC_ACTION:
                kb = ctypes.cast(
                    lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)
                ).contents
                vk = kb.vkCode
                is_down = wParam in (WM_KEYDOWN, WM_SYSKEYDOWN)
                is_up = wParam in (WM_KEYUP, WM_SYSKEYUP)
                if self._handle_key_event(vk, is_down, is_up):
                    return 1  # avalé : n'atteint aucune autre app
        except Exception:
            logger.exception("Erreur dans le hook clavier")
            # Fail-OPEN : si on était verrouillé, on libère IMMÉDIATEMENT.
            if self._locked:
                try:
                    threading.Thread(
                        target=self.unlock, kwargs={"reason": "fail_open"}, daemon=True
                    ).start()
                except Exception:
                    self._locked = False
        return ctypes.windll.user32.CallNextHookEx(None, nCode, wParam, lParam)

    def _ll_mouse_proc(self, nCode, wParam, lParam):
        """Avalé UNIQUEMENT si verrouillé ; sinon tout passe (CallNextHookEx)."""
        try:
            if nCode == HC_ACTION and self._locked:
                return 1  # verrouillé : toute la souris/pad est avalée
        except Exception:
            logger.exception("Erreur dans le hook souris")
            if self._locked:
                try:
                    threading.Thread(
                        target=self.unlock, kwargs={"reason": "fail_open"}, daemon=True
                    ).start()
                except Exception:
                    self._locked = False
        return ctypes.windll.user32.CallNextHookEx(None, nCode, wParam, lParam)

    def _handle_key_event(self, vk: int, is_down: bool, is_up: bool) -> bool:
        """Retourne True si l'évènement doit être avalé (verrouillé)."""
        name = _vk_to_name(vk)

        if not self._locked:
            # Déverrouillé : on NE bloque rien, on détecte juste la combo de lock.
            if name is not None:
                if is_down:
                    self._pressed.add(name)
                    if self._combo_matches(self.lock_combo, self._pressed):
                        threading.Thread(target=self.lock, daemon=True).start()
                elif is_up:
                    self._pressed.discard(name)
            return False

        # Verrouillé.
        # IMPORTANT : laisser passer les KEYUP des modifiers, sinon après
        # Ctrl+Alt+L Windows croit que Ctrl/Alt restent enfoncés et le
        # clavier paraît "encore bloqué" même après déverrouillage.
        if is_up and vk in _MODIFIER_VKS:
            return False

        if is_down:
            # Urgence Esc : basée sur vkCode (indépendante du layout).
            if vk == _VK_ESC:
                if self._note_emergency_esc():
                    threading.Thread(
                        target=self.unlock, kwargs={"reason": "emergency"}, daemon=True
                    ).start()
                    return True
            self._process_locked_key(name)
        return True

    # ======================================================================
    # Urgence Esc x5 + logique de séquence
    # ======================================================================

    def _note_emergency_esc(self) -> bool:
        """Enregistre un Esc ; True si 5 presses dans la fenêtre de 3 s."""
        now = time.monotonic()
        cutoff = now - _EMERGENCY_ESC_WINDOW_S
        self._esc_times = [t for t in self._esc_times if t >= cutoff]
        self._esc_times.append(now)
        return len(self._esc_times) >= _EMERGENCY_ESC_COUNT

    def _process_locked_key(self, name: Optional[str]) -> None:
        """Traitement pur de la séquence (testable sans hooks Windows).

        Esc seul ne déverrouille JAMAIS via la séquence (l'urgence Esc x5
        est gérée à part dans _handle_key_event / selftest).
        """
        if name is None:
            return
        # Esc : ne compte PAS comme mauvaise touche de séquence (géré à part).
        if name == "esc":
            return
        # Modifiers seuls : neutres.
        if name in ("ctrl", "alt", "shift", "cmd", "caps_lock"):
            return

        expected = self.unlock_sequence[self._unlock_index]

        if name == expected:
            self._unlock_index += 1
            logger.debug(
                "Séquence OK (%s/%s): %s",
                self._unlock_index, len(self.unlock_sequence), name,
            )
            if self._unlock_index >= len(self.unlock_sequence):
                threading.Thread(target=self.unlock, daemon=True).start()
            return

        # Mauvaise touche : si c'est la 1re touche de la séquence, on redémarre.
        if name == self.unlock_sequence[0]:
            had_progress = self._unlock_index > 0
            self._unlock_index = 1
            if had_progress:
                self._register_fail(f"broke_then_restart:{name}")
            return

        had_progress = self._unlock_index > 0
        self._unlock_index = 0
        reason = f"wrong_key:{name}" if had_progress else f"wrong_attempt:{name}"
        self._register_fail(reason)

    def _register_fail(self, reason: str) -> None:
        self._fail_count += 1
        logger.warning(
            "Tentative échouée (%s/%s) — %s",
            self._fail_count, self.fail_threshold, reason,
        )
        if self._fail_count >= self.fail_threshold:
            self._fail_count = 0
            # Caméra + bip en arrière-plan — JAMAIS dans le chemin du hook.
            self.camera.capture_async(reason=reason)
            if self.overlay_flash:
                flash_async()

    @staticmethod
    def _combo_matches(combo: list, pressed: Set[str]) -> bool:
        return all(k in pressed for k in combo)

    # ======================================================================
    # Backend pynput (non-Windows : dev / tests)
    # ======================================================================

    def _start_pynput_unlocked(self) -> None:
        from pynput import keyboard
        self._kb_listener = keyboard.Listener(
            on_press=self._pynput_press_unlocked,
            on_release=self._pynput_release_unlocked,
            suppress=False,
        )
        self._kb_listener.start()

    def _start_pynput_locked(self) -> None:
        from pynput import keyboard, mouse
        self._kb_listener = keyboard.Listener(
            on_press=self._pynput_press_locked, suppress=True,
        )
        self._mouse_listener = mouse.Listener(
            on_move=lambda *a, **k: None,
            on_click=lambda *a, **k: None,
            on_scroll=lambda *a, **k: None,
            suppress=True,
        )
        self._kb_listener.start()
        self._mouse_listener.start()

    def _stop_pynput(self) -> None:
        for lst in (self._kb_listener, self._mouse_listener):
            if lst is not None:
                try:
                    lst.stop()
                except Exception:
                    pass
        self._kb_listener = None
        self._mouse_listener = None

    @staticmethod
    def _pynput_name(key) -> Optional[str]:
        from pynput.keyboard import Key, KeyCode
        _mods = {
            Key.ctrl: "ctrl", Key.ctrl_l: "ctrl", Key.ctrl_r: "ctrl",
            Key.alt: "alt", Key.alt_l: "alt", Key.alt_r: "alt", Key.alt_gr: "alt",
            Key.shift: "shift", Key.shift_l: "shift", Key.shift_r: "shift",
            Key.cmd: "cmd", Key.cmd_l: "cmd", Key.cmd_r: "cmd",
            Key.esc: "esc", Key.enter: "enter", Key.space: "space", Key.tab: "tab",
        }
        if key in _mods:
            return _mods[key]
        if isinstance(key, KeyCode):
            if key.vk is not None:
                n = _vk_to_name(key.vk)
                if n:
                    return n
            if key.char:
                return key.char.lower()
        try:
            s = str(key)
            if s.startswith("Key."):
                return s[4:].lower()
        except Exception:
            pass
        return None

    def _pynput_press_unlocked(self, key) -> None:
        name = self._pynput_name(key)
        if name is None:
            return
        self._pressed.add(name)
        if self._combo_matches(self.lock_combo, self._pressed):
            threading.Thread(target=self._delayed_lock, daemon=True).start()

    def _delayed_lock(self) -> None:
        time.sleep(0.15)
        self.lock()

    def _pynput_release_unlocked(self, key) -> None:
        name = self._pynput_name(key)
        if name is not None:
            self._pressed.discard(name)

    def _pynput_press_locked(self, key) -> None:
        name = self._pynput_name(key)
        if name == "esc":
            if self._note_emergency_esc():
                threading.Thread(
                    target=self.unlock, kwargs={"reason": "emergency"}, daemon=True
                ).start()
                return
            return
        self._process_locked_key(name)
