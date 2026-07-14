"""
Client local vers l'agent de prédiction (HTTP :7071).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

AGENT_URL = os.environ.get("VC_AGENT_API_URL", "http://127.0.0.1:7071").rstrip("/")
TIMEOUT = float(os.environ.get("VC_AGENT_PREDICT_TIMEOUT", "8"))


def query_local_availability(horizon_min: int = 15) -> Optional[Dict[str, Any]]:
    """
    Demande à l'agent local si la machine restera disponible ~15 min.
    Fallback : calcul ARX in-process (telemetry_bridge) si :7071 down.
    """
    try:
        r = requests.get(f"{AGENT_URL}/predict", timeout=TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            data["horizon_min"] = int(data.get("horizon_min") or horizon_min)
            return data
        logger.warning("Agent /predict HTTP %s: %s", r.status_code, r.text[:200])
    except Exception as exc:
        logger.warning("Agent disponibilité injoignable (%s): %s", AGENT_URL, exc)

    # Fallback sans processus HTTP (évite launch=0 / hybrid=0 faute d'agent down)
    try:
        from services.telemetry_bridge import _predict, _snapshot

        snap = _snapshot()
        pred = _predict(snap)
        pred["horizon_min"] = int(pred.get("horizon_min") or horizon_min)
        pred.setdefault("mode", pred.get("mode") or "arx_bridge_inline")
        return pred
    except Exception as exc:
        try:
            from volontaire.services.telemetry_bridge import _predict, _snapshot

            snap = _snapshot()
            pred = _predict(snap)
            pred["horizon_min"] = int(pred.get("horizon_min") or horizon_min)
            pred.setdefault("mode", pred.get("mode") or "arx_bridge_inline")
            return pred
        except Exception as exc2:
            logger.warning("Fallback predicteur inline échoué: %s / %s", exc, exc2)
            return None


def agent_is_healthy() -> bool:
    try:
        r = requests.get(f"{AGENT_URL}/health", timeout=2)
        return r.status_code == 200
    except Exception:
        return False
