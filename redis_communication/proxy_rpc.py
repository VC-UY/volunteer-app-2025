"""RPC request/response fiable via le proxy Redis (connexions separees)."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any, Dict, Optional, Tuple

import redis

logger = logging.getLogger(__name__)


def _redis_kwargs() -> dict:
    return dict(
        host=os.environ.get("COORDINATOR_HOST", "173.249.38.251"),
        port=int(os.environ.get("COORDINATOR_PROXY_PORT", "6380")),
        db=0,
        decode_responses=True,
        protocol=2,
        lib_name=None,
        lib_version=None,
        socket_connect_timeout=10,
        socket_timeout=15,
    )


def proxy_request_response(
    request_channel: str,
    response_channel: str,
    data: Dict[str, Any],
    *,
    sender_id: str = "volunteer",
    timeout: float = 30.0,
) -> Tuple[bool, Dict[str, Any]]:
    request_id = str(uuid.uuid4())
    payload = {
        "request_id": request_id,
        "sender": {"type": "volunteer", "id": sender_id},
        "message_type": "request",
        "timestamp": time.time(),
        "data": data,
    }

    kwargs = _redis_kwargs()
    # protocol/lib_name peuvent etre absents sur vieilles versions
    try:
        sub_client = redis.Redis(**kwargs)
        pub_client = redis.Redis(**kwargs)
    except TypeError:
        kwargs.pop("protocol", None)
        kwargs.pop("lib_name", None)
        kwargs.pop("lib_version", None)
        sub_client = redis.Redis(**kwargs)
        pub_client = redis.Redis(**kwargs)

    pubsub = sub_client.pubsub(ignore_subscribe_messages=True)
    try:
        pubsub.subscribe(response_channel)
        time.sleep(0.15)
        pub_client.publish(request_channel, json.dumps(payload))
        deadline = time.time() + timeout
        while time.time() < deadline:
            message = pubsub.get_message(timeout=1.0)
            if not message or message.get("type") != "message":
                continue
            try:
                body = json.loads(message["data"])
            except (TypeError, json.JSONDecodeError):
                continue
            if body.get("request_id") != request_id:
                continue
            response_data = body.get("data") or {}
            return response_data.get("status") == "success", response_data
        return False, {"status": "error", "message": "Timeout"}
    except Exception as exc:
        logger.error("RPC volunteer error: %s", exc)
        return False, {"status": "error", "message": str(exc)}
    finally:
        try:
            pubsub.close()
            sub_client.close()
            pub_client.close()
        except Exception:
            pass
