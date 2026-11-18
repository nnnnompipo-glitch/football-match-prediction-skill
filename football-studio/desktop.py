"""Double-click entry point for the Touchline Lab portable Windows app."""
from __future__ import annotations

import argparse
import http.client
import json
import threading
import webbrowser

from server import STATIC, STUDIO_VERSION, StudioHandler, StudioServer
from studio_engine import data_dir


def running_studio(port):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
    try:
        connection.request("GET", "/api/health")
        response = connection.getresponse()
        if response.status != 200:
            return False
        health = json.loads(response.read(1024))
        return (health.get("status") == "ok" and health.get("engine") == "football-forecast-lab"
                and health.get("version") == STUDIO_VERSION)
    except (TimeoutError, OSError, ValueError, AttributeError, http.client.HTTPException):
        return False
    finally:
        connection.close()


def find_server(requested_port=None):
    ports = (requested_port,) if requested_port is not None else range(8765, 8781)
    # Reopen the same instance even if another program has since freed port 8765.
    hint = data_dir() / "desktop-port.txt"
    if requested_port is None:
        try:
            previous = int(hint.read_text(encoding="ascii"))
            if previous in ports and previous != ports[0] and running_studio(previous):
                return None, f"http://127.0.0.1:{previous}/"
        except (ValueError, OSError):
            pass
    for port in ports:
        try:
            server = StudioServer(("127.0.0.1", port), StudioHandler)
        except OSError:
            if running_studio(port):
                return None, f"http://127.0.0.1:{port}/"
            if requested_port is not None:
                raise
        else:
            if requested_port is None and port != ports[0]:
                try:
                    hint.parent.mkdir(parents=True, exist_ok=True)
                    hint.write_text(str(port), encoding="ascii")
                except OSError:
                    pass
            return server, f"http://127.0.0.1:{server.server_port}/"
    raise OSError("常用本地端口均已被占用，请用 --port 指定其他端口。")


def desktop_window(server, url, auto_open=True):
    from windows_ui import show_manager

    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        show_manager(url, STATIC / "mark.ico", auto_open)
    finally:
        server.shutdown()
        worker.join()


def main():
    parser = argparse.ArgumentParser(description="Touchline Lab · 桌面启动器")
    parser.add_argument("--port", type=int, help="指定本地监听端口")
    parser.add_argument("--serve", action="store_true", help="只运行本地服务")
    parser.add_argument("--no-browser", action="store_true", help="启动时仅显示桌面控制窗口")
    args = parser.parse_args()
    if args.port is not None and not 0 <= args.port <= 65535:
        parser.error("端口须在 0 至 65535 之间")
    try:
        server, url = find_server(args.port)
    except OSError as exc:
        if args.serve:
            raise
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, str(exc), "足球赛前研究室", 16)
        return
    if server is None:
        if not args.serve and not args.no_browser:
            webbrowser.open(url)
        return
    with server:
        try:
            if args.serve:
                server.serve_forever()
            else:
                desktop_window(server, url, not args.no_browser)
        finally:
            import localization
            localization.shutdown()


if __name__ == "__main__":
    main()
