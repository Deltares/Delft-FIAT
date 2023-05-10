import time
from pathlib import Path

from delft_fiat.fiat import FIAT

curr_path = Path(__file__)

setting_path = curr_path.parent / "tmp" / "Casus" / "settings.toml"


t1 = time.time()
fiat = FIAT(str(setting_path))
fiat.run_sim()
t2 = time.time()
print("elapsed: ", t2 - t1, "s")

# run another simulation with updated settings file
# FIAT.update_sim_config(newfile)
# FIAT.run_sim()
# FIAT.run_sim()
