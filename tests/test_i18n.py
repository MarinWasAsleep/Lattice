"""Tests for the localisation package and every UI file that shows text to the user."""

from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QFormLayout  # noqa: E402

from lattice_dither import i18n  # noqa: E402
from lattice_dither.core.types import ParamSpec  # noqa: E402
from lattice_dither.i18n import (  # noqa: E402
    current_language,
    init_language,
    save_language,
    set_language,
    tr,
)
from lattice_dither.ui.param_form import ParamForm  # noqa: E402

CATALOGUE_DIR = Path(i18n.__file__).resolve().parent
UI_DIR = Path(i18n.__file__).resolve().parents[1] / "ui"
# Every module of the interface, not a hand-picked subset: a new file is covered on the
# day it is created, which is the only way the check stays true.
CONVERTED_FILES: tuple[str, ...] = tuple(sorted(path.name for path in UI_DIR.glob("*.py")))

# The glossary of §22.3: the English term must be gone from fr.json, the French
# one must be there. "palette" is unchanged and is checked separately.
GLOSSARY: tuple[tuple[str, str], ...] = (
    ("dithering", "tramage"),
    ("algorithm", "algorithme"),
    ("strength", "force"),
    ("density", "densité"),
    ("before", "avant"),
    ("after", "après"),
)

# A user-visible setter called with a string literal, as named by the card.
LITERAL_NAMED_SETTER = re.compile(
    r"\.(?:setText|setWindowTitle|setPlaceholderText)\(\s*[rbfuRBFU]{0,2}[\"']"
)
# Any other setter called with a string literal. setStyle and setObjectName take
# identifiers, not text a user reads, so they are the only ones allowed through.
LITERAL_ANY_SETTER = re.compile(r"\.(set[A-Z]\w*)\(\s*[rbfuRBFU]{0,2}[\"']")
ALLOWED_SETTERS = frozenset({"setStyle", "setObjectName"})
# The same mistake in a widget constructor, a layout row or a message box title.
LITERAL_WIDGET = re.compile(
    r"\b(?:QLabel|QPushButton|QCheckBox|QGroupBox|QAction|QToolBar|QDockWidget|"
    r"addRow|addItem|addItems|showMessage|setToolTip)\(\s*[rbfuRBFU]{0,2}[\"']"
)
LITERAL_MESSAGE_BOX = re.compile(r"QMessageBox\.\w+\(\s*[^,()]*,\s*[rbfuRBFU]{0,2}[\"']")
TR_CALL = re.compile(r"\btr\(\s*[\"']([^\"']+)[\"']")
# tr(NAME) and tr(NAME[...]) where NAME is a module-level constant of the same file.
TR_CONSTANT = re.compile(r"\btr\(\s*([A-Z][A-Z0-9_]*)\s*[,)]")
TR_LOOKUP = re.compile(r"\btr\(\s*([A-Z][A-Z0-9_]*)\[")
# A call that puts text in front of the user. A file that has one must import tr.
TEXT_API = re.compile(
    r"\b(?:QLabel|QPushButton|QCheckBox|QGroupBox|QAction|QToolBar|QDockWidget|QMessageBox|"
    r"setText|setWindowTitle|setPlaceholderText|setToolTip|showMessage|addRow|setApplicationName)\b"
)
TR_IMPORT = "from lattice_dither.i18n import"


def _literal_setters(source: str) -> list[str]:
    """Return every setter of source that is called with a string literal."""
    return [name for name in LITERAL_ANY_SETTER.findall(source) if name not in ALLOWED_SETTERS]


class FakeSettings:
    """In-memory stand-in for QSettings so tests never touch the registry."""

    store: dict[str, object] = {}

    def __init__(self, organisation: str, application: str) -> None:
        self._prefix = f"{organisation}/{application}/"

    def value(self, key: str, default: object = None) -> object:
        """Return the stored value of key, or default."""
        return FakeSettings.store.get(self._prefix + key, default)

    def setValue(self, key: str, value: object) -> None:
        """Store value under key."""
        FakeSettings.store[self._prefix + key] = value


def _load(code: str) -> dict[str, str]:
    """Return the catalogue of one language as a plain dictionary."""
    return json.loads((CATALOGUE_DIR / f"{code}.json").read_text(encoding="utf-8"))


def _store_language(code: str) -> None:
    """Write code into the fake settings store under the language key."""
    FakeSettings(i18n.SETTINGS_ORGANISATION, i18n.SETTINGS_APPLICATION).setValue(
        i18n.LANGUAGE_KEY, code
    )


def _fake_locale(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """Make QLocale.system() report name inside the i18n module."""

    class FakeLocale:
        """Stand-in for QLocale returning a fixed locale name."""

        @staticmethod
        def system() -> FakeLocale:
            """Return the fake locale itself."""
            return FakeLocale()

        def name(self) -> str:
            """Return the fixed locale name."""
            return name

    monkeypatch.setattr(i18n, "QLocale", FakeLocale)


def _source(name: str) -> str:
    """Return the source text of one UI file."""
    return (UI_DIR / name).read_text(encoding="utf-8")


def _module_constants(source: str) -> dict[str, object]:
    """Return the module-level string and dict-of-string constants of a UI module."""
    constants: dict[str, object] = {}
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        try:
            value = ast.literal_eval(node.value)
        except ValueError:
            continue
        if isinstance(value, str) or (
            isinstance(value, dict) and all(isinstance(item, str) for item in value.values())
        ):
            constants[target.id] = value
    return constants


def _tr_keys(source: str) -> set[str]:
    """Return every catalogue key a UI module passes to tr(), constants resolved.

    A key is either a literal, a module-level string constant, or a value of a
    module-level dict of strings. Resolving the last two is what keeps the check
    honest for the panels, which name their labels once and translate them at the
    point of use.
    """
    constants = _module_constants(source)
    keys = set(TR_CALL.findall(source))
    for name in TR_CONSTANT.findall(source):
        value = constants.get(name)
        if isinstance(value, str):
            keys.add(value)
    for name in TR_LOOKUP.findall(source):
        value = constants.get(name)
        if isinstance(value, dict):
            keys.update(item for item in value.values() if isinstance(item, str))
    return keys


def _forget_language(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop the cached language so the next lookup resolves it again."""
    monkeypatch.setattr(i18n, "_current", None)


@pytest.fixture(autouse=True)
def isolated_language(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the language to English and keep QSettings in memory."""
    FakeSettings.store = {}
    monkeypatch.setattr(i18n, "QSettings", FakeSettings)
    monkeypatch.setattr(i18n, "_current", None)
    set_language("en")


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Return the shared offscreen QApplication."""
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    return app


def test_catalogues_share_the_same_key_set() -> None:
    """en.json and fr.json describe exactly the same strings."""
    assert set(_load("en")) == set(_load("fr"))


@pytest.mark.parametrize("code", ["en", "fr"])
def test_every_value_is_a_non_empty_string(code: str) -> None:
    """No catalogue entry is empty, blank or a non-string."""
    for key, value in _load(code).items():
        assert isinstance(value, str), (code, key)
        assert value.strip(), (code, key)


def test_english_catalogue_maps_every_key_to_itself() -> None:
    """The English catalogue is the identity, so a key is its own source text."""
    for key, value in _load("en").items():
        assert value == key


@pytest.mark.parametrize(("english", "french"), GLOSSARY)
def test_french_catalogue_uses_the_contract_glossary(english: str, french: str) -> None:
    """The English term is gone from fr.json and the French one is present."""
    values = [value.lower() for value in _load("fr").values()]
    assert not any(re.search(rf"\b{english}\b", value) for value in values), english
    assert any(french in value for value in values), french


def test_french_catalogue_keeps_palette_unchanged() -> None:
    """§22.3 keeps "palette" as it is in French."""
    assert _load("fr")["Palette"] == "Palette"


def test_french_catalogue_really_differs_from_english() -> None:
    """A handful of core strings are translated, not copied."""
    english, french = _load("en"), _load("fr")
    for key in ("Strength", "Algorithm", "Before dither", "Ready", "Open image"):
        assert french[key] != english[key], key


def test_catalogue_covers_every_parameter_label() -> None:
    """Every ParamSpec label of every algorithm and effect is a catalogue key."""
    import lattice_dither.algorithms  # noqa: F401  (registers the algorithms)
    import lattice_dither.effects  # noqa: F401  (registers the effects)
    from lattice_dither.core.registry import list_algorithms, list_effects

    catalogue = _load("en")
    labels = {spec.label for info in list_algorithms() for spec in info.params}
    labels |= {spec.label for info in list_effects() for spec in info.params}
    assert labels
    assert labels <= set(catalogue), sorted(labels - set(catalogue))


def test_tr_returns_the_key_when_it_is_missing() -> None:
    """An unknown key is its own translation."""
    assert tr("no such key") == "no such key"


def test_tr_formats_the_key_fallback_too() -> None:
    """A missing key is still formatted, so a placeholder never reaches the user."""
    assert tr("Wrote {name}", name="plate.png") == "Wrote plate.png"


def test_tr_formats_keyword_arguments() -> None:
    """Placeholders are filled from the keyword arguments."""
    text = tr("Render: {ms} ms", ms=12)
    assert text == _load("en")["Render: {ms} ms"].format(ms=12)
    assert "12" in text


def test_tr_leaves_a_broken_placeholder_alone() -> None:
    """A missing placeholder argument returns the raw text instead of raising."""
    assert tr("Render: {ms} ms") == "Render: {ms} ms"


def test_tr_falls_back_to_english(monkeypatch: pytest.MonkeyPatch) -> None:
    """A key missing from the active catalogue is looked up in English."""

    def fake_catalogue(code: str) -> dict[str, str]:
        return {} if code == "fr" else {"Only English": "Only English"}

    monkeypatch.setattr(i18n, "_catalogue", fake_catalogue)
    set_language("fr")
    assert tr("Only English") == "Only English"


def test_set_language_rejects_an_unknown_code() -> None:
    """An unsupported code raises ValueError and leaves the language alone."""
    with pytest.raises(ValueError, match="de"):
        set_language("de")
    assert current_language() == "en"


def test_set_language_switches_to_french() -> None:
    """After set_language("fr") every lookup returns the French value."""
    set_language("fr")
    assert current_language() == "fr"
    assert tr("Ready") == _load("fr")["Ready"]
    assert tr("Ready") != _load("en")["Ready"]


def test_language_comes_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """A language stored in QSettings wins over the system locale."""
    _forget_language(monkeypatch)
    _store_language("fr")
    assert current_language() == "fr"


def test_language_falls_back_to_the_system_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no stored language the system locale decides."""
    _forget_language(monkeypatch)
    _fake_locale(monkeypatch, "fr_CA")
    assert current_language() == "fr"


def test_language_falls_back_to_english(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unsupported system locale falls back to English."""
    _forget_language(monkeypatch)
    _fake_locale(monkeypatch, "de_DE")
    assert current_language() == "en"


def test_settings_win_over_the_system_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    """A stored English choice beats a French system locale."""
    _forget_language(monkeypatch)
    _fake_locale(monkeypatch, "fr_CA")
    _store_language("en")
    assert current_language() == "en"


def test_save_language_persists_the_choice() -> None:
    """save_language selects the language and writes it to QSettings."""
    save_language("fr")
    assert current_language() == "fr"
    stored = FakeSettings(i18n.SETTINGS_ORGANISATION, i18n.SETTINGS_APPLICATION)
    assert stored.value(i18n.LANGUAGE_KEY) == "fr"


def test_init_language_applies_the_stored_language() -> None:
    """init_language reads QSettings and makes tr() follow it."""
    _store_language("fr")
    assert init_language() == "fr"
    assert tr("Ready") == _load("fr")["Ready"]


def test_literal_detector_flags_a_literal() -> None:
    """The detectors used below really catch a hard-coded UI string."""
    source = 'self.setWindowTitle("Lattice Dither")\nself.setText(f"Ready {n}")\n'
    assert len(LITERAL_NAMED_SETTER.findall(source)) == 2
    assert _literal_setters(source) == ["setWindowTitle", "setText"]
    assert _literal_setters('app.setApplicationName("Lattice Dither")\n') == ["setApplicationName"]
    assert LITERAL_WIDGET.findall('QLabel("Ready", self)\nform.addRow("Algorithm", box)\n')
    assert LITERAL_MESSAGE_BOX.findall('QMessageBox.critical(self, "Lattice Dither", text)\n')


def test_literal_detector_ignores_translated_calls() -> None:
    """The detectors do not flag a call routed through tr()."""
    source = 'self.setWindowTitle(tr("Lattice Dither"))\nself.setText(tr("Ready"))\n'
    assert LITERAL_NAMED_SETTER.findall(source) == []
    assert _literal_setters(source) == []
    widgets = 'QLabel(tr("Ready"), self)\nform.addRow(tr("Algorithm"), box)\n'
    assert LITERAL_WIDGET.findall(widgets) == []
    box = 'QMessageBox.critical(self, tr("Lattice Dither"), text)\n'
    assert LITERAL_MESSAGE_BOX.findall(box) == []


def test_literal_detector_allows_identifier_setters() -> None:
    """setStyle and setObjectName take identifiers, so they are not flagged."""
    source = 'app.setStyle("Fusion")\nwidget.setObjectName("panel")\n'
    assert _literal_setters(source) == []


@pytest.mark.parametrize("name", CONVERTED_FILES)
def test_converted_files_have_no_literal_ui_string(name: str) -> None:
    """No user-visible string of the converted files is a literal."""
    source = _source(name)
    assert LITERAL_NAMED_SETTER.findall(source) == []
    assert _literal_setters(source) == []
    assert LITERAL_WIDGET.findall(source) == []
    assert LITERAL_MESSAGE_BOX.findall(source) == []


@pytest.mark.parametrize("name", CONVERTED_FILES)
def test_converted_files_route_their_strings_through_tr(name: str) -> None:
    """A file that puts text in front of the user imports tr and calls it."""
    source = _source(name)
    if not TEXT_API.search(source):
        return
    assert TR_IMPORT in source, name
    assert re.search(r"\btr\(", source), name


def test_param_form_translates_the_spec_label() -> None:
    """The form row label is the translated spec label, not the raw one."""
    assert re.search(r"addRow\(\s*tr\(spec\.label\)", _source("param_form.py"))


@pytest.mark.parametrize("name", CONVERTED_FILES)
def test_every_key_used_by_the_converted_files_exists(name: str) -> None:
    """Each tr() key of the converted files is in the catalogue, constants included."""
    catalogue = _load("en")
    missing = sorted(_tr_keys(_source(name)) - set(catalogue))
    assert missing == [], (name, missing)


def test_the_key_extractor_resolves_module_constants() -> None:
    """The extractor really follows a constant and a dict, not just a literal."""
    source = (
        'TITLE = "Before dither"\n'
        'LABELS = {"builtin": "Built-in", "custom": "Custom"}\n'
        'box = QGroupBox(tr(TITLE))\n'
        'button = QRadioButton(tr(LABELS[name]))\n'
        'label = QLabel(tr("Ready"))\n'
    )
    assert _tr_keys(source) == {"Before dither", "Built-in", "Custom", "Ready"}


def test_param_form_translates_its_labels(qapp: QApplication) -> None:
    """The form shows the catalogue label, and follows a language change."""
    spec = ParamSpec(
        id="strength", label="Strength", kind="float", default=0.5, min=0.0, max=1.0, step=0.01
    )
    form = ParamForm((spec,))
    try:
        layout = form.layout()
        assert isinstance(layout, QFormLayout)
        label = layout.labelForField(form.widget("strength"))
        assert label is not None
        assert label.text() == _load("en")["Strength"]
        set_language("fr")
        form.set_specs((spec,))
        label = layout.labelForField(form.widget("strength"))
        assert label is not None
        assert label.text() == _load("fr")["Strength"]
    finally:
        form.close()


def test_create_application_uses_the_translated_name(qapp: QApplication) -> None:
    """The bootstrap resolves the language and names the application through tr()."""
    from lattice_dither.ui.app import create_application

    _store_language("fr")
    app = create_application([])
    assert current_language() == "fr"
    assert app.applicationName() == _load("fr")["Lattice Dither"]
