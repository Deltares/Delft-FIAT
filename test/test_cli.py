import subprocess
from pathlib import Path


def test_parse_run(mocker, cli_parser):
    parser = cli_parser
    mocker.patch("fiat.cli.main.argparse.ArgumentParser.exit")
    args = parser.parse_args(args=["run"])
    assert args.command == "run"
    assert args.threads is None
    assert args.quiet == 0
    assert args.verbose == 0

    args = parser.parse_args(args=["run", "-t", "4"])
    assert args.threads == 4

    args = parser.parse_args(args=["run", "-qq", "-v"])
    assert args.quiet == 2
    assert args.verbose == 1

    args = parser.parse_args(
        args=["run", "-d", "output.path=other", "-d", "some_var=some_value"]
    )
    assert isinstance(args.set_entry, dict)
    assert len(args.set_entry) == 2
    assert "output.path" in args.set_entry


def test_cli_main():
    p = subprocess.run(["fiat"], check=True, capture_output=True, text=True)
    assert p.returncode == 0
    assert p.stdout.split("\n")[0].startswith("Usage: fiat")


def test_cli_info():
    p = subprocess.run(["fiat", "info"], check=True, capture_output=True, text=True)
    assert p.returncode == 0
    assert p.stdout.split("\n")[-2].endswith("MIT license.")


def test_cli_run():
    p = subprocess.run(
        ["fiat", "run", "--help"], check=True, capture_output=True, text=True
    )
    assert p.returncode == 0
    assert p.stdout.split("\n")[0].startswith("Usage: fiat run")


def test_cli_run_exec(tmp_path, geom_tmp_model):
    p = subprocess.run(
        ["fiat", "run", "-d", "output.path=output", geom_tmp_model],
        check=True,
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0
    assert p.stdout.split("\n")[-2].endswith("Geom calculation are done!")
    assert Path(tmp_path, "output", "spatial.gpkg").is_file()


def test_cli_run_profile(tmp_path, geom_tmp_model):
    p = subprocess.run(
        ["fiat", "run", "-p", "-d", "output.path=output", geom_tmp_model],
        check=True,
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0
    assert p.stdout.split("\n")[-4].endswith("Geom calculation are done!")
    assert p.stdout.split("\n")[-2].endswith("profile.txt")
    assert Path(tmp_path, "output", "spatial.gpkg").is_file()
    assert Path(tmp_path, "output", "profile.txt").is_file()
