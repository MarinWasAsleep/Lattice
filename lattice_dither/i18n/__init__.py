"""Translation lookup for every user-visible string of the interface.

Keys are the English source strings, so a string missing from a catalogue falls
back to readable English instead of to a dotted identifier. The catalogues live
in ``en.json`` and ``fr.json`` next to this module and share one key set.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from PySide6.QtCore import QLocale, QSettings

SETTINGS_ORGANISATION = "LatticeDither"
SETTINGS_APPLICATION = "LatticeDither"
LANGUAGE_KEY = "language"
DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "fr")

_current: str | None = None


@cache
def _catalogue(code: str) -> dict[str, str]:
    """Return the catalogue of one language, read once from its JSON file."""
    path = Path(__file__).with_name(f"{code}.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(key): str(value) for key, value in data.items()}


def tr(key: str, **kwargs: object) -> str:
    """Return key translated into the current language, formatted with kwargs."""
    text = _catalogue(current_language()).get(key)
    if text is None:
        text = _catalogue(DEFAULT_LANGUAGE).get(key)
    if text is None:
        text = key
    if not kwargs:
        return text
    try:
        return text.format(**kwargs)
    except (IndexError, KeyError, ValueError):
        return text


def set_language(code: str) -> None:
    """Select the language used by tr(); code must be one of SUPPORTED_LANGUAGES."""
    if code not in SUPPORTED_LANGUAGES:
        raise ValueError(f"unsupported language {code!r}, expected one of {SUPPORTED_LANGUAGES}")
    global _current
    _current = code


def current_language() -> str:
    """Return the active language code, resolving it on first use."""
    global _current
    if _current is None:
        _current = _resolve_language()
    return _current


def init_language() -> str:
    """Resolve the language from QSettings, the system locale, then English."""
    set_language(_resolve_language())
    return current_language()


def save_language(code: str) -> None:
    """Select code and remember it in QSettings for the next launch."""
    set_language(code)
    _settings().setValue(LANGUAGE_KEY, code)


def _settings() -> QSettings:
    """Return the settings store holding the user preferences."""
    return QSettings(SETTINGS_ORGANISATION, SETTINGS_APPLICATION)


def _stored_language() -> str | None:
    """Return the language remembered in QSettings, or None when it is unset."""
    value = _settings().value(LANGUAGE_KEY)
    return str(value) if value else None


def _system_language() -> str:
    """Return the two-letter language of the system locale."""
    return QLocale.system().name().split("_")[0].lower()


def _resolve_language() -> str:
    """Return the stored language, else the system locale, else English."""
    for candidate in (_stored_language(), _system_language()):
        if candidate in SUPPORTED_LANGUAGES:
            return str(candidate)
    return DEFAULT_LANGUAGE
