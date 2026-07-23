import psutil # type: ignore
import datetime
import socket
import hashlib
import uuid
import platform
import re
import time
import math
import json
import os
from collections import deque

# --- RESEARCH SPECIFICATIONS (18 DIMENSIONS) ---
HISTORY_FILE = "collector_history.json"
PREFERENCES_FILE = "preferences.json"

# Laptop sur batterie = toujours OK sauf batterie vraiment critique.
# (Débranché ≠ indisponible — flotte VC-UY = surtout des portables.)
MIN_BATTERY_PERCENT = float(os.environ.get("VC_MIN_BATTERY_PERCENT", "15"))


def read_power_state() -> dict:
    """
    Chassis + alimentation.

    - has_battery True  → laptop/portable : autonomie autorisée
    - has_battery False → desktop : pas de contrainte batterie (toujours « secteur »)
    - outage_active     → uniquement si laptop débranché ET batterie < seuil
                          (jamais juste parce que le câble est retiré)
    """
    power_plugged = True
    has_battery = False
    battery_percent = None
    try:
        battery = psutil.sensors_battery()
        if battery is not None:
            has_battery = True
            power_plugged = bool(battery.power_plugged)
            if battery.percent is not None:
                battery_percent = float(battery.percent)
    except Exception:
        pass

    chassis = "laptop" if has_battery else "desktop"
    # Desktop sans capteur batterie : considéré sur secteur.
    if not has_battery:
        power_plugged = True

    critical_battery = (
        has_battery
        and not power_plugged
        and battery_percent is not None
        and battery_percent < MIN_BATTERY_PERCENT
    )
    outage_active = 1 if critical_battery else 0

    return {
        "power_plugged": power_plugged,
        "has_battery": has_battery,
        "battery_percent": battery_percent,
        "chassis": chassis,
        "outage_active": outage_active,
        "require_ac": chassis == "desktop",
    }

class FeatureEngine:
    def __init__(self):
        # Historique du CPU LIBRE (aligné spec / feature_schema)
        self.cpu_free_history = deque(maxlen=1440)  # 24 h à 60 s/sample
        self.last_outage_ts = None
        self._prev_outage = False
        self.load_history()

    def load_history(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r") as f:
                    data = json.load(f)
                    hist = data.get("cpu_free_history")
                    if hist is None:
                        # Migration anciens dumps (CPU utilisé → approx. libre)
                        old = data.get("cpu_history", [])
                        hist = [max(0.0, 100.0 - float(x)) for x in old]
                    self.cpu_free_history = deque(hist, maxlen=1440)
                    self.last_outage_ts = data.get("last_outage_ts", None)
                    self._prev_outage = bool(data.get("prev_outage", False))
            except Exception:
                pass

    def save_history(self):
        try:
            with open(HISTORY_FILE, "w") as f:
                json.dump({
                    "cpu_free_history": list(self.cpu_free_history),
                    "last_outage_ts": self.last_outage_ts,
                    "prev_outage": self._prev_outage,
                }, f)
        except Exception:
            pass

    def get_cyclic_time(self, val, period):
        sin_val = math.sin(2 * math.pi * val / period)
        cos_val = math.cos(2 * math.pi * val / period)
        return sin_val, cos_val

    def get_moving_stats(self):
        # Dim 9-11 : moyennes glissantes du CPU libre ; dim 12 : std 1 h
        history_list = list(self.cpu_free_history)
        avg_1h = sum(history_list[-60:]) / len(history_list[-60:]) if history_list else 0
        avg_6h = sum(history_list[-360:]) / len(history_list[-360:]) if history_list else 0
        avg_24h = sum(history_list) / len(history_list) if history_list else 0

        if len(history_list[-60:]) > 1:
            mean = avg_1h
            variance = sum((x - mean) ** 2 for x in history_list[-60:]) / len(history_list[-60:])
            std_1h = math.sqrt(variance)
        else:
            std_1h = 0

        return avg_1h, avg_6h, avg_24h, std_1h

    def get_outage_stats(self, power_state: dict | None = None):
        """outage = batterie critique (laptop), pas simple débranchement."""
        state = power_state or read_power_state()
        outage_in_progress = int(state.get("outage_active") or 0)

        now = time.time()
        if outage_in_progress == 1 and not self._prev_outage:
            self.last_outage_ts = now
        self._prev_outage = outage_in_progress == 1

        if self.last_outage_ts is None:
            log_hours = 0.0
        else:
            hours_since = (now - self.last_outage_ts) / 3600
            log_hours = math.log1p(max(hours_since, 0.0))

        return log_hours, outage_in_progress

    def get_compatibility_score(self, local_now):
        # Dim 18: User preference score
        if not os.path.exists(PREFERENCES_FILE):
            return 1.0 # Default to fully available if no prefs
            
        try:
            with open(PREFERENCES_FILE, "r") as f:
                prefs = json.load(f)
                
            day_name = local_now.strftime("%a").lower() # e.g. "mon"
            current_time = local_now.time()
            
            # Check if current day is allowed
            allowed_days = prefs.get("allowed_days", [])
            if allowed_days and day_name not in allowed_days:
                return 0.0
                
            # Check if current time is within allowed slots
            allowed_slots = prefs.get("allowed_slots", [])
            if not allowed_slots:
                return 1.0
                
            for slot in allowed_slots:
                start_str, end_str = slot.split("-")
                start_time = datetime.datetime.strptime(start_str, "%H:%M").time()
                end_time = datetime.datetime.strptime(end_str, "%H:%M").time()
                
                if start_time <= current_time <= end_time:
                    return 1.0
                # Handle overnight slots (e.g. 22:00-06:00)
                if start_time > end_time:
                    if current_time >= start_time or current_time <= end_time:
                        return 1.0
            return 0.0
        except:
            return 1.0

engine = FeatureEngine()

def get_mac_address(anonymize=True):
    mac = ':'.join(re.findall('..', '%012x' % uuid.getnode()))
    if anonymize:
        salt = "vc-uy1-cameroon-2026"
        return hashlib.sha256((mac + salt).encode()).hexdigest()[:16]
    return mac

def get_stats(aggregate=True):
    global engine
    
    # 1. Base Metrics
    cpu_percent = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory()
    ram_available_mb = int(ram.available / (1024 * 1024))
    ram_used_mb = int((ram.total - ram.available) / (1024 * 1024))
    
    # Swap Metrics
    try:
        swap = psutil.swap_memory()
        swap_percent = swap.percent
        swap_total_mb = int(swap.total / (1024 * 1024))
        swap_used_mb = int(swap.used / (1024 * 1024))
    except:
        swap_percent = 0.0
        swap_total_mb = 0
        swap_used_mb = 0

    # Storage Metrics
    try:
        disk = psutil.disk_usage('/')
        disk_percent_used = disk.percent
        disk_used_gb = round(disk.used / (1024**3), 2)
        disk_free_gb = round(disk.free / (1024**3), 2)
    except:
        disk_percent_used = 0.0
        disk_used_gb = 0.0
        disk_free_gb = 0.0

    # CPU Load & Processes
    try:
        if os.name == 'posix':
            load1, load5, load15 = os.getloadavg()
        else:
            load1 = load5 = load15 = cpu_percent / 100.0
    except:
        load1 = load5 = load15 = 0.0

    try:
        process_count = len(psutil.pids())
    except:
        process_count = 0
    
    # Update history (CPU libre)
    engine.cpu_free_history.append(100.0 - cpu_percent)
    engine.save_history()
    
    now = datetime.datetime.utcnow()
    local_now = datetime.datetime.now()
    
    # 2. Generate 18-Dimension Feature Vector
    # Dim 1-8: Cyclic Time
    s_hour, c_hour = engine.get_cyclic_time(local_now.hour, 24)
    s_dow, c_dow = engine.get_cyclic_time(local_now.weekday(), 7)
    s_dom, c_dom = engine.get_cyclic_time(local_now.day, 31)
    s_mon, c_mon = engine.get_cyclic_time(local_now.month, 12)
    
    # Dim 9-12: Moving Stats
    avg1, avg6, avg24, std1 = engine.get_moving_stats()
    
    # Dim 13-15: System State
    cpu_free = 100.0 - cpu_percent
    is_conn = 1 if check_connectivity() else 0
    
    # Dim 16-17: Outage (batterie critique seulement — pas le simple débranchement laptop)
    power_state = read_power_state()
    log_h, outage_active = engine.get_outage_stats(power_state)

    # Dim 18: Preferences
    compat_score = engine.get_compatibility_score(local_now)

    # Disponibilite : laptop débranché OK si batterie >= seuil ; desktop = pas de gate AC
    is_available = int(
        cpu_percent < 90.0
        and ram.percent < 90.0
        and is_conn == 1
        and outage_active == 0
        and compat_score >= 0.5
    )

    # 3. Build Result
    return {
        "ts_utc": now.isoformat(),
        "ts_local": local_now.isoformat(),

        # --- THE 18 DIMENSIONS ---
        "features": [
            s_hour, c_hour, s_dow, c_dow, s_dom, c_dom, s_mon, c_mon,  # 1-8
            avg1, avg6, avg24, std1,                                  # 9-12
            cpu_free, float(ram_available_mb), is_conn,               # 13-15
            log_h, float(outage_active),                              # 16-17
            compat_score                                              # 18
        ],

        # --- RAW METRICS FOR DATABASE & DASHBOARD ---
        "cpu_percent": cpu_percent,
        "ram_available_mb": ram_available_mb,
        "ram_percent_used": ram.percent,
        "ram_used_mb": ram_used_mb,
        "swap_percent": swap_percent,
        "swap_total_mb": swap_total_mb,
        "swap_used_mb": swap_used_mb,
        "disk_percent_used": disk_percent_used,
        "disk_used_gb": disk_used_gb,
        "disk_free_gb": disk_free_gb,
        "load_avg_1m": load1,
        "load_avg_5m": load5,
        "load_avg_15m": load15,
        "process_count": process_count,
        "is_connected": is_conn == 1,
        "power_plugged": bool(power_state["power_plugged"]),
        "has_battery": bool(power_state["has_battery"]),
        "battery_percent": power_state["battery_percent"],
        "chassis": power_state["chassis"],
        "require_ac": bool(power_state["require_ac"]),
        "compat_score": compat_score,
        "is_available": is_available == 1,
        "idle_seconds": get_idle_time()
    }

def check_connectivity(host="8.8.8.8", port=53, timeout=3):
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except:
        return False

_idle_ts = time.time()
def get_idle_time():
    global _idle_ts
    if psutil.cpu_percent(interval=0.1) > 15.0:
        _idle_ts = time.time()
    return int(time.time() - _idle_ts)

def clear_aggregation_buffers():
    pass # No longer needed with new history engine
