"""The config interpreter of FIAT."""

import os
from pathlib import Path
from typing import Any

import tomli
from osgeo import gdal

from fiat.check import (
    check_config_entries,
    check_config_geom,
    check_config_grid,
)
from fiat.util import (
    create_hidden_folder,
    flatten_dict,
    generic_folder_check,
    generic_path_check,
)


class ConfigReader(dict):
    """Object holding information from a settings file.

    Parameters
    ----------
    file : Path | str
        Path to the settings file.
    extra_args : dict, optional
        Extra arguments that are not in the settings file.
    """

    def __init__(
        self,
        file: Path | str,
        extra_args: dict = None,
    ):
        # container for extra
        self._build = True
        self._extra_args = {}
        if extra_args is not None:
            self._extra_args.update(extra_args)

        # Set the root directory
        self.filepath = Path(file)
        self.path = self.filepath.parent

        # Load the config as a simple flat dictionary
        f = open(file, "rb")
        dict.__init__(self, flatten_dict(tomli.load(f), "", "."))
        f.close()

        # Initial check for mandatory entries of the settings toml
        check_config_entries(
            self.keys(),
            self.filepath,
            self.path,
        )

        # Ensure the output directory is there
        self._create_output_dir(self["output.path"])

        # Create the hidden temporary folder
        self._create_temp_dir()

        # Create risk directory if needed
        if self.get("hazard.risk"):
            self._create_risk_dir()

        # Set the cache size per GDAL object
        _cache_size = self.get("global.gdal_cache")
        if _cache_size is not None:
            gdal.SetCacheMax(_cache_size * 1024**2)
        else:
            gdal.SetCacheMax(50 * 1024**2)

        # Do some checking concerning the file paths in the settings file
        for key, item in self.items():
            if key.endswith(("file", "csv")) or key.rsplit(".", 1)[1].startswith(
                "file"
            ):
                path = generic_path_check(
                    item,
                    self.path,
                )
                self[key] = path
            else:
                if isinstance(item, str):
                    self[key] = item.lower()

        self._build = False

        # (Re)set the extra values
        self.update(self._extra_args)

    def __repr__(self):
        return f"<ConfigReader object file='{self.filepath}'>"

    def __reduce__(self):
        """_summary_."""
        return self.__class__, (
            self.filepath,
            self._extra_args,
        )

    def __setitem__(self, __key: Any, __value: Any):
        if not self._build:
            self._extra_args[__key] = __value
        super().__setitem__(__key, __value)

    def _create_output_dir(
        self,
        path: Path | str,
    ):
        """_summary_."""
        _p = Path(path)
        if not _p.is_absolute():
            _p = Path(self.path, _p)
        generic_folder_check(_p)
        self["output.path"] = _p

    def _create_risk_dir(
        self,
    ):
        """_summary_."""
        _ph = Path(self["output.path"], "rp_damages")
        generic_folder_check(_ph)
        self["output.path.risk"] = _ph

    def _create_temp_dir(
        self,
    ):
        """_summary_."""
        _ph = Path(self["output.path"], ".tmp")
        create_hidden_folder(_ph)
        self["output.path.tmp"] = _ph

    def get_model_type(
        self,
    ):
        """Get the types of models.

        Inferred by the arguments in the settings file.
        When enough arguments are present for one type of model, \
the bool is set to True.

        Returns
        -------
        tuple
            Tuple containing booleans for each model.
            Order is (GeomModel, GridModel).
        """
        _models = [False, False]

        if check_config_geom(self):
            _models[0] = True
        if check_config_grid(self):
            _models[1] = True

        return _models

    def get_path(
        self,
        key: str,
    ):
        """Get a Path to a file that is present in the object.

        Parameters
        ----------
        key : str
            Key of the Path. (e.g. exposure.geom.file1)

        Returns
        -------
        Path
            A path.
        """
        return str(self[key])

    def generate_kwargs(
        self,
        base: str,
    ):
        """Generate keyword arguments.

        Based on the base string of certain arguments of the settings file.
        E.g. `hazard.settings` for all extra hazard settings.

        Parameters
        ----------
        base : str
            Base of wanted keys/ values.

        Returns
        -------
        dict
            A dictionary containing the keyword arguments.
        """
        keys = [item for item in list(self) if base in item]
        kw = {key.split(".")[-1]: self[key] for key in keys}

        return kw

    def set_output_dir(
        self,
        path: Path | str,
    ):
        """Set the output directory.

        Parameters
        ----------
        path : Path | str
            A Path to the new directory.
        """
        _p = Path(path)
        if not _p.is_absolute():
            _p = Path(self.path, _p)

        if not any(self["output.path.tmp"].iterdir()):
            os.rmdir(self["output.path.tmp"])

        if not any(self["output.path"].iterdir()):
            os.rmdir(self["output.path"])

        self._create_output_dir(_p)
        self._create_temp_dir()
