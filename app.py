"""Minimal zero-dependency web server for the Dua Kelinci Sales Pulse app."""

from __future__ import annotations

import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from analytics import (
    build_telegram_summary,
    compute_dashboard,
    load_and_clean_csv,
    load_csv_file,
    query_transactions,
    send_telegram_message,
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DEFAULT_CSV = BASE_DIR / "sales.csv"


class AppState:
    def __init__(self, csv_path: Path) -> None:
        self.source_name = csv_path.name
        self.rows, self.audit = load_csv_file(csv_path)

    def load_uploaded(self, filename: str, csv_text: str) -> None:
        rows, audit = load_and_clean_csv(csv_text)
        if not rows:
            raise ValueError("Uploaded CSV contains no valid data rows.")
        self.source_name = filename
        self.rows = rows
        self.audit = audit


STATE = AppState(DEFAULT_CSV)


class SalesHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        print(f"[server] {self.address_string()} - {format % args}")

    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, path: Path) -> None:
        if not path.is_file():
            self.send_error(404, "File not found")
            return
        mime, _ = mimetypes.guess_type(str(path))
        content = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{mime or 'application/octet-stream'}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/dashboard":
            params = parse_qs(parsed.query)
            month = params.get("month", ["all"])[0]
            region = params.get("region", ["all"])[0]
            brand = params.get("brand", ["all"])[0]
            lang = params.get("lang", ["id"])[0]
            outlet_mode = params.get("outlet_mode", ["lowest"])[0]
            data = compute_dashboard(
                STATE.rows,
                STATE.audit,
                month=month,
                region=region,
                brand=brand,
                lang=lang,
                outlet_mode=outlet_mode,
            )
            data["source_name"] = STATE.source_name
            self._send_json(data)
            return

        if parsed.path == "/api/transactions":
            params = parse_qs(parsed.query)
            data = query_transactions(
                STATE.rows,
                month=params.get("month", ["all"])[0],
                region=params.get("region", ["all"])[0],
                brand=params.get("brand", ["all"])[0],
                date_from=params.get("date_from", [""])[0],
                date_to=params.get("date_to", [""])[0],
                search=params.get("search", [""])[0],
                sort_by=params.get("sort_by", ["date"])[0],
                sort_dir=params.get("sort_dir", ["desc"])[0],
                page=int(params.get("page", ["1"])[0]),
                page_size=int(params.get("page_size", ["20"])[0]),
            )
            self._send_json(data)
            return

        if parsed.path in ("/", "/index.html"):
            self._serve_file(STATIC_DIR / "index.html")
            return

        rel = parsed.path.lstrip("/")
        candidate = (STATIC_DIR / rel).resolve()
        if str(candidate).startswith(str(STATIC_DIR.resolve())) and candidate.is_file():
            self._serve_file(candidate)
            return

        self.send_error(404, "Not found")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length) if length > 0 else b"{}"

        if parsed.path == "/api/summary":
            try:
                body = json.loads(raw_body.decode("utf-8"))
            except ValueError:
                self._send_json({"error": "Invalid JSON body"}, status=400)
                return

            dashboard = compute_dashboard(
                STATE.rows,
                STATE.audit,
                month=body.get("month", "all"),
                region=body.get("region", "all"),
                brand=body.get("brand", "all"),
                lang=body.get("lang", "id"),
            )
            text, source = build_telegram_summary(
                dashboard,
                lang=body.get("lang", "id"),
                outlet_mode=body.get("outlet_mode", "lowest"),
                use_llm=bool(body.get("use_llm", False)),
            )
            self._send_json({"text": text, "source": source, "lang": body.get("lang", "id")})
            return

        if parsed.path == "/api/send-telegram":
            try:
                body = json.loads(raw_body.decode("utf-8"))
                text = (body.get("text") or "").strip()
                if not text:
                    raise ValueError("Summary text cannot be empty.")
                send_telegram_message(text)
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json({"ok": True})
            return

        if parsed.path == "/api/upload":
            try:
                body = json.loads(raw_body.decode("utf-8"))
                filename = body.get("filename", "uploaded.csv")
                csv_text = body.get("csv_text", "")
                STATE.load_uploaded(filename, csv_text)
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json({"ok": True, "source_name": STATE.source_name, "audit": STATE.audit})
            return

        if parsed.path == "/api/reset":
            STATE.__init__(DEFAULT_CSV)
            self._send_json({"ok": True, "source_name": STATE.source_name})
            return

        self.send_error(404, "Not found")


def main() -> None:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), SalesHandler)
    display_host = "127.0.0.1" if host == "0.0.0.0" else host
    print(f"Dua Kelinci Sales Pulse running at http://{display_host}:{port}")
    print(f"Loaded {STATE.audit['clean_rows']} clean rows from {STATE.source_name}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
