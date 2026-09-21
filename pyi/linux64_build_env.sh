echo "Setup paths relative to this script"
#!/usr/bin/bash
# Absolute path to this script, e.g. /home/user/bin/foo.sh
SCRIPT=$(readlink -f "$0")
# Absolute path this script is in, thus /home/user/bin
SCRIPTPATH=$(dirname "$SCRIPT")

# Setup conda stuff
echo "Locating conda.."
conda_executable=$(which conda)
conda_base_dir=$(dirname $(dirname $conda_executable))
source $conda_base_dir/etc/profile.d/conda.sh

# Extract the GDAL version number
echo "Get GDAL version"
version=$(gdalinfo --version | cut -d' ' -f2)
# Remove the annoying comma
version=${version%,}

# Make the yaml and create the environment
echo "Create the fiat_build env"
python $SCRIPTPATH/../make_env.py build -p 3.11.*
mamba env create -f $SCRIPTPATH/../environment.yml

# Set the appropriate env variables for GDAL
echo "Setup some important GDAL env variables"
export CPLUS_INCLUDE_PATH=/usr/include/gdal
export C_INCLUDE_PATH=/usr/include/gdal

# Install GDAL and FIAT
echo "Install GDAL and FIAT"
conda activate fiat_build
pip install --no-cache-dir gdal==$version
pip install -e $SCRIPTPATH/..
conda deactivate

# Clear the conda and pip cache
echo "Clear the python cache"
rm -rf $conda_base_dir/pkgs/*
pip cache purge
