"""
Простой настольный клиент для Windows на Python (только стандартная библиотека).

Что умеет:
  * импорт ссылок vless:// и ss://, а также подписки (URL со списком ссылок);
  * список серверов (хранится в servers.json рядом со скриптом);
  * подключение: запускает ядро Xray (xray.exe рядом со скриптом) как локальный
    прокси SOCKS5 127.0.0.1:10808 и HTTP 127.0.0.1:10809;
  * включение/выключение системного прокси Windows.

Это прокси-режим, а не TUN: системный прокси охватывает браузеры и программы,
которые его учитывают. WireGuard/AmneziaWG здесь не поддерживаются.

Запуск:  python vpn_client.py
Сборка:  pip install pyinstaller && pyinstaller --noconsole --onefile vpn_client.py
(xray.exe положите рядом с получившимся .exe)
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
import urllib.request
from tkinter import messagebox, simpledialog
from urllib.parse import parse_qs, unquote, urlparse

BASE = os.path.dirname(os.path.abspath(sys.argv[0]))
SERVERS_FILE = os.path.join(BASE, "servers.json")
XRAY = os.path.join(BASE, "xray.exe" if os.name == "nt" else "xray")
SOCKS_PORT, HTTP_PORT = 10808, 10809


# ---------- разбор ссылок ----------
def _b64(s: str) -> str:
    s = s.strip().replace("-", "+").replace("_", "/")
    return base64.b64decode(s + "=" * (-len(s) % 4)).decode("utf-8", "replace")


def parse_link(link: str) -> dict:
    link = link.strip()
    u = urlparse(link)
    name = unquote(u.fragment) or u.hostname or "server"
    if u.scheme == "vless":
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        return {"name": name, "type": "vless", "host": u.hostname, "port": u.port or 443,
                "uuid": u.username, "q": q}
    if u.scheme == "ss":
        body = link[5:].split("#")[0]
        if "@" in body:
            userinfo, hostport = body.rsplit("@", 1)
            method, password = (_b64(userinfo) if ":" not in userinfo else userinfo).split(":", 1)
        else:
            decoded = _b64(body)
            userinfo, hostport = decoded.rsplit("@", 1)
            method, password = userinfo.split(":", 1)
        host, port = hostport.split("?")[0].rsplit(":", 1)
        return {"name": name, "type": "ss", "host": host, "port": int(port),
                "method": method, "password": password}
    raise ValueError("Поддерживаются только vless:// и ss://")


def parse_text(text: str) -> list:
    text = text.strip()
    if "://" not in text.splitlines()[0]:  # подписка в base64
        text = _b64(text)
    out = []
    for line in text.splitlines():
        try:
            out.append(parse_link(line))
        except Exception:
            pass
    return out


# ---------- конфиг Xray ----------
def build_xray_config(s: dict) -> dict:
    if s["type"] == "vless":
        q = s["q"]
        user = {"id": s["uuid"], "encryption": "none"}
        if q.get("flow"):
            user["flow"] = q["flow"]
        stream = {"network": q.get("type", "tcp"), "security": q.get("security", "none")}
        if stream["security"] == "reality":
            stream["realitySettings"] = {
                "serverName": q.get("sni", ""), "fingerprint": q.get("fp", "chrome"),
                "publicKey": q.get("pbk", ""), "shortId": q.get("sid", ""), "spiderX": q.get("spx", "")}
        elif stream["security"] == "tls":
            stream["tlsSettings"] = {"serverName": q.get("sni") or q.get("host") or s["host"]}
        if stream["network"] == "ws":
            stream["wsSettings"] = {"path": unquote(q.get("path", "/")),
                                    "headers": {"Host": q.get("host", s["host"])}}
        outbound = {"protocol": "vless",
                    "settings": {"vnext": [{"address": s["host"], "port": s["port"], "users": [user]}]},
                    "streamSettings": stream}
    else:
        outbound = {"protocol": "shadowsocks",
                    "settings": {"servers": [{"address": s["host"], "port": s["port"],
                                              "method": s["method"], "password": s["password"]}]}}
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {"listen": "127.0.0.1", "port": SOCKS_PORT, "protocol": "socks", "settings": {"udp": True}},
            {"listen": "127.0.0.1", "port": HTTP_PORT, "protocol": "http"},
        ],
        "outbounds": [outbound],
    }


# ---------- системный прокси Windows ----------
def set_system_proxy(enable: bool):
    if os.name != "nt":
        return
    import ctypes
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                         r"Software\Microsoft\Windows\CurrentVersion\Internet Settings", 0,
                         winreg.KEY_SET_VALUE)
    winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1 if enable else 0)
    if enable:
        winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, f"127.0.0.1:{HTTP_PORT}")
    winreg.CloseKey(key)
    wininet = ctypes.windll.Wininet
    wininet.InternetSetOptionW(0, 39, 0, 0)  # SETTINGS_CHANGED
    wininet.InternetSetOptionW(0, 37, 0, 0)  # REFRESH


# ---------- GUI ----------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Мой VPN-клиент")
        self.geometry("460x420")
        self.proc = None
        self.servers = self.load()

        self.listbox = tk.Listbox(self, height=12)
        self.listbox.pack(fill="both", expand=True, padx=10, pady=(10, 5))
        row = tk.Frame(self)
        row.pack(fill="x", padx=10)
        tk.Button(row, text="Добавить ссылку", command=self.add_link).pack(side="left")
        tk.Button(row, text="Подписка (URL)", command=self.add_sub).pack(side="left", padx=5)
        tk.Button(row, text="Удалить", command=self.remove).pack(side="left")
        self.btn = tk.Button(self, text="Подключить", height=2, command=self.toggle)
        self.btn.pack(fill="x", padx=10, pady=10)
        self.status = tk.Label(self, text="Отключено", fg="gray")
        self.status.pack(pady=(0, 10))
        self.refresh()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # данные
    def load(self):
        try:
            with open(SERVERS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def save(self):
        with open(SERVERS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.servers, f, ensure_ascii=False, indent=2)

    def refresh(self):
        self.listbox.delete(0, "end")
        for s in self.servers:
            self.listbox.insert("end", f'{s["name"]}  [{s["type"]}] {s["host"]}:{s["port"]}')

    # действия
    def add_link(self):
        text = simpledialog.askstring("Ссылка", "Вставьте vless:// или ss:// ссылку:")
        if not text:
            return
        try:
            self.servers.append(parse_link(text))
            self.save()
            self.refresh()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def add_sub(self):
        url = simpledialog.askstring("Подписка", "URL подписки:")
        if not url:
            return
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                items = parse_text(r.read().decode("utf-8", "replace"))
            self.servers.extend(items)
            self.save()
            self.refresh()
            messagebox.showinfo("Готово", f"Добавлено серверов: {len(items)}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def remove(self):
        sel = self.listbox.curselection()
        if sel:
            del self.servers[sel[0]]
            self.save()
            self.refresh()

    def toggle(self):
        if self.proc:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showwarning("Сервер", "Выберите сервер в списке")
            return
        if not os.path.exists(XRAY):
            messagebox.showerror("Нет ядра", f"Положите xray рядом с программой:\n{XRAY}")
            return
        cfg = os.path.join(tempfile.gettempdir(), "vpn_client_xray.json")
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump(build_xray_config(self.servers[sel[0]]), f)
        flags = 0x08000000 if os.name == "nt" else 0  # без окна консоли
        self.proc = subprocess.Popen([XRAY, "run", "-c", cfg], creationflags=flags,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        set_system_proxy(True)
        self.btn.config(text="Отключить")
        self.status.config(text=f"Подключено: {self.servers[sel[0]]['name']}", fg="green")

    def disconnect(self):
        if self.proc:
            self.proc.terminate()
            self.proc = None
        set_system_proxy(False)
        self.btn.config(text="Подключить")
        self.status.config(text="Отключено", fg="gray")

    def on_close(self):
        self.disconnect()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
