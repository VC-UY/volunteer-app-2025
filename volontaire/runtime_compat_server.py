#!/usr/bin/env python3
"""
Runtime local compatible vc-uyr (API HTTP :7070), sans Docker et sans root.

Remplace le binaire Rust quand celui-ci n'est pas utilisable (auth VC-UY1,
namespaces privilégiés). Même contrat pour l'app volontaire :
  POST /api/task {task_id, bundle_b64}
  GET  /api/status | /api/result | /api/health | /api/disk | /api/tasks/history
  POST /api/control/{pause,resume,shutdown}
  POST /api/resources
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class RuntimeState:
    def __init__(self, root: Path):
        self.lock = threading.RLock()
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.state = "Ready"  # Ready | Executing | Paused
        self.task_id: str | None = None
        self.proc: subprocess.Popen | None = None
        self.started_at: float | None = None
        self.cpu_percent = 30
        self.memory_mb = 512
        self.disk_total_mb = 5000
        self.last_result: dict | None = None
        self.history: list[dict] = []
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._stop = False

    def status_payload(self) -> dict:
        with self.lock:
            return {
                "state": self.state,
                "task_id": self.task_id,
                "cpu_percent": self.cpu_percent,
                "memory_mb": self.memory_mb,
                "disk_total_mb": self.disk_total_mb,
                "uptime_secs": int(time.time() - (self.started_at or time.time()))
                if self.started_at
                else 0,
            }


STATE: RuntimeState | None = None


def _extract_bundle(bundle_bytes: bytes, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    tmp = dest / "bundle.tar.gz"
    tmp.write_bytes(bundle_bytes)
    with tarfile.open(tmp, "r:*") as tar:
        tar.extractall(dest)
    run_sh = dest / "run.sh"
    if not run_sh.is_file():
        # parfois run.sh dans un sous-dossier
        matches = list(dest.rglob("run.sh"))
        if not matches:
            raise FileNotFoundError("run.sh introuvable dans le bundle")
        run_sh = matches[0]
    run_sh.chmod(0o755)
    return run_sh


def _collect_files(output_dir: Path) -> list[dict]:
    files = []
    if not output_dir.exists():
        return files
    for path in sorted(output_dir.rglob("*")):
        if path.is_file():
            rel = path.relative_to(output_dir).as_posix()
            files.append(
                {
                    "name": rel,
                    "content_b64": base64.b64encode(path.read_bytes()).decode("ascii"),
                }
            )
    return files


def _looks_like_dl_bundle(run_sh: Path) -> bool:
    """True si le bundle est une tâche d'apprentissage distribué."""
    parent = run_sh.parent
    markers = (
        parent / "run_volunteer_vcuy.py",
        parent / "dl_config.json",
        parent / "volunteer_core.py",
    )
    if any(p.is_file() for p in markers):
        return True
    try:
        text = run_sh.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return "run_volunteer_vcuy" in text or "DISTRIBUTED_LEARNING" in text


def _ensure_dl_deps(py: str, cache_dir: Path, logf) -> None:
    """Installe torch + CIFAR seulement à la 1ʳᵉ tâche DL (pas à l'install app)."""
    def _log(msg: str) -> None:
        line = f"[runtime-dl-deps] {msg}\n"
        try:
            logf.write(line)
            logf.flush()
        except Exception:
            pass
        print(line, end="", file=sys.stderr)

    if not py:
        raise RuntimeError("VCUY_PYTHON manquant pour installer les deps DL")

    # 1) PyTorch CPU
    check = subprocess.run(
        [py, "-c", "import torch, torchvision"],
        capture_output=True,
        text=True,
    )
    if check.returncode != 0:
        _log("Installation PyTorch CPU (première tâche DL)…")
        pip = str(Path(py).parent / "pip")
        if not Path(pip).is_file():
            pip = py
            cmd = [py, "-m", "pip", "install", "-q", "torch", "torchvision",
                   "--index-url", "https://download.pytorch.org/whl/cpu"]
        else:
            cmd = [pip, "install", "-q", "torch", "torchvision",
                   "--index-url", "https://download.pytorch.org/whl/cpu"]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"pip torch failed: {proc.stderr or proc.stdout or proc.returncode}"
            )
        _log("PyTorch installé.")
    else:
        _log("PyTorch déjà présent.")

    # 2) CIFAR-10 cache machine (une fois)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cifar = cache_dir / "cifar-10-batches-py"
    if cifar.is_dir() and (cifar / "data_batch_1").is_file():
        _log(f"CIFAR-10 déjà en cache: {cifar}")
        return

    _log(f"Préparation CIFAR-10 dans {cache_dir}…")
    # Copie locale si disponible, sinon téléchargement torchvision
    candidates = [
        os.environ.get("VCUY_CIFAR_DIR", "").strip(),
        str(Path.home() / ".vcuy" / "datasets" / "cifar-10-batches-py"),
    ]
    for cand in candidates:
        if not cand:
            continue
        src = Path(cand)
        if src.is_dir() and (src / "data_batch_1").is_file():
            if src.resolve() != cifar.resolve():
                if cifar.exists():
                    shutil.rmtree(cifar)
                shutil.copytree(src, cifar)
            _log(f"CIFAR-10 copié depuis {src}")
            return

    dl = subprocess.run(
        [
            py,
            "-c",
            "import torchvision; from pathlib import Path; "
            f"root=Path({str(cache_dir)!r}); root.mkdir(parents=True, exist_ok=True); "
            "torchvision.datasets.CIFAR10(root=str(root), train=True, download=True); "
            "torchvision.datasets.CIFAR10(root=str(root), train=False, download=True); "
            "print('cifar_ok')",
        ],
        capture_output=True,
        text=True,
    )
    if dl.returncode != 0 or not (cifar.is_dir() and (cifar / "data_batch_1").is_file()):
        raise RuntimeError(
            f"CIFAR-10 indisponible: {dl.stderr or dl.stdout or 'missing batches'}"
        )
    _log("CIFAR-10 prêt.")


def _run_task(task_id: str, bundle_bytes: bytes) -> None:
    assert STATE is not None
    work = STATE.root / "tasks" / task_id / str(uuid.uuid4())[:8]
    input_dir = work / "input"
    output_dir = work / "output"
    state_dir = work / "state"
    logs_dir = work / "logs"
    for d in (input_dir, output_dir, state_dir, logs_dir):
        d.mkdir(parents=True, exist_ok=True)

    exit_code = -1
    stdout = ""
    success = False
    try:
        run_sh = _extract_bundle(bundle_bytes, input_dir)
        # Python 3.14+: un compression.py à la racine masque stdlib compression/ (gzip → crash).
        root_compression = run_sh.parent / "compression.py"
        src_compression = run_sh.parent / "src" / "compression.py"
        if root_compression.is_file() and src_compression.is_file():
            try:
                root_compression.unlink()
            except OSError:
                pass
        env = os.environ.copy()
        # Prefer the volunteer venv Python; fall back to PATH python3.
        py = (
            os.environ.get("VCUY_PYTHON")
            or os.environ.get("RUNTIME_PYTHON")
            or ""
        ).strip()
        if not py:
            # Common layout: .../e2e-v1/venv/bin/python next to runtime_compat_server.py
            for cand in (
                Path(__file__).resolve().parent / "venv" / "bin" / "python",
                Path(__file__).resolve().parent / "venv" / "bin" / "python3",
            ):
                if cand.is_file():
                    py = str(cand.resolve())
                    break
        if py:
            env["VCUY_PYTHON"] = py
            env["PATH"] = str(Path(py).parent) + os.pathsep + env.get("PATH", "")
            # Force absolute interpreter in run.sh so bare `python3` never wins.
            try:
                text = run_sh.read_text(encoding="utf-8", errors="replace")
                rewritten = text.replace("${VCUY_PYTHON:-python3}", py)
                rewritten = rewritten.replace("python3 ", f"{py} ")
                if rewritten != text:
                    run_sh.write_text(rewritten, encoding="utf-8")
            except Exception:
                pass
        # Cache dataset (rempli à la 1ʳᵉ tâche DL, pas à l'install app).
        cache = (os.environ.get("VCUY_DATASET_CACHE") or "").strip()
        if not cache:
            cache = str(Path.home() / ".vcuy" / "datasets")
        env["VCUY_DATASET_CACHE"] = cache
        # Identité DL stable pour multi-vols sur la même machine (lab E2E).
        e2e_mac = (os.environ.get("VCUY_E2E_MAC") or "").strip()
        if e2e_mac:
            env["VCUY_E2E_MAC"] = e2e_mac
        env.update(
            {
                "vc_INPUT": str(input_dir),
                "vc_OUTPUT": str(output_dir),
                "vc_STATE": str(state_dir),
                "vc_LOGS": str(logs_dir),
                "vc_TASK_ID": task_id,
                "OUTPUT_DIR": str(output_dir),
                "INPUT_DIR": str(input_dir),
            }
        )
        with STATE.lock:
            STATE.state = "Executing"
            STATE.task_id = task_id
            STATE.started_at = time.time()
            STATE.last_result = None

        log_path = logs_dir / "run.log"
        with open(log_path, "w", encoding="utf-8") as logf:
            if _looks_like_dl_bundle(run_sh):
                _ensure_dl_deps(py, Path(cache), logf)
            proc = subprocess.Popen(
                ["bash", str(run_sh)],
                cwd=str(run_sh.parent),
                env=env,
                stdout=logf,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid if hasattr(os, "setsid") else None,
            )
            with STATE.lock:
                STATE.proc = proc

            while True:
                STATE._pause_event.wait()
                if STATE._stop:
                    try:
                        os.killpg(proc.pid, signal.SIGTERM)
                    except Exception:
                        proc.terminate()
                    break
                code = proc.poll()
                if code is not None:
                    exit_code = code
                    break
                time.sleep(0.2)

        stdout = log_path.read_text(encoding="utf-8", errors="replace")
        success = exit_code == 0
    except Exception as exc:
        stdout = f"runtime error: {exc}"
        exit_code = 1
        success = False
    finally:
        files = _collect_files(output_dir)
        result = {
            "ready": True,
            "result": {
                "task_id": task_id,
                "success": success,
                "exit_code": exit_code,
                "return_code": exit_code,
                "stdout": stdout[-8000:],
            },
            "files": files,
        }
        with STATE.lock:
            STATE.last_result = result
            STATE.history.append(
                {
                    "task_id": task_id,
                    "success": success,
                    "exit_code": exit_code,
                    "finished_at": time.time(),
                }
            )
            STATE.history = STATE.history[-50:]
            STATE.state = "Ready"
            STATE.proc = None
            STATE.task_id = None
            STATE.started_at = None
            STATE._stop = False
            STATE._pause_event.set()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _send(self, code: int, payload) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        assert STATE is not None
        path = self.path.split("?", 1)[0]
        if path in ("/api/health", "/health"):
            self._send(200, {"ok": True, "backend": "vc-uyr-compat"})
            return
        if path == "/api/status":
            self._send(200, STATE.status_payload())
            return
        if path == "/api/result":
            with STATE.lock:
                if STATE.last_result and STATE.last_result.get("ready"):
                    self._send(200, STATE.last_result)
                else:
                    self._send(200, {"ready": False})
            return
        if path == "/api/disk":
            self._send(
                200,
                {
                    "disk_total_mb": STATE.disk_total_mb,
                    "disk_used_mb": 0,
                    "disk_free_mb": STATE.disk_total_mb,
                },
            )
            return
        if path == "/api/tasks/history":
            with STATE.lock:
                self._send(200, list(STATE.history))
            return
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        assert STATE is not None
        path = self.path.split("?", 1)[0]
        if path == "/api/task":
            data = self._read_json()
            task_id = str(data.get("task_id") or "").strip()
            bundle_b64 = data.get("bundle_b64") or ""
            if not task_id or not bundle_b64:
                self._send(400, {"error": "task_id and bundle_b64 required"})
                return
            with STATE.lock:
                if STATE.state == "Executing":
                    self._send(409, {"error": "runtime busy", "task_id": STATE.task_id})
                    return
            try:
                bundle_bytes = base64.b64decode(bundle_b64)
            except Exception:
                self._send(400, {"error": "invalid bundle_b64"})
                return
            threading.Thread(
                target=_run_task, args=(task_id, bundle_bytes), daemon=True
            ).start()
            # petite latence pour basculer en Executing
            time.sleep(0.05)
            self._send(200, {"accepted": True, "task_id": task_id})
            return

        if path == "/api/resources":
            data = self._read_json()
            with STATE.lock:
                if "cpu_percent" in data:
                    STATE.cpu_percent = int(data["cpu_percent"])
                if "memory_mb" in data:
                    STATE.memory_mb = int(data["memory_mb"])
                if "disk_total_mb" in data:
                    STATE.disk_total_mb = int(data["disk_total_mb"])
            self._send(200, {"ok": True})
            return

        if path == "/api/control/pause":
            with STATE.lock:
                if STATE.state == "Executing" and STATE.proc:
                    try:
                        os.kill(STATE.proc.pid, signal.SIGSTOP)
                    except Exception:
                        pass
                    STATE.state = "Paused"
                    STATE._pause_event.clear()
            self._send(200, {"ok": True})
            return

        if path == "/api/control/resume":
            with STATE.lock:
                if STATE.state == "Paused" and STATE.proc:
                    try:
                        os.kill(STATE.proc.pid, signal.SIGCONT)
                    except Exception:
                        pass
                    STATE.state = "Executing"
                    STATE._pause_event.set()
            self._send(200, {"ok": True})
            return

        if path == "/api/control/shutdown":
            with STATE.lock:
                STATE._stop = True
                STATE._pause_event.set()
                if STATE.proc:
                    try:
                        os.killpg(STATE.proc.pid, signal.SIGTERM)
                    except Exception:
                        try:
                            STATE.proc.terminate()
                        except Exception:
                            pass
            self._send(200, {"ok": True})
            return

        self._send(404, {"error": "not found"})

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[vc-uyr-compat] " + (fmt % args) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Runtime compatible vc-uyr")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7070)
    parser.add_argument(
        "--data-dir",
        default=os.environ.get(
            "VCUYR_DATA_DIR",
            str(Path.home() / ".vcuy" / "runtime-compat"),
        ),
    )
    args = parser.parse_args()

    global STATE
    STATE = RuntimeState(Path(args.data_dir))
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(
        f"vc-uyr-compat listening on http://{args.host}:{args.port} data={args.data_dir}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
