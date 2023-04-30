import time
from typing import List

from delft_fiat.cfg_test import ConfigReader
from delft_fiat.models_refactor.exposure_models.base_model import BaseModel
from delft_fiat.models_refactor.exposure_models.model_factory import ModelFactory
from delft_fiat.models_refactor.hazard_impact import HazardImpactModel


class FIAT:
    def __init__(self, toml_file: str):
        self.config: ConfigReader  # make this a cache to store configurations. Makes it easier to cmpare
        self.hazard_impact: HazardImpactModel
        self.exposure_models: List[BaseModel | None]

        self.config = self.read_toml(toml_file)

        self.set_sim_config()

    def read_toml(self, toml_file: str) -> ConfigReader:
        return ConfigReader(toml_file=toml_file)

    def set_sim_config(self) -> None:
        self.hazard_impact = HazardImpactModel(config=self.config)

        exposure_config = self.config["exposure"]

        self.exposure_models = [
            ModelFactory.issue(
                model_type=config["type"],
                config=config,
                crs=self.config.get("global.crs"),
            )
            for config in exposure_config
        ]

    def update_sim_config(self, toml_file: str):
        # use set_sim_config
        pass

    def run_sim(self):
        for exposure_model in self.exposure_models:
            if exposure_model is not None:
                self.hazard_impact.simulate_impact(exposure_model)


if __name__ == "__main__":
    setting_file: str = "/Users/sarwanpeiter/Documents/deltaresSB/Delft-FIAT/test/tmp/Casus/settings.toml"

    t1 = time.time()
    fiat = FIAT(setting_file)
    fiat.run_sim()
    t2 = time.time()
    print("elapsed: ", t2 - t1, "s")

    # run another simulation with updated settings file
    # FIAT.update_sim_config(newfile)
    # FIAT.run_sim()
