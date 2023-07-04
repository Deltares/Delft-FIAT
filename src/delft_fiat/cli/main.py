from delft_fiat.cfg import ConfigReader
from delft_fiat.log import setup_default_log
from delft_fiat.main import FIAT
from delft_fiat.version import __version__
from delft_fiat.cli.util import Path, file_path_check

import click
import sys
from multiprocessing import freeze_support

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


@click.group(
    options_metavar="<options>",
    subcommand_metavar="<commands>",
)
@click.version_option(__version__, message=f"Delft-FIAT {__version__}")
@click.pass_context
def main(ctx):
    if ctx.obj is None:
        ctx.obj = {}


_cfg = click.argument(
    "cfg",
    metavar="<cfg>",
    type=str,
    callback=file_path_check,
)

_verbose = click.option("-v", "--verbose", count=True, help="Increase verbosity")
_quiet = click.option("-q", "--quiet", count=True, help="Decrease verbosity")


@main.command(
    short_help="Information concerning Delft-FIAT",
    options_metavar="<options>",
)
@click.pass_context
def info(
    ctx,
):
    pass


@main.command(
    short_help="Run Delft-FIAT via a settings file",
    options_metavar="<options>",
)
@_cfg
@_quiet
@_verbose
@click.pass_context
def run(
    ctx,
    cfg,
    quiet,
    verbose,
):
    """
    \b
    <cfg>  Configurations file (toml) containing the settings for the FIAT model
    """

    cfg = ConfigReader(cfg)
    logger = setup_default_log(
        "fiat",
        log_level=2 + quiet - verbose,
        dst=cfg.get("output.path"),
    )
    sys.stdout.write(fiat_start_str)
    logger.info(f"Delft-Fiat version: {__version__}")
    obj = FIAT(cfg)
    obj.run()


if __name__ == "__main__":
    freeze_support()
    main()
