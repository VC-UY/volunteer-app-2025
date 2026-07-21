"""
Construction / localisation des bundles self-contained pour vc-uyr.

Le runtime attend un .tar.gz (ou .tgz) contenant un run.sh à la racine.
Si le manager n'a fourni que des fichiers libres, on packe un bundle
temporaire avec un run.sh généré à partir de task.command.
"""

from __future__ import annotations

import logging
import os
import tarfile
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

RUN_SH_TEMPLATE = """#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

export OUTPUT_DIR="${{vc_OUTPUT:-$SCRIPT_DIR/output}}"
mkdir -p "$OUTPUT_DIR"

# Exposer les entrées éventuelles fournies hors du bundle
if [ -n "${{vc_INPUT:-}}" ] && [ -d "$vc_INPUT" ]; then
  find "$vc_INPUT" -maxdepth 3 -type f 2>/dev/null | while read -r src; do
    base="$(basename "$src")"
    if [ ! -f "$SCRIPT_DIR/$base" ]; then
      cp -f "$src" "$SCRIPT_DIR/$base" || true
    fi
  done
fi

{command}
"""


def locate_bundle(input_path: str | None) -> str | None:
    """Retourne le chemin d'un .tar.gz/.tgz déjà présent dans le dossier d'entrée."""
    if not input_path:
        return None
    path = Path(input_path)
    if path.is_file() and path.name.endswith((".tar.gz", ".tgz")):
        return str(path)
    if not path.is_dir():
        return None
    candidates = sorted(path.iterdir())
    for item in candidates:
        if item.is_file() and item.name.endswith((".tar.gz", ".tgz")):
            return str(item)
    return None


def build_bundle_from_directory(
    input_path: str,
    command: str,
    dest_path: str | None = None,
) -> str:
    """
    Crée un bundle .tar.gz self-contained à partir d'un dossier de fichiers
    + un run.sh généré.
    """
    src = Path(input_path)
    if src.is_file():
        src = src.parent
    if not src.is_dir():
        raise FileNotFoundError(f"Dossier d'entrée introuvable: {input_path}")

    cmd = (command or "true").strip() or "true"
    run_sh = RUN_SH_TEMPLATE.format(command=cmd)

    if dest_path is None:
        fd, dest_path = tempfile.mkstemp(prefix="vcuy-bundle-", suffix=".tar.gz")
        os.close(fd)

    with tarfile.open(dest_path, "w:gz") as tar:
        run_info = tarfile.TarInfo(name="run.sh")
        run_bytes = run_sh.encode("utf-8")
        run_info.size = len(run_bytes)
        run_info.mode = 0o755
        import io

        tar.addfile(run_info, io.BytesIO(run_bytes))
        for item in sorted(src.rglob("*")):
            if not item.is_file():
                continue
            if item.name.endswith((".tar.gz", ".tgz")):
                continue
            arcname = item.relative_to(src).as_posix()
            tar.add(str(item), arcname=arcname)

    logger.info("Bundle généré: %s (depuis %s, cmd=%s)", dest_path, src, cmd)
    return dest_path


def resolve_task_bundle(task) -> str:
    """
    Localise le bundle manager, sinon en construit un à partir des fichiers
    téléchargés + task.command (ou runtime_info.command en secours).
    """
    input_path = getattr(task, "local_input_path", None)
    if not input_path:
        # Fallback: dossier standard créé au téléchargement des entrées
        candidate = Path(".volunteer") / "tasks" / str(task.task_id) / "input"
        if candidate.is_dir():
            input_path = str(candidate.resolve())
            try:
                task.local_input_path = input_path
                task.save(update_fields=["local_input_path"])
            except Exception:
                pass
    bundle = locate_bundle(input_path)
    if bundle:
        return bundle

    command = getattr(task, "command", None) or ""
    runtime_info = getattr(task, "runtime_info", None) or {}
    if not command and isinstance(runtime_info, dict):
        command = runtime_info.get("command") or runtime_info.get("cmd") or ""
    if not command:
        command = "python3 run_simulation.py"

    if not input_path:
        raise ValueError(f"Aucun fichier d'entrée pour la tâche {task.task_id}")

    tasks_root = os.environ.get("VOLUNTEER_TASKS_DIR", "tasks")
    out_dir = Path(tasks_root) / str(task.task_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = str(out_dir / "task_bundle.tar.gz")
    return build_bundle_from_directory(input_path, command, dest_path=dest)
