import json
import time
import psutil
from pathlib import Path

HEARTBEAT_FILE = Path("heartbeat.json")

def write_heartbeat(shutdown_clean=False):
    """Write the heartbeat every collection cycle (e.g., 5 mins)."""
    data = {
        "last_ts": time.time(),
        "shutdown_clean": shutdown_clean
    }
    HEARTBEAT_FILE.write_text(json.dumps(data))

def detect_power_cut():
    """Verify at startup if the previous session stopped abruptly."""
    if not HEARTBEAT_FILE.exists():
        return None # First run
    
    try:
        data = json.loads(HEARTBEAT_FILE.read_text())
        boot_time = psutil.boot_time()
        last_hb = data["last_ts"]
        gap_s = boot_time - last_hb
        
        if data.get("shutdown_clean", False):
            return {"type": "clean", "gap_s": 0}
        elif gap_s > 60:
            return {"type": "power_cut", "gap_s": int(gap_s)}
        else:
            return {"type": "unknown", "gap_s": int(gap_s)}
    except Exception:
        return {"type": "error", "gap_s": 0}
