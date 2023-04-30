from pathlib import Path

import tomli

from delft_fiat.util import flatten_dict, generic_path_check


class ConfigReader(dict):
    def __init__(self, toml_file):
        self._filepath: Path = Path(toml_file)
        self.parent: Path = self._filepath.parent

        with open(toml_file, "rb") as f:
            super().__init__(flatten_dict(tomli.load(f), "", "."))

        self.set_file_path()

    def set_file_path(self):
        for key, item in self.items():
            if key.endswith("file"):
                path: Path = generic_path_check(
                    item,
                    self.parent,
                )
                self[key] = path

            elif isinstance(item, str):
                self[key] = item.lower()

        for elem in self["exposure"]:
            for key, item in elem.items():
                if key.endswith("file"):
                    path: Path = generic_path_check(
                        item,
                        self.parent,
                    )
                    elem[key] = path

                elif isinstance(item, str):
                    elem[key] = item.lower()

    def __repr__(self) -> str:
        return f"<ConfigReader object file='{self._filepath}'>"

    def get_path(
        self,
        key: str,
    ) -> str:
        """_Summary_"""

        return str(self[key])
