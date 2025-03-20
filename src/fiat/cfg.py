"""The config interpreter of FIAT."""

import re
import tomllib
from pathlib import Path
from typing import Any

from osgeo import gdal

from fiat.check import (
    check_config_grid,
)
from fiat.util import (
    MANDATORY_GEOM_ENTRIES,
    MANDATORY_GRID_ENTRIES,
    MANDATORY_MODEL_ENTRIES,
    create_dir,
    flatten_dict,
    generic_path_check,
)

MODEL_ENTRIES = (
    MANDATORY_MODEL_ENTRIES
    + MANDATORY_GEOM_ENTRIES
    + MANDATORY_GRID_ENTRIES
    + ["exposure.csv.file"]  # Check for the only non mandatory file
)


class Configurations(dict):
    """Object holding model configuration information.

    Parameters
    ----------
    settings : dict
        Model configuration in dictionary format.
    """

    def __init__(
        self,
        **settings: dict,
    ):
        # Set the root directory
        root = settings.get("_root")
        if root is None:
            root = Path.cwd()
        self.path = Path(root)

        # Set filepath is applicable
        name = settings.get("_name")
        if name is None:
            self.filepath = Path("< Configurations-in-memory >")
        else:
            self.filepath = Path(self.path, name)

        # Load the config as a simple flat dictionary
        dict.__init__(self, flatten_dict(settings, "", "."))

        # Set the cache size per GDAL object
        _cache_size = self.get("global.gdal_cache")
        if _cache_size is not None:
            gdal.SetCacheMax(_cache_size * 1024**2)
        else:
            gdal.SetCacheMax(50 * 1024**2)

        # Do some checking concerning the file paths in the settings file
        for key, item in self.items():
            if not any([re.match(f"^{pattern}$", key) for pattern in MODEL_ENTRIES]):
                continue
            if (
                key.endswith(("file",)) or key.rsplit(".", 1)[1].startswith("file")
            ) and item:
                path = generic_path_check(
                    item,
                    self.path,
                )
                self[key] = path

        # Ensure absolute path for output
        self._ensure_output_path()

    def __repr__(self):
        _mem_loc = f"{id(self):#018x}".upper()
        return f"<{self.__class__.__name__} object at {_mem_loc}>"

    def __setitem__(self, __key: Any, __value: Any):
        super().__setitem__(__key, __value)  # Honestly this does nothing
        # For the time being

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
        """Initialize Configurations from a file.

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
        obj = cls(_root=path.parent, _name=path.name, **settings)
        return obj

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

        Parameters
        ----------
        key : str
            The name of the entry. Can be a joined string by periods ('.').
        value : Any
            The value corresponding to the entry.
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

    def update(self, other: dict):
        """Update the config settings object.

        Parameters
        ----------
        other : dict
            Dictionary (or Configurations) used to update current object.
        """
        dict.__init__(self, other)
        self._ensure_output_path()
