import click
import sphobjinv as soi
import yaml
from pathlib import Path
from quartodoc import convert_inventory
from quartodoc.interlinks import inventory_from_url


@click.group()
def cli():
    pass


@click.command(
    short_help="Generate inventory files that the Quarto "
    "`interlink` extension can use to auto-link to other docs."
)
@click.argument("config", default="_quarto.yml")
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--fast", is_flag=True, default=False)
def interlinks(config, dry_run, fast):
    """
    Generate inventory files that the Quarto `interlink` extension can use to
    auto-link to other docs.

    The files are stored in a cache directory, which defaults to _inv.
    The Quarto extension `interlinks` will look for these files in the cache
    and add links to your docs accordingly.
    """

    # config loading ----
    cfg = yaml.safe_load(open(config))
    interlinks = cfg.get("interlinks", {})

    p_root = Path(config).parent

    if not interlinks:
        print("No interlinks field found in your quarto config. Quitting.")
        return

    # interlinks config settings ----
    cache = p_root / "_inv"
    cfg_fast = interlinks.get("fast", False)

    fast = cfg_fast or fast

    for k, v in interlinks["sources"].items():
        # don't include user's own docs (users don't need to specify their own docs in
        # the interlinks config anymore, so this is for backwards compat).
        if v["url"] == "/":
            continue

        url = v["url"] + v.get("inv", "objects.inv")

        inv = inventory_from_url(url)

        p_dst = cache / f"{k}_objects"
        p_dst.parent.mkdir(exist_ok=True, parents=True)

        if fast:
            # use sphobjinv to dump inv in txt format
            df = inv.data_file()
            soi.writebytes(p_dst.with_suffix(".txt"), df)

        else:
            # old behavior of converting to custom json format
            convert_inventory(inv, p_dst.with_suffix(".json"))


cli.add_command(interlinks)


if __name__ == "__main__":
    cli()
