@echo off
rem Сборка vpn_client.exe одним кликом. Нужен установленный Python 3.10+.
python -m pip install pyinstaller
python -m PyInstaller --noconsole --onefile vpn_client.py
echo.
echo Готово: dist\vpn_client.exe
echo Положите xray.exe (https://github.com/XTLS/Xray-core/releases) в папку dist рядом с vpn_client.exe
pause
