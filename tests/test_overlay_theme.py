"""Tests for the LOGITECHMOUSE_THEME env-var switch.

Themes are baked at import time, so each test importlib-reloads
the widget module under a chosen env var. Marked requires_display
because the module pulls in PyQt6.QtWidgets at import.
"""
import importlib
import os
import sys

import pytest

pytest.importorskip("PyQt6.QtWidgets")


def _reload_widget(theme_value: str | None):
    """Set LOGITECHMOUSE_THEME and reload logitechmouse.overlay.widget."""
    if theme_value is None:
        os.environ.pop("LOGITECHMOUSE_THEME", None)
    else:
        os.environ["LOGITECHMOUSE_THEME"] = theme_value
    mod_name = "logitechmouse.overlay.widget"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


@pytest.mark.requires_display
def test_default_theme_is_dark():
    widget = _reload_widget(None)
    # Dark theme dead zone is near-black.
    assert widget._theme["dead_zone"].red() == 6
    assert widget._theme["dead_zone"].green() == 6
    assert widget._theme["dead_zone"].blue() == 6
    # center_label is light for legibility on dark background.
    assert widget._theme["center_label"].red() >= 200


@pytest.mark.requires_display
def test_brazil_theme_swaps_palette():
    widget = _reload_widget("brazil")
    # Yellow dead zone.
    assert widget._theme["dead_zone"].red() == 255
    assert widget._theme["dead_zone"].green() == 223
    # Blue label_active.
    assert widget._theme["label_active"].blue() == 118
    # center_label is dark blue for legibility on yellow dead zone.
    assert widget._theme["center_label"].blue() == 118
    # Both themes define the center_label key.
    assert "center_label" in widget._THEMES["dark"]
    assert "center_label" in widget._THEMES["brazil"]


@pytest.mark.requires_display
def test_unknown_theme_falls_back_to_dark():
    widget = _reload_widget("nonsense")
    # Falls back to dark theme colors.
    assert widget._theme["dead_zone"].red() == 6


@pytest.mark.requires_display
def test_apply_theme_swaps_palette():
    widget = _reload_widget(None)
    widget.apply_theme(name="brazil")
    assert widget._theme["dead_zone"].red() == 255
    assert widget._theme["dead_zone"].green() == 223
    widget.apply_theme(name="dark")
    assert widget._theme["dead_zone"].red() == 6


@pytest.mark.requires_display
def test_apply_theme_with_overrides_replaces_specific_keys():
    widget = _reload_widget(None)
    widget.apply_theme(
        name="dark",
        overrides={"bubble_active": "#ffdf00", "center_label": "#002776"},
    )
    # Override took.
    assert widget._theme["bubble_active"].red() == 255
    assert widget._theme["bubble_active"].green() == 223
    assert widget._theme["center_label"].blue() == 118
    # Non-overridden key still comes from dark preset.
    assert widget._theme["dead_zone"].red() == 6


@pytest.mark.requires_display
def test_apply_theme_overrides_do_not_leak_into_preset_table():
    widget = _reload_widget(None)
    widget.apply_theme(name="dark", overrides={"bubble_active": "#ff0000"})
    # The shared _THEMES["dark"] entry must not have been mutated.
    assert widget._THEMES["dark"]["bubble_active"].red() != 255 or \
        widget._THEMES["dark"]["bubble_active"].green() != 0


@pytest.mark.requires_display
def test_env_var_overrides_apply_theme_name():
    """Env var is the testing escape hatch — it must beat the TOML-derived name
    that the CLI passes to apply_theme()."""
    widget = _reload_widget("brazil")
    widget.apply_theme(name="dark")  # CLI says dark, env says brazil
    assert widget._theme["dead_zone"].red() == 255  # brazil wins


@pytest.mark.requires_display
def test_apply_theme_with_8_digit_hex_uses_alpha():
    widget = _reload_widget(None)
    widget.apply_theme(name="dark", overrides={"bubble": "#ffdf0080"})
    assert widget._theme["bubble"].alpha() == 0x80


@pytest.fixture(autouse=True)
def _restore_default_theme_after_test():
    yield
    _reload_widget(None)
