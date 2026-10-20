"""Signal discret et TOUJOURS sûr quand une mauvaise touche est détectée.

IMPORTANT (sécurité anti-blocage) :
Les versions précédentes ouvraient une fenêtre tkinter plein écran (topmost,
focus_force) dans un thread secondaire. Faire tourner une boucle mainloop Tk
hors du thread principal est instable sous Windows et pouvait figer le
processus — une cause probable du blocage total clavier/souris vécu par
l'utilisateur.

On remplace donc le flash plein écran par un signal minimal et incassable :
un court bip sonore (winsound.Beep sous Windows) émis dans un thread daemon,
plus une ligne de log. AUCUNE fenêtre, aucun focus volé, rien qui puisse
figer le processus ni retenir les entrées.
"""

from __future__ import annotations

import logging
import platform
import threading

logger = logging.getLogger("pc-lock.overlay")

_IS_WINDOWS = platform.system() == "Windows"


def flash_async(duration_ms: int = 180, color: str = "#ff2222") -> None:
    """Signale une mauvaise touche : bip sonore bref (non bloquant) + log.

    Les paramètres duration_ms / color sont conservés pour compatibilité
    d'appel mais ne créent plus aucune fenêtre.
    """
    logger.info("Mauvaise séquence détectée (signal).")
    t = threading.Thread(
        target=_beep_safe,
        args=(duration_ms,),
        name="overlay-beep",
        daemon=True,
    )
    t.start()


def _beep_safe(duration_ms: int) -> None:
    try:
        if _IS_WINDOWS:
            import winsound
            winsound.Beep(880, max(60, min(int(duration_ms), 400)))
        else:
            # Pas de fenêtre, pas de blocage possible hors Windows.
            logger.debug("Bip (non-Windows) ignoré.")
    except Exception as exc:  # pragma: no cover
        logger.debug("Bip indisponible: %s", exc)
