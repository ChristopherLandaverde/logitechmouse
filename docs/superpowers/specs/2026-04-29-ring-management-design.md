# Interactive Ring Management CLI — Design Spec

**Date:** 2026-04-29
**Status:** Approved

## Context

Users currently manage rings, segments, actions, and profiles by hand-editing
`~/.config/logitechmouse/config.toml`. This spec describes a CLI and interactive
menu that make those edits without touching the file directly.

## Scope

Full stack: rings, ring segments, actions, and profiles (including per-profile
bindings). TOML is rewritten cleanly on each mutation (comments are not
preserved — user confirmed this is acceptable).

## Command Surface

### Ring commands

```text
logitechmouse ring list
logitechmouse ring create <name>
logitechmouse ring delete <name>
logitechmouse ring show <name>

logitechmouse ring segment add <ring> --action <action> --label <label> [--icon <icon>] [--position <n>]
logitechmouse ring segment remove <ring> <position>
logitechmouse ring segment move <ring> <from> <to>
```

### Action commands

```text
logitechmouse action list
logitechmouse action create <name> --command <cmd>
logitechmouse action delete <name>
```

### Profile commands

```text
logitechmouse profile list
logitechmouse profile create <name> --match <wm_class>
logitechmouse profile delete <name>
logitechmouse profile binding set <profile> --trigger <BTN_SIDE|...> --target <ring:NAME|action:NAME>
logitechmouse profile binding remove <profile> <trigger>
```

### Interactive menu

```text
logitechmouse config   # drops into questionary-based interactive menu
```

All mutating commands validate with the existing `validate_config()` before
writing. Invalid results (ring below 3 segments, unknown action reference, etc.)
abort with an error message.

## Architecture

### New files

| File | Purpose |
|---|---|
| `src/logitechmouse/cli/ring.py` | `ring` subcommand group + `ring segment` sub-group |
| `src/logitechmouse/cli/action.py` | `action` subcommand group |
| `src/logitechmouse/cli/profile.py` | `profile` subcommand group |
| `src/logitechmouse/cli/config_menu.py` | Interactive questionary menu |
| `src/logitechmouse/config_writer.py` | AppConfig → TOML dict → `tomli_w.dumps()` |

### Existing files touched

| File | Change |
|---|---|
| `src/logitechmouse/main.py` | Wire new subparsers; add `config` verb |
| `pyproject.toml` | Add `questionary` and `tomli-w` to dependencies |

### Mutation data flow

```text
CLI arg parse
  → load_config(path)          # existing
  → mutate AppConfig in memory
  → validate_config(config)    # existing — raises ConfigError on bad state
  → config_writer.write(path, config)   # tomli-w clean rewrite
```

### Interactive menu flow

`logitechmouse config` launches a questionary top-level menu:
pick entity (Ring / Action / Profile) → pick operation → prompted
field-by-field → same mutate→validate→write path as subcommands.

## Error Handling

- `ConfigError` from `validate_config()` is caught and printed as a
  human-readable message (no stack trace).
- Unknown names in arguments print a "did you mean?" suggestion via
  `difflib.get_close_matches`.
- Deleting a ring referenced by a binding fails with a message listing
  which bindings would break. `--force` removes those bindings automatically.
- Deleting an action referenced by a segment fails the same way.

## Testing

- Unit tests for `config_writer`: roundtrip `AppConfig → TOML dict → re-parse → same AppConfig`.
- Unit tests for each CLI verb using argparse + temp config files (no subprocess).
- Integration tests for `ring segment add/remove/move` covering 3-segment floor
  and 12-segment ceiling.
- Interactive menu tested via mock: inject answers as a list, verify resulting
  config mutation.
- No changes to existing 178 tests — new tests are additive only.

## New Dependencies

| Package | Why |
|---|---|
| `questionary` | Lightweight interactive prompts (~30 KB) |
| `tomli-w` | Clean TOML serialization (already commonly used in Python tooling) |
