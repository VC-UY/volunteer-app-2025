"""
API HTTP locale pour que le volontaire / coordinateur consulte la prédiction 15 min.

Endpoints :
  GET  /health
  GET  /predict   → {"hybrid", "gru", "linear", "launch", "horizon_min"}
  POST /predict   (même sortie ; body JSON optionnel ignoré)
"""
from __future__ import annotations

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

logger = logging.getLogger("VC-AvailabilityAPI")

DEFAULT_HOST = os.getenv("VC_AGENT_API_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("VC_AGENT_API_PORT", "7071"))

_predictor = None
_server: Optional[ThreadingHTTPServer] = None
_thread: Optional[threading.Thread] = None
_lock = threading.Lock()
_last_detail: dict = {}


def bind_predictor(predictor) -> None:
    global _predictor
    _predictor = predictor


def last_prediction() -> dict:
    return dict(_last_detail)


def _run_predict() -> dict[str, Any]:
    import collector

    if _predictor is None:
        raise RuntimeError("Predicteur non initialisé")
    snapshot = collector.get_stats(aggregate=False)
    detail = _predictor.predict_from_snapshot(snapshot)
    y_now = 1.0 if snapshot.get("is_available") else 0.0
    try:
        _predictor.observe(snapshot, y_now)
    except Exception as exc:
        logger.debug("observe skip: %s", exc)
    with _lock:
        global _last_detail
        _last_detail = {
            "linear": float(detail.get("linear", 0)),
            "gru": float(detail.get("gru", 0)),
            "hybrid": float(detail.get("hybrid", 0)),
            "launch": bool(detail.get("launch")),
            "horizon_min": int(detail.get("horizon_min") or 15),
            "is_available_now": bool(snapshot.get("is_available")),
            "machine_id": collector.get_mac_address(),
        }
        return dict(_last_detail)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        logger.debug("%s - %s", self.address_string(), fmt % args)

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/health", "/"):
            self._send(200, {"status": "ok", "service": "vc-uy-agent", "port": DEFAULT_PORT})
            return
        if path == "/predict":
            try:
                self._send(200, _run_predict())
            except Exception as exc:
                self._send(503, {"error": str(exc), "launch": False})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/predict":
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        try:
            self._send(200, _run_predict())
        except Exception as exc:
            self._send(503, {"error": str(exc), "launch": False})


def start_availability_api(predictor=None, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    """Démarre le serveur HTTP en thread daemon (idempotent)."""
    global _server, _thread
    if predictor is not None:
        bind_predictor(predictor)
    if _thread and _thread.is_alive():
        return

    def _serve() -> None:
        global _server
        _server = ThreadingHTTPServer((host, port), _Handler)
        logger.info("Availability API sur http://%s:%s/predict", host, port)
        _server.serve_forever()

    _thread = threading.Thread(target=_serve, name="vc-agent-api", daemon=True)
    _thread.start()


def stop_availability_api() -> None:
    global _server
    if _server:
        _server.shutdown()
        _server = None
