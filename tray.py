"""Icône système (systray) optionnelle via pystray + Pillow.

Si pystray ou Pillow manquent, l'app tourne quand même en console.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger("pc-lock.tray")

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover
    pystray = None
    Image = None
    ImageDraw = None


def _make_icon_image(locked: bool):
    """Petite icône 64x64 : vert = prêt, rouge = verrouillé."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = (200, 40, 40, 255) if locked else (40, 160, 70, 255)
    draw.ellipse((8, 8, 56, 56), fill=color)
    # Cadenas stylisé
    draw.rectangle((22, 30, 42, 50), fill=(255, 255, 255, 230))
    draw.arc((24, 16, 40, 36), start=0, end=180, fill=(255, 255, 255, 230), width=3)
    return img


class TrayIcon:
    """Gestionnaire d'icône de barre système."""

    def __init__(
        self,
        on_lock: Callable[[], None],
        on_quit: Callable[[], None],
        get_locked: Callable[[], bool],
    ):
        self.on_lock = on_lock
        self.on_quit = on_quit
        self.get_locked = get_locked
        self._icon = None
        self._thread: Optional[threading.Thread] = None

    @property
    def available(self) -> bool:
        return pystray is not None and Image is not None

    def start(self) -> bool:
        if not self.available:
            logger.warning(
                "pystray/Pillow absents : pas d'icône systray. "
                "L'app continue en console. pip install pystray Pillow"
            )
            return False

        menu = pystray.Menu(
            pystray.MenuItem(
                lambda item: "État : VERROUILLÉ" if self.get_locked() else "État : prêt",
                None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Verrouiller maintenant", self._action_lock),
            pystray.MenuItem("Quitter", self._action_quit),
        )
        self._icon = pystray.Icon(
            "pc-lock",
            _make_icon_image(False),
            "PC Lock — prêt (Ctrl+Alt+L)",
            menu,
        )
        self._thread = threading.Thread(target=self._icon.run, name="tray", daemon=True)
        self._thread.start()
        return True

    def update(self, locked: bool) -> None:
        if self._icon is None:
            return
        try:
            self._icon.icon = _make_icon_image(locked)
            self._icon.title = (
                "PC Lock — VERROUILLÉ (tapez u-n-l-o-c-k)"
                if locked
                else "PC Lock — prêt (Ctrl+Alt+L)"
            )
        except Exception as exc:
            logger.debug("Mise à jour tray: %s", exc)

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None

    def _action_lock(self, icon, item) -> None:
        if not self.get_locked():
            self.on_lock()

    def _action_quit(self, icon, item) -> None:
        self.on_quit()
