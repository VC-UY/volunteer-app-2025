"""
Exécution locale d'un bundle vc-uyr (run.sh) — secours quand l'isolant Ashley
accepte la tâche puis meurt en code=-1 / « Résultat introuvable ».

Même contrat env : vc_INPUT, vc_OUTPUT, vc_STATE, vc_LOGS, vc_TASK_ID.
"""

from __future__ import annotations

import base64
import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def _runtime_data_dirs() -> dict[str, Path]:
    """Chemins Ashley : /tmp/vc (contrat officiel) ou VCUY_RUNTIME_HOME/data."""
    root = os.environ.get("VCUY_VC_ROOT") or "/tmp/vc"
    root_path = Path(root)
    if not root_path.is_dir():
        home = os.environ.get("VCUY_RUNTIME_HOME")
        if home:
            root_path = Path(home) / "data"
    for name in ("input", "output", "state", "logs", "bundles"):
        (root_path / name).mkdir(parents=True, exist_ok=True)
    return {
        "root": root_path,
        "input": root_path / "input",
        "output": root_path / "output",
        "state": root_path / "state",
        "logs": root_path / "logs",
    }


def run_bundle_locally(
    *,
    task_id: str,
    bundle_path: str | Path,
    timeout_secs: int = 3600,
) -> dict:
    """
    Extrait le bundle, lance run.sh, renvoie un dict compatible GET /api/result.
    """
    dirs = _runtime_data_dirs()
    # Nettoyer output pour cette exécution
    for p in dirs["output"].iterdir():
        try:
            if p.is_file():
                p.unlink()
            else:
                shutil.rmtree(p, ignore_errors=True)
        except OSError:
            pass

    work = Path(tempfile.mkdtemp(prefix=f"vcuy-local-{task_id}-"))
    try:
        with tarfile.open(bundle_path, "r:*") as tar:
            tar.extractall(work)
        run_sh = work / "run.sh"
        if not run_sh.is_file():
            matches = list(work.rglob("run.sh"))
            if not matches:
                raise FileNotFoundError("run.sh introuvable dans le bundle")
            run_sh = matches[0]
        run_sh.chmod(0o755)

        # Copier aussi dans input Ashley (visibilité / debug)
        try:
            shutil.copy2(run_sh, dirs["input"] / "run.sh")
        except OSError:
            pass

        env = os.environ.copy()
        env.update(
            {
                "vc_INPUT": str(dirs["input"]),
                "vc_OUTPUT": str(dirs["output"]),
                "vc_STATE": str(dirs["state"]),
                "vc_LOGS": str(dirs["logs"]),
                "vc_TASK_ID": str(task_id),
                "OUTPUT_DIR": str(dirs["output"]),
                "INPUT_DIR": str(dirs["input"]),
            }
        )

        logger.warning(
            "Fallback local : exécution run.sh pour tâche %s (Ashley isolant KO)",
            task_id,
        )
        proc = subprocess.run(
            ["bash", str(run_sh)],
            cwd=str(run_sh.parent),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_secs,
        )
        # Contrat Ashley : result.txt / progress.txt
        result_txt = dirs["output"] / "result.txt"
        progress_txt = dirs["output"] / "progress.txt"
        if not result_txt.exists():
            result_txt.write_text(
                f"local-fallback exit={proc.returncode}\n{(proc.stdout or '')[-2000:]}",
                encoding="utf-8",
            )
        if not progress_txt.exists():
            progress_txt.write_text("100\n", encoding="utf-8")

        files = []
        for path in sorted(dirs["output"].rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(dirs["output"]).as_posix()
            files.append(
                {
                    "name": rel,
                    "content_b64": base64.b64encode(path.read_bytes()).decode("ascii"),
                }
            )

        return {
            "ready": True,
            "result": {
                "task_id": str(task_id),
                "exit_code": int(proc.returncode),
                "return_code": int(proc.returncode),
                "stdout": (proc.stdout or "")[-8000:],
                "stderr": (proc.stderr or "")[-4000:],
                "backend": "local-fallback",
                "finished_at": time.time(),
            },
            "files": files,
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)
