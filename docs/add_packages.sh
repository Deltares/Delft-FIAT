#!/usr/bin/expect -f

# Define your list of packages
set packages {quarto-ext/include-code-files quarto-ext/fontawesome}

# Iterate over the packages
foreach package $packages {
    spawn quarto add $package
    expect "Do you trust the authors of this extension"
    send -- "y\r"
    expect "Would you like to continue"
    send -- "y\r"
    expect eof
}
