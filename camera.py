"""Capture photo depuis la webcam par défaut (OpenCV).

Important : la capture tourne dans un thread séparé. Les hooks clavier/souris
de Windows doivent répondre très vite ; si on bloquait le callback pendant
l'ouverture de la caméra (souvent 1-2 s), Windows pourrait retirer le hook
silencieusement et le verrou cesserait de fonctionner.

Aucune donnée n'est envoyée sur le réseau : les photos restent locales.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime

logger = logging.getLogger("pc-lock.camera")

# Import optionnel : l'app doit pouvoir verrouiller/déverrouiller même sans caméra.
try:
    import cv2  # type: ignore
except ImportError:  # pragma: no cover
    cv2 = None


class CameraCapture:
    """Capture asynchrone d'une photo webcam, avec cooldown anti-rafale."""

    def __init__(self, capture_dir: str, cooldown_seconds: float = 3.0):
        self.capture_dir = capture_dir
        self.cooldown_seconds = float(cooldown_seconds)
        self._lock = threading.Lock()
        self._last_capture = 0.0
        self._camera_ok = True  # bascule à False après un échec répété
        os.makedirs(self.capture_dir, exist_ok=True)

    def capture_async(self, reason: str = "failed_unlock") -> None:
        """Lance une capture dans un thread daemon. Ne bloque jamais l'appelant."""
        t = threading.Thread(
            target=self._capture_safe,
            args=(reason,),
            name="webcam-capture",
            daemon=True,
        )
        t.start()

    def _capture_safe(self, reason: str) -> None:
        try:
            self._capture(reason)
        except Exception as exc:  # pragma: no cover
            logger.exception("Erreur inattendue pendant la capture: %s", exc)

    def _capture(self, reason: str) -> None:
        if cv2 is None:
            logger.error(
                "opencv-python n'est pas installé. Impossible de prendre une photo. "
                "Installez avec: pip install opencv-python"
            )
            return

        now = time.monotonic()
        with self._lock:
            if now - self._last_capture < self.cooldown_seconds:
                logger.info("Capture ignorée (cooldown %ss).", self.cooldown_seconds)
                return
            self._last_capture = now

        if not self._camera_ok:
            logger.warning(
                "Caméra précédemment inaccessible. Capture ignorée. "
                "Vérifiez les permissions Windows (Paramètres > Confidentialité > Caméra)."
            )
            return

        logger.info("Capture webcam demandée (raison=%s).", reason)
        cap = None
        try:
            # 0 = webcam par défaut. CAP_DSHOW accélère l'ouverture sous Windows.
            try:
                cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            except Exception:
                cap = cv2.VideoCapture(0)

            if not cap or not cap.isOpened():
                self._camera_ok = False
                logger.error(
                    "Impossible d'ouvrir la webcam. "
                    "Sous Windows : Paramètres > Confidentialité et sécurité > Caméra "
                    "— autorisez l'accès pour les applications de bureau. "
                    "Le verrouillage/déverrouillage continue de fonctionner."
                )
                return

            # Quelques frames pour laisser l'exposition se stabiliser.
            frame = None
            for _ in range(8):
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.05)
            if frame is None:
                logger.error("La webcam n'a renvoyé aucune image.")
                return

            stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            safe_reason = "".join(c if c.isalnum() or c in "-_" else "_" for c in reason)[:40]
            filename = f"capture_{stamp}_{safe_reason}.jpg"
            path = os.path.join(self.capture_dir, filename)
            if not cv2.imwrite(path, frame):
                logger.error("Échec d'écriture de la photo: %s", path)
                return
            logger.info("Photo enregistrée: %s", path)
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass

    def reset_camera_flag(self) -> None:
        """Réessaie la caméra après un échec (ex. permission accordée entre-temps)."""
        self._camera_ok = True
