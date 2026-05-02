# Mouse Service Reliability RCA

## Summary

The mouse bindings did not stay active after shutdown or reset because the
systemd user service exited when the Logitech input device was not visible at
startup. The service was enabled, but it treated temporary device absence as a
fatal error.

## Root Cause

At login or boot, Linux may expose Bluetooth/HID input devices after the user
service starts. The old `logitechmouse.service` command ran one device discovery
attempt:

```text
logitechmouse --config ~/.config/logitechmouse/config.toml listen
```

When no matching device was present yet, the listener exited with:

```text
no input device matched auto-discovery
```

Systemd restarted it a few times, then stopped retrying after its start-limit
window was exhausted. Once that happened, reconnecting the mouse later did not
restart the listener.

## Fix

The listener now supports persistent device discovery:

```text
logitechmouse --config ~/.config/logitechmouse/config.toml listen --retry-device --retry-interval 5
```

With `--retry-device`, a missing mouse is no longer fatal. The service process
stays alive and retries discovery every five seconds until the device appears.

The service installer now writes this retry-enabled command by default.

## Persistence Requirements

The user service must remain enabled:

```bash
systemctl --user enable logitechmouse.service
systemctl --user status logitechmouse.service
```

The user must have permission to read input devices. On this machine,
`chrisland` is already in the `input` group.

The `uinput` kernel module should be loaded persistently so the app can create
its virtual device and swallow bound buttons cleanly:

```bash
sudo modprobe uinput
printf 'uinput\n' | sudo tee /etc/modules-load.d/uinput.conf
printf 'KERNEL=="uinput", GROUP="input", MODE="0660"\n' | sudo tee /etc/udev/rules.d/60-logitechmouse-uinput.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
systemctl --user restart logitechmouse.service
```

## Verification

Run:

```bash
logitechmouse --config ~/.config/logitechmouse/config.toml check-config
systemctl --user status logitechmouse.service
```

Expected results:

- Config validation reports the configured actions and bindings.
- `logitechmouse.service` is `active (running)`.
- The service command includes `listen --retry-device --retry-interval 5`.
