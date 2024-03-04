import subprocess


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
