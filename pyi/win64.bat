@echo off

REM set the current directory of the batch file
set CUR_DIR=%~dp0

REM Execute building
pixi run -e build-win pyinstaller "%CUR_DIR%/build.spec" --distpath %CUR_DIR%../bin --workpath %CUR_DIR%../bin/intermediates

pause
