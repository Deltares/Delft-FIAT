from delft_fiat.check import check_config_data
from delft_fiat.util import generic_path_check, Path

import os
import tomli


class ConfigReader(dict):
    def __init__(
        self,
        file: str,
    ):
        # Set the root directory
        self._filepath = Path(file)
        self.path = self._filepath.parent

        # Load the config as a simple dictionary
        f = open(file, "rb")
        dict.__init__(self, tomli.load(f))
        f.close()

        # Do some checking concerning the file paths in the settings file
        for group in self.values():
            if not isinstance(group, dict):
                continue
            else:
                for key, item in group.items():
                    if key.endswith("file"):
                        path = generic_path_check(
                            item,
                            self.path,
                        )
                        group[key] = path
                    else:
                        if isinstance(item, str):
                            group[key] = item.lower()

    def __repr__(self):
        return f"<ConfigReader object file='{self._filepath}'>"

    def get_model_type(
        self,
    ):
        """_Summary_"""

        if ["geom_file"] in self["exposure"]:
            return 0
        else:
            return 1

    def get_path(
        self,
        gr: str,
        item: str,
    ):
        """_Summary_"""

        return str(self[gr][item])
