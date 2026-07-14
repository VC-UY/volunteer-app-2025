"""
Répond aux sondes de disponibilité du coordinateur (prédiction agent 15 min).
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

QUERY_CHANNEL = "volunteer/availability/query"
REPLY_CHANNEL = "volunteer/availability/reply"
REPLY_KEY_PREFIX = "availability:reply:"

# Champs admin à exposer dans prediction_detail
_DETAIL_KEYS = (
    "linear",
    "gru",
    "hybrid",
    "launch",
    "horizon_min",
    "launch_threshold",
    "threshold",
    "label",
    "cpu_percent_current",
    "ram_percent_used_current",
    "cpu_percent_avg_15m",
    "ram_percent_used_avg_15m",
    "samples_15m",
    "degraded",
    "mode",
    "model",
    "machine_id",
    "is_available_now",
    "power_plugged",
    "network_ok",
    "hybrid_alpha",
)


def _volunteer_id() -> str:
    try:
        from redis_communication.utils import get_volunteer_id

        return str(get_volunteer_id() or "")
    except Exception:
        return ""


def _extract_detail(pred: dict) -> dict:
    detail = {k: pred[k] for k in _DETAIL_KEYS if k in pred}
    # alias seuil
    if "launch_threshold" not in detail and "threshold" in detail:
        detail["launch_threshold"] = detail["threshold"]
    return detail


def handle_availability_query(channel: str, message: Any) -> None:
    """
    Handler Redis : si la requête cible ce volontaire, interroge l'agent local
    et écrit la réponse dans une clé Redis éphémère (lu par le coordinateur).
    """
    try:
        data = message.data if hasattr(message, "data") else message
        if not isinstance(data, dict):
            # parfois payload enveloppe {data: {...}}
            if isinstance(message, dict) and isinstance(message.get("data"), dict):
                data = message["data"]
            else:
                return
        target = str(data.get("volunteer_id") or "")
        request_id = str(data.get("request_id") or "")
        me = _volunteer_id()
        if not request_id or not me or target != me:
            return

        from volontaire.services.availability_client import query_local_availability

        pred = query_local_availability(int(data.get("horizon_min") or 15))
        if pred is None:
            payload = {
                "ok": False,
                "launch": False,
                "error": "agent_unreachable",
                "volunteer_id": me,
                "request_id": request_id,
                "source": "redis_probe",
                "ts": time.time(),
            }
        else:
            detail = _extract_detail(pred)
            payload = {
                "ok": True,
                "volunteer_id": me,
                "request_id": request_id,
                "source": "redis_probe",
                "ts": time.time(),
                "prediction_detail": detail,
                **detail,
            }

        from redis_communication.client import RedisClient

        client = RedisClient.get_instance()
        key = f"{REPLY_KEY_PREFIX}{request_id}"
        raw = json.dumps(payload, default=str)
        client.redis.setex(key, 60, raw)
        # Canal pub/sub miroir (proxy Redis souvent plus fiable que GET via gateway)
        try:
            client.publish(
                REPLY_CHANNEL,
                payload,
                request_id=request_id,
                message_type="response",
            )
        except Exception as pub_exc:
            logger.debug("publish reply soft-fail: %s", pub_exc)

        logger.info(
            "Disponibilité répondue request=%s launch=%s hybrid=%s cpu=%.1f",
            request_id[:8],
            payload.get("launch"),
            payload.get("hybrid"),
            float(payload.get("cpu_percent_current") or 0),
        )
    except Exception as exc:
        logger.error("handle_availability_query: %s", exc)


def register_availability_handlers(redis_client) -> None:
    redis_client.subscribe(QUERY_CHANNEL, handle_availability_query)
    logger.info("Abonné à %s (sonde disponibilité coordinateur)", QUERY_CHANNEL)
