@echo off
setlocal
cd /d "%~dp0"
title IRMS emu pro - PC + iPad

rem --- Recherche de Python (lanceur "py" d'abord, puis "python") ---
set "PY="
py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if defined PY goto check
python -c "import sys" >nul 2>nul
if not errorlevel 1 set "PY=python"
if defined PY goto check
goto nopython

:check
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"
if errorlevel 1 goto oldpython

echo.
echo  Demarrage d'IRMS emu pro avec affichage sur iPad (reseau local, lecture seule)...
echo  Laisse cette fenetre ouverte pendant que tu roules. Pour arreter : ferme-la.
echo.
%PY% -m irms run --lan %*
if errorlevel 1 (
  echo.
  echo  IRMS s'est arrete avec une erreur. Lis le message ci-dessus,
  echo  puis consulte la partie "En cas de probleme" de INSTALLATION_WINDOWS.txt.
  echo.
  pause
)
goto end

:nopython
echo.
echo  Python n'est pas installe sur ce PC (ou n'est pas dans le PATH).
echo.
echo  1. Ouvre https://www.python.org/downloads/windows/
echo  2. Telecharge puis lance l'installateur Windows 64 bits.
echo  3. Coche la case "Add python.exe to PATH" avant de cliquer sur Install.
echo  4. Relance ce fichier.
echo.
echo  Le detail est dans INSTALLATION_WINDOWS.txt.
echo.
pause
goto end

:oldpython
echo.
echo  La version de Python installee est trop ancienne : il faut Python 3.9 ou plus recent.
echo  Installe la version actuelle depuis https://www.python.org/downloads/windows/
echo.
pause
goto end

:end
endlocal
