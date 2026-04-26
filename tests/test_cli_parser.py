from logitechmouse.main import build_parser


def test_listen_accepts_device_override():
    parser = build_parser()
    args = parser.parse_args(["listen", "--device", "/dev/input/event25"])
    assert args.command == "listen"
    assert args.device == "/dev/input/event25"


def test_listen_device_defaults_to_none():
    parser = build_parser()
    args = parser.parse_args(["listen"])
    assert args.device is None


def test_check_config_accepts_device_override():
    parser = build_parser()
    args = parser.parse_args(["check-config", "--device", "/dev/input/event25"])
    assert args.device == "/dev/input/event25"


def test_run_does_not_accept_device_override():
    """`run` fires an action one-shot and never opens a device, so --device is
    intentionally not exposed there to keep the surface honest."""
    parser = build_parser()
    args = parser.parse_args(["run", "screenshot"])
    assert args.name == "screenshot"
    assert not hasattr(args, "device")
