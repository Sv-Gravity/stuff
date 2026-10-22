@echo off
rem Builds a standalone AkumaQuest.exe in the dist folder (no Python needed to play it).
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py) || (set PY=python)
%PY% -m pip install --user pygame numpy pyinstaller || %PY% -m pip install --user pygame-ce numpy pyinstaller
%PY% -m PyInstaller --noconfirm --onefile --windowed --name AkumaQuest --collect-submodules akuma --add-data "akuma\assets;akuma\assets" main.py
echo.
echo Done: dist\AkumaQuest.exe
pause
