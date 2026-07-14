"""
Démarre le dossier agent/ (prédiction ARX+GRU + sync site) en sous-processus.
Appelé automatiquement au démarrage Daphne pour que la télémétrie parte même
si l'utilisateur n'a pas lancé start_with_runtime.sh.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_started = False
_lock = threading.Lock()


def _vcuy_root() -> Path:
    # .../VL/volunteer-app-2025/volontaire/services → VC-UY
    return Path(__file__).resolve().parents[4]


def _agent_dir() -> Path:
    # .../volontaire/services → .../volunteer-app-2025/agent
    return Path(__file__).resolve().parents[2] / "agent"


def _pid_file() -> Path:
    d = _vcuy_root() / ".vcuy" / "pids"
    d.mkdir(parents=True, exist_ok=True)
    return d / "vc-agent.pid"


def _log_file() -> Path:
    d = _vcuy_root() / ".vcuy" / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d / "vc-agent.log"


def agent_api_url() -> str:
    return os.environ.get("VC_AGENT_API_URL", "http://127.0.0.1:7071").rstrip("/")


def is_agent_up(timeout: float = 1.5) -> bool:
    try:
        import requests

        r = requests.get(f"{agent_api_url()}/health", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def ensure_agent_venv(agent_dir: Path) -> Path | None:
    py = agent_dir / ".venv" / "bin" / "python"
    if py.is_file():
        return py
    logger.info("Création venv agent + installation deps (torch)…")
    try:
        subprocess.run([sys.executable, "-m", "venv", str(agent_dir / ".venv")], check=True)
        pip = agent_dir / ".venv" / "bin" / "pip"
        subprocess.run([str(pip), "install", "-q", "-U", "pip"], check=True)
        subprocess.run(
            [str(pip), "install", "-q", "-r", str(agent_dir / "requirements.txt")],
            check=True,
        )
        return py if py.is_file() else None
    except Exception as exc:
        logger.error("Échec venv agent: %s", exc)
        return None


def start_research_agent(*, force: bool = False) -> bool:
    """Démarre l'agent en arrière-plan. Idempotent."""
    global _started
    with _lock:
        if _started and not force and is_agent_up():
            return True
        if is_agent_up():
            _started = True
            logger.info("Agent déjà actif sur %s", agent_api_url())
            return True

        agent_dir = _agent_dir()
        if not agent_dir.is_dir():
            logger.error("Dossier agent introuvable: %s", agent_dir)
            return False

        py = ensure_agent_venv(agent_dir)
        if not py:
            return False

        env = os.environ.copy()
        env.setdefault("VCUY_SITE_API", "https://vc-uy.npe-techs.com/api/agent")
        env.setdefault("VC_AGENT_API_HOST", "127.0.0.1")
        env.setdefault("VC_AGENT_API_PORT", "7071")
        env.setdefault("VC_AGENT_SYNC_SECONDS", "20")

        # volunteer id if known
        for cand in (
            Path(__file__).resolve().parents[1] / ".volunteer_id",
            Path(__file__).resolve().parents[1] / ".volunteer" / "volunteer_info.json",
        ):
            try:
                if cand.name.endswith(".json"):
                    import json

                    data = json.loads(cand.read_text())
                    vid = data.get("volunteer_id")
                    if vid:
                        env["VCUY_VOLUNTEER_ID"] = str(vid)
                elif cand.is_file():
                    env["VCUY_VOLUNTEER_ID"] = cand.read_text().strip()
            except Exception:
                pass

        log_path = _log_file()
        log_f = open(log_path, "a", buffering=1)
        try:
            proc = subprocess.Popen(
                [str(py), "main.py", "--foreground"],
                cwd=str(agent_dir),
                env=env,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            _pid_file().write_text(str(proc.pid))
        except Exception as exc:
            logger.error("Lancement agent échoué: %s", exc)
            log_f.close()
            return False

        for _ in range(30):
            if is_agent_up():
                _started = True
                logger.info("Agent démarré PID=%s → %s", proc.pid, agent_api_url())
                return True
            time.sleep(1)

        logger.error("Agent non joignable après démarrage — voir %s", log_path)
        return False


def start_research_agent_async() -> None:
    t = threading.Thread(target=start_research_agent, name="vc-agent-supervisor", daemon=True)
    t.start()
