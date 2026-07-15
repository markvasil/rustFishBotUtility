@echo off
setlocal

echo === Rust Utility Overlay — сборка .exe ===
echo.

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller>=6.0

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

python -m PyInstaller rust_utility.spec --noconfirm

if errorlevel 1 (
    echo.
    echo Сборка не удалась.
    exit /b 1
)

echo.
echo Копирование runtime (Node + Rust+ CLI)...
if exist dist\runtime rmdir /s /q dist\runtime
xcopy /E /I /Y /Q runtime dist\runtime >nul

echo.
echo Готово:
echo   dist\RustUtilityOverlay.exe
echo   dist\runtime\
echo.
echo Для друзей: заархивируйте папку dist\ целиком.
echo Данные сессии сохраняются в %%APPDATA%%\RustUtilityOverlay\
echo.
pause
