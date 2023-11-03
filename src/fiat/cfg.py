"""The config interpreter of FIAT."""

import os
from typing import Any

import tomli
from osgeo import gdal

from fiat.check import (
    check_config_entries,
    check_config_geom,
    check_config_grid,
)
from fiat.util import (
    Path,
    create_hidden_folder,
    flatten_dict,
    generic_folder_check,
    generic_path_check,
)


class ConfigReader(dict):
    """_summary_."""

    def __init__(
        self,
        file: str,
        extra: dict = None,
    ):
        """_summary_."""
        # container for extra
        self._build = True
        self._extra = {}
        if extra is not None:
            self._extra.update(extra)

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
        self.update(self._extra)

    def __repr__(self):
        return f"<ConfigReader object file='{self.filepath}'>"

    def __reduce__(self):
        """_summary_."""
        return self.__class__, (
            self.filepath,
            self._extra,
        )

    def __setitem__(self, __key: Any, __value: Any):
        if not self._build:
            self._extra[__key] = __value
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
        """_Summary_."""
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
        """_Summary_."""
        return str(self[key])

    def generate_kwargs(
        self,
        base: str,
    ):
        """_summary_."""
        keys = [item for item in list(self) if base in item]
        kw = {key.split(".")[-1]: self[key] for key in keys}

        return kw

    def set_output_dir(
        self,
        path: Path | str,
    ):
        """_summary_."""
        _p = Path(path)
        if not _p.is_absolute():
            _p = Path(self.path, _p)

        if not any(self["output.path.tmp"].iterdir()):
            os.rmdir(self["output.path.tmp"])

        if not any(self["output.path"].iterdir()):
            os.rmdir(self["output.path"])

        self._create_output_dir(_p)
        self._create_temp_dir()
