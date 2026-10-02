import argparse

from fiat.cli.formatter import MainHelpFormatter


def test_help_formatter_options():
    # Set a parser using the formatter
    parser = argparse.ArgumentParser(
        prog="fiat",
        add_help=False,
        formatter_class=MainHelpFormatter,
    )
    parser.add_argument("-h", "--help", action="help", help="Show help")
    parser.add_argument("-t", "--threads", metavar="<THREADS>", help="Set threads")
    parser.add_argument("config", help="Path to the settings file")

    # Format the help text
    help_text = parser.format_help()

    # Assert the output
    assert help_text.startswith("Usage: fiat <options> config\n")
    assert "Options:" in help_text
    assert "-h, --help " in help_text
    assert "-t, --threads <THREADS>" in help_text
    assert "Path to the settings file" in help_text


def test_help_formatter_commands():
    # Set a parser with subcommands
    parser = argparse.ArgumentParser(
        prog="fiat",
        add_help=False,
        formatter_class=MainHelpFormatter,
    )
    subparsers = parser.add_subparsers(
        title="commands", dest="command", metavar="<commands>"
    )
    subparsers.add_parser(
        "run",
        help="Run Delft-FIAT via a settings file",
        formatter_class=MainHelpFormatter,
    )

    # Format the help text
    help_text = parser.format_help()

    # Assert the output
    assert "Usage: fiat <options> <commands>" in help_text
    assert "Commands:" in help_text
    assert "run" in help_text
    assert "Run Delft-FIAT via a settings file" in help_text
