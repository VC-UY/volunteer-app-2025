@echo off
setlocal EnableDelayedExpansion

:: Script pour désinstaller le service System Monitoring Agent
:: Doit être exécuté en tant qu'administrateur

echo Désinstallation de l'Agent de Surveillance Système...

:: Définir les paramètres du service et des répertoires
set "SERVICE_NAME=SystemMonitorAgent"
set "INSTALL_DIR=C:\Program Files\SystemMonitor"
set "NSSM_PATH=%INSTALL_DIR%\nssm.exe"
set "DATA_DIR=%INSTALL_DIR%\data"
set "LOG_DIR=C:\ProgramData\SystemMonitor"
set "MACHINE_ID_FILE=%INSTALL_DIR%\machine_id.txt"

:: Vérifier si NSSM existe
if not exist "%NSSM_PATH%" (
    echo ERREUR : nssm.exe introuvable dans %INSTALL_DIR%
    echo Poursuite de la désinstallation en supposant que le service est installé.
)

:: Vérifier si le service existe
sc query %SERVICE_NAME% >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Service %SERVICE_NAME% introuvable. Vérification des répertoires pour le nettoyage...
) else (
    :: Arrêter le service
    echo Arrêt du service %SERVICE_NAME%...
    net stop %SERVICE_NAME%

    :: Supprimer le service
    echo Suppression du service %SERVICE_NAME%...
    "%NSSM_PATH%" remove %SERVICE_NAME% confirm
    if %ERRORLEVEL% equ 0 (
        echo Service %SERVICE_NAME% supprimé avec succès.
    ) else (
        echo ERREUR : Échec de la suppression du service %SERVICE_NAME%.
        pause
        exit /b 1
    )
)

:: Demander la suppression des répertoires et fichiers
set /p DELETE_DATA=Supprimer les répertoires d'installation et de données (C:\Program Files\SystemMonitor, C:\ProgramData\SystemMonitor) et machine_id.txt ? (o/n) : 
if /i "%DELETE_DATA%"=="o" (
    if exist "%INSTALL_DIR%" (
        rmdir /s /q "%INSTALL_DIR%"
        echo Répertoire d'installation supprimé : %INSTALL_DIR%
    )
    if exist "%LOG_DIR%" (
        rmdir /s /q "%LOG_DIR%"
        echo Répertoire de journaux supprimé : %LOG_DIR%
    )
    if exist "%MACHINE_ID_FILE%" (
        del /f "%MACHINE_ID_FILE%"
        echo Fichier machine_id.txt supprimé.
    )
) else (
    echo Répertoires d'installation et de données préservés.
)

echo Désinstallation terminée.
pause
exit /b 0