from delft_fiat.check import check_config_entries
from delft_fiat.util import (
    Path,
    create_hidden_folder,
    flatten_dict,
    generic_folder_check,
    generic_path_check,
)

import os
import tomli


class ConfigReader(dict):
    """ConfigReader class to read the settings file and store the settings in a dictionary."""

    def __init__(
        self,
        file: str,
    ):
        """Initialize the ConfigReader class.

        Parameters
        ----------
        file : str
            Configuration file.
        """

        # Check if the file exists
        if not os.path.isfile(file):
            raise FileNotFoundError(f"Settings file '{file}' not found.")

        # Check the settings file
        check_config_data(file)

        # Set the root directory
        self.filepath = Path(file)
        self.path = self.filepath.parent

        # Load the config as a simple flat dictionary and store it as self
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

        # Do some checking concerning the file paths in the settings file
        for key, item in self.items():
            # Check if the item is a file path
            if key.endswith(("file", "csv")) or key.rsplit(".", 1)[1].startswith(
                "file"
            ):
                path = generic_path_check(
                    item,
                    self.path,
                )
                self[key] = path
            else:
                # Store strings as lowercase
                if isinstance(item, str):
                    self[key] = item.lower()

    def __repr__(self):
        return f"<ConfigReader object file='{self.filepath}'>"

    def _create_output_dir(
        self,
        path: Path | str,
    ):
        """_summary_"""

        _p = Path(path)
        if not _p.is_absolute():
            _p = Path(self.path, _p)
        generic_folder_check(_p)
        self["output.path"] = _p

    def _create_temp_dir(
        self,
    ):
        """_summary_"""

        _ph = Path(self["output.path"], ".tmp")
        create_hidden_folder(_ph)
        self["output.path.tmp"] = _ph

    def get_model_type(
        self,
    ):
        """TODO: Implement this function? If so, make this an NotImplementedError."""

        if "exposure.geom_file" in self:
            return 0
        else:
            return 1

    def get_path(
        self,
        key: str,
    ):
        """Return the path of a file.

        Parameters
        ----------
        key : str
            Key of the file path.

        Returns
        -------
        Path
            Path of the file.

        Raises
        ------
        KeyError
            If the key is not found in the settings file.
         """
        # TODO: Isn't this implemented just as get_key?

        return str(self[key])

    def generate_kwargs(
        self,
        base: str,
    ):
        """Add the remaining settings to the kwargs dictionary, filtered by a base key.

        Parameters
        ----------
        base : str
            Base key.
        
        Returns
        -------
        dict
            Dictionary with the remaining settings.
        """

        # Loop over the keys and store the remaining settings in a dictionary
        keys = [item for item in list(self) if base in item]

        # Create a dictionary with the remaining settings
        kw = {key.split(".")[-1]: self[key] for key in keys}

        return kw

    def set_output_dir(
        self,
        path: Path | str,
    ):
        """_summary_"""

        _p = Path(path)
        if not _p.is_absolute():
            _p = Path(self.path, _p)

        if not any(self["output.path.tmp"].iterdir()):
            os.rmdir(self["output.path.tmp"])

        if not any(self["output.path"].iterdir()):
            os.rmdir(self["output.path"])

        self._create_output_dir(_p)
        self._create_temp_dir()
