@echo off
cd /d "%~dp0"
echo Menjalankan Rasty Florist (mode pengembangan) di http://127.0.0.1:5000
echo Untuk server produksi gunakan jalankan-server.bat
python app.py
pause
