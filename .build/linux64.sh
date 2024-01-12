echo "Setup paths relative to this script"
#!/usr/bin/bash
# Absolute path to this script, e.g. /home/user/bin/foo.sh
SCRIPT=$(readlink -f "$0")
# Absolute path this script is in, thus /home/user/bin
SCRIPTPATH=$(dirname "$SCRIPT")

# Setting up..
echo "Locating conda.."
conda_executable=$(which conda)
conda_base_dir=$(dirname $(dirname $conda_executable))
conda init
echo "Reload .bashrc.."
source /home/runner/.bashrc

# Do the thing!
echo "Build stuff.."
conda activate fiat_build
export PROJ_LIB=/usr/share/proj
pyinstaller "$SCRIPTPATH/build.spec" --distpath $SCRIPTPATH/../bin --workpath $SCRIPTPATH/../bin/intermediates
