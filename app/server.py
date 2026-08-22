"""Winziger lokaler HTTP-Server (nur Python-Standardbibliothek).

Kein Web-Framework: Dient ausschließlich dazu, der Desktop-Anwendung
(pywebview) über "echte" URLs mit Query-Parametern zu bedienen, damit
z. B. die Tabellensortierung serverseitig über Links funktioniert.
Der Server lauscht ausschließlich auf 127.0.0.1 und ist nie im Netzwerk
erreichbar – es handelt sich nicht um eine Web-Anwendung.
"""

from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlsplit

from app import data, routes

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Verhindert, dass eine sehr große Datei den Server-Prozess blockiert/überlastet.
MAX_BODY_BYTES = 25 * 1024 * 1024 + 1024


def _single_valued(qs: dict[str, list[str]]) -> dict[str, str]:
    return {key: values[0] for key, values in qs.items() if values}


def _serve_static(handler: BaseHTTPRequestHandler, rel_path: str) -> None:
    target = (STATIC_DIR / rel_path).resolve()
    if STATIC_DIR not in target.parents or not target.is_file():
        handler.send_error(404, "Datei nicht gefunden")
        return

    content_type, _ = mimetypes.guess_type(str(target))
    body = target.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", content_type or "application/octet-stream")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _render_html(handler: BaseHTTPRequestHandler, html: str, status: int = 200) -> None:
    body = html.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _render_json(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _redirect(handler: BaseHTTPRequestHandler, location: str) -> None:
    handler.send_response(303)  # See Other -> Browser folgt mit GET
    handler.send_header("Location", location)
    handler.send_header("Content-Length", "0")
    handler.end_headers()


def _serve_document_file(handler: BaseHTTPRequestHandler, doc_path: str | None, mode: str) -> None:
    """Liefert eine Original-PDF aus – nur wenn sie innerhalb SCAN_DIRECTORY
    liegt (siehe data.resolve_document_path). Kein anderer Dateizugriff
    ist über die Anwendung möglich."""
    resolved = data.resolve_document_path(doc_path)
    if resolved is None:
        _render_html(handler, "<h1>404</h1><p>Datei nicht gefunden oder nicht zulässig.</p>", status=404)
        return

    body = resolved.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", "application/pdf")
    handler.send_header("Content-Length", str(len(body)))
    if mode == "download":
        safe_name = resolved.name.replace('"', "").replace("\r", "").replace("\n", "")
        handler.send_header("Content-Disposition", f'attachment; filename="{safe_name}"')
    handler.end_headers()
    handler.wfile.write(body)


def _serve_csv(handler: BaseHTTPRequestHandler, csv_text: str, filename: str) -> None:
    # UTF-8 mit BOM, damit Excel unter Windows Umlaute korrekt anzeigt.
    body = csv_text.encode("utf-8-sig")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/csv; charset=utf-8")
    handler.send_header("Content-Disposition", f'attachment; filename="{filename}"')
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_body(handler: BaseHTTPRequestHandler) -> bytes | None:
    try:
        length = int(handler.headers.get("Content-Length", 0))
    except ValueError:
        length = 0
    if length <= 0 or length > MAX_BODY_BYTES:
        return None
    return handler.rfile.read(length)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002 – Signatur der Basisklasse
        pass  # Konsole ruhig halten; bei Bedarf hier Logging ergänzen.

    def do_GET(self) -> None:  # noqa: N802 – von BaseHTTPRequestHandler vorgegeben
        parts = urlsplit(self.path)
        path = parts.path
        query = _single_valued(parse_qs(parts.query))

        if path.startswith("/static/"):
            _serve_static(self, path[len("/static/"):])
            return

        try:
            if path == "/":
                _render_html(self, routes.dashboard(query))
            elif path == "/zuordnungen":
                params: dict[str, str] = {}
                legacy = query.get("filter")
                if legacy == "bestaetigt" or legacy == "automatisch":
                    params["status"] = "bestaetigt"
                elif legacy in {"pruefung", "nicht_zuordenbar"}:
                    params["status"] = legacy
                if query.get("q"):
                    params["q"] = query["q"]
                if query.get("error"):
                    params["error"] = query["error"]
                target = f"/dokumente?{urlencode(params)}" if params else "/dokumente"
                _redirect(self, target)
            elif path == "/zuordnung/pruefen":
                _render_html(self, routes.pruefen(query))
            elif path == "/api/auftraege/suche":
                _render_json(self, routes.search_orders_api(query))
            elif path == "/eingang":
                _redirect(self, "/")
            elif path == "/auftraege":
                _render_html(self, routes.auftraege(query))
            elif path == "/auftrag/details":
                _render_html(self, routes.auftrag_details(query))
            elif path == "/dokumente":
                _render_html(self, routes.dokumente(query))
            elif path == "/dokument/datei":
                _serve_document_file(self, query.get("doc"), query.get("mode", "inline"))
            elif path == "/auswertungen":
                _render_html(self, routes.auswertungen(query))
            elif path == "/auswertungen/export.csv":
                _serve_csv(self, routes.export_csv(query), "auswertungen.csv")
            elif path == "/einstellungen":
                _render_html(self, routes.einstellungen(query))
            else:
                _render_html(self, f"<h1>404</h1><p>Seite nicht gefunden: {path}</p>", status=404)
        except Exception as exc:  # noqa: BLE001 – Anwendung darf nicht abstürzen
            _render_html(
                self,
                f"<h1>Fehler</h1><p>Beim Laden der Seite ist ein Fehler aufgetreten:</p><pre>{exc}</pre>",
                status=500,
            )

    def do_POST(self) -> None:  # noqa: N802 – von BaseHTTPRequestHandler vorgegeben
        parts = urlsplit(self.path)
        path = parts.path
        query = _single_valued(parse_qs(parts.query))

        try:
            if path == "/eingang/upload":
                filename = unquote(query.get("filename", "upload.pdf"))
                body = _read_body(self)
                if body is None:
                    _render_json(self, {"ok": False, "error": "Datei fehlt oder ist zu groß."}, status=400)
                    return
                result = routes.upload(filename, body)
                _render_json(self, result, status=200 if result["ok"] else 400)

            elif path == "/zuordnung/bestaetigen":
                body = _read_body(self) or b""
                form = _single_valued(parse_qs(body.decode("utf-8")))
                location = routes.confirm(form)
                _redirect(self, location)

            elif path == "/zuordnung/loeschen":
                body = _read_body(self) or b""
                form = _single_valued(parse_qs(body.decode("utf-8")))
                _redirect(self, routes.delete_assignment(form))

            elif path == "/dokument/loeschen":
                body = _read_body(self) or b""
                form = _single_valued(parse_qs(body.decode("utf-8")))
                _redirect(self, routes.delete_document(form))

            elif path == "/einstellungen/verbindung-pruefen":
                _redirect(self, routes.einstellungen_verbindung_pruefen())

            elif path == "/einstellungen/verarbeitung":
                body = _read_body(self) or b""
                form = _single_valued(parse_qs(body.decode("utf-8")))
                _redirect(self, routes.einstellungen_verarbeitung_speichern(form))

            elif path == "/einstellungen/matching":
                body = _read_body(self) or b""
                form = _single_valued(parse_qs(body.decode("utf-8")))
                _redirect(self, routes.einstellungen_matching_speichern(form))

            elif path == "/einstellungen/ordner":
                body = _read_body(self) or b""
                form = _single_valued(parse_qs(body.decode("utf-8")))
                _redirect(self, routes.einstellungen_ordner_speichern(form))

            else:
                _render_html(self, f"<h1>404</h1><p>Seite nicht gefunden: {path}</p>", status=404)
        except Exception as exc:  # noqa: BLE001 – Anwendung darf nicht abstürzen
            _render_json(self, {"ok": False, "error": str(exc)}, status=500)


def start_server(host: str = "127.0.0.1", port: int = 0) -> tuple[ThreadingHTTPServer, int]:
    """Startet den Server in einem Hintergrund-Thread und gibt den Port zurück."""
    import threading

    server = ThreadingHTTPServer((host, port), Handler)
    bound_port = server.server_address[1]

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # OCR/Matching nicht im Page-Load – neue/fehlerhafte PDFs im Hintergrund
    threading.Thread(target=data.process_pending_documents, daemon=True).start()

    return server, bound_port
