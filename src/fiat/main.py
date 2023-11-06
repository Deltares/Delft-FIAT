"""Main entry point code-wise."""

from pathlib import Path

from fiat.cfg import ConfigReader
from fiat.log import spawn_logger
from fiat.models import GeomModel, GridModel

logger = spawn_logger("fiat.main")


class FIAT:
    """Main FIAT Object.

    Create a FIAT object from a loaded settings file.

    Parameters
    ----------
    cfg : ConfigReader
        Object containing the information from the setttings file.
    """

    def __init__(self, cfg: ConfigReader):
        self.cfg = cfg

    @classmethod
    def from_path(
        cls,
        file: Path | str,
    ):
        """Create a FIAT object from a path to settings file.

        Parameters
        ----------
        file : Path | str
            Path to the settings file (e.g. settings.toml).

        Returns
        -------
        FIAT
            A FIAT object.
        """
        file = Path(file)
        if not Path(file).is_absolute():
            file = Path(Path.cwd(), file)
        cfg = ConfigReader(file)

        return cls(cfg)

    def run(self):
        """Run FIAT with provided settings.

        Will determine which models to run based on input.
        I.e. if enough input is provioded for the GeomModel, it will be run.
        """
        _models = self.cfg.get_model_type()
        if _models[0]:
            logger.info("Setting up geom model..")
            model = GeomModel(self.cfg)
            model.run()
        if _models[1]:
            logger.info("Setting up grid model..")
            model = GridModel(self.cfg)
            model.run()
