"""Run the local Football Forecast Studio browser app with Python 3.10+."""
from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import socket
import sqlite3
import sys
import threading
import webbrowser
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

import studio_engine

STATIC = Path(__file__).resolve().parent / "static"
MAX_REQUEST_BYTES = 24 * 1024 * 1024
STUDIO_VERSION = "2.2.0"


def reject_number(number):
    raise ValueError(f"JSON 中包含无效数字 {number}")


class StudioServer(ThreadingHTTPServer):
    allow_reuse_address = not hasattr(socket, "SO_EXCLUSIVEADDRUSE")

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class StudioHandler(BaseHTTPRequestHandler):
    server_version = "FootballStudio"

    def reply(self, status, content, mime):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(content)

    def send_json(self, status, value):
        content = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.reply(status, content, "application/json; charset=utf-8")

    def valid_origin(self):
        port = self.server.server_address[1]
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if port == 80:
            allowed.update(("127.0.0.1", "localhost"))
        host = self.headers.get("Host", "").lower()
        origin = self.headers.get("Origin")
        if host not in allowed or (origin is not None and origin.lower() != "http://" + host):
            self.send_json(403, {"error": "请通过本机足球研究室页面访问。"})
            return False
        return True

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self.valid_origin():
            return
        path = urlsplit(self.path).path
        try:
            if path.startswith("/api/"):
                if path == "/api/examples":
                    result = studio_engine.examples()
                elif path == "/api/ledger":
                    result = studio_engine.ledger_records()
                elif path == "/api/health":
                    result = {"status": "ok", "engine": "football-forecast-lab", "version": STUDIO_VERSION}
                elif path == "/api/ai/settings":
                    import ai_service
                    status, result = ai_service.handle("GET", path, {})
                    self.send_json(status, result)
                    return
                else:
                    self.send_json(404, {"error": "接口不存在"})
                    return
                self.send_json(200, result)
                return
            relative = unquote(path).lstrip("/") or "index.html"
            target = (STATIC / relative).resolve()
            if not target.is_relative_to(STATIC) or not target.is_file():
                self.send_json(404, {"error": "文件不存在"})
                return
            overrides = {".js": "text/javascript", ".css": "text/css", ".html": "text/html",
                         ".svg": "image/svg+xml", ".woff2": "font/woff2"}
            mime = overrides.get(target.suffix.lower()) or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if mime.startswith("text/"):
                mime += "; charset=utf-8"
            self.reply(200, target.read_bytes(), mime)
        except (OSError, sqlite3.Error, ValueError) as exc:
            self.send_json(500, {"error": f"读取失败：{exc}"})

    def do_POST(self):
        if not self.valid_origin():
            return
        path = urlsplit(self.path).path
        command = path.removeprefix("/api/")
        if not path.startswith("/api/") or (command not in studio_engine.COMMANDS and
                                             command not in {"ai/settings", "ai/test", "ai/analyze"}):
            self.send_json(404, {"error": "接口不存在"})
            return
        if self.headers.get_content_type() != "application/json":
            self.send_json(415, {"error": "请以 application/json 提交"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_REQUEST_BYTES:
                self.send_json(413, {"error": "请求体为空或超过 24 MiB"})
                return
            payload = json.loads(self.rfile.read(size).decode("utf-8-sig"), parse_constant=reject_number)
            if not isinstance(payload, dict):
                raise ValueError("需要 JSON 对象")
            if command.startswith("ai/"):
                import ai_service
                status, result = ai_service.handle("POST", path, payload)
            else:
                status, result = 200, studio_engine.run(command, payload)
            self.send_json(status, result)
        except KeyError as exc:
            self.send_json(400, {"error": f"缺少字段 {exc.args[0]}"})
        except (ValueError, TypeError, AttributeError, IndexError, ArithmeticError, RecursionError,
                csv.Error, ET.ParseError) as exc:
            self.send_json(400, {"error": str(exc)})
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass
        except (OSError, sqlite3.Error):
            self.send_json(500, {"error": "无法访问本地数据文件，请检查存储位置和文件权限。"})

    def log_request(self, code="-", size="-"):
        # Keep request payloads, credentials and query parameters out of server logs.
        self.log_message("%s %s %s", self.command, urlsplit(self.path).path, code)

    def log_message(self, format, *args):
        if sys.stderr is not None:
            super().log_message(format, *args)


def main():
    parser = argparse.ArgumentParser(description="足球赛前研究室 · 本机服务")
    parser.add_argument("--port", type=int, default=8765, help="监听端口（默认 8765）")
    parser.add_argument("--open", action="store_true", help="启动后打开系统浏览器")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("端口须在 0 至 65535 之间")
    try:
        server = StudioServer(("127.0.0.1", args.port), StudioHandler)
    except OSError as exc:
        parser.exit(1, f"无法启动本地服务，请检查端口占用或指定 --port：{exc}\n")
    with server:
        url = f"http://127.0.0.1:{server.server_address[1]}/"
        print(f"足球赛前研究室 {url}", flush=True)
        if args.open:
            threading.Timer(0.1, webbrowser.open, (url,)).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            import localization
            localization.shutdown()


if __name__ == "__main__":
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    main()
