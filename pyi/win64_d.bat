@echo off

call activate fiat_build
pyinstaller "win64_d.spec" --distpath ../bin --workpath ../bin/intermediates

pause
