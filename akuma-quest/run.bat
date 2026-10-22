@echo off
rem Akuma Quest - Windows launcher
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py) || (set PY=python)
%PY% -c "import pygame" >nul 2>nul
if errorlevel 1 (
    echo Installing pygame...
    %PY% -m pip install --user pygame || %PY% -m pip install --user pygame-ce
)
rem level 13's 3D renderer needs numpy
%PY% -c "import numpy" >nul 2>nul
if errorlevel 1 (
    echo Installing numpy...
    %PY% -m pip install --user numpy
)
%PY% main.py %*
if errorlevel 1 pause
