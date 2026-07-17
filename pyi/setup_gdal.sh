# A small script to unsure a reasonably recent gdal on the linux machine
sudo add-apt-repository ppa:ubuntugis/ubuntugis-unstable -y
sudo apt update
sudo apt -y install gdal-bin
sudo apt-get -y install libgdal-dev
