@echo off
setlocal
cd /d "%~dp0"

set "DIST_DIR=dist"
if not "%~1"=="" set "DIST_DIR=%~1"

echo Building QTPdfPro into "%DIST_DIR%"...
python -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onedir ^
    --windowed ^
    --name QTPdfPro ^
    --distpath "%DIST_DIR%" ^
    --icon qtpdfpro\ui\assets\app_icon.ico ^
    --add-data "qtpdfpro\ui\assets\app_icon.ico;qtpdfpro\ui\assets" ^
    --exclude-module tkinter ^
    --exclude-module matplotlib ^
    --exclude-module scipy ^
    run_qtpdfpro.py

if errorlevel 1 (
    echo Build failed!
    exit /b 1
)

if exist "%DIST_DIR%\QTPdfPro\_internal\opengl32sw.dll" (
    del /q "%DIST_DIR%\QTPdfPro\_internal\opengl32sw.dll"
)

copy /y LICENSE "%DIST_DIR%\QTPdfPro\LICENSE" >nul
copy /y THIRD_PARTY_NOTICES.md "%DIST_DIR%\QTPdfPro\THIRD_PARTY_NOTICES.md" >nul

echo Build succeeded: "%DIST_DIR%\QTPdfPro\QTPdfPro.exe"
