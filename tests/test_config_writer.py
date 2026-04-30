from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from logitechmouse.config import (
    AppConfig, Action, Ring, Segment, Binding, Target,
    Profile, Theme, load_config,
)
from logitechmouse.config_writer import config_to_dict, write_config


def _minimal_config() -> AppConfig:
    return AppConfig(
        actions={"shot": Action(name="shot", kind="command", command="flameshot gui")},
        rings={"main": Ring(name="main", segments=[
            Segment(action="shot", label="Screenshot", icon="fa.camera"),
            Segment(action="shot", label="Alpha"),
            Segment(action="shot", label="Beta"),
        ])},
        bindings={"thumb": Binding(
            name="thumb", trigger="BTN_SIDE",
            target=Target(kind="ring", name="main"),
        )},
    )


def test_config_to_dict_actions():
    d = config_to_dict(_minimal_config())
    assert d["actions"]["shot"]["type"] == "command"
    assert d["actions"]["shot"]["command"] == "flameshot gui"


def test_config_to_dict_rings():
    segs = config_to_dict(_minimal_config())["rings"]["main"]["segments"]
    assert len(segs) == 3
    assert segs[0] == {"action": "shot", "label": "Screenshot", "icon": "fa.camera"}
    assert segs[1] == {"action": "shot", "label": "Alpha"}


def test_config_to_dict_bindings():
    d = config_to_dict(_minimal_config())["bindings"]["thumb"]
    assert d["trigger"] == "BTN_SIDE"
    assert d["target"] == "ring:main"


def test_config_to_dict_no_theme_section_for_defaults():
    assert "theme" not in config_to_dict(AppConfig())


def test_config_to_dict_theme_section_when_non_default():
    d = config_to_dict(AppConfig(theme=Theme(name="brazil", overrides={})))
    assert d["theme"]["name"] == "brazil"


def test_write_config_roundtrip(tmp_path):
    p = tmp_path / "config.toml"
    write_config(p, _minimal_config())
    loaded = load_config(p)
    assert loaded.actions["shot"].command == "flameshot gui"
    assert loaded.rings["main"].segments[0].label == "Screenshot"
    assert loaded.rings["main"].segments[0].icon == "fa.camera"
    assert loaded.rings["main"].segments[1].icon is None
    assert loaded.bindings["thumb"].target.kind == "ring"
    assert loaded.bindings["thumb"].target.name == "main"


def test_write_config_creates_parent_dirs(tmp_path):
    p = tmp_path / "nested" / "dir" / "config.toml"
    write_config(p, AppConfig())
    assert p.exists()


def test_roundtrip_profile(tmp_path):
    cfg = AppConfig(
        actions={"shot": Action(name="shot", kind="command", command="true")},
        profiles={"myapp": Profile(
            name="myapp",
            match_wm_class="MyApp",
            bindings={"btn_side": Binding(
                name="btn_side", trigger="BTN_SIDE",
                target=Target(kind="action", name="shot"),
            )},
        )},
    )
    p = tmp_path / "config.toml"
    write_config(p, cfg)
    loaded = load_config(p)
    assert loaded.profiles["myapp"].match_wm_class == "MyApp"
    assert loaded.profiles["myapp"].bindings["btn_side"].trigger == "BTN_SIDE"
