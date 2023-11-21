# Quick setup guide

## How setup/ install fiat
A brief summary will be put here for:
- Just installing it for use
- Development install
- Freeze it as an application

For each and every one of these installs we solely look at the
commandline user interface or batch/ bash scripts.

N.b. this guide assumes one has conda/ mamba/ micro3 and git installed
(Who doesnt..)

## Just install for use
For just using fiat, either create a new environment:
```bat
# Create an environment
conda create -n fiat python=3.11.*
# Activate it
conda activate fiat

#Install the good stuff
pip install git+https://github.com/Deltares/Delft-FIAT.git
```

or install FIAT directly in an existing environment
```bat
pip install git+https://github.com/Deltares/Delft-FIAT.git
```

## Development install
This is for those who wish to contribute at this early stage
First, clone the repository
```bat
# Go to some directory where your repos are located
cd ~/{your path}
# Clone FIAT
git clone https://github.com/Deltares/Delft-FIAT.git fiat
```

Now let's do the python stuff.
Make sure you either have tomli or tomllib (build-in with py 3.11)
in your base enviroment
```bat
# Go into the FIAT repository directory
cd ~/{your path}/fiat

# Create the environment file
python make_env.py dev

# Create conda env
conda env create -f environment.yml

# Activate and install FIAT
conda activate fiat_dev
pip install -e .
```

There ya go.

## Freeze FIAT as an application
This more or less assumes the one went for a development install
If not: do the development install for FIAT first

Create a yaml for a seperate environment
```bat
python make_env.py build
```

Again, create the environment with conda
```bat
conda env create -f environment.yml
```

This time FIAT will be automatically installed with the environment
Now, go to the .build/core directory
```bat
cd ./.build/core
```

And just execute the pybuild.bat script
```bat
pybuild.bat
```

That's it.
FIAT will be located in the {root}/bin/core/Release folder.
