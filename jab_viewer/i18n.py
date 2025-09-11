from __future__ import annotations

import json
import os
import sys
import configparser
from dataclasses import dataclass
from typing import Dict, Optional, List

try:
    import tomllib  # Python 3.11+
except Exception:  # pragma: no cover
    tomllib = None  # type: ignore


LOCALES_DIRNAME = 'locales'
DEFAULT_LANG = 'en'


def _read_toml(path: str) -> Dict[str, object]:
    if not os.path.isfile(path):
        return {}
    if tomllib is None:
        return {}
    with open(path, 'rb') as f:
        return tomllib.load(f)  # type: ignore[no-any-return]


def _read_ini(path: str) -> Dict[str, object]:
    if not os.path.isfile(path):
        return {}
    cp = configparser.ConfigParser()
    try:
        cp.read(path, encoding='utf-8')
    except Exception:
        return {}
    data: Dict[str, object] = {}
    for section in cp.sections():
        data[section] = dict(cp.items(section))
    return data


def _load_json(path: str) -> Dict[str, str]:
    if not os.path.isfile(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


@dataclass
class I18N:
    lang: str = DEFAULT_LANG
    messages: Dict[str, str] = None  # type: ignore[assignment]
    fallback: Dict[str, str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.reload()

    def _config_search_dirs(self) -> list[str]:
        # When frozen (PyInstaller), prefer the directory where the binary lives
        if getattr(sys, 'frozen', False):  # type: ignore[attr-defined]
            exe_dir = os.path.dirname(os.path.abspath(sys.executable))
            return [exe_dir]
        # When running from source, prefer package directory
        pkg_dir = os.path.dirname(os.path.abspath(__file__))
        return [pkg_dir]

    def _ensure_default_config(self, target_dir: str) -> None:
        # Create a default config next to the binary when running frozen
        if not getattr(sys, 'frozen', False):
            return
        toml_path = os.path.join(target_dir, 'config.toml')
        ini_path = os.path.join(target_dir, 'config.ini')
        if os.path.exists(toml_path) or os.path.exists(ini_path):
            return
        try:
            with open(toml_path, 'w', encoding='utf-8') as f:
                f.write(
                    """[app]
language = \"en\"
"""
                )
        except Exception:
            # Silently ignore if cannot create file
            pass

    def _detect_lang(self) -> str:
        # Priority: explicit config near binary/package -> env var -> default
        lang: Optional[str] = None
        loaded_cfg: Dict[str, object] = {}
        for d in self._config_search_dirs():
            cfg_toml_path = os.path.join(d, 'config.toml')
            cfg_ini_path = os.path.join(d, 'config.ini')
            cfg = _read_toml(cfg_toml_path) or _read_ini(cfg_ini_path)
            if cfg:
                loaded_cfg = cfg
                break
        # If running as a frozen binary and no config found, create a default one
        if not loaded_cfg:
            for d in self._config_search_dirs():
                self._ensure_default_config(d)
                break

        if isinstance(loaded_cfg, dict):
            app = loaded_cfg.get('app', {}) or {}
            if isinstance(app, dict):
                val = app.get('language')
                if isinstance(val, str) and val:
                    lang = val

        env_lang = os.environ.get('JAB_VIEWER_LANG')
        if isinstance(env_lang, str) and env_lang:
            lang = env_lang

        return (lang or DEFAULT_LANG).lower()

    def reload(self) -> None:
        self.lang = self._detect_lang()

        def locales_dirs() -> List[str]:
            dirs: List[str] = []
            # When frozen, prefer resources extracted into _MEIPASS
            base_meipass = getattr(sys, '_MEIPASS', None)
            if isinstance(base_meipass, str) and base_meipass:
                dirs.append(
                    os.path.join(base_meipass, 'jab_viewer', LOCALES_DIRNAME)
                )
                dirs.append(os.path.join(base_meipass, LOCALES_DIRNAME))
            # Always include package directory fallback
            pkg_dir = os.path.dirname(os.path.abspath(__file__))
            dirs.append(os.path.join(pkg_dir, LOCALES_DIRNAME))
            return dirs

        def load_lang(lang: str) -> Dict[str, str]:
            for d in locales_dirs():
                p = os.path.join(d, f'{lang}.json')
                if os.path.isfile(p):
                    return _load_json(p)
            return {}

        self.fallback = load_lang(DEFAULT_LANG)
        self.messages = load_lang(self.lang)

    def tr(self, key: str, /, **kwargs) -> str:
        text = self.messages.get(key) if self.messages else None
        if not text:
            text = self.fallback.get(key, key) if self.fallback else key
        try:
            if kwargs:
                return text.format(**kwargs)
            return text
        except Exception:
            # If formatting fails, return raw text to avoid crashing UI
            return text


_i18n = I18N()


def tr(key: str, /, **kwargs) -> str:
    """Translate a message key using current language.

    Example:
        tr("errors.list_windows.body", e=str(err))
    """
    return _i18n.tr(key, **kwargs)


def current_language() -> str:
    return _i18n.lang


def reload_language() -> None:
    _i18n.reload()
