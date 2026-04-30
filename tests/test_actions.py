import time

from logitechmouse import actions as actions_mod
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


def test_systemd_run_wrapper_falls_back_when_scope_probe_fails(monkeypatch):
    actions_mod._systemd_run_scope_available.cache_clear()
    monkeypatch.setattr(actions_mod.shutil, "which", lambda name: "/usr/bin/systemd-run")
    monkeypatch.setattr(actions_mod, "_user_bus_available", lambda: True)

    class Result:
        returncode = 1

    monkeypatch.setattr(actions_mod.subprocess, "run", lambda *args, **kwargs: Result())

    assert actions_mod._in_own_cgroup(["/bin/true"]) == ["/bin/true"]
    actions_mod._systemd_run_scope_available.cache_clear()


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
    for _ in range(50):
        if marker.exists():
            break
        time.sleep(0.05)
    assert marker.exists()
