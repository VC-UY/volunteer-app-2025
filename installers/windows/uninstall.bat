@echo off
REM
REM Script de desinstallation du service volontaire sur Windows
REM

echo ================================================================
echo   Desinstallation du Service Volontaire - Computing Distribue
echo ================================================================
echo.

REM Verification des privileges administrateur
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERREUR] Ce script doit etre execute en tant qu'administrateur
    pause
    exit /b 1
)

set "INSTALL_DIR=C:\volunteer-app"
set "SERVICE_NAME=VolunteerService"
set "NSSM_DIR=%INSTALL_DIR%\nssm"

REM Confirmation
echo Cette action va supprimer completement le service volontaire.
set /p CONFIRM="Etes-vous sur de vouloir continuer? (O/N): "
if /i not "%CONFIRM%"=="O" (
    echo Desinstallation annulee.
    pause
    exit /b 0
)

REM Arreter le service
echo.
echo Arret du service...
sc query "%SERVICE_NAME%" >nul 2>&1
if %errorLevel% equ 0 (
    "%NSSM_DIR%\nssm.exe" stop "%SERVICE_NAME%"
    timeout /t 2 /nobreak >nul
    echo [OK] Service arrete
)

REM Supprimer le service
echo.
echo Suppression du service...
sc query "%SERVICE_NAME%" >nul 2>&1
if %errorLevel% equ 0 (
    "%NSSM_DIR%\nssm.exe" remove "%SERVICE_NAME%" confirm
    echo [OK] Service supprime
)

REM Supprimer le repertoire d'installation
echo.
set /p DELETE_DATA="Voulez-vous aussi supprimer la base de donnees et les logs? (O/N): "
if /i "%DELETE_DATA%"=="O" (
    echo Suppression du repertoire d'installation...
    rd /s /q "%INSTALL_DIR%"
    echo [OK] Repertoire d'installation supprime (avec donnees)
) else (
    echo Suppression des fichiers (donnees preservees)...
    for /d %%D in ("%INSTALL_DIR%\*") do (
        if /i not "%%~nxD"=="logs" (
            if /i not "%%~nxD"=="data" (
                rd /s /q "%%D"
            )
        )
    )
    del /q "%INSTALL_DIR%\*.py" 2>nul
    del /q "%INSTALL_DIR%\*.txt" 2>nul
    echo [OK] Fichiers supprimes (donnees preservees)
)

echo.
echo ================================================================
echo            DESINSTALLATION TERMINEE
echo ================================================================
pause
