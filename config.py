"""Chargement et validation de la configuration (config.json).

Toute la configuration utilisateur vit dans config.json, à côté de ce fichier.
On fournit des valeurs par défaut robustes si une clé manque, afin que l'app
reste fonctionnelle même avec un config.json incomplet.
"""

import json
import os

# Dossier racine du projet (là où se trouve ce fichier).
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

# Valeurs par défaut. Elles servent de secours si config.json est absent ou
# incomplet.
DEFAULTS = {
    "lock_combo": ["ctrl", "alt", "l"],
    "unlock_sequence": ["u", "n", "l", "o", "c", "k"],
    "capture_folder": r"%USERPROFILE%\\Desktop\\PC-Lock-Captures",
    "fail_threshold": 1,
    "overlay_flash": True,
    "capture_cooldown_seconds": 3,
    "max_lock_seconds": 120,
}


class Config:
    """Configuration de l'application, normalisée en minuscules."""

    def __init__(self, data):
        # On normalise toutes les touches en minuscules pour comparer sans se
        # soucier de la casse.
        self.lock_combo = [str(k).lower() for k in data.get("lock_combo", DEFAULTS["lock_combo"])]
        self.unlock_sequence = [str(k).lower() for k in data.get("unlock_sequence", DEFAULTS["unlock_sequence"])]
        self.capture_folder = data.get("capture_folder", DEFAULTS["capture_folder"])
        self.fail_threshold = int(data.get("fail_threshold", DEFAULTS["fail_threshold"]))
        self.overlay_flash = bool(data.get("overlay_flash", DEFAULTS["overlay_flash"]))
        self.capture_cooldown_seconds = float(
            data.get("capture_cooldown_seconds", DEFAULTS["capture_cooldown_seconds"])
        )
        self.max_lock_seconds = int(
            data.get("max_lock_seconds", DEFAULTS["max_lock_seconds"])
        )

        # Chemin absolu des captures : expand %USERPROFILE%, ~, etc.
        folder = os.path.expandvars(os.path.expanduser(str(self.capture_folder)))
        if os.path.isabs(folder):
            self.capture_dir = folder
        else:
            self.capture_dir = os.path.join(BASE_DIR, folder)

        self._validate()

    def _validate(self):
        """Garde-fous : empêche une config absurde de casser l'app."""
        if not self.lock_combo:
            self.lock_combo = list(DEFAULTS["lock_combo"])
        if not self.unlock_sequence:
            self.unlock_sequence = list(DEFAULTS["unlock_sequence"])
        # Lock et unlock doivent être différents pour éviter les conflits.
        if self.lock_combo == self.unlock_sequence:
            raise ValueError("lock_combo et unlock_sequence doivent être différents.")
        if self.fail_threshold < 1:
            self.fail_threshold = 1
        if self.max_lock_seconds < 0:
            self.max_lock_seconds = 0

    def ensure_capture_dir(self):
        """Crée le dossier de captures s'il n'existe pas."""
        os.makedirs(self.capture_dir, exist_ok=True)
        return self.capture_dir


def load_config(path=CONFIG_PATH):
    """Lit config.json et renvoie un objet Config. Tombe sur les valeurs par
    défaut si le fichier est absent ou illisible."""
    data = dict(DEFAULTS)
    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            data.update(loaded)
    except FileNotFoundError:
        print(f"[config] {path} introuvable, utilisation des valeurs par défaut.")
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[config] Erreur de lecture ({exc}), utilisation des valeurs par défaut.")
    return Config(data)
