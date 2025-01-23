#!/usr/bin/expect -f
SCRIPT=$(readlink -f "$0")
SCRIPTPATH=$(dirname "$SCRIPT")
PROJECTPATH=$(dirname $(dirname "$SCRIPTPATH"))

# Shell hook
pixi shell-hook --manifest-path $PROJECTPATH/pyproject.toml -s bash -e build-linux > $PROJECTPATH/pixi-hook.rc
source $PROJECTPATH/pixi-hook.rc

# Define your list of packages
set packages {machow/quartodoc pandoc-ext/section-bibliographies quarto-ext/fontawesome quarto-ext/include-code-files}

# Iterate over the packages
foreach package $packages {
    spawn quarto add $package
    expect "Do you trust the authors of this extension"
    send -- "y\r"
    expect "Would you like to continue"
    send -- "y\r"
    expect "View documentation using default browser"
    send -- "n\r"
    expect eof
}
