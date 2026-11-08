@echo off
setlocal
title FotoWerk einrichten
cd /d "%~dp0"
echo FotoWerk - Desktop-Verknuepfung einrichten
echo.
py -3 -c "import sys; assert sys.version_info >= (3,10)" >nul 2>nul
if not errorlevel 1 goto pylauncher
python -c "import sys; assert sys.version_info >= (3,10)" >nul 2>nul
if not errorlevel 1 goto pythonlauncher
echo Python ab Version 3.10 wurde nicht gefunden.
echo Bitte verwende die Python-Installation, mit der das Fotoskript bereits lief.
echo Danach diese Datei erneut doppelklicken.
pause
exit /b 1
:pylauncher
py -3 "%~dp0einrichten.py"
goto finish
:pythonlauncher
python "%~dp0einrichten.py"
:finish
if errorlevel 1 pause
endlocal
