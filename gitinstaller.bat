@echo off
setlocal

set "BASE_DIR=%~dp0"
if "%BASE_DIR:~-1%"=="\" set "BASE_DIR=%BASE_DIR:~0,-1%"
set "NODE_DIR=%BASE_DIR%\.gitinstaller\node"
set "NODE_EXE=%NODE_DIR%\node.exe"

rem -------- Locate Node.js --------
if exist "%NODE_EXE%" (
    rem Use portable Node.js — prepend its dir to PATH so npm.cmd / npx.cmd are found
    set "PATH=%NODE_DIR%;%PATH%"
    set "NODE=%NODE_EXE%"
    goto :run
)

rem Fall back to system Node.js
where node >nul 2>&1
if %errorlevel% == 0 (
    set "NODE=node"
    goto :run
)

echo.
echo [ERROR] Node.js is not installed and no portable Node.js was found.
echo         Please run setup.bat first to install Node.js automatically.
echo.
exit /b 1

:run
"%NODE%" "%BASE_DIR%\index.js" %*
endlocal
