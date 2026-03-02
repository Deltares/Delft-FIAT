"""The config interpreter of FIAT."""

import tomllib
from pathlib import Path
from typing import Any, cast

from fiat.util import OUTPUT, OUTPUT_PATH, generic_directory_check


def get_item(
    parts: list,
    current: dict,
    fallback: Any | None = None,
) -> Any:
    """Get item from a configurations."""
    num_parts = len(parts)
    for i, part in enumerate(parts):
        if isinstance(current, list):
            return [get_item(parts[i:], item, fallback) for item in current]
        if i < num_parts - 1:
            current = current.get(part, {})
        else:
            return current.get(part, fallback)


def set_item(
    parts: list,
    current: dict,
    value: Any,
):
    """Set an item in the configurations."""
    part = parts[0]
    if part not in current:
        current[part] = {}
    if len(parts) != 1:
        if not isinstance(current[part], dict):
            current[part] = {}
        set_item(parts[1:], current[part], value)
    else:
        current[part] = value


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
        self._name = settings.get("_name")
        self._path = settings.get("_root") or Path.cwd()
        self._path = Path(Path.cwd(), self._path)

        # Load the config as a simple flat dictionary
        dict.__init__(self, settings)

        # Ensure absolute path for output
        self._ensure_output_path()

    def __repr__(self):
        _mem_loc = f"{id(self):#018x}".upper()
        return f"<{self.__class__.__name__} object at {_mem_loc}>"

    def __setitem__(self, __key: Any, __value: Any):
        super().__setitem__(__key, __value)  # Honestly this does nothing
        # For the time being

    ## Private methods
    def _ensure_output_path(self):
        """Make sure the output path is present and absolute."""
        output_dir = Path(self.get(OUTPUT_PATH, OUTPUT))
        if not output_dir.is_absolute():
            output_dir = Path(self.path, output_dir)
        self.set(OUTPUT_PATH, output_dir)

    # Properties
    @property
    def filepath(self) -> Path:
        """Return the path of the config file itself."""
        if self._name is None:
            return Path("< Configurations-in-memory >")
        else:
            return Path(self.path, self._name)

    @property
    def output_dir(self):
        """Return the path to the output directory."""
        self._ensure_output_path()
        return self.get(OUTPUT_PATH)

    @property
    def path(self) -> Path:
        """Return the path of the directory in which the config file is located."""
        return self._path

    ## Class methods (read)
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
        with open(path, mode="rb") as f:
            settings = tomllib.load(f)

        # Create the object
        obj = cls(_root=path.parent, _name=path.name, **settings)
        return obj

    ## Actions methods
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
        kw = self.get(base, {})
        if not isinstance(kw, dict):
            return {}
        return kw

    def get(
        self, key: str, fallback: Any | None = None, abs_path: bool = False
    ) -> Any | None:
        """_summary_.

        Parameters
        ----------
        key : str
            The key of the entry, parts separated by a period ('.'), e.g. 'foo.bar'.
        fallback : Any | None, optional
            Fallback value if nothing is found, by default None.
        abs_path : bool
            Whether to the return the entry as an absolute path in regards to the
            location of the configurations file (`Configurations.path`).
            By default False.

        Returns
        -------
        Any | None
            The value corresponding to the entry.
        """
        parts = key.split(".")
        current = dict(self)  # reads config at first call
        value = get_item(parts, current, fallback=fallback)

        return value

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
        parts = key.split(".")
        current = cast(dict[str, Any], self)
        set_item(parts, current, value)

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
            path = self.get(OUTPUT_PATH)
        _p = generic_directory_check(
            path=path,
            root=self.path,
        )
        self.set(OUTPUT_PATH, _p)

    def update(self, other: dict):
        """Update the config settings object.

        Parameters
        ----------
        other : dict
            Dictionary (or Configurations) used to update current object.
        """
        dict.__init__(self, other)
        self._ensure_output_path()
