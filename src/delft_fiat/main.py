from delft_fiat.cfg import ConfigReader
from delft_fiat.log import Log
from delft_fiat.models import GeomModel, GridModel

from pathlib import Path


class FIAT:
    """FIAT class."""

    def __init__(self, cfg: ConfigReader):
        """Initialize the FIAT class.

        Parameters
        ----------
        cfg : ConfigReader
            _description_
        """

        self.cfg = cfg

    @classmethod
    def from_path(
        cls,
        file: str,
    ):
        """Get a FIAT object from a settings file.

        Parameters
        ----------
        file : str
            Path to the settings file.

        Returns
        -------
        FIAT
            FIAT object.
        """

        # Check if the file exists
        if not Path(file).is_file():
            raise FileNotFoundError(f"Settings file '{file}' not found.")

        # Initialize the path
        file = Path(file)

        # Check if the path is absolute or relative
        if not Path(file).is_absolute(): 
            file = Path(Path.cwd(), file)

        # Read and parse the settings file
        cfg = ConfigReader(file)

        return cls(cfg)

    def run(self):
        """Run the main program. Up to now, only the GeomModel is implemented. 
        Later, the GridModel and other models will be added. This wil then be 
        transformed into the model factory pattern.
        
        Returns
        -------
        None.
        
        """

        model = GeomModel(self.cfg)
        model.run()


if __name__ == "__main__":
    pass
