@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"

echo IRMS emu pro 3.0.1 - Ferme IRMS avant de compiler.

if not exist "irms\desktop.py" goto missing
if not exist "irms\web\assistant.html" goto missing

py -3.13 -c "import sys; sys.exit(0 if sys.maxsize > 2**32 else 1)" >nul 2>nul
if errorlevel 1 goto nopython

if exist ".venv-build-irms-301\Scripts\python.exe" goto ready

py -3.13 -m venv .venv-build-irms-301
if errorlevel 1 goto failed

:ready
set "PY=%CD%\.venv-build-irms-301\Scripts\python.exe"

"%PY%" -m pip install -r requirements-build-irms.txt
if errorlevel 1 goto failed

"%PY%" -m pip freeze > COMPILATION_IRMS_DEPENDANCES.txt

"%PY%" -m unittest discover -s tests -p "test_assistant_301.py" -v
if errorlevel 1 goto failed

"%PY%" -m PyInstaller --noconfirm --clean --distpath . IRMS_emu_pro.spec
if errorlevel 1 goto failed

if not exist "IRMS-emu-pro.exe" goto failed

powershell -NoProfile -Command "$p=Start-Process -FilePath (Join-Path (Get-Location) 'IRMS-emu-pro.exe') -ArgumentList '--self-test' -Wait -PassThru; exit $p.ExitCode"
if errorlevel 1 goto failed

set QT_QPA_PLATFORM=offscreen
powershell -NoProfile -Command "$p=Start-Process -FilePath (Join-Path (Get-Location) 'IRMS-emu-pro.exe') -ArgumentList '--ui-smoke-test' -Wait -PassThru; exit $p.ExitCode"
if errorlevel 1 goto failed
set QT_QPA_PLATFORM=

echo TERMINE : IRMS-emu-pro.exe a la racine.
echo Validation Windows reelle, jeu, reseau et iPad encore necessaire.

if defined GITHUB_ACTIONS exit /b 0
pause
exit /b 0

:missing
echo Projet incomplet. Lis LIRE_MOI_301.md avant de compiler.
goto errorend

:nopython
echo Python 3.13 64 bits est introuvable via le lanceur py.
goto errorend

:failed
echo ECHEC. Un exe eventuellement present n'est pas valide par cet essai.
echo Journaux : %%LOCALAPPDATA%%\IRMS-emu-pro\logs

:errorend
if defined GITHUB_ACTIONS exit /b 1
pause
exit /b 1