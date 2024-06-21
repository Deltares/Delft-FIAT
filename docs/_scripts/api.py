"""Creating the API Reference for Delft-FIAT with the help of quartodoc."""
import argparse
import yaml
import sys
from pathlib import Path

from quartodoc import (
    Builder,
    blueprint,
    collect,
)
from quartodoc.layout import DocAttribute, Page, Section

from fiat.cli.util import file_path_check
from fiat.cli.formatter import MainHelpFormatter


def parse_content(
    cont: Page,
    builder: Builder,
    rel_dir: Path | str,
    members: list = None,
    members_paths: list = None,
    parent: object = None,
    module: object = None,
):
    """_summary_

    Parameters
    ----------
    cont : Page
        _description_
    parent : object, optional
        _description_, by default None
    """
    try:
        pages, _ = collect(
            cont.contents[0].members,
            base_dir=builder.dir,
        )
        for _p in pages:
            parse_content(
                _p,
                builder,
                rel_dir=rel_dir,
                members=members,
                members_paths=members_paths,
                parent=cont,
            )

    except Exception:
        pass

    finally:
        if parent is not None:
            cont.path = f"{parent.obj.name}/{cont.obj.name}"
            if cont.obj.is_attribute:
                cont = DocAttribute.from_griffe(cont.obj.name, cont.obj)
            else:
                builder.write_doc_pages([cont], filter="*")
                members_paths.append(f"{rel_dir}/{parent.obj.name}/{cont.obj.name}.qmd")
            members.append(cont)
        else:
            if members:
                cont.contents[0].members = members
                content = {
                    "section": cont.path,
                    "href": f"{rel_dir}/{cont.path}.qmd",
                    "contents": members_paths,
                }
            else:
                content = f"{rel_dir}/{cont.path}.qmd"
                if module:
                    cont.path = f"{module.name}/{cont.obj.name}"
                    content = f"{rel_dir}/{cont.path}.qmd"

            builder.write_doc_pages([cont], filter="*")
            return content


def parse_section(
    sect: Section,
    builder: Builder,
    rel_dir: Path | str,
):
    """_summary_

    Parameters
    ----------
    sect : Section
        _description_
    """
    sub = False
    title = sect.title
    module = None
    if sect.subtitle is not None:
        sub = True
        title = sect.subtitle
    section_content = []
    for cont in sect.contents:
        module = None
        if sub:
            module = cont.obj.parent
        content = parse_content(
            cont,
            builder,
            rel_dir,
            members=[],
            members_paths=[],
            module=module,
        )
        section_content.append(content)
    if sect.subtitle is not None:
        sub = True

    return section_content, sub, title


def parse_tree_section(
    section_title: str,
    section_content: list,
    content: list,
    sub: bool = False,
):
    """_summary_

    Parameters
    ----------
    section_title : str
        _description_
    section_content : list
        _description_
    tree : dict
        _description_
    sub : bool, optional
        _description_, by default False
    """
    if sub:
        section = {
            "section": section_title,
            "contents": section_content,
        }
        prev = content[-1]
        prev["contents"].append(section)
        content[-1] = prev
    else:
        section = {
            "contents": section_content,
            "section": section_title,
        }
        content.append(section)


def create_tree(
    file: Path | str,
    filter: str = "*",
):
    """_summary_

    Parameters
    ----------
    file : Path | str
        _description_
    """
    # set some meta info
    p = Path(file).parent

    # Setup the builder and global blueprint
    b = Builder.from_quarto_config(file)
    bp = blueprint(b.layout, dynamic=b.dynamic, parser=b.parser)

    # Define basic structure
    tree = {}
    content = []

    # Set the vars relative to this file
    rel_dir = b.dir
    b.dir = Path(p, rel_dir).as_posix()

    # Loop trough sections
    for sect in bp.sections:
        section_content, sub, title = parse_section(
            sect,
            b,
            rel_dir,
        )

        parse_tree_section(
            title,
            section_content,
            content,
            sub,
        )

    tree = {
        "website": {
            "sidebar": {
                "collapse-level": 2,
                "contents": {
                    "section": "API Reference",
                    "href": "api/index.qmd",
                    "contents": content,
                },
                "id": rel_dir,
            }
        }
    }

    # Write the sidebar to the drive
    with open(Path(p, rel_dir, "_sidebar.yml"), "w") as _w:
        yaml.dump(tree, _w, sort_keys=False)

    # Also write the index to the hard drive
    b.write_index(bp)

    # Return the directory
    return Path(p, rel_dir)


def run(args):
    """Dummy run method."""
    yml = file_path_check(args.config)
    p = create_tree(yml.as_posix())
    sys.stdout.write(f"Written api docs to {p.as_posix()}\n")


def args_parser():
    """A simple parser."""
    parser = argparse.ArgumentParser(
        #    usage="%(prog)s <options> <commands>",
        add_help=False,
        formatter_class=MainHelpFormatter,
    )
    # Simple help option
    parser.add_argument(
        "-h",
        "--help",
        action="help",
        default=argparse.SUPPRESS,
        help="Show this help message and exit",
    )

    # Add the quarto config file
    parser.add_argument(
        "config",
        help="Path to the _quarto.yml settings file.",
    )
    # Set the default behaviour
    parser.set_defaults(func=run)

    # Return the parser
    return parser


def main(argv=sys.argv[1:]):
    parser = args_parser()
    args = parser.parse_args(args=None if argv else ["--help"])
    args.func(args)


if __name__ == "__main__":
    main()
