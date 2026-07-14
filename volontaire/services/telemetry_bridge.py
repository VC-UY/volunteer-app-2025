"""
Pont télémétrie léger (sans torch/numpy) — démarre avec Daphne.

- Collecte CPU/RAM/secteur avec psutil
- Prédiction ARX 15D + seuil launch (si poids présents)
- Expose http://127.0.0.1:7071/predict pour le coordinateur
- Sync périodique vers https://vc-uy.npe-techs.com/api/agent
"""
from __future__ import annotations

import json
import logging
import math
import os
import socket
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_last: Dict[str, Any] = {}
_started = False


def _agent_models() -> Path:
    return Path(__file__).resolve().parents[2] / "agent" / "models"


def _site_ip() -> str:
    return (
        os.environ.get("VCUY_SITE_IP")
        or os.environ.get("COORDINATOR_HOST")
        or "173.249.38.251"
    )


def _site_base() -> str:
    return (
        os.environ.get("VCUY_SITE_API")
        or "https://vc-uy.npe-techs.com/api/agent"
    ).rstrip("/")


def _site_host() -> str:
    base = _site_base().replace("https://", "").replace("http://", "")
    return base.split("/")[0].split(":")[0]


def _machine_id() -> str:
    vid = (os.environ.get("VCUY_VOLUNTEER_ID") or "").strip()
    if vid:
        return f"vol-{vid[:12]}"
    try:
        return format(uuid.getnode(), "012x")
    except Exception:
        return socket.gethostname()


def _http_json(method: str, url: str, payload: Optional[dict] = None, timeout: int = 20) -> tuple[int, str]:
    """
    POST/GET JSON via curl (évite proxy Python / DNS cassés).
    Utilise --resolve host:443:IP si DNS local échoue.
    """
    import subprocess
    import tempfile

    host = _site_host()
    ip = _site_ip()
    cmd = [
        "curl",
        "-sS",
        "-X",
        method.upper(),
        "-o",
        "-",
        "-w",
        "\n__HTTP_CODE__:%{http_code}",
        "--max-time",
        str(timeout),
        "--resolve",
        f"{host}:443:{ip}",
        "--resolve",
        f"{host}:80:{ip}",
        "-H",
        "Content-Type: application/json",
        "-H",
        "Accept: application/json",
    ]
    tmp = None
    try:
        if payload is not None:
            tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
            json.dump(payload, tmp)
            tmp.close()
            cmd.extend(["--data-binary", f"@{tmp.name}"])
        cmd.append(url)
        env = os.environ.copy()
        for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
            env.pop(k, None)
        out = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout + 5)
        text = (out.stdout or "")
        err = (out.stderr or "")
        code = 0
        body = text
        if "__HTTP_CODE__:" in text:
            body, _, tail = text.rpartition("__HTTP_CODE__:")
            try:
                code = int(tail.strip().split()[0])
            except Exception:
                code = 0
            body = body.rstrip("\n")
        if out.returncode != 0 and code == 0:
            logger.warning("curl failed rc=%s: %s%s", out.returncode, body[:120], err[:200])
            # Fallback: pousser via SSH vers le backend site sur le VPS (réseau local Docker).
            if method.upper() == "POST" and payload is not None and "sync/snapshots" in url:
                return _sync_via_ssh(payload)
        return code, body
    except Exception as exc:
        logger.warning("curl http_json: %s", exc)
        if method.upper() == "POST" and payload is not None and "sync/snapshots" in url:
            return _sync_via_ssh(payload)
        return 0, str(exc)
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass


def _ssh_base() -> list[str]:
    """SSH/SCP sans /etc/ssh/ssh_config.d (cassé sur certaines machines)."""
    key = os.environ.get("VCUY_VPS_KEY", os.path.expanduser("~/.ssh/vcuy_vps"))
    host = os.environ.get("VCUY_VPS_SSH", "root@173.249.38.251")
    return [
        "-F",
        "/dev/null",
        "-i",
        key,
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=12",
        host,
    ]


def _sync_via_ssh(payload: dict) -> tuple[int, str]:
    """Dernier recours : POST depuis le VPS vers site-backend localhost."""
    import subprocess
    import tempfile

    try:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            json.dump(payload, tmp)
            path = tmp.name
        remote = f"/tmp/vcuy-snap-{os.getpid()}.json"
        scp_cmd = [
            "scp",
            "-F",
            "/dev/null",
            "-i",
            os.environ.get("VCUY_VPS_KEY", os.path.expanduser("~/.ssh/vcuy_vps")),
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            path,
            f"{os.environ.get('VCUY_VPS_SSH', 'root@173.249.38.251')}:{remote}",
        ]
        scp = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=12)
        if scp.returncode != 0:
            logger.warning("scp snapshot failed: %s", (scp.stderr or scp.stdout)[:200])
            return 0, scp.stderr or ""
        remote_cmd = (
            f"curl -sS -o /tmp/vcuy-snap-out.json -w '%{{http_code}}' "
            f"-X POST http://127.0.0.1:8003/api/agent/sync/snapshots "
            f"-H 'Content-Type: application/json' --data-binary @{remote}; "
            f"rm -f {remote}"
        )
        ssh = subprocess.run(
            ["ssh", *_ssh_base()[:-1], _ssh_base()[-1], remote_cmd],
            capture_output=True,
            text=True,
            timeout=18,
        )
        try:
            os.unlink(path)
        except Exception:
            pass
        code_s = (ssh.stdout or "").strip()[-3:]
        try:
            code = int(code_s)
        except Exception:
            code = 0
        if code == 200:
            logger.info("snapshot sync via SSH OK")
        else:
            logger.warning("ssh sync HTTP %s out=%s err=%s", code, ssh.stdout[:120], ssh.stderr[:120])
        return code, ssh.stdout or ""
    except Exception as exc:
        logger.warning("ssh sync failed: %s", exc)
        return 0, str(exc)


def _load_arx() -> Optional[dict]:
    path = _agent_models() / "weights_arx_stay_15m.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        logger.warning("ARX weights unreadable: %s", exc)
        return None


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


# Fenêtre glissante (~15 min si sync ~8–15 s) pour moyennes admin
_history: list[dict] = []
_HISTORY_MAX = 120


def _push_history(cpu: float, ram: float) -> None:
    _history.append({"cpu": float(cpu), "ram": float(ram), "ts": time.time()})
    if len(_history) > _HISTORY_MAX:
        del _history[: len(_history) - _HISTORY_MAX]


def _resource_summary(cpu: float, ram: float) -> Dict[str, Any]:
    cutoff = time.time() - 15 * 60
    recent = [h for h in _history if h["ts"] >= cutoff] or list(_history[-1:])
    cpu_vals = [h["cpu"] for h in recent]
    ram_vals = [h["ram"] for h in recent]
    return {
        "cpu_percent_current": round(float(cpu), 2),
        "ram_percent_used_current": round(float(ram), 2),
        "cpu_percent_avg_15m": round(sum(cpu_vals) / max(1, len(cpu_vals)), 2),
        "ram_percent_used_avg_15m": round(sum(ram_vals) / max(1, len(ram_vals)), 2),
        "samples_15m": int(len(recent)),
    }


def _snapshot() -> Dict[str, Any]:
    import psutil

    cpu = float(psutil.cpu_percent(interval=0.2))
    mem = psutil.virtual_memory()
    batt = None
    try:
        batt = psutil.sensors_battery()
    except Exception:
        pass
    plugged = True if batt is None else bool(batt.power_plugged)
    # Conservateur : ne force jamais network_ok=False (coupe hybrid à 0)
    net_ok = True

    now = time.localtime()
    hour = now.tm_hour + now.tm_min / 60.0
    free = max(0.0, 100.0 - cpu)
    _push_history(cpu, float(mem.percent))
    snap = {
        "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cpu_percent": cpu,
        "cpu_free": free,
        "ram_percent": float(mem.percent),
        "ram_percent_used": float(mem.percent),
        "ram_available_gb": round(mem.available / (1024**3), 3),
        "power_plugged": plugged,
        "network_ok": net_ok,
        "is_available": bool(plugged and net_ok and cpu < 85),
        "hour_sin": math.sin(2 * math.pi * hour / 24),
        "hour_cos": math.cos(2 * math.pi * hour / 24),
        "dow": now.tm_wday,
        "machine_id": _machine_id(),
        "hostname": socket.gethostname(),
        "source": "telemetry_bridge",
    }
    return snap


def _predict(snap: Dict[str, Any]) -> Dict[str, Any]:
    weights = _load_arx()
    threshold = float(os.environ.get("VC_LAUNCH_THRESHOLD", "0.32"))
    label = "stay_soft_15m"
    linear = 0.5
    if weights:
        try:
            threshold = float(
                weights.get("threshold") or weights.get("launch_threshold") or threshold
            )
            label = str(weights.get("label") or label)
            coef = weights.get("coef") or weights.get("coefficients") or weights.get("w")
            intercept = float(weights.get("intercept") or weights.get("bias") or 0.0)
            names = weights.get("feature_names") or []
            if coef and names:
                fmap = {
                    "cpu_free": snap.get("cpu_free", 0),
                    "cpu_percent": snap.get("cpu_percent", 0),
                    "ram_percent": snap.get("ram_percent", 0),
                    "power_plugged": 1.0 if snap.get("power_plugged") else 0.0,
                    "network_ok": 1.0 if snap.get("network_ok") else 0.0,
                    "hour_sin": snap.get("hour_sin", 0),
                    "hour_cos": snap.get("hour_cos", 0),
                    "is_available": 1.0 if snap.get("is_available") else 0.0,
                }
                score = intercept
                for i, name in enumerate(names):
                    if i >= len(coef):
                        break
                    val = fmap.get(name)
                    if val is None:
                        val = fmap.get(name.lower().replace(" ", "_"), 0.0)
                    score += float(coef[i]) * float(val or 0.0)
                linear = _sigmoid(score)
            elif coef:
                feats = [
                    snap.get("cpu_free", 0) / 100.0,
                    1.0 if snap.get("power_plugged") else 0.0,
                    1.0 if snap.get("network_ok") else 0.0,
                    snap.get("hour_sin", 0),
                    snap.get("hour_cos", 0),
                ]
                score = intercept
                for i, v in enumerate(feats):
                    if i < len(coef):
                        score += float(coef[i]) * float(v)
                linear = _sigmoid(score)
        except Exception as exc:
            logger.warning("ARX predict fallback: %s", exc)
            linear = 0.7 if snap.get("is_available") else 0.2
    else:
        linear = 0.7 if snap.get("is_available") else 0.2

    # Gate lancement sur secteur : on garde les scores ARX visibles (pas de zero artificiel)
    plugged = bool(snap.get("power_plugged"))
    hybrid = linear
    launch = bool(plugged and hybrid >= threshold)
    if not plugged:
        # launch refuse, mais les scores restent ceux du modèle
        pass

    res = _resource_summary(
        float(snap.get("cpu_percent") or 0),
        float(snap.get("ram_percent") or snap.get("ram_percent_used") or 0),
    )
    return {
        "linear": round(float(linear), 4),
        "gru": round(float(linear), 4),
        "hybrid": round(float(hybrid), 4),
        "launch": bool(launch),
        "horizon_min": 15,
        "launch_threshold": float(threshold),
        "threshold": float(threshold),
        "label": label,
        "degraded": True,
        "mode": "arx_bridge",
        "model": "arx_bridge",
        "machine_id": snap.get("machine_id"),
        "is_available_now": bool(snap.get("is_available")),
        "power_plugged": plugged,
        "network_ok": bool(snap.get("network_ok")),
        "launch_block_reason": (None if launch else ("power_unplugged" if not plugged else "below_threshold")),
        **res,
    }


def _sync(snap: Dict[str, Any], pred: Dict[str, Any], session_id: str) -> bool:
    body_snap = dict(snap)
    body_snap["predicted_availability"] = pred["hybrid"]
    body_snap["prediction_detail"] = pred
    body_snap["session_id"] = session_id
    payload = {
        "machine_id": snap["machine_id"],
        "volunteer_id": os.environ.get("VCUY_VOLUNTEER_ID") or "",
        "snapshots": [body_snap],
    }
    code, body = _http_json("POST", f"{_site_base()}/sync/snapshots", payload)
    if code != 200:
        logger.warning("sync HTTP %s %s", code, body[:200])
    return code == 200


def _register(machine_id: str) -> None:
    import psutil

    data = {
        "machine_id": machine_id,
        "hostname": socket.gethostname(),
        "os": os.name,
        "ram_gb": round(psutil.virtual_memory().total / (1024**3), 1),
        "cpu_cores": psutil.cpu_count() or 1,
        "consent_level": 3,
        "volunteer_id": os.environ.get("VCUY_VOLUNTEER_ID") or "",
    }
    code, body = _http_json("POST", f"{_site_base()}/register", data)
    if code not in (200, 201):
        logger.warning("register HTTP %s %s", code, body[:200])


def _start_session(machine_id: str, session_id: str) -> None:
    code, body = _http_json(
        "POST",
        f"{_site_base()}/sessions/start",
        {
            "session_id": session_id,
            "machine_id": machine_id,
            "boot_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    )
    if code not in (200, 201):
        logger.debug("session start HTTP %s %s", code, body[:120])
class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        logger.debug("api: " + fmt, *args)

    def _send(self, code: int, payload: dict) -> None:
        raw = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/health"):
            self._send(200, {"status": "ok", "service": "vc-telemetry-bridge"})
            return
        if path == "/predict":
            snap = _snapshot()
            pred = _predict(snap)
            with _lock:
                global _last
                _last = dict(pred)
            self._send(200, pred)
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path.split("?", 1)[0] == "/predict":
            return self.do_GET()
        self._send(404, {"error": "not found"})


def _loop() -> None:
    mid = _machine_id()
    session_id = str(uuid.uuid4())
    _register(mid)
    _start_session(mid, session_id)

    interval = max(5, int(os.environ.get("VC_AGENT_SYNC_SECONDS", "15")))
    while True:
        try:
            snap = _snapshot()
            pred = _predict(snap)
            with _lock:
                global _last
                _last = dict(pred)
            ok = _sync(snap, pred, session_id)
            logger.info(
                "bridge sync=%s hybrid=%.3f launch=%s",
                ok,
                pred["hybrid"],
                pred["launch"],
            )
        except Exception as exc:
            logger.error("bridge loop: %s", exc)
        time.sleep(interval)


def start_telemetry_bridge() -> bool:
    """Démarre API predict locale + boucle sync (idempotent)."""
    global _started
    if _started:
        return True

    host = os.environ.get("VC_AGENT_API_HOST", "127.0.0.1")
    port = int(os.environ.get("VC_AGENT_API_PORT", "7071"))

    # Si une API est déjà active sur NOTRE port, ne pas en relancer une deuxième
    try:
        import urllib.request

        with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=1) as resp:
            if resp.status == 200:
                _started = True
                logger.info("Agent/API déjà actif sur :%s", port)
                return True
    except Exception:
        pass

    def _serve():
        try:
            httpd = ThreadingHTTPServer((host, port), _Handler)
            logger.info("Telemetry bridge API http://%s:%s/predict", host, port)
            httpd.serve_forever()
        except OSError as exc:
            logger.warning("API bridge non démarrée (%s)", exc)

    threading.Thread(target=_serve, name="telemetry-api", daemon=True).start()
    threading.Thread(target=_loop, name="telemetry-sync", daemon=True).start()
    _started = True
    return True


def start_telemetry_bridge_async() -> None:
    threading.Thread(target=start_telemetry_bridge, name="telemetry-boot", daemon=True).start()
