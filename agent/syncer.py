import requests

def _session():
    s=requests.Session(); s.trust_env=False; return s

import logging
import json
import collector
import datetime
import os
import sys
import certifi
import socket
import time
import psutil
import platform

def check_connectivity():
    """Proxy to collector connectivity check."""
    return collector.check_connectivity()

# Fix for PyInstaller one-file bundled execution certificate resolution
if getattr(sys, 'frozen', False):
    # This ensures requests finds the CA bundle inside the temp MEI directory
    os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

logger = logging.getLogger("VC-Syncer")

# Site officiel VC-UY (télémétrie recherche + téléchargement public)
SITE_API_BASE = (
    os.environ.get("VCUY_SITE_API")
    or os.environ.get("VC_SITE_API")
    or "https://vc-uy.npe-techs.com/api/agent"
).rstrip("/")

# Serveur recherche historique (optionnel, dual-write si défini)
RESEARCH_API_BASE = (
    os.environ.get("VCUY_RESEARCH_API")
    or os.environ.get("VC_RESEARCH_API")
    or ""
).rstrip("/")

# Compat : ancien nom unique
SERVER_URL = SITE_API_BASE


def _targets() -> list[str]:
    bases = [SITE_API_BASE]
    if RESEARCH_API_BASE and RESEARCH_API_BASE not in bases:
        bases.append(RESEARCH_API_BASE)
    return [b for b in bases if b]

def get_verify_path():
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, 'certifi', 'cacert.pem')
    return certifi.where()

def get_cpu_model():
    """Retrieve clean, human-readable CPU model string."""
    if platform.system().lower() == "windows":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            val, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            return val.strip()
        except:
            return platform.processor() or "Unknown CPU"
    else:
        try:
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if "model name" in line:
                        return line.split(":", 1)[1].strip()
        except:
            pass
    return platform.processor() or "Unknown CPU"

def register(machine_id, consent_level=3):
    """Register machine with specific research consent level and volunteer preferences."""
    allowed_days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    allowed_slots = ["00:00-23:59"]
    contrib_mode = "total"
    
    pref_file = "preferences.json"
    if os.path.exists(pref_file):
        try:
            with open(pref_file, "r") as f:
                prefs = json.load(f)
                allowed_days = prefs.get("allowed_days", allowed_days)
                allowed_slots = prefs.get("allowed_slots", allowed_slots)
                contrib_mode = prefs.get("mode") or prefs.get("contrib_mode", contrib_mode)
        except Exception as e:
            logger.error(f"Error reading preferences for registration: {e}")

    try:
        disk_total = round(psutil.disk_usage('/').total / (1024**3), 1)
    except Exception:
        disk_total = 0.0

    data = {
        "machine_id": machine_id,
        "hostname": socket.gethostname(),
        "os": platform.system().lower(),
        "ram_gb": round(psutil.virtual_memory().total / (1024**3), 1),
        "cpu_cores": psutil.cpu_count(),
        "timezone": time.tzname[0],
        "city": "Unknown",
        "consent_level": consent_level,
        "allowed_days": allowed_days,
        "allowed_slots": allowed_slots,
        "contrib_mode": contrib_mode,
        "cpu_model": get_cpu_model(),
        "cpu_cores_physical": psutil.cpu_count(logical=False) or psutil.cpu_count() or 1,
        "disk_total_gb": disk_total,
        "volunteer_id": os.environ.get("VCUY_VOLUNTEER_ID") or "",
    }
    ok = False
    for base in _targets():
        try:
            _session().post(f"{base}/register", json=data, verify=get_verify_path(), timeout=10)
            logger.info("Registered on %s (consent=%s)", base, consent_level)
            ok = True
        except Exception as e:
            logger.error("Registration failed on %s: %s", base, e)
    return ok

def start_session(machine_id, session_id):
    """Notify the server about a new session start."""
    data = {
        "session_id": session_id,
        "machine_id": machine_id,
        "boot_time": datetime.datetime.utcnow().isoformat(),
    }
    ok = False
    for base in _targets():
        try:
            response = _session().post(
                f"{base}/sessions/start", json=data, timeout=10, verify=get_verify_path()
            )
            if response.status_code in (200, 201):
                ok = True
        except Exception as e:
            logger.error("Session start failed on %s: %s", base, e)
    return ok

def report_power_event(machine_id, event_type, gap_s):
    """Report a power cut or restoration event to the server."""
    payload = {
        "machine_id": machine_id,
        "event_type": event_type,
        "gap_s": gap_s,
        "ts_utc": datetime.datetime.utcnow().isoformat()
    }
    for base in _targets():
        try:
            _session().post(
                f"{base}/sync/power-events", json=payload, timeout=10, verify=get_verify_path()
            )
        except Exception as e:
            logger.error("Failed to report power event on %s: %s", base, e)

# File d'attente locale : aucune donnée perdue si hors-ligne.
# Après envoi réussi → retrait de l'outbox. Rétention modèle = 72 h ailleurs.
OUTBOX_FILE = os.environ.get("VC_SYNC_OUTBOX", "sync_outbox.json")
OUTBOX_MAX = int(os.environ.get("VC_SYNC_OUTBOX_MAX", "20000"))


def _load_outbox() -> list:
    if not os.path.exists(OUTBOX_FILE):
        return []
    try:
        with open(OUTBOX_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_outbox(items: list) -> None:
    try:
        with open(OUTBOX_FILE, "w", encoding="utf-8") as f:
            json.dump(items[-OUTBOX_MAX:], f)
    except Exception as e:
        logger.error("Outbox write failed: %s", e)


def enqueue_snapshots(snapshots: list) -> None:
    """Ajoute des snapshots à l'outbox (avant / pendant sync)."""
    if not snapshots:
        return
    box = _load_outbox()
    box.extend(snapshots)
    _save_outbox(box)


def flush_outbox(machine_id, session_id) -> bool:
    """Envoie tout l'outbox au serveur. True si vide ou tout envoyé."""
    box = _load_outbox()
    if not box:
        return True
    return sync_batch(machine_id, session_id, [], include_outbox_only=True)


def sync_batch(machine_id, session_id, snapshots, *, include_outbox_only: bool = False):
    """
    Envoie les snapshots au site (et serveur recherche si défini).

    - Toujours fusionne avec l'outbox locale
    - Succès HTTP 200 → retire de l'outbox (aucune perte : sync d'abord)
    - Échec → conserve dans l'outbox pour retry
    """
    pending = [] if include_outbox_only else list(snapshots or [])
    for s in pending:
        s["session_id"] = session_id

    # Outbox d'abord (anciennes données non envoyées), puis nouveaux
    box = _load_outbox()
    for s in box:
        if "session_id" not in s:
            s["session_id"] = session_id
    batch = box + pending
    if not batch:
        return True

    # Persister immédiatement les nouveaux (hors ligne / crash)
    if pending:
        _save_outbox(box + pending)

    payload = {
        "machine_id": machine_id,
        "snapshots": batch,
        "volunteer_id": os.environ.get("VCUY_VOLUNTEER_ID") or "",
    }
    ok = False
    for base in _targets():
        try:
            response = _session().post(
                f"{base}/sync/snapshots", json=payload, timeout=30, verify=get_verify_path()
            )
            if response.status_code == 200:
                ok = True
            else:
                logger.warning("Sync %s → HTTP %s", base, response.status_code)
        except Exception as e:
            logger.error("Sync failed on %s: %s", base, e)

    if ok:
        _save_outbox([])
        logger.info("Sync OK — %d snapshot(s) envoyés, outbox vidée", len(batch))
    else:
        logger.warning("Sync échoué — %d snapshot(s) conservés en outbox locale", len(batch))
    return ok
