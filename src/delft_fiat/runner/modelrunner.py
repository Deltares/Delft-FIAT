from delft_fiat.models.base import BaseModel


class HazardExposureModel():

    def __init__(self, model: BaseModel):
        ...

    def read_hazard(self):
        ...

    def set_hazard(self, data):
        ...

    def read_vunerability(self):
        ...

    def calc_damage(self):
        ...

    # def write_to_file(self):
    #     ...
