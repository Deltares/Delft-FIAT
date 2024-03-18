import subprocess


def test_parse_run(mocker, cli_parser):
    parser = cli_parser
    mocker.patch("fiat.cli.main.argparse.ArgumentParser.exit")
    args = parser.parse_args(
        args=[
            "run",
        ]
    )
    assert args.command == "run"
    assert args.threads is None
    assert args.quiet == 0
    assert args.verbose == 0

    args = parser.parse_args(args=["run", "-t", "4"])
    assert args.threads == 4

    args = parser.parse_args(args=["run", "-qq", "-v"])
    assert args.quiet == 2
    assert args.verbose == 1


def test_cli_main():
    p = subprocess.run(["fiat"], check=True, capture_output=True, text=True)
    assert p.returncode == 0
    assert p.stdout.split("\n")[0].startswith("usage:")


def test_cli_info():
    p = subprocess.run(["fiat", "info"], check=True, capture_output=True, text=True)
    assert p.returncode == 0
    assert p.stdout.split("\n")[-2].endswith("MIT license.")


def test_cli_run():
    p = subprocess.run(
        ["fiat", "run", "--help"], check=True, capture_output=True, text=True
    )
    assert p.returncode == 0
    assert p.stdout.split("\n")[0].startswith("usage:")


def test_cli_run_exec(settings_files):
    p = subprocess.run(
        ["fiat", "run", settings_files["geom_event"]],
        check=True,
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0
    assert p.stdout.split("\n")[-2].endswith("Geom calculation are done!")
