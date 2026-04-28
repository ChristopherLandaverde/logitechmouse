# Contributing to logitechmouse

Thanks for your interest! This project is small and the contribution loop is
intentionally simple.

## Filing issues

Before opening an issue:

1. **Run `logitechmouse check-config`** — many problems surface as a clear
   validation error.
2. **Capture what your mouse actually emits** — `sudo ./scripts/dump-keys.py
   /dev/input/eventNN` and press the affected button. Capability bits on MX
   devices can lie, and the codes you see in the dump are ground truth.
3. **Check the journal** — `journalctl --user -u logitechmouse.service -n 50`
   if you're running as a service.

When opening the issue, please include:

- Distro + version (e.g. Pop!\_OS 22.04, Arch, Fedora 39)
- Display server (`echo $XDG_SESSION_TYPE`)
- Mouse model
- Output of `dump-keys.py` for the relevant button
- The relevant section of your `config.toml`
- Service / listener log output

## Development setup

```bash
git clone https://github.com/ChristopherLandaverde/logitechmouse.git
cd logitechmouse
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,ring]"
```

System packages required for tests to run end-to-end:

```bash
sudo apt install libxcb-cursor0 xdotool xvfb
```

## Running the test suite

```bash
pytest                  # full suite; Qt + uinput tests skip if env not ready
xvfb-run -a pytest      # headless (matches CI)
```

Markers:

- `requires_display` — Qt widget tests; skipped when `$DISPLAY` is unset.
- `requires_uinput` — `/dev/uinput` end-to-end tests; skipped when not writable.

The full suite is **178 tests** at the time of this writing; CI runs them
all under `xvfb-run` on Python 3.11 and 3.12.

## Pull request workflow

1. Branch from `main`. Use a descriptive name (`feat/`, `fix/`, `docs/`, …).
2. Write tests first when feasible. If you're fixing a bug, add a regression
   test that fails before your fix.
3. Keep PRs focused — one concern per PR. Bundle adjacent docs updates with
   the code change they describe.
4. Run `pytest` locally before pushing. CI will also run it, but a green
   local run shortens the loop.
5. Open the PR with a short summary. Link any issue it closes.

## Commit message style

The project uses short conventional-style prefixes (no strict spec):

- `feat(scope): …` — user-visible new behavior
- `fix(scope): …` — bug fix
- `docs: …` — documentation only
- `test: …` — tests only
- `chore: …` — tooling, deps, refactors with no behavior change
- `style(...): …` — visual / cosmetic changes

Subject line under ~72 chars. Body (if needed) explains the *why*, not the
*what*. The diff is the *what*.

## Code style

- Python 3.11+. Use `from __future__ import annotations` in modules with
  forward references.
- Type hints on public surfaces; favor `dataclass` for plain data.
- No comments that describe what well-named code already says. Comments are
  for non-obvious *why*.
- Keep new modules small and orthogonal. The repo's structure is intentional
  — `config.py` doesn't import PyQt; the overlay package owns Qt; the CLI
  layer wires them together.

## Things that need test coverage

- Every config validation rule has a test in `tests/test_config*.py`.
- Every `try_grab` failure branch has a test in `tests/test_device_grab.py`.
- Theme parsing + plumbing has tests in both `tests/test_config.py` and
  `tests/test_overlay_theme.py`.

If you're adding a new feature, follow the same pattern: a unit test for
parsing/validation in `test_config.py`, and an integration test where the
seam matters.

## Areas where help is welcome

- **Hardware coverage** — the project is tested against MX Master 3 / 4. If
  you have a different MX (Anywhere, Vertical, Ergo) and find quirks, a PR
  to `examples/config.toml` documenting the codes that fire is hugely
  helpful.
- **Wayland support** — the ring overlay is X11-only today. A layer-shell
  client or per-compositor implementation would unblock a lot of users.
- **Distro packaging** — AUR, Nix, deb, rpm. None exist yet.
- **Interactive ring management** — a CLI or small GUI to add/remove apps
  from a ring without hand-editing TOML. Design notes in the project memory.

## License

By contributing, you agree your contributions are licensed under the
project's [MIT License](LICENSE).
