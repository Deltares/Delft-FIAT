"""Misc. I/O functions and objects."""

from pathlib import Path

from osgeo_utils.ogrmerge import process as ogr_merge


def merge_geom_layers(
    out_fn: Path | str,
    in_fn: Path | str,
    driver: str = None,
    append: bool = True,
    overwrite: bool = False,
    single_layer: bool = False,
    out_layer_name: str = None,
):
    """Merge multiple vector layers into one file.

    Either in one layer or multiple within the new file.
    Also usefull for appending datasets.

    Essentially a python friendly function of the ogr2ogr merge functionality.

    Parameters
    ----------
    out_fn : Path | str
        The resulting file name/ path.
    in_fn : Path | str
        The input file(s).
    driver : str, optional
        The driver to be used for the resulting file.
    append : bool, optional
        Whether to append an existing file.
    overwrite : bool, optional
        Whether to overwrite the resulting dataset.
    single_layer : bool, optional
        Output in a single layer.
    out_layer_name : str, optional
        The name of the resulting single layer.
    """
    # Create pathlib.Path objects
    out_fn = Path(out_fn)
    in_fn = Path(in_fn)

    # Sort the arguments
    args = []
    if not append and driver is not None:
        args += ["-f", driver]
    if append:
        args += ["-append"]
    if overwrite:
        args += ["-overwrite_ds"]
    if single_layer:
        args += ["-single"]
    args += ["-o", str(out_fn)]
    if out_layer_name is not None:
        args += ["-nln", out_layer_name]
    if "vsimem" in str(in_fn):
        in_fn = in_fn.as_posix()
    args += [str(in_fn)]

    # Execute the merging
    ogr_merge([*args])
