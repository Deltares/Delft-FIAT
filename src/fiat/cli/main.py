"""Cli of FIAT."""

import argparse
import sys
from multiprocessing import freeze_support

from fiat.cfg import ConfigReader
from fiat.cli.formatter import MainHelpFormatter
from fiat.cli.util import file_path_check
from fiat.log import setup_default_log
from fiat.main import FIAT
from fiat.version import __version__

fiat_start_str = """
###############################################################

        #########    ##          ##      ##############
        ##           ##         ####         ######
        ##           ##         ####           ##
        ##           ##        ##  ##          ##
        ######       ##        ##  ##          ##
        ##           ##       ########         ##
        ##           ##      ##      ##        ##
        ##           ##     ##        ##       ##
        ##           ##    ##          ##      ##

###############################################################

                Fast Impact Assessment Tool
                \u00A9 Deltares

"""


# Info function
def info(args):
    """_summary_."""
    sys.stdout.write(fiat_start_str)
    sys.stdout.write(
        """This tool is meant for quick impact assessment.

It is open source and meant to be used and implemented as such.
Therefore it is available under the GPLv3 license.\n"""
    )


# Run FIAT function
def run(args):
    """_summary_."""
    # Setup the config reader
    cfg = file_path_check(args.config)
    cfg = ConfigReader(cfg)

    # Setup the logger
    logger = setup_default_log(
        "fiat",
        level=2 + args.quiet - args.verbose,
        dst=cfg.get("output.path"),
    )
    sys.stdout.write(fiat_start_str)
    logger.info(f"Delft-Fiat version: {__version__}")

    # Kickstart the model
    obj = FIAT(cfg)
    obj.run()


## Main entry point: parsing gets done here
def main():
    """_summary_."""
    parser = argparse.ArgumentParser(
        #    usage="%(prog)s <options> <commands>",
        formatter_class=MainHelpFormatter,
    )
    parser.add_argument(
        "-q",
        "--quiet",
        help="Decrease output verbosity",
        action="count",
        default=0,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        help="Increase output verbosity",
        action="count",
        default=0,
    )

    subparser = parser.add_subparsers(
        title="Commands",
        dest="command",
        metavar="<commands>",
    )

    info_parser = subparser.add_parser(
        name="info",
        help="Information concerning Delft-FIAT",
        formatter_class=MainHelpFormatter,
    )
    info_parser.set_defaults(func=info)

    run_parser = subparser.add_parser(
        name="run",
        help="Run Delft-FIAT via a settings file",
        formatter_class=MainHelpFormatter,
        # usage="%(prog)s subcommand1 [options] sub1_arg"
    )
    run_parser.add_argument(
        "config",
        help="Path to the settings file",
    )
    run_parser.set_defaults(func=run)
    args = parser.parse_args(args=None if sys.argv[1:] else ["--help"])
    args.func(args)


if __name__ == "__main__":
    freeze_support()
    main()
