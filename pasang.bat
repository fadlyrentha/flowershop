@echo off
setlocal
cd /d "%~dp0"
title Pemasang Rasty Florist

python --version >nul 2>nul
if not errorlevel 1 (
    python "installer\install.py" %*
    goto selesai
)

py -3 --version >nul 2>nul
if not errorlevel 1 (
    py -3 "installer\install.py" %*
    goto selesai
)

echo.
echo Python tidak ditemukan di komputer ini.
echo.
echo   1. Unduh Python dari https://www.python.org/downloads/
echo   2. Saat memasang, centang "Add python.exe to PATH".
echo   3. Jalankan ulang berkas ini.

:selesai
echo.
pause
