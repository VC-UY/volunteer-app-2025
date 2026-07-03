@echo off
REM
REM Script d'installation du service volontaire sur Windows
REM Utilise NSSM (Non-Sucking Service Manager)
REM

echo ================================================================
echo    Installation du Service Volontaire - Computing Distribue
echo ================================================================
echo.

REM Verification des privileges administrateur
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERREUR] Ce script doit etre execute en tant qu'administrateur
    echo Faites un clic droit sur le fichier et selectionnez "Executer en tant qu'administrateur"
    pause
    exit /b 1
)

echo [OK] Privileges administrateur detectes

REM Variables
set "INSTALL_DIR=C:\volunteer-app"
set "SERVICE_NAME=VolunteerService"
set "NSSM_URL=https://nssm.cc/release/nssm-2.24.zip"
set "NSSM_DIR=%INSTALL_DIR%\nssm"

REM Verification de Python
echo.
echo Verification de Python...
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERREUR] Python n'est pas installe ou pas dans le PATH
    echo Telechargez Python depuis https://www.python.org/downloads/
    echo Cochez "Add Python to PATH" lors de l'installation
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [OK] Python %PYTHON_VERSION% detecte

REM Creer le repertoire d'installation
echo.
echo Creation du repertoire d'installation...
if not exist "%INSTALL_DIR%" (
    mkdir "%INSTALL_DIR%"
)
echo [OK] Repertoire %INSTALL_DIR% cree

REM Copier les fichiers de l'application
echo.
echo Copie des fichiers de l'application...
xcopy /E /I /Y "%~dp0..\..\" "%INSTALL_DIR%\" /EXCLUDE:%~dp0exclude.txt >nul
echo [OK] Fichiers copies

REM Creer l'environnement virtuel
echo.
echo Creation de l'environnement virtuel...
cd /d "%INSTALL_DIR%"
python -m venv exp-env
if %errorLevel% neq 0 (
    echo [ERREUR] Impossible de creer l'environnement virtuel
    pause
    exit /b 1
)
echo [OK] Environnement virtuel cree

REM Installer les dependances
echo.
echo Installation des dependances Python...
"%INSTALL_DIR%\exp-env\Scripts\python.exe" -m pip install --upgrade pip
"%INSTALL_DIR%\exp-env\Scripts\pip.exe" install -r "%INSTALL_DIR%\requirements.txt"
if %errorLevel% neq 0 (
    echo [ERREUR] Impossible d'installer les dependances
    pause
    exit /b 1
)
echo [OK] Dependances installees

REM Telecharger NSSM si necessaire
echo.
echo Verification de NSSM...
if not exist "%NSSM_DIR%\nssm.exe" (
    echo Telechargement de NSSM...
    mkdir "%NSSM_DIR%"
    
    REM Utiliser PowerShell pour telecharger
    powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%NSSM_URL%' -OutFile '%NSSM_DIR%\nssm.zip'}"
    
    REM Extraire
    powershell -Command "& {Expand-Archive -Path '%NSSM_DIR%\nssm.zip' -DestinationPath '%NSSM_DIR%' -Force}"
    
    REM Deplacer l'executable au bon endroit
    if exist "%NSSM_DIR%\nssm-2.24\win64\nssm.exe" (
        move "%NSSM_DIR%\nssm-2.24\win64\nssm.exe" "%NSSM_DIR%\nssm.exe"
    ) else if exist "%NSSM_DIR%\nssm-2.24\win32\nssm.exe" (
        move "%NSSM_DIR%\nssm-2.24\win32\nssm.exe" "%NSSM_DIR%\nssm.exe"
    )
    
    REM Nettoyer
    rd /s /q "%NSSM_DIR%\nssm-2.24" 2>nul
    del "%NSSM_DIR%\nssm.zip" 2>nul
    
    echo [OK] NSSM telecharge et installe
) else (
    echo [OK] NSSM deja installe
)

REM Arreter le service s'il existe
sc query "%SERVICE_NAME%" >nul 2>&1
if %errorLevel% equ 0 (
    echo.
    echo Arret du service existant...
    "%NSSM_DIR%\nssm.exe" stop "%SERVICE_NAME%"
    timeout /t 2 /nobreak >nul
)

REM Supprimer le service existant
sc query "%SERVICE_NAME%" >nul 2>&1
if %errorLevel% equ 0 (
    echo Suppression du service existant...
    "%NSSM_DIR%\nssm.exe" remove "%SERVICE_NAME%" confirm
)

REM Installer le service
echo.
echo Installation du service Windows...

REM Creer les repertoires necessaires pour les logs et donnees
if not exist "%INSTALL_DIR%\logs" mkdir "%INSTALL_DIR%\logs"
if not exist "%INSTALL_DIR%\data" mkdir "%INSTALL_DIR%\data"
if not exist "%INSTALL_DIR%\pending_requests" mkdir "%INSTALL_DIR%\pending_requests"
echo [OK] Repertoires de donnees crees

"%NSSM_DIR%\nssm.exe" install "%SERVICE_NAME%" "%INSTALL_DIR%\exp-env\Scripts\python.exe" "%INSTALL_DIR%\volunteer_daemon.py"

REM Configurer le service
"%NSSM_DIR%\nssm.exe" set "%SERVICE_NAME%" AppDirectory "%INSTALL_DIR%"
"%NSSM_DIR%\nssm.exe" set "%SERVICE_NAME%" DisplayName "Volunteer Computing Service"
"%NSSM_DIR%\nssm.exe" set "%SERVICE_NAME%" Description "Service de calcul distribue pour volontaires"
"%NSSM_DIR%\nssm.exe" set "%SERVICE_NAME%" Start SERVICE_AUTO_START

REM Configuration des logs
"%NSSM_DIR%\nssm.exe" set "%SERVICE_NAME%" AppStdout "%INSTALL_DIR%\logs\service_stdout.log"
"%NSSM_DIR%\nssm.exe" set "%SERVICE_NAME%" AppStderr "%INSTALL_DIR%\logs\service_stderr.log"
"%NSSM_DIR%\nssm.exe" set "%SERVICE_NAME%" AppRotateFiles 1
"%NSSM_DIR%\nssm.exe" set "%SERVICE_NAME%" AppRotateOnline 1
"%NSSM_DIR%\nssm.exe" set "%SERVICE_NAME%" AppRotateSeconds 86400
"%NSSM_DIR%\nssm.exe" set "%SERVICE_NAME%" AppRotateBytes 10485760

REM Configuration du redemarrage automatique
"%NSSM_DIR%\nssm.exe" set "%SERVICE_NAME%" AppExit Default Restart
"%NSSM_DIR%\nssm.exe" set "%SERVICE_NAME%" AppRestartDelay 5000

echo [OK] Service configure

REM Demarrer le service
echo.
echo Demarrage du service...
"%NSSM_DIR%\nssm.exe" start "%SERVICE_NAME%"
timeout /t 3 /nobreak >nul

REM Verifier le statut
sc query "%SERVICE_NAME%" | find "RUNNING" >nul
if %errorLevel% equ 0 (
    echo.
    echo ================================================================
    echo             INSTALLATION REUSSIE
    echo ================================================================
    echo.
    echo Le service volontaire est maintenant installe et actif!
    echo.
    echo Commandes utiles:
    echo   * Status     : sc query %SERVICE_NAME%
    echo   * Arreter    : net stop %SERVICE_NAME%
    echo   * Demarrer   : net start %SERVICE_NAME%
    echo   * Redemarrer : net stop %SERVICE_NAME% ^&^& net start %SERVICE_NAME%
    echo   * Logs       : %INSTALL_DIR%\logs\
    echo   * Config GUI : %NSSM_DIR%\nssm.exe edit %SERVICE_NAME%
    echo.
) else (
    echo.
    echo [ERREUR] Le service n'a pas demarre correctement
    echo Consultez les logs dans %INSTALL_DIR%\logs\
    pause
    exit /b 1
)

pause
