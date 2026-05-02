from logitechmouse.main import build_parser


def test_parser_ring_list():
    args = build_parser().parse_args(["ring", "list"])
    assert args.command == "ring" and args.ring_command == "list"


def test_parser_action_list():
    args = build_parser().parse_args(["action", "list"])
    assert args.command == "action" and args.action_command == "list"


def test_parser_profile_list():
    args = build_parser().parse_args(["profile", "list"])
    assert args.command == "profile" and args.profile_command == "list"


def test_parser_config():
    args = build_parser().parse_args(["config"])
    assert args.command == "config"


def test_listen_accepts_device_override():
    parser = build_parser()
    args = parser.parse_args(["listen", "--device", "/dev/input/event25"])
    assert args.command == "listen"
    assert args.device == "/dev/input/event25"


def test_listen_device_defaults_to_none():
    parser = build_parser()
    args = parser.parse_args(["listen"])
    assert args.device is None
    assert args.retry_device is False
    assert args.retry_interval == 5.0


def test_listen_accepts_device_retry_options():
    parser = build_parser()
    args = parser.parse_args(
        ["listen", "--retry-device", "--retry-interval", "1.5"]
    )
    assert args.retry_device is True
    assert args.retry_interval == 1.5


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
