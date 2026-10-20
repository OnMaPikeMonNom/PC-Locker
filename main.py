#!/usr/bin/env python3
"""PC Lock — verrouille clavier et pavé tactile, garde l'écran allumé.

Usage:
    python main.py
    python main.py --setup    # vérifie la caméra / permissions
    python main.py --selftest # teste séquence + urgence sans hooks Windows
    python main.py --no-tray

Raccourcis par défaut (config.json) :
    Verrouiller   : Ctrl+Alt+L
    Déverrouiller : u puis n puis l puis o puis c puis k
    Urgence       : Esc x5 en moins de 3 secondes
    Auto-unlock   : après max_lock_seconds (défaut 120)
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time

from config import load_config, BASE_DIR
from camera import CameraCapture
from locker import InputLocker
from tray import TrayIcon

LOG_FORMAT = "[%(asctime)s] %(levelname)s %(name)s — %(message)s"


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        datefmt="%H:%M:%S",
    )
    # Fichier de log local (jamais envoyé ailleurs).
    log_path = os.path.join(BASE_DIR, "pc-lock.log")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(logging.Formatter(LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
    logging.getLogger().addHandler(fh)


def run_setup(camera: CameraCapture) -> int:
    """Vérifie la caméra et rappelle les permissions Windows."""
    logger = logging.getLogger("pc-lock.setup")
    print("=" * 60)
    print("PC Lock — mode --setup")
    print("=" * 60)
    print()
    print("1) Permissions caméra Windows")
    print("   Paramètres > Confidentialité et sécurité > Caméra")
    print("   - Autoriser l'accès à la caméra : OUI")
    print("   - Autoriser les applications de bureau à accéder à la caméra : OUI")
    print()
    print("2) Test de capture...")
    camera.reset_camera_flag()
    camera.capture_async(reason="setup_test")
    # Laisser le thread de capture terminer.
    time.sleep(3.5)
    captures = []
    if os.path.isdir(camera.capture_dir):
        captures = sorted(
            f for f in os.listdir(camera.capture_dir) if f.startswith("capture_")
        )
    if captures:
        print(f"   OK — dernière photo : {captures[-1]}")
        print(f"   Dossier : {camera.capture_dir}")
        return 0
    print("   ÉCHEC — aucune photo écrite.")
    print("   Causes fréquentes : permission refusée, webcam absente,")
    print("   webcam utilisée par une autre appli, opencv non installé.")
    print("   Le verrouillage/déverrouillage fonctionnera quand même.")
    logger.error("Setup : capture webcam échouée.")
    return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PC Lock — verrou clavier/souris Windows")
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Tester la webcam et afficher les notes de permissions Windows.",
    )
    parser.add_argument(
        "--no-tray",
        action="store_true",
        help="Ne pas afficher l'icône systray (console uniquement).",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="Tester séquence / Esc x5 d'urgence SANS installer de hooks Windows.",
    )
    args = parser.parse_args(argv)

    if args.selftest:
        from selftest import run_selftest
        return run_selftest()

    setup_logging()
    logger = logging.getLogger("pc-lock")

    if sys.platform != "win32":
        logger.warning(
            "Cette application est conçue pour Windows. "
            "Sur %s le comportement (suppress, caméra, éveil) peut être incomplet.",
            sys.platform,
        )

    cfg = load_config()
    cfg.ensure_capture_dir()
    camera = CameraCapture(cfg.capture_dir, cooldown_seconds=cfg.capture_cooldown_seconds)

    if args.setup:
        return run_setup(camera)

    print("=" * 60)
    print("  PC Lock")
    print("=" * 60)
    print(f"  Verrouiller   : {'+'.join(cfg.lock_combo).upper()}")
    print(f"  Déverrouiller : {' → '.join(cfg.unlock_sequence)}")
    print(f"  Urgence       : Esc x5 en moins de 3 s")
    auto = cfg.max_lock_seconds
    print(f"  Auto-unlock   : {auto}s" if auto else "  Auto-unlock   : désactivé")
    print(f"  Photos        : {cfg.capture_dir}")
    print("  Esc seul ne déverrouille PAS (il faut Esc x5).")
    print("  Quitter       : menu systray ou Ctrl+C dans cette fenêtre")
    print("=" * 60)
    print()
    logger.info("Configuration chargée depuis config.json")

    stop_event = {"flag": False}
    tray_holder = {"tray": None}

    def request_stop():
        stop_event["flag"] = True

    locker = InputLocker(
        lock_combo=cfg.lock_combo,
        unlock_sequence=cfg.unlock_sequence,
        camera=camera,
        fail_threshold=cfg.fail_threshold,
        overlay_flash=cfg.overlay_flash,
        max_lock_seconds=cfg.max_lock_seconds,
    )

    def on_lock():
        t = tray_holder["tray"]
        if t:
            t.update(True)
        logger.info("État : VERROUILLÉ")

    def on_unlock():
        t = tray_holder["tray"]
        if t:
            t.update(False)
        logger.info("État : prêt (ré-armé)")

    locker.on_lock = on_lock
    locker.on_unlock = on_unlock

    if not args.no_tray:
        tray = TrayIcon(
            on_lock=locker.lock,
            on_quit=request_stop,
            get_locked=lambda: locker.is_locked,
        )
        if tray.start():
            tray_holder["tray"] = tray
            logger.info("Icône systray active.")
        else:
            logger.info("Systray indisponible — mode console.")

    locker.start()

    def _sigint(signum, frame):
        logger.info("Signal %s reçu, arrêt...", signum)
        request_stop()

    try:
        signal.signal(signal.SIGINT, _sigint)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _sigint)
    except Exception:
        pass

    if sys.platform == "win32" and getattr(locker, "hooks_failed", False):
        logger.error(
            "Les hooks bas niveau n'ont pas pu être installés. "
            "Relancez via run-admin.bat (administrateur) pour un blocage effectif."
        )

    try:
        while not stop_event["flag"]:
            time.sleep(0.25)
            # Relance le backend s'il est mort de façon inattendue.
            locker.ensure_alive()
    except KeyboardInterrupt:
        pass
    finally:
        locker.stop()
        t = tray_holder["tray"]
        if t:
            t.stop()
        logger.info("PC Lock terminé.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
