# VPN-клиент на Python

## Запуск
1. Установите Python 3.10+ (на Windows tkinter входит в комплект).
2. Скачайте Xray-core для Windows: https://github.com/XTLS/Xray-core/releases (файл `Xray-windows-64.zip`).
   Положите `xray.exe` в одну папку с `vpn_client.py`.
3. `python vpn_client.py`
4. Нажмите «Добавить ссылку» и вставьте `vless://...` из панели (страница «Ключи»)
   или «Подписка (URL)». Выберите сервер и нажмите «Подключить».

## Сборка в .exe
```
pip install pyinstaller
pyinstaller --noconsole --onefile vpn_client.py
```
Готовый файл будет в `dist/`. Положите `xray.exe` рядом с ним.

## Ограничения
- Работает как системный прокси (HTTP 127.0.0.1:10809, SOCKS5 127.0.0.1:10808), не как TUN.
- Поддерживаются VLESS (Reality, TLS, WS) и Shadowsocks. WireGuard/AmneziaWG — нет.
- При закрытии окна системный прокси выключается. Если программа аварийно завершилась и
  интернет «пропал», отключите прокси: Параметры Windows → Сеть → Прокси.
- Код не проверялся на вашей системе: проверьте на тестовой ссылке.
