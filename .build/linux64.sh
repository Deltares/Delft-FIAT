echo "Setup paths relative to this script"
#!/usr/bin/bash
# Absolute path to this script, e.g. /home/user/bin/foo.sh
SCRIPT=$(readlink -f "$0")
# Absolute path this script is in, thus /home/user/bin
SCRIPTPATH=$(dirname "$SCRIPT")

# Setting up..
echo "Locating conda.."
paths=$(which -a conda)
conda_executable=$(echo "$paths" | grep "^$HOME")

if [ -z "$conda_executable" ]
then
  # If home_conda is empty, grep with "/home/share"
  conda_executable=$(echo "$paths" | grep "^/usr/share")
fi

if [ -z "$conda_executable" ]
then
  conda_executable="/usr/share/miniconda3/condabin/conda"
fi

conda_base_dir=$(dirname $(dirname $conda_executable))
source $conda_base_dir/etc/profile.d/conda.sh

# Do the thing!
echo "Build stuff.."
conda activate fiat_build
export PROJ_LIB=/usr/share/proj
pip install -e "$SCRIPTPATH/.."
pyinstaller "$SCRIPTPATH/build.spec" --distpath $SCRIPTPATH/../bin --workpath $SCRIPTPATH/../bin/intermediates
