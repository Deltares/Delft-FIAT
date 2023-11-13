import subprocess


def test_main_cli():
    p = subprocess.run(["fiat"], check=True, capture_output=True, text=True)
    assert p.returncode == 0
    assert p.stdout.split("\n")[0].startswith("usage:")


def test_info_cli():
    p = subprocess.run(["fiat", "info"], check=True, capture_output=True, text=True)
    assert p.returncode == 0
    assert p.stdout.split("\n")[-2].endswith("GPLv3 license.")


def test_run_cli():
    p = subprocess.run(
        ["fiat", "run", "--help"], check=True, capture_output=True, text=True
    )
    assert p.returncode == 0
    assert p.stdout.split("\n")[0].startswith("usage:")


def test_run_cli_exec(settings_toml_event):
    p = subprocess.run(
        ["fiat", "run", settings_toml_event], check=True, capture_output=True, text=True
    )
    assert p.returncode == 0
    assert p.stdout.split("\n")[-2].endswith("Geom calculation are done!")
