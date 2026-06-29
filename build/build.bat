@echo off
setlocal EnableDelayedExpansion

REM 切换到项目根目录（无论从哪里执行）
cd /d "%~dp0.."

echo ========================================
echo   魔兽改键精灵 打包
echo ========================================
echo.

REM ---------- 版本号：只需编辑 build\version.txt 最后一行有效版本 ----------
set "VERSION_FILE=build\version.txt"
set "VERSION="
if not exist "%VERSION_FILE%" (
    echo [ERROR] Missing %VERSION_FILE%
    pause
    exit /b 1
)
for /f "usebackq eol=# delims=" %%a in ("%VERSION_FILE%") do (
    if not defined VERSION set "VERSION=%%a"
)
set "VERSION=!VERSION: =!"
if "!VERSION!"=="" (
    echo [ERROR] No version in %VERSION_FILE%
    pause
    exit /b 1
)
set "VERSION=!VERSION:v=!"
set "VERSION=!VERSION:V=!"

echo Version: !VERSION!
echo.

if exist build\work rmdir /s /q build\work
if not exist build\dist mkdir build\dist

python -m PyInstaller --clean --noconfirm --workpath build\work --distpath build\dist build\warcraft_key_remapper.spec
if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller failed.
    pause
    exit /b 1
)

set "OUT=build\dist\魔兽改键精灵-!VERSION!.exe"
if not exist "!OUT!" (
    echo [ERROR] Expected output not found: !OUT!
    pause
    exit /b 1
)

for %%A in ("!OUT!") do set "FSIZE=%%~zA"
>> build\dist\releases.log echo !DATE! !TIME!  !VERSION!  魔兽改键精灵-!VERSION!.exe  !FSIZE! bytes

echo.
echo ========================================
echo   Build finished!
echo   Output: !OUT!
echo   Log:    build\dist\releases.log
echo ========================================
echo.
pause
