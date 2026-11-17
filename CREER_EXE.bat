@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
echo.
echo IRMS emu pro - Creation de l'executable Windows
echo Cette operation installe PyInstaller dans un environnement isole.
echo Internet est necessaire pour cette compilation, pas pour utiliser l'exe.
echo.
if not exist "irms\__main__.py" goto missing
if not exist "irms\server.py" goto missing
if not exist "irms\web\index.html" goto missing
if not exist "irms\web\app.js" goto missing
if not exist "lancer_irms.pyw" goto missing
if not exist "IRMS_emu_pro.spec" goto missing
set "IRMS_PY="
py -3.12 -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)" >nul 2>nul
if not errorlevel 1 set "IRMS_PY=py -3.12"
if defined IRMS_PY goto pythonready
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)" >nul 2>nul
if not errorlevel 1 set "IRMS_PY=py -3"
if defined IRMS_PY goto pythonready
python -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)" >nul 2>nul
if not errorlevel 1 set "IRMS_PY=python"
if not defined IRMS_PY goto nopython
:pythonready
if exist ".venv-build-irms\Scripts\python.exe" goto venvready
%IRMS_PY% -m venv .venv-build-irms
if errorlevel 1 goto failed
:venvready
set "BUILD_PY=%CD%\.venv-build-irms\Scripts\python.exe"
"%BUILD_PY%" -c "import tkinter; print('Tkinter disponible')"
if errorlevel 1 goto failed
"%BUILD_PY%" -m pip install --upgrade pip
if errorlevel 1 goto failed
"%BUILD_PY%" -m pip install -r requirements-build-irms.txt
if errorlevel 1 goto failed
"%BUILD_PY%" -m pip freeze > COMPILATION_IRMS_DEPENDANCES.txt
"%BUILD_PY%" -m PyInstaller --noconfirm --clean IRMS_emu_pro.spec
if errorlevel 1 goto failed
if not exist "dist\IRMS-emu-pro.exe" goto failed
echo Verification de l'executable et des ressources web...
powershell -NoProfile -Command "$p = Start-Process -FilePath (Join-Path (Get-Location) 'dist\IRMS-emu-pro.exe') -ArgumentList '--self-test' -Wait -PassThru; exit $p.ExitCode"
if errorlevel 1 goto failed
echo.
echo TERMINE : dist\IRMS-emu-pro.exe
echo Ce seul fichier suffit pour utiliser IRMS sans Python installe.
echo Le test automatise ne valide pas la lecture du vrai jeu ni le rendu iPad.
echo.
if defined GITHUB_ACTIONS exit /b 0
pause
exit /b 0
:missing
echo ERREUR : place les fichiers du kit a la racine du depot IRMS complet.
echo Les dossiers irms et irms\web doivent etre presents a cote de CREER_EXE.bat.
goto errorend
:nopython
echo ERREUR : Python 3.9 ou plus recent requis pour la compilation seulement.
echo Python 3.12 64 bits recommande. Installer aussi Tcl/Tk.
goto errorend
:failed
echo.
echo ECHEC DE COMPILATION OU DU TEST. Lire les messages precedents.
echo Les journaux du test sont dans %%LOCALAPPDATA%%\IRMS-emu-pro\logs.
echo Aucune validation avec le vrai jeu n'a ete realisee.
:errorend
if defined GITHUB_ACTIONS exit /b 1
pause
exit /b 1
