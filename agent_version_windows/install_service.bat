@echo off
setlocal EnableDelayedExpansion

:: Script to install System Monitoring Agent as a Windows service
:: Copies files to C:\Program Files\SystemMonitor and installs service using NSSM
:: Must be run as Administrator

echo Installing System Monitoring Agent...

:: Define source and target directories
set "SOURCE_DIR=%~dp0"
set "SOURCE_DIR=%SOURCE_DIR:~0,-1%"
set "INSTALL_DIR=C:\Program Files\SystemMonitor"
set "DATA_DIR=%INSTALL_DIR%\data"
set "LOG_DIR=C:\ProgramData\SystemMonitor"
set "LOG_FILE=%LOG_DIR%\system_monitor.log"

:: Define service parameters
set "SERVICE_NAME=SystemMonitorAgent"
set "SERVICE_DISPLAY_NAME=System Monitoring Agent"
set "SERVICE_DESCRIPTION=Monitors system performance and sends data to a central server for analysis."
set "EXE_PATH=%INSTALL_DIR%\agent.exe"
set "NSSM_PATH=%INSTALL_DIR%\nssm.exe"

:: Check if NSSM exists in source directory
if not exist "%SOURCE_DIR%\nssm.exe" (
    echo ERROR: nssm.exe not found in %SOURCE_DIR%
    echo Please download NSSM from https://nssm.cc/download and place it in the source directory.
    pause
    exit /b 1
)

:: Check if agent.exe exists in source directory
if not exist "%SOURCE_DIR%\agent.exe" (
    echo ERROR: agent.exe not found in %SOURCE_DIR%
    echo Please ensure agent.exe is in the source directory.
    pause
    exit /b 1
)

:: Create installation directory
if not exist "%INSTALL_DIR%" (
    mkdir "%INSTALL_DIR%"
    echo Created installation directory: %INSTALL_DIR%
)

:: Copy files to installation directory
echo Copying files to %INSTALL_DIR%...
copy /Y "%SOURCE_DIR%\agent.exe" "%INSTALL_DIR%\agent.exe"
copy /Y "%SOURCE_DIR%\nssm.exe" "%INSTALL_DIR%\nssm.exe"
copy /Y "%SOURCE_DIR%\install_service.bat" "%INSTALL_DIR%\install_service.bat"
copy /Y "%SOURCE_DIR%\uninstall_service.bat" "%INSTALL_DIR%\uninstall_service.bat"
if exist "%SOURCE_DIR%\README.markdown" (
    copy /Y "%SOURCE_DIR%\README.markdown" "%INSTALL_DIR%\README.markdown"
)

:: Create data directory
if not exist "%DATA_DIR%" (
    mkdir "%DATA_DIR%"
    echo Created data directory: %DATA_DIR%
)

:: Create log directory
if not exist "%LOG_DIR%" (
    mkdir "%LOG_DIR%"
    echo Created log directory: %LOG_DIR%
)

:: Grant permissions to SYSTEM
icacls "%INSTALL_DIR%" /grant SYSTEM:F /T
icacls "%LOG_DIR%" /grant SYSTEM:F /T

:: Check if service already exists
sc query %SERVICE_NAME% >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo Service %SERVICE_NAME% already exists. Stopping and removing it...
    net stop %SERVICE_NAME%
    "%NSSM_PATH%" remove %SERVICE_NAME% confirm
)

:: Install the service
echo Installing service %SERVICE_NAME%...
"%NSSM_PATH%" install %SERVICE_NAME% "%EXE_PATH%"
"%NSSM_PATH%" set %SERVICE_NAME% DisplayName "%SERVICE_DISPLAY_NAME%"
"%NSSM_PATH%" set %SERVICE_NAME% Description "%SERVICE_DESCRIPTION%"
"%NSSM_PATH%" set %SERVICE_NAME% Start SERVICE_AUTO_START
"%NSSM_PATH%" set %SERVICE_NAME% AppDirectory "%INSTALL_DIR%"
"%NSSM_PATH%" set %SERVICE_NAME% AppStdout "%LOG_FILE%"
"%NSSM_PATH%" set %SERVICE_NAME% AppStderr "%LOG_FILE%"
"%NSSM_PATH%" set %SERVICE_NAME% AppRestartDelay 5000
"%NSSM_PATH%" set %SERVICE_NAME% AppExit Default Restart

:: Start the service
echo Starting service %SERVICE_NAME%...
net start %SERVICE_NAME%
if %ERRORLEVEL% equ 0 (
    echo Service %SERVICE_NAME% installed and started successfully.
) else (
    echo ERROR: Failed to start service %SERVICE_NAME%.
    echo Check %LOG_FILE% for details.
    echo Attempting to run agent.exe manually for debugging...
    "%EXE_PATH%"
    pause
    exit /b 1
)

echo Installation complete.
echo Logs are saved to %LOG_FILE%.
echo Data is saved to %DATA_DIR%.
pause
exit /b 0