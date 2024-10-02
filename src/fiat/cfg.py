"""The config interpreter of FIAT."""

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

        # Set the cache size per GDAL object
        _cache_size = self.get("global.gdal_cache")
        if _cache_size is not None:
            gdal.SetCacheMax(_cache_size * 1024**2)
        else:
            gdal.SetCacheMax(50 * 1024**2)

        # Do some checking concerning the file paths in the settings file
        for key, item in self.items():
            if (
                key.endswith(("file",)) or key.rsplit(".", 1)[1].startswith("file")
            ) and item:
                path = generic_path_check(
                    item,
                    self.path,
                )
                self[key] = path
            else:
                if isinstance(item, str):
                    self[key] = item.lower()

        # Switch the build flag off
        self._build = False

        # (Re)set the extra values
        self.update(self._extra_args)

        # Ensure the output directory is there
        self._create_model_dirs(self.get("output.path"))

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

    def _create_dir(
        self,
        root: Path | str,
        path: Path | str,
        hidden: bool = False,
    ):
        """_summary_."""
        _p = Path(path)
        if not _p.is_absolute():
            _p = Path(root, _p)
        if hidden:
            create_hidden_folder(_p)
        else:
            generic_folder_check(_p)
        return _p

    def _create_model_dirs(
        self,
        path: Path | str,
    ):
        """_summary_."""
        # Global output directory
        _p = self._create_dir(
            self.path,
            path,
        )
        self.set("output.path", _p)

        # Damage directory for grid risk calculations
        if self.get("hazard.risk") and check_config_grid(self):
            _p = self._create_dir(
                self.get("output.path"),
                "damages",
            )
            self.set("output.damages.path", _p)

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

    def set(
        self,
        key: str,
        value: Any,
    ):
        """Set a value in the configuration data.

        _extended_summary_

        Parameters
        ----------
        key : str
            _description_
        value : Any
            _description_
        """
        self[key] = value

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
        self._create_model_dirs(path)
