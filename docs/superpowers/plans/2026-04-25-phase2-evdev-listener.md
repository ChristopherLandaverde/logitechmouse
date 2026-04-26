# Phase 2 evdev Listener Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing scaffold into a working tool that listens to a real Logitech MX mouse via `evdev` and fires configured shell-command actions on button press.

**Architecture:** Single-threaded blocking `evdev` read loop on the main thread. Auto-discovery of the MX device with optional config override. Subcommand-based CLI (`listen`, `devices`, `run`, `check-config`). Subprocesses spawned fire-and-forget so a slow action does not stall event reading. Default examples bind the conflict-free gesture button (`BTN_TASK`) so we can skip device-grabbing and `uinput` entirely in this MVP.

**Tech Stack:** Python 3.11+, `evdev>=1.6`, stdlib `argparse` / `logging` / `subprocess` / `signal` / `tomllib`, `pytest>=7` for tests.

**Spec:** `docs/superpowers/specs/2026-04-25-phase2-evdev-listener-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` (modify) | Add `evdev>=1.6` runtime dep; add `pytest>=7` to dev extras. |
| `src/logitechmouse/config.py` (modify) | Add optional `[device]` section parsing (`name`, `path`); validate trigger codes via `evdev.ecodes.ecodes`. |
| `src/logitechmouse/device.py` (rewrite) | `EvdevBackend` with `list_candidates()`, `resolve(config)`, and a blocking `read_loop()` generator. |
| `src/logitechmouse/actions.py` (modify) | Switch `subprocess.run` → `subprocess.Popen` (fire-and-forget); catch spawn errors. |
| `src/logitechmouse/main.py` (rewrite) | Subcommand CLI: `listen`, `devices`, `run`, `check-config`. SIGINT/SIGTERM handler. `logging.basicConfig`. |
| `src/logitechmouse/cli/__init__.py` (create) | Package marker for subcommand handlers. |
| `src/logitechmouse/cli/listen.py` (create) | `listen` subcommand handler — wires config + backend + dispatcher loop. |
| `src/logitechmouse/cli/devices.py` (create) | `devices` subcommand handler — print candidate table. |
| `src/logitechmouse/cli/check_config.py` (create) | `check-config` subcommand handler. |
| `src/logitechmouse/cli/run.py` (create) | `run` subcommand handler (replaces `--run-action`). |
| `examples/config.toml` (modify) | Default trigger becomes `BTN_TASK`; comment about side-button conflicts. |
| `tests/__init__.py` (create) | Empty marker. |
| `tests/test_config.py` (create) | Config parsing + validation tests. |
| `tests/test_actions.py` (create) | Action execution tests using real `/bin/true` and `/bin/false`. |
| `tests/test_device_resolve.py` (create) | Device resolution tests with mocked `evdev.InputDevice` factory. |

CLI handlers live in their own files because each grows independently and the dispatch table in `main.py` stays trivial.

---

## Task 1: Add dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Update `pyproject.toml`**

Replace the existing `[project]` `dependencies` and `[project.optional-dependencies]` blocks:

```toml
dependencies = [
  "evdev>=1.6",
]

[project.optional-dependencies]
dev = [
  "pytest>=7",
]
```

- [ ] **Step 2: Reinstall in editable mode**

Run: `pip install -e ".[dev]"`
Expected: installs `evdev` and `pytest`. No errors. `python -c "import evdev; print(evdev.__version__)"` prints a version.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: add evdev runtime and pytest dev dependencies"
```

---

## Task 2: Test directory scaffolding

**Files:**
- Create: `tests/__init__.py`

- [ ] **Step 1: Create empty package marker**

Write `tests/__init__.py` with content:

```python
```

(empty file)

- [ ] **Step 2: Verify pytest discovers an empty test set**

Run: `pytest -q`
Expected: `no tests ran` (exit 5 is acceptable).

- [ ] **Step 3: Commit**

```bash
git add tests/__init__.py
git commit -m "test: add tests package marker"
```

---

## Task 3: Config — parse optional `[device]` section (TDD)

**Files:**
- Test: `tests/test_config.py`
- Modify: `src/logitechmouse/config.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_config.py`:

```python
from pathlib import Path
import textwrap

import pytest

from logitechmouse.config import load_config


def write_cfg(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(body))
    return p


def test_missing_file_returns_empty_config(tmp_path):
    cfg = load_config(tmp_path / "nope.toml")
    assert cfg.actions == {}
    assert cfg.bindings == {}
    assert cfg.device.name is None
    assert cfg.device.path is None


def test_parses_actions_and_bindings(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"

        [bindings.gesture]
        trigger = "BTN_TASK"
        action = "shot"
    """)
    cfg = load_config(p)
    assert cfg.actions["shot"].command == "true"
    assert cfg.bindings["gesture"].trigger == "BTN_TASK"
    assert cfg.bindings["gesture"].action == "shot"


def test_parses_device_section(tmp_path):
    p = write_cfg(tmp_path, """
        [device]
        name = "MX Master"
        path = "/dev/input/event7"
    """)
    cfg = load_config(p)
    assert cfg.device.name == "MX Master"
    assert cfg.device.path == "/dev/input/event7"


def test_device_section_optional(tmp_path):
    p = write_cfg(tmp_path, "[actions.x]\ntype = \"command\"\ncommand = \"true\"\n")
    cfg = load_config(p)
    assert cfg.device.name is None
    assert cfg.device.path is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: failures referencing `cfg.device` not existing.

- [ ] **Step 3: Update `src/logitechmouse/config.py`**

Replace file contents with:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "logitechmouse" / "config.toml"


@dataclass
class Action:
    name: str
    kind: str
    command: str | None = None


@dataclass
class Binding:
    name: str
    trigger: str
    action: str


@dataclass
class DeviceConfig:
    name: str | None = None
    path: str | None = None


@dataclass
class AppConfig:
    actions: dict[str, Action] = field(default_factory=dict)
    bindings: dict[str, Binding] = field(default_factory=dict)
    device: DeviceConfig = field(default_factory=DeviceConfig)


def load_config(path: Path | None = None) -> AppConfig:
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return AppConfig()

    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)

    actions = {
        name: Action(
            name=name,
            kind=data.get("type", "command"),
            command=data.get("command"),
        )
        for name, data in raw.get("actions", {}).items()
    }
    bindings = {
        name: Binding(
            name=name,
            trigger=data["trigger"],
            action=data["action"],
        )
        for name, data in raw.get("bindings", {}).items()
    }
    raw_device = raw.get("device", {}) or {}
    device = DeviceConfig(
        name=raw_device.get("name"),
        path=raw_device.get("path"),
    )

    return AppConfig(actions=actions, bindings=bindings, device=device)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/logitechmouse/config.py tests/test_config.py
git commit -m "feat(config): add optional [device] section parsing"
```

---

## Task 4: Config — validate triggers and action references (TDD)

**Files:**
- Test: `tests/test_config.py` (extend)
- Modify: `src/logitechmouse/config.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_config.py`:

```python
from logitechmouse.config import ConfigError, validate_config


def test_validate_passes_on_good_config(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"

        [bindings.g]
        trigger = "BTN_TASK"
        action = "shot"
    """)
    validate_config(load_config(p))  # no raise


def test_validate_rejects_unknown_action_reference(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"

        [bindings.g]
        trigger = "BTN_TASK"
        action = "missing"
    """)
    with pytest.raises(ConfigError, match="binding 'g' references unknown action 'missing'"):
        validate_config(load_config(p))


def test_validate_rejects_unknown_trigger_code(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"

        [bindings.g]
        trigger = "BTN_NOPE"
        action = "shot"
    """)
    with pytest.raises(ConfigError, match="binding 'g' has unknown trigger 'BTN_NOPE'"):
        validate_config(load_config(p))


def test_validate_rejects_command_action_without_command(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
    """)
    with pytest.raises(ConfigError, match="action 'shot' is type=command but has no command"):
        validate_config(load_config(p))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: 4 new failures, `ConfigError` not importable.

- [ ] **Step 3: Implement validation**

Append to `src/logitechmouse/config.py`:

```python
from evdev import ecodes


class ConfigError(Exception):
    """Raised when a loaded config fails validation."""


def validate_config(config: AppConfig) -> None:
    for action in config.actions.values():
        if action.kind == "command" and not action.command:
            raise ConfigError(f"action {action.name!r} is type=command but has no command")

    for binding in config.bindings.values():
        if binding.action not in config.actions:
            raise ConfigError(
                f"binding {binding.name!r} references unknown action {binding.action!r}"
            )
        if binding.trigger not in ecodes.ecodes:
            raise ConfigError(
                f"binding {binding.name!r} has unknown trigger {binding.trigger!r}"
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add src/logitechmouse/config.py tests/test_config.py
git commit -m "feat(config): validate trigger codes and action references"
```

---

## Task 5: Actions — fire-and-forget Popen (TDD)

**Files:**
- Test: `tests/test_actions.py`
- Modify: `src/logitechmouse/actions.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_actions.py`:

```python
import time

from logitechmouse.actions import run_action
from logitechmouse.config import Action


def test_dry_run_does_not_spawn():
    action = Action(name="x", kind="command", command="/bin/false")
    result = run_action(action, dry_run=True)
    assert result.ok is True
    assert "dry-run" in result.detail


def test_unsupported_kind_returns_error():
    action = Action(name="x", kind="overlay")
    result = run_action(action)
    assert result.ok is False
    assert "unsupported" in result.detail


def test_missing_command_returns_error():
    action = Action(name="x", kind="command", command=None)
    result = run_action(action)
    assert result.ok is False
    assert "missing command" in result.detail


def test_spawn_failure_is_caught():
    action = Action(name="x", kind="command", command="/no/such/binary --flag")
    result = run_action(action)
    assert result.ok is False
    assert "failed to spawn" in result.detail


def test_successful_spawn_does_not_block(tmp_path):
    marker = tmp_path / "marker"
    action = Action(
        name="x",
        kind="command",
        command=f"/bin/sh -c 'sleep 0.2 && touch {marker}'",
    )
    start = time.monotonic()
    result = run_action(action)
    elapsed = time.monotonic() - start
    assert result.ok is True
    assert elapsed < 0.15, f"run_action blocked for {elapsed:.2f}s"
    # Wait for the background process to finish so the marker exists.
    for _ in range(50):
        if marker.exists():
            break
        time.sleep(0.05)
    assert marker.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_actions.py -v`
Expected: failures around blocking behavior and spawn-failure handling (current code uses `subprocess.run(check=True)` and raises).

- [ ] **Step 3: Rewrite `src/logitechmouse/actions.py`**

Replace file contents with:

```python
from __future__ import annotations

from dataclasses import dataclass
import shlex
import subprocess

from .config import Action


@dataclass
class ActionResult:
    action: str
    ok: bool
    detail: str


def run_action(action: Action, dry_run: bool = False) -> ActionResult:
    if action.kind != "command":
        return ActionResult(action.name, False, f"unsupported action type: {action.kind}")

    if not action.command:
        return ActionResult(action.name, False, "missing command")

    if dry_run:
        return ActionResult(action.name, True, f"dry-run: {action.command}")

    try:
        subprocess.Popen(shlex.split(action.command))
    except (FileNotFoundError, PermissionError, OSError) as exc:
        return ActionResult(action.name, False, f"failed to spawn: {exc}")

    return ActionResult(action.name, True, f"fired: {action.command}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_actions.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/logitechmouse/actions.py tests/test_actions.py
git commit -m "feat(actions): fire-and-forget Popen with spawn-error capture"
```

---

## Task 6: Device — candidate listing (TDD)

**Files:**
- Test: `tests/test_device_resolve.py`
- Rewrite: `src/logitechmouse/device.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_device_resolve.py`:

```python
from dataclasses import dataclass
from unittest.mock import patch

import pytest

from logitechmouse.config import DeviceConfig
from logitechmouse.device import (
    CandidateDevice,
    DeviceNotFoundError,
    DeviceUnreadableError,
    EvdevBackend,
)


@dataclass
class FakeEvdev:
    path: str
    name: str
    vendor: int = 0x046D
    product: int = 0x4082
    readable: bool = True

    @property
    def info(self):
        class _I:
            vendor = self.vendor
            product = self.product
        return _I()


def make_factory(devices):
    """Return a callable that mimics evdev.InputDevice(path)."""
    by_path = {d.path: d for d in devices}

    def factory(path):
        d = by_path.get(path)
        if d is None or not d.readable:
            raise PermissionError(f"cannot open {path}")
        return d

    return factory


def patch_backend(devices):
    paths = [d.path for d in devices]
    factory = make_factory(devices)
    return (
        patch("logitechmouse.device.list_devices", return_value=paths),
        patch("logitechmouse.device.InputDevice", side_effect=factory),
    )


def test_list_candidates_marks_unreadable(monkeypatch):
    devices = [
        FakeEvdev("/dev/input/event5", "Logitech MX Master 3S"),
        FakeEvdev("/dev/input/event7", "Locked Device", readable=False),
    ]
    p1, p2 = patch_backend(devices)
    with p1, p2:
        result = EvdevBackend().list_candidates()

    assert len(result) == 2
    by_path = {c.path: c for c in result}
    assert by_path["/dev/input/event5"].readable is True
    assert by_path["/dev/input/event5"].name == "Logitech MX Master 3S"
    assert by_path["/dev/input/event7"].readable is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_device_resolve.py -v`
Expected: ImportError — none of the new symbols exist.

- [ ] **Step 3: Rewrite `src/logitechmouse/device.py`**

Replace file contents with:

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator

from evdev import InputDevice, categorize, ecodes, list_devices

from .config import DeviceConfig


_AUTO_NAME_RE = re.compile(r"logitech|mx (master|anywhere|ergo|vertical)", re.IGNORECASE)


class DeviceNotFoundError(Exception):
    """Raised when no device matches the resolution criteria."""


class DeviceUnreadableError(Exception):
    """Raised when the matched device cannot be opened for reading."""


@dataclass
class CandidateDevice:
    path: str
    name: str
    vendor: int
    product: int
    readable: bool


@dataclass
class InputEvent:
    trigger: str  # evdev key code name, e.g. "BTN_TASK"


class EvdevBackend:
    def list_candidates(self) -> list[CandidateDevice]:
        candidates: list[CandidateDevice] = []
        for path in list_devices():
            try:
                dev = InputDevice(path)
                candidates.append(
                    CandidateDevice(
                        path=path,
                        name=dev.name,
                        vendor=dev.info.vendor,
                        product=dev.info.product,
                        readable=True,
                    )
                )
            except (PermissionError, OSError):
                candidates.append(
                    CandidateDevice(
                        path=path,
                        name="(unreadable)",
                        vendor=0,
                        product=0,
                        readable=False,
                    )
                )
        return candidates
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_device_resolve.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/logitechmouse/device.py tests/test_device_resolve.py
git commit -m "feat(device): list_candidates with readability detection"
```

---

## Task 7: Device — resolution (path / name / auto / not-found) (TDD)

**Files:**
- Test: `tests/test_device_resolve.py` (extend)
- Modify: `src/logitechmouse/device.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_device_resolve.py`:

```python
def test_resolve_by_explicit_path():
    devices = [FakeEvdev("/dev/input/event5", "Logitech MX Master 3S")]
    p1, p2 = patch_backend(devices)
    with p1, p2:
        dev = EvdevBackend().resolve(DeviceConfig(path="/dev/input/event5"))
    assert dev.path == "/dev/input/event5"


def test_resolve_explicit_path_unreadable_raises():
    devices = [FakeEvdev("/dev/input/event5", "x", readable=False)]
    p1, p2 = patch_backend(devices)
    with p1, p2, pytest.raises(DeviceUnreadableError):
        EvdevBackend().resolve(DeviceConfig(path="/dev/input/event5"))


def test_resolve_by_name_substring_case_insensitive():
    devices = [
        FakeEvdev("/dev/input/event4", "AT Keyboard"),
        FakeEvdev("/dev/input/event5", "Logitech MX Master 3S"),
    ]
    p1, p2 = patch_backend(devices)
    with p1, p2:
        dev = EvdevBackend().resolve(DeviceConfig(name="mx master"))
    assert dev.path == "/dev/input/event5"


def test_resolve_auto_matches_logitech_or_mx():
    devices = [
        FakeEvdev("/dev/input/event4", "AT Keyboard"),
        FakeEvdev("/dev/input/event5", "Logitech USB Receiver Mouse"),
    ]
    p1, p2 = patch_backend(devices)
    with p1, p2:
        dev = EvdevBackend().resolve(DeviceConfig())
    assert dev.path == "/dev/input/event5"


def test_resolve_not_found_raises():
    devices = [FakeEvdev("/dev/input/event4", "AT Keyboard")]
    p1, p2 = patch_backend(devices)
    with p1, p2, pytest.raises(DeviceNotFoundError):
        EvdevBackend().resolve(DeviceConfig())


def test_resolve_path_missing_raises_not_found():
    devices = [FakeEvdev("/dev/input/event5", "Logitech MX Master 3S")]
    p1, p2 = patch_backend(devices)
    with p1, p2, pytest.raises(DeviceNotFoundError):
        EvdevBackend().resolve(DeviceConfig(path="/dev/input/event99"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_device_resolve.py -v`
Expected: 6 failures around `EvdevBackend.resolve` not existing.

- [ ] **Step 3: Add `resolve()` to `EvdevBackend`**

In `src/logitechmouse/device.py`, add method to the `EvdevBackend` class:

```python
    def resolve(self, device_cfg: DeviceConfig) -> InputDevice:
        all_paths = list_devices()

        if device_cfg.path:
            if device_cfg.path not in all_paths:
                raise DeviceNotFoundError(
                    f"configured device path {device_cfg.path!r} not present"
                )
            try:
                return InputDevice(device_cfg.path)
            except (PermissionError, OSError) as exc:
                raise DeviceUnreadableError(str(exc)) from exc

        match_name = device_cfg.name
        for path in all_paths:
            try:
                dev = InputDevice(path)
            except (PermissionError, OSError):
                continue
            if match_name and match_name.lower() in dev.name.lower():
                return dev
            if not match_name and _AUTO_NAME_RE.search(dev.name):
                return dev

        criterion = f"name~{match_name!r}" if match_name else "auto-discovery"
        raise DeviceNotFoundError(
            f"no input device matched {criterion}; try `logitechmouse devices`"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_device_resolve.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/logitechmouse/device.py tests/test_device_resolve.py
git commit -m "feat(device): resolve by path, name substring, or auto-discovery"
```

---

## Task 8: Device — `read_loop` generator

**Files:**
- Modify: `src/logitechmouse/device.py`

No unit test — `read_loop` wraps `evdev`'s blocking iterator and is verified by manual smoke test.

- [ ] **Step 1: Add `read_loop` to `EvdevBackend`**

Append to the `EvdevBackend` class in `src/logitechmouse/device.py`:

```python
    def read_loop(self, device: InputDevice) -> Iterator[InputEvent]:
        """Yield InputEvent for every key-down on `device`. Blocking."""
        for event in device.read_loop():
            if event.type != ecodes.EV_KEY:
                continue
            if event.value != 1:  # key-down only; skip up (0) and autorepeat (2)
                continue
            key_event = categorize(event)
            keycode = key_event.keycode
            # `keycode` may be a list when one scancode maps to multiple names.
            name = keycode[0] if isinstance(keycode, list) else keycode
            yield InputEvent(trigger=name)
```

- [ ] **Step 2: Sanity import check**

Run: `python -c "from logitechmouse.device import EvdevBackend; print(EvdevBackend().read_loop.__doc__)"`
Expected: prints the docstring; no import errors.

- [ ] **Step 3: Commit**

```bash
git add src/logitechmouse/device.py
git commit -m "feat(device): blocking read_loop yielding key-down events"
```

---

## Task 9: CLI scaffolding — package + dispatcher

**Files:**
- Create: `src/logitechmouse/cli/__init__.py`
- Rewrite: `src/logitechmouse/main.py`

- [ ] **Step 1: Create CLI package marker**

Write `src/logitechmouse/cli/__init__.py`:

```python
"""Subcommand handlers for the logitechmouse CLI."""
```

- [ ] **Step 2: Rewrite `src/logitechmouse/main.py`**

Replace file contents with:

```python
from __future__ import annotations

import argparse
import logging
import signal
import sys
from pathlib import Path


LOG_FORMAT = "%(asctime)s %(levelname)s  %(message)s"


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")


def _install_signal_handlers() -> None:
    def _handle(signum, _frame):
        logging.info("received signal %s, exiting", signum)
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="logitechmouse")
    parser.add_argument("--config", type=Path, help="Path to config TOML")
    sub = parser.add_subparsers(dest="command", required=True)

    p_listen = sub.add_parser("listen", help="Run the event listener")

    p_devices = sub.add_parser("devices", help="List detected input devices")

    p_check = sub.add_parser("check-config", help="Validate config and exit")

    p_run = sub.add_parser("run", help="Run a configured action once")
    p_run.add_argument("name", help="Action name as defined in config")
    p_run.add_argument("--dry-run", action="store_true", help="Do not spawn the command")

    return parser


def main() -> int:
    _configure_logging()
    _install_signal_handlers()

    parser = build_parser()
    args = parser.parse_args()

    # Lazy imports so subcommand failures don't drag in evdev when not needed.
    if args.command == "listen":
        from .cli.listen import run as run_cmd
    elif args.command == "devices":
        from .cli.devices import run as run_cmd
    elif args.command == "check-config":
        from .cli.check_config import run as run_cmd
    elif args.command == "run":
        from .cli.run import run as run_cmd
    else:
        parser.error(f"unknown command: {args.command}")

    return run_cmd(args)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Smoke test the parser**

Run: `logitechmouse --help`
Expected: help text listing the four subcommands. (Subcommand handlers don't exist yet — invoking one will fail. That's OK.)

- [ ] **Step 4: Commit**

```bash
git add src/logitechmouse/cli/__init__.py src/logitechmouse/main.py
git commit -m "feat(cli): subcommand parser with logging and signal handling"
```

---

## Task 10: `devices` subcommand

**Files:**
- Create: `src/logitechmouse/cli/devices.py`

- [ ] **Step 1: Write `cli/devices.py`**

Create `src/logitechmouse/cli/devices.py`:

```python
from __future__ import annotations

import argparse

from ..device import EvdevBackend


def run(args: argparse.Namespace) -> int:
    candidates = EvdevBackend().list_candidates()

    print(f"{'PATH':<22}{'NAME':<36}{'VENDOR':<8}{'PRODUCT':<9}READABLE")
    for c in candidates:
        print(
            f"{c.path:<22}{c.name[:35]:<36}"
            f"{c.vendor:04x}    {c.product:04x}     "
            f"{'yes' if c.readable else 'no'}"
        )

    if any(not c.readable for c in candidates):
        print()
        print("Some devices unreadable. Add yourself to the `input` group:")
        print("  sudo usermod -aG input $USER")
        print("Then log out and back in.")

    return 0
```

- [ ] **Step 2: Smoke test**

Run: `logitechmouse devices`
Expected: a table of input devices on the host. Either readable or with the remediation footer if any aren't.

- [ ] **Step 3: Commit**

```bash
git add src/logitechmouse/cli/devices.py
git commit -m "feat(cli): devices subcommand prints candidate table"
```

---

## Task 11: `check-config` subcommand

**Files:**
- Create: `src/logitechmouse/cli/check_config.py`

- [ ] **Step 1: Write `cli/check_config.py`**

Create `src/logitechmouse/cli/check_config.py`:

```python
from __future__ import annotations

import argparse
import logging

from ..config import ConfigError, load_config, validate_config


def run(args: argparse.Namespace) -> int:
    try:
        cfg = load_config(args.config)
        validate_config(cfg)
    except ConfigError as exc:
        logging.error("config invalid: %s", exc)
        return 1
    except Exception as exc:  # parse errors from tomllib, etc.
        logging.error("could not load config: %s", exc)
        return 1

    print(
        f"OK: {len(cfg.actions)} actions, {len(cfg.bindings)} bindings, "
        f"device={cfg.device.path or cfg.device.name or '(auto)'}"
    )
    return 0
```

- [ ] **Step 2: Smoke test against the example config**

Run: `logitechmouse --config examples/config.toml check-config`
Expected: prints `OK: 2 actions, 2 bindings, device=(auto)` and exits 0.
(The current `examples/config.toml` uses `BTN_EXTRA`/`BTN_SIDE`; we'll update it in Task 14. Both are valid evdev codes so validation passes.)

- [ ] **Step 3: Commit**

```bash
git add src/logitechmouse/cli/check_config.py
git commit -m "feat(cli): check-config subcommand validates without listening"
```

---

## Task 12: `run` subcommand

**Files:**
- Create: `src/logitechmouse/cli/run.py`

- [ ] **Step 1: Write `cli/run.py`**

Create `src/logitechmouse/cli/run.py`:

```python
from __future__ import annotations

import argparse
import logging

from ..actions import run_action
from ..config import ConfigError, load_config, validate_config


def run(args: argparse.Namespace) -> int:
    try:
        cfg = load_config(args.config)
        validate_config(cfg)
    except ConfigError as exc:
        logging.error("config invalid: %s", exc)
        return 1

    action = cfg.actions.get(args.name)
    if action is None:
        logging.error("unknown action: %s", args.name)
        return 1

    result = run_action(action, dry_run=args.dry_run)
    logging.info(result.detail)
    return 0 if result.ok else 1
```

- [ ] **Step 2: Smoke test (dry-run)**

Run: `logitechmouse --config examples/config.toml run screenshot --dry-run`
Expected: log line `dry-run: gnome-screenshot -a` and exit 0.

- [ ] **Step 3: Commit**

```bash
git add src/logitechmouse/cli/run.py
git commit -m "feat(cli): run subcommand for one-shot action execution"
```

---

## Task 13: `listen` subcommand

**Files:**
- Create: `src/logitechmouse/cli/listen.py`

- [ ] **Step 1: Write `cli/listen.py`**

Create `src/logitechmouse/cli/listen.py`:

```python
from __future__ import annotations

import argparse
import logging

from ..actions import run_action
from ..config import ConfigError, load_config, validate_config
from ..device import (
    DeviceNotFoundError,
    DeviceUnreadableError,
    EvdevBackend,
)


REMEDIATION = (
    "device is not readable. Add yourself to the `input` group:\n"
    "  sudo usermod -aG input $USER\n"
    "Then log out and back in."
)


def run(args: argparse.Namespace) -> int:
    try:
        cfg = load_config(args.config)
        validate_config(cfg)
    except ConfigError as exc:
        logging.error("config invalid: %s", exc)
        return 1

    backend = EvdevBackend()
    try:
        device = backend.resolve(cfg.device)
    except DeviceUnreadableError as exc:
        logging.error("%s\n%s", exc, REMEDIATION)
        return 1
    except DeviceNotFoundError as exc:
        logging.error("%s", exc)
        return 1

    bindings_by_trigger = {b.trigger: b for b in cfg.bindings.values()}
    summary = ", ".join(
        f"{b.name}[{b.trigger}]->{b.action}" for b in cfg.bindings.values()
    ) or "(none)"
    logging.info("listening on %s (%s)", device.path, device.name)
    logging.info("bindings: %s", summary)

    try:
        for event in backend.read_loop(device):
            binding = bindings_by_trigger.get(event.trigger)
            if binding is None:
                continue
            action = cfg.actions[binding.action]
            result = run_action(action)
            if result.ok:
                logging.info("%s", result.detail)
            else:
                logging.warning("action %r %s", action.name, result.detail)
    except OSError as exc:
        logging.warning("device read failed: %s", exc)
        return 1

    return 0
```

- [ ] **Step 2: Smoke test (manual, requires hardware)**

Run: `logitechmouse --config examples/config.toml listen`
Expected (with MX mouse plugged in and gesture button bound):
- log: `listening on /dev/input/event<N> (Logitech ...)`
- log: `bindings: gesture_button[BTN_TASK]->screenshot`
- press the gesture button → screenshot fires → log: `fired: gnome-screenshot -a`
- Ctrl-C → log: `received signal 2, exiting` → exit 0

If no MX hardware is present, expect `DeviceNotFoundError` with the suggestion to run `logitechmouse devices`. This is correct behavior.

- [ ] **Step 3: Commit**

```bash
git add src/logitechmouse/cli/listen.py
git commit -m "feat(cli): listen subcommand wires config + backend + dispatcher"
```

---

## Task 14: Update `examples/config.toml`

**Files:**
- Modify: `examples/config.toml`

- [ ] **Step 1: Replace example config**

Overwrite `examples/config.toml` with:

```toml
# Optional. Omit to auto-discover the first Logitech / MX device.
# [device]
# name = "MX Master"
# path = "/dev/input/event7"

[actions.screenshot]
type = "command"
command = "gnome-screenshot -a"

[actions.fullscreen]
type = "command"
command = "gnome-screenshot"

# BTN_TASK is the MX gesture button (under the thumb). It has no default
# OS action, so binding it does not double-fire with browser navigation.
[bindings.gesture_button]
trigger = "BTN_TASK"
action = "screenshot"

# BTN_SIDE / BTN_EXTRA double-fire with browser back / forward in this MVP
# (no device grabbing yet). Bind them only if you accept that overlap.
[bindings.thumb_button]
trigger = "BTN_SIDE"
action = "fullscreen"
```

- [ ] **Step 2: Verify with check-config**

Run: `logitechmouse --config examples/config.toml check-config`
Expected: `OK: 2 actions, 2 bindings, device=(auto)` exit 0.

- [ ] **Step 3: Commit**

```bash
git add examples/config.toml
git commit -m "docs(examples): default to BTN_TASK; document side-button conflict"
```

---

## Task 15: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update Local development and usage sections**

Replace the `## Local development` section through `## Configuration` with:

```markdown
## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
logitechmouse --help
```

## Permissions

Reading `/dev/input/event*` requires membership in the `input` group:

```bash
sudo usermod -aG input $USER
# log out and back in for the change to apply
```

## Usage

```bash
logitechmouse devices                   # list detected input devices
logitechmouse check-config              # validate config and exit
logitechmouse run screenshot --dry-run  # run a configured action once
logitechmouse listen                    # start the event listener
```

## Configuration

The app looks for a TOML config file, defaulting to:

```text
~/.config/logitechmouse/config.toml
```

See `examples/config.toml` for a working sample. Default examples bind the
gesture button (`BTN_TASK`) because it has no OS-default action — `BTN_SIDE`
and `BTN_EXTRA` will double-fire with browser back/forward in this MVP.
```

- [ ] **Step 2: Update Project status**

Replace the existing `## Project status` block with:

```markdown
## Project status

Phase 2 MVP: the CLI listens on a real Logitech MX device via `evdev` and
fires shell-command actions on configured button presses. No device grabbing,
no overlay, no profiles yet — those are scheduled for later phases.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(readme): document Phase 2 MVP usage and permissions"
```

---

## Task 16: Final verification

- [ ] **Step 1: Run the full test suite**

Run: `pytest -v`
Expected: all tests in `tests/test_config.py`, `tests/test_actions.py`, `tests/test_device_resolve.py` pass. No failures, no errors.

- [ ] **Step 2: Smoke each subcommand**

Run each and confirm sensible output / exit code:

```bash
logitechmouse --help
logitechmouse devices
logitechmouse --config examples/config.toml check-config
logitechmouse --config examples/config.toml run screenshot --dry-run
```

- [ ] **Step 3: Manual hardware smoke (if MX mouse is connected)**

Run: `logitechmouse --config examples/config.toml listen`
Press the gesture button. Screenshot fires. Ctrl-C exits cleanly.

- [ ] **Step 4: Final summary commit (only if any housekeeping changes)**

If any stray formatting or doc tweaks fell out of verification, commit them:

```bash
git status
git add -p
git commit -m "chore: post-verification cleanup"
```

If `git status` is clean, skip this step.
