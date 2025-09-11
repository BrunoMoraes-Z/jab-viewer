@echo off
setlocal enabledelayedexpansion

REM JABViewer build script (one-file exe via PyInstaller)
REM Usage: double-click or run from terminal at repo root

cd /d "%~dp0"

echo [1/4] Cleaning previous build artifacts...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist JABViewer.spec del /q JABViewer.spec

echo [2/4] Building one-file, windowed executable...
set NAME=JABViewer
set ENTRY=jab_viewer\app.py

REM Collect extra submodules just in case (safe no-ops if not needed)
uv run PyInstaller ^
  --noconfirm --clean --onefile --windowed ^
  --name %NAME% ^
  --collect-submodules JABWrapper ^
  --collect-submodules win32com ^
  --collect-submodules win32 ^
  --add-data "jab_viewer\locales;jab_viewer\locales" ^
  "%ENTRY%"

set ERR=%ERRORLEVEL%
if not "%ERR%"=="0" (
  echo Build failed with exit code %ERR%.
  exit /b %ERR%
)

echo [3/4] Done. Verifying output...
if not exist dist\%NAME%.exe (
  echo ERROR: dist\%NAME%.exe not found.
  exit /b 1
)

echo [4/4] Success!
echo Output: %CD%\dist\%NAME%.exe
echo.
echo Note:
echo - Set RC_JAVA_ACCESS_BRIDGE_DLL to the path of windowsaccessbridge -64.dll
echo.
endlocal
