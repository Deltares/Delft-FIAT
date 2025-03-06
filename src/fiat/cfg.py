"""The config interpreter of FIAT."""

import tomllib
from pathlib import Path
from typing import Any

from osgeo import gdal

from fiat.check import (
    check_config_entries,
    check_config_geom,
    check_config_grid,
)
from fiat.util import (
    create_dir,
    flatten_dict,
    generic_path_check,
    get_module_attr,
)


class ConfigReader(dict):
    """Object holding model configuration information.

    Parameters
    ----------
    settings : dict,
        Model configuration in dictionary format.
    root : Path | str, optional
        Working directory of the model.
    extra_args : dict, optional
        Extra arguments that are not in the settings file.
    """

    def __init__(
        self,
        settings: dict,
        root: Path | str = None,
        extra_args: dict = None,
    ):
        # container for extra
        self._build = True
        self._extra_args = {}
        if extra_args is not None:
            self._extra_args.update(extra_args)

        # Set the root directory
        if root is None:
            root = Path.cwd()
        self.path = root

        # Load the config as a simple flat dictionary
        dict.__init__(self, flatten_dict(settings, "", "."))

        # Initial check for mandatory entries of the settings toml
        extra_entries = get_module_attr(
            f"fiat.methods.{self.get('global.type', 'flood')}", "MANDATORY_ENTRIES"
        )
        check_config_entries(
            self.keys(),
            extra_entries,
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

        # Switch the build flag off
        self._build = False

        # (Re)set the extra values
        self.update(self._extra_args)

        # Ensure absolute path for output
        self._ensure_output_path()

    def __repr__(self):
        _mem_loc = f"{id(self):#018x}".upper()
        return f"<{self.__class__.__name__} object at {_mem_loc}>"

    def __reduce__(self):
        return self.__class__, (
            self,
            self.path,
            self._extra_args,
        )

    def __setitem__(self, __key: Any, __value: Any):
        if not self._build:
            self._extra_args[__key] = __value
        super().__setitem__(__key, __value)

    def _ensure_output_path(self):
        """Make sure the output path is present and absolute."""
        output_dir = Path(self.get("output.path", "output"))
        if not output_dir.is_absolute():
            output_dir = Path(self.path, output_dir)
        self.set("output.path", output_dir)

    @classmethod
    def from_file(
        cls,
        path: Path | str,
    ):
        """Initialize ConfigReader from a file.

        Parameters
        ----------
        path : Path | str
            Path to the settings file.
        """
        path = Path(path)

        # Open the file
        with open(path, "rb") as f:
            settings = tomllib.load(f)

        # Create the object
        obj = cls(settings, root=path.parent)
        return obj

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

    def setup_output_dir(
        self,
        path: Path | str = None,
    ):
        """Set the output directory.

        Parameters
        ----------
        path : Path | str, optional
            A Path to the new directory.
        """
        if path is None:
            path = self.get("output.path")
        _p = create_dir(
            self.path,
            path,
        )
        self.set("output.path", _p)

        # Damage directory for grid risk calculations
        if self.get("hazard.risk") and check_config_grid(self):
            _p = create_dir(
                _p,
                "damages",
            )
            self.set("output.damages.path", _p)

    def update(self, other):
        """Update the config settings object."""
        dict.__init__(self, other)
        self._ensure_output_path()
