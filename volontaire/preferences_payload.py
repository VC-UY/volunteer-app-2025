"""Préférences volontaire: stockage local + export heartbeat + filtrage tâches.

Par défaut : toujours disponible (schedule=[]), 7j/7 24h/24.
L'utilisateur peut ensuite restreindre la plage s'il le souhaite.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

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
    "monday": "lundi",
    "tuesday": "mardi",
    "wednesday": "mercredi",
    "thursday": "jeudi",
    "friday": "vendredi",
    "saturday": "samedi",
    "sunday": "dimanche",
    "mon": "lundi",
    "tue": "mardi",
    "wed": "mercredi",
    "thu": "jeudi",
    "fri": "vendredi",
    "sat": "samedi",
    "sun": "dimanche",
}

ALL_DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def normalize_day(day: str) -> str:
    return DAY_ALIASES.get((day or "").strip().lower(), (day or "").strip().lower())


def normalize_hhmm(value: str | None, default: str = "00:00") -> str:
    """Normalise '8:00', '23:5', '23:05:00' → 'HH:MM'."""
    raw = (value or default).strip()
    if not raw:
        return default
    parts = raw.replace("h", ":").replace("H", ":").split(":")
    try:
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 and parts[1] != "" else 0
    except (TypeError, ValueError):
        return default
    hour = max(0, min(23, hour))
    minute = max(0, min(59, minute))
    return f"{hour:02d}:{minute:02d}"


def _parse_hhmm(value: str | None, default: str = "00:00") -> time:
    return time.fromisoformat(normalize_hhmm(value, default))


def _machine_resources() -> dict:
    """Lit CPU/RAM/disque machine ; tolère octets OU déjà en Mo/Go."""
    try:
        from volontaire.models import MachineInfo

        machine = getattr(MachineInfo.objects, "get_last_inserted", lambda: None)()
        if not machine:
            machine = MachineInfo.objects.first()
        if not machine:
            return {"cpu_cores": 2, "ram_mb": 4096, "disk_gb": 20}

        cpu = int(
            getattr(machine, "cpu_cores_logical", None)
            or getattr(machine, "cpu_cores", None)
            or 2
        )

        ram_total = int(getattr(machine, "ram_total", 0) or 0)
        # >= 100 Mo en octets → convertir ; sinon déjà en Mo (ex. 16384)
        if ram_total >= 100 * 1024 * 1024:
            ram_mb = ram_total // (1024 * 1024)
        elif ram_total >= 256:
            ram_mb = ram_total
        else:
            ram_mb = int(getattr(machine, "ram_mb", 0) or 4096)

        disk_total = int(getattr(machine, "disk_total", 0) or 0)
        if disk_total >= 10 * 1024 ** 3:
            disk_gb = disk_total // (1024 ** 3)
        elif disk_total >= 5:
            # déjà en Go
            disk_gb = disk_total
        else:
            disk_gb = int(getattr(machine, "disk_gb", 0) or 20)

        return {
            "cpu_cores": max(1, cpu),
            "ram_mb": max(512, ram_mb),
            "disk_gb": max(1, disk_gb),
        }
    except Exception:
        return {"cpu_cores": 2, "ram_mb": 4096, "disk_gb": 20}


def default_preferences_payload(machine: dict | None = None) -> dict:
    """Défauts : toujours disponible, ~80% des ressources machine."""
    machine = machine or _machine_resources()
    return {
        "cpu_max_utilisation": 80,
        "max_cpu_cores": max(1, int(machine["cpu_cores"] * 0.8)),
        "max_ram_gb": max(1, int(machine["ram_mb"] * 0.8 / 1024)),
        "max_disk_gb": max(1, int(machine["disk_gb"] * 0.9)),
        "duree_max_execution": 0,
        "priorite_min_acceptee": 0,
        "types_calcul_autorises": "",
        # schedule vide = 24h/24, 7j/7
        "schedule": [],
        "always_available": True,
        "machine_cpu_cores": machine["cpu_cores"],
        "machine_ram_mb": machine["ram_mb"],
        "machine_disk_gb": machine["disk_gb"],
    }


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


def schedule_is_always_on(schedule: list | None) -> bool:
    """True si pas de contrainte, ou couverture complète 00:00–23:59 tous les jours."""
    if not schedule:
        return True
    days_seen = set()
    for slot in schedule:
        day = normalize_day(slot.get("day") or "")
        if not day:
            continue
        start = normalize_hhmm(slot.get("start") or slot.get("startTime"), "00:00")
        end = normalize_hhmm(slot.get("end") or slot.get("endTime"), "23:59")
        if start <= "00:01" and end >= "23:58":
            days_seen.add(day)
    return days_seen.issuperset(ALL_DAYS)


def normalize_schedule_for_storage(schedule: list | None, *, always_available: bool = False) -> list:
    if always_available or schedule_is_always_on(schedule):
        return []
    out = []
    for slot in schedule or []:
        day = normalize_day(slot.get("day") or slot.get("jour") or "")
        if not day:
            continue
        out.append(
            {
                "day": day,
                "start": normalize_hhmm(slot.get("start") or slot.get("startTime"), "00:00"),
                "end": normalize_hhmm(slot.get("end") or slot.get("endTime"), "23:59"),
            }
        )
    return out


def ensure_default_preferences(*, force: bool = False) -> dict:
    """Crée preferences.json avec dispo totale si absent (ou force=True)."""
    if PREFS_FILE.exists() and not force:
        payload = build_preferences_payload()
        return payload
    payload = default_preferences_payload()
    save_preferences_file(payload)
    logger.info("Préférences par défaut écrites (toujours disponible): %s", PREFS_FILE)
    return payload


def build_preferences_payload() -> dict:
    """Payload envoyé au Manager via heartbeat."""
    machine = _machine_resources()
    stored = load_preferences_file()
    if not stored:
        return default_preferences_payload(machine)

    # Fusionne avec défauts + ressources machine à jour
    base = default_preferences_payload(machine)
    base.update({k: v for k, v in stored.items() if v is not None})
    base["machine_cpu_cores"] = machine["cpu_cores"]
    base["machine_ram_mb"] = machine["ram_mb"]
    base["machine_disk_gb"] = machine["disk_gb"]

    # Ressources offertes : ne jamais rester à des valeurs absurdes (ex. 1 Go sur ZBook)
    if int(base.get("max_ram_gb") or 0) < 1:
        base["max_ram_gb"] = max(1, int(machine["ram_mb"] * 0.8 / 1024))
    if int(base.get("max_disk_gb") or 0) < 1:
        base["max_disk_gb"] = max(1, int(machine["disk_gb"] * 0.9))
    if int(base.get("max_cpu_cores") or 0) < 1:
        base["max_cpu_cores"] = max(1, int(machine["cpu_cores"] * 0.8))

    schedule = normalize_schedule_for_storage(
        base.get("schedule") or [],
        always_available=bool(base.get("always_available")),
    )
    base["schedule"] = schedule
    base["always_available"] = len(schedule) == 0
    return base


def is_available_now(prefs: dict | None, when: datetime | None = None) -> bool:
    prefs = prefs or {}
    if prefs.get("always_available"):
        return True
    schedule = prefs.get("schedule") or []
    if not schedule or schedule_is_always_on(schedule):
        return True

    when = when or datetime.now(SCHEDULE_TZ)
    if when.tzinfo is None:
        when = when.replace(tzinfo=SCHEDULE_TZ)
    else:
        when = when.astimezone(SCHEDULE_TZ)

    today = ALL_DAYS[when.weekday()]
    now_t = when.time().replace(second=0, microsecond=0)

    for slot in schedule:
        if normalize_day(slot.get("day")) != today:
            continue
        try:
            start = _parse_hhmm(slot.get("start") or slot.get("startTime"), "00:00")
            end = _parse_hhmm(slot.get("end") or slot.get("endTime"), "23:59")
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
    # Soft-cap besoins disque absurdes (souvent = free disk machine)
    if req_disk > 20:
        req_disk = 2.0

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
