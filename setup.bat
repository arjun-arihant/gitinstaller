@echo off
setlocal enabledelayedexpansion

echo ============================================
echo  GitInstaller Setup
echo ============================================
echo.

set "BASE_DIR=%~dp0"
set "GI_DIR=%BASE_DIR%.gitinstaller"
set "NODE_DIR=%GI_DIR%\node"
set "NODE_EXE=%NODE_DIR%\node.exe"
set "NODE_VERSION=22.14.0"

rem -------- Check for portable Node.js already installed --------
if exist "%NODE_EXE%" (
    echo [OK] Portable Node.js already present at:
    echo      %NODE_EXE%
    goto :npm_install
)

rem -------- Check for system Node.js --------
where node >nul 2>&1
if %errorlevel% == 0 (
    echo [OK] System Node.js found in PATH. Skipping download.
    set "NODE_EXE=node"
    goto :npm_install
)

rem -------- Download portable Node.js --------
echo [*] Node.js not found. Downloading portable Node.js v%NODE_VERSION%...
echo.

if not exist "%GI_DIR%" mkdir "%GI_DIR%"
if not exist "%NODE_DIR%" mkdir "%NODE_DIR%"

set "NODE_ZIP_NAME=node-v%NODE_VERSION%-win-x64.zip"
set "NODE_URL=https://nodejs.org/dist/v%NODE_VERSION%/%NODE_ZIP_NAME%"
set "ZIP_FILE=%GI_DIR%\%NODE_ZIP_NAME%"

echo     Downloading from: %NODE_URL%
echo     To: %ZIP_FILE%
echo.

powershell -NoProfile -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%NODE_URL%' -OutFile '%ZIP_FILE%' -UseBasicParsing }"
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to download Node.js.
    echo         Check your internet connection and try again.
    exit /b 1
)

echo [*] Extracting Node.js...
set "TEMP_EXTRACT=%GI_DIR%\node_temp"
if exist "%TEMP_EXTRACT%" rmdir /s /q "%TEMP_EXTRACT%"

powershell -NoProfile -Command "Expand-Archive -Path '%ZIP_FILE%' -DestinationPath '%TEMP_EXTRACT%' -Force"
if %errorlevel% neq 0 (
    echo [ERROR] Failed to extract Node.js archive.
    exit /b 1
)

rem Move contents from node-v{version}-win-x64/ into .gitinstaller/node/
for /d %%D in ("%TEMP_EXTRACT%\node-v*") do (
    xcopy "%%D\*" "%NODE_DIR%\" /E /Y /Q >nul
)

rmdir /s /q "%TEMP_EXTRACT%"
del "%ZIP_FILE%"

if not exist "%NODE_EXE%" (
    echo [ERROR] Node.js extraction succeeded but node.exe not found at:
    echo         %NODE_EXE%
    exit /b 1
)

echo [OK] Portable Node.js installed to: %NODE_DIR%
echo.

rem -------- Install npm dependencies --------
:npm_install
echo [*] Installing npm dependencies (node_modules)...
echo.

rem Prefer portable node; it has npm bundled in the same directory
if exist "%NODE_EXE%" if not "%NODE_EXE%"=="node" (
    rem Use the portable node + npm from the portable install
    set "PATH=%NODE_DIR%;%PATH%"
)

call npm install --prefix "%BASE_DIR%"
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] npm install failed. Check the output above.
    exit /b 1
)

echo.
echo ============================================
echo  Setup complete!
echo ============================================
echo.
echo  Usage:
echo    gitinstaller.bat install https://github.com/owner/repo
echo.
echo  Make sure you have a .env file with your OpenRouter API key.
echo  (Copy .env.example to .env and fill in OPENROUTER_API_KEY)
echo.
endlocal
