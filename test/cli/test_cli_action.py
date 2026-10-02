import argparse

import pytest

from fiat.cli.action import KeyValueAction, parse_cli_value


def test_parse_cli_value_int():
    # Integer strings are coerced to int
    assert parse_cli_value("1") == 1
    assert parse_cli_value("-2") == -2
    assert parse_cli_value("1000") == 1000


def test_parse_cli_value_float():
    # Float strings are coerced to float
    assert parse_cli_value("1.25") == 1.25


def test_parse_cli_value_string():
    # Non numeric values stay a (stripped) string
    assert parse_cli_value(" text ") == "text"
    assert parse_cli_value("true") == "true"  # Not parsed as a bool
    assert parse_cli_value("False") == "False"


def test_parse_cli_value_list():
    # Bracketed values become a list with coerced elements
    assert parse_cli_value("[1, 2,3]") == [1, 2, 3]
    assert parse_cli_value("[1.0, 2,3]") == [1.0, 2.0, 3.0]
    assert parse_cli_value("[a, b,c]") == ["a", "b", "c"]


def test_key_value_action():
    # Set a parser using the action
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--set-entry", action=KeyValueAction)

    # Repeated flags collect into a dict with coerced values
    args = parser.parse_args(
        [
            "-d",
            "model.threads=4",
            "--set-entry",
            "model.type=grid",
            "-d",
            "hazard.return_periods=[1, 2.5]",
        ]  # fmt: skip
    )

    # Assert the output
    assert args.set_entry == {
        "model.threads": 4,
        "model.type": "grid",
        "hazard.return_periods": [1.0, 2.5],
    }


def test_key_value_action_error(capsys):
    # Set a parser using the action
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--set-entry", action=KeyValueAction)

    # A value without a '=' separator is rejected
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["-d", "not-a-pair"])

    # Assert the output
    assert exc.value.code == 2
    assert "Should be KEY=VALUE" in capsys.readouterr().err
