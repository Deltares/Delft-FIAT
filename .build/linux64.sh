#!/usr/bin/bash
# Absolute path to this script, e.g. /home/user/bin/foo.sh
SCRIPT=$(readlink -f "$0")
SCRIPTPATH=$(dirname "$SCRIPT")
PROJECTPATH=$(dirname "$SCRIPTPATH")
PIXIPATH=$PROJECTPATH/.pixi

bin_var=conda
shell_var=bash

# Help message
function help_message {
  echo "Building FIAT on linux systems."
  echo "Usage: $0 [-b value] [-h | --help]"
  echo ""
  echo "Options:"
  echo $'\t'"-b"$'\t'"Binary name for python environment creation (default: $bin_var)"
  echo $'\t'"-s"$'\t'"Shell type (default: $shell_var)"
  echo $'\t'"-h,"$'\t'"Display this help message"$'\n\t'"--help"
}

# Parsing the cli input
while [[ "$1" != "" ]]; do
  case $1 in
    -b ) shift
         bin_var=$1
         ;;
    -s ) shift
         shell_var=$1
         ;;
    -h | --help ) help_message
                  exit 0
                  ;;
    * ) echo "Invalid option: $1"
        help_message
        exit 1
  esac
  shift
done

# Valid bin values
valid_values=("conda" "pixi")

# Check if value for binary is valid
is_valid=false
for value in "${valid_values[@]}"; do
  if [[ "$bin_var" == "$value" ]]; then
    is_valid=true
    break
  fi
done

if [ $is_valid == false ]; then
  echo "Not a valid python env system: $bin_var"
  exit 1
fi

# Setting up..
echo "INFO: Locating $bin_var"
paths=$(which -a $bin_var)
executable=$(echo "$paths" | grep "^$HOME")

if [ -z "$executable" ] && [ $bin_var != "conda" ]; then
  echo "Cannot find binary for: $bin_var"
  exit 1
elif [ -z "$executable" ]; then
  executable="/home/runner/miniconda3/condabin/conda"
  if [ ! -e $executable ]; then
    echo "Cannot find binary for: $bin_var"
    exit 1
  fi
fi

echo "INFO: Executable found here: $executable"

bin_dir=$(dirname $(dirname $executable))

if [ $bin_var == "conda" ]; then
  source $bin_dir/etc/profile.d/conda.sh
  conda activate fiat_build
  export PROJ_LIB=$bin_dir/envs/fiat_build/share/proj
elif [ $bin_var == "pixi" ]; then
  eval $(pixi shell-hook --manifest-path $PROJECTPATH/pixi.toml -s $shell_var -e build)
  export PROJ_LIB=$PIXIPATH/envs/build/share/proj
fi

# Do the thing!
echo "INFO: Building binary.."
pip install -e "$SCRIPTPATH/.."
pyinstaller "$SCRIPTPATH/build.spec" --distpath $SCRIPTPATH/../bin --workpath $SCRIPTPATH/../bin/intermediates
