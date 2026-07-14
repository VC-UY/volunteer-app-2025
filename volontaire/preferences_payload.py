"""Préférences volontaire: stockage local + export heartbeat + filtrage tâches."""

from __future__ import annotations

import json
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

PREFS_FILE = Path(__file__).resolve().parent / ".volunteer" / "preferences.json"
SCHEDULE_TZ = ZoneInfo("Europe/Paris")

DAY_ALIASES = {
    "lundi": "lundi",
    "mardi": "mardi",
    "mercredi": "mercredi",
    "jeudi": "jeudi",
    "vendredi": "vendredi",
    "samedi": "samedi",
    "dimanche": "dimanche",
}


def normalize_day(day: str) -> str:
    return DAY_ALIASES.get((day or "").strip().lower(), (day or "").strip().lower())


def _machine_resources() -> dict:
    try:
        from volontaire.models import MachineInfo

        machine = getattr(MachineInfo.objects, "get_last_inserted", lambda: None)()
        if not machine:
            machine = MachineInfo.objects.first()
        if not machine:
            return {"cpu_cores": 2, "ram_mb": 4096, "disk_gb": 20}
        cpu = int(getattr(machine, "cpu_cores_logical", None) or getattr(machine, "cpu_cores", None) or 2)
        ram_total = int(getattr(machine, "ram_total", 0) or 0)
        ram_mb = int(ram_total / (1024 * 1024)) if ram_total else int(getattr(machine, "ram_mb", 0) or 4096)
        disk_total = int(getattr(machine, "disk_total", 0) or 0)
        disk_gb = int(disk_total / (1024 ** 3)) if disk_total else int(getattr(machine, "disk_gb", 0) or 20)
        return {"cpu_cores": max(1, cpu), "ram_mb": max(512, ram_mb), "disk_gb": max(1, disk_gb)}
    except Exception:
        return {"cpu_cores": 2, "ram_mb": 4096, "disk_gb": 20}


def save_preferences_file(payload: dict) -> None:
    PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PREFS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_preferences_file() -> dict:
    if PREFS_FILE.exists():
        try:
            return json.loads(PREFS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def build_preferences_payload() -> dict:
    """Payload envoyé au Manager via heartbeat."""
    machine = _machine_resources()
    stored = load_preferences_file()
    if stored:
        stored.setdefault("machine_cpu_cores", machine["cpu_cores"])
        stored.setdefault("machine_ram_mb", machine["ram_mb"])
        stored.setdefault("machine_disk_gb", machine["disk_gb"])
        return stored

    # Défaut: offre 80% des ressources machine, toujours disponible
    return {
        "cpu_max_utilisation": 80,
        "max_cpu_cores": max(1, int(machine["cpu_cores"] * 0.8)),
        "max_ram_gb": max(1, int(machine["ram_mb"] * 0.8 / 1024)),
        "max_disk_gb": max(1, int(machine["disk_gb"] * 0.9)),
        "duree_max_execution": 0,
        "priorite_min_acceptee": 0,
        "types_calcul_autorises": "",
        "schedule": [],
        "machine_cpu_cores": machine["cpu_cores"],
        "machine_ram_mb": machine["ram_mb"],
        "machine_disk_gb": machine["disk_gb"],
    }


def is_available_now(prefs: dict | None, when: datetime | None = None) -> bool:
    prefs = prefs or {}
    schedule = prefs.get("schedule") or []
    if not schedule:
        return True

    when = when or datetime.now(SCHEDULE_TZ)
    if when.tzinfo is None:
        when = when.replace(tzinfo=SCHEDULE_TZ)
    else:
        when = when.astimezone(SCHEDULE_TZ)

    days = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    today = days[when.weekday()]
    now_t = when.time().replace(second=0, microsecond=0)

    for slot in schedule:
        if normalize_day(slot.get("day")) != today:
            continue
        try:
            start = time.fromisoformat(slot.get("start", "00:00"))
            end = time.fromisoformat(slot.get("end", "23:59"))
        except ValueError:
            continue
        if start <= now_t <= end:
            return True
    return False


def task_matches_preferences(task_data: dict, prefs: dict | None) -> tuple[bool, str]:
    prefs = prefs or build_preferences_payload()
    if not is_available_now(prefs):
        return False, "Hors plage de disponibilité configurée"

    req = task_data.get("required_resources") or {}
    req_cpu = float(req.get("cpu") or req.get("cpu_cores") or 1)
    req_ram = float(req.get("ram") or req.get("memory_mb") or 512)
    req_disk = float(req.get("disk") or req.get("disk_gb") or 1)

    max_cpu = float(prefs.get("max_cpu_cores") or 1)
    max_ram_mb = float(prefs.get("max_ram_gb") or 1) * 1024.0
    max_disk = float(prefs.get("max_disk_gb") or 1)

    if req_cpu > max_cpu + 0.05:
        return False, f"CPU requis ({req_cpu}) > offert ({max_cpu})"
    if req_ram > max_ram_mb + 1:
        return False, f"RAM requise ({req_ram:.0f} Mo) > offerte ({max_ram_mb:.0f} Mo)"
    if req_disk > max_disk + 0.05:
        return False, f"Disque requis ({req_disk} Go) > offert ({max_disk} Go)"

    max_min = int(prefs.get("duree_max_execution") or 0)
    est = float(task_data.get("estimated_execution_time") or 0)
    if max_min > 0 and est > max_min * 60:
        return False, f"Durée estimée ({est / 60:.0f} min) > max ({max_min} min)"

    types = (prefs.get("types_calcul_autorises") or "").strip()
    if types:
        allowed = {t.strip().upper() for t in types.split(",") if t.strip()}
        wf_type = (task_data.get("workflow_type") or "").upper()
        if allowed and wf_type and wf_type not in allowed:
            return False, f"Type de calcul {wf_type} non autorisé dans vos préférences"

    return True, "ok"
