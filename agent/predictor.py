"""
Predictors locaux pour l'agent volontaire VC-UY1.

Architecture OBLIGATOIRE : hybride ARX 15D + GRU.
Les deux artefacts doivent etre presents dans agent/models/ :

  - weights_arx_stay_15m.json   (branche lineaire / logistique)
  - gru_uy1_phase2.pt           (branche recurrentielle)

Rien n'est optionnel : sans ARX ou sans GRU, l'agent refuse de demarrer.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import sys

import numpy as np

logger = logging.getLogger("VC-Predictor")

WEIGHTS_FILE = "rls_weights.json"
BUFFER_FILE = "sliding_window_72h.json"
MAX_BUFFER_HOURS = 72
MINUTES_IN_72H = MAX_BUFFER_HOURS * 60

ARX_WEIGHTS_NAME = "weights_arx_stay_15m.json"
GRU_CHECKPOINT_NAME = "gru_uy1_phase2.pt"

LAUNCH_THRESHOLD = float(os.getenv("VC_LAUNCH_THRESHOLD", "0.32"))
# Melange hybride : alpha * ARX + (1-alpha) * GRU
HYBRID_ALPHA = float(os.getenv("VC_HYBRID_ALPHA", "0.5"))
HORIZON_MIN = 15


def _agent_dir() -> str:
    """Racine agent/ (ou _MEIPASS sous PyInstaller)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS  # type: ignore[attr-defined]
    return os.path.dirname(os.path.abspath(__file__))


def _models_dir() -> str:
    return os.path.join(_agent_dir(), "models")


def resolve_model_path(filename: str) -> str:
    """
    Cherche un artefact modele, dans l'ordre :
      1. agent/models/<filename>
      2. research_models/... (dev depuis la racine du repo)
    """
    candidates = [
        os.path.join(_models_dir(), filename),
    ]
    repo = os.path.dirname(_agent_dir())
    if filename == ARX_WEIGHTS_NAME:
        candidates.extend(
            [
                os.path.join(repo, "research_models", "linear_model", filename),
                os.path.join(repo, "research_models", "linear_model", "weights_arx_15m.json"),
            ]
        )
    elif filename == GRU_CHECKPOINT_NAME:
        candidates.append(
            os.path.join(repo, "research_models", "gru_model", "checkpoints", filename)
        )

    for path in candidates:
        if os.path.isfile(path):
            return path
    raise FileNotFoundError(
        f"Artefact modele manquant : {filename}. "
        f"Placez-le dans {_models_dir()}/ (architecture hybride ARX+GRU obligatoire)."
    )


class FrugalPredictor:
    """Branche ARX 15D (logistique stay_soft) — obligatoire."""

    def __init__(self, feature_dim: int = 15, lambda_coeff: float = 0.99977):
        self.d = feature_dim
        self.lambda_ = lambda_coeff
        self.w = np.zeros(self.d)
        self.P = np.eye(self.d) * 100.0
        self.scaler_mean = None
        self.scaler_scale = None
        self.coef = None
        self.intercept = 0.0
        self.decision_threshold = 0.32
        self.weights_path = resolve_model_path(ARX_WEIGHTS_NAME)
        self._load_global_logistic(self.weights_path)
        self.load_weights()

    def _load_global_logistic(self, path: str) -> None:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        dim = int(data.get("input_dim", len(data.get("coef", []))))
        if dim != self.d:
            self.d = dim
            self.w = np.zeros(self.d)
            self.P = np.eye(self.d) * 100.0
        self.scaler_mean = np.array(data["scaler_mean"], dtype=np.float64)
        self.scaler_scale = np.array(data["scaler_scale"], dtype=np.float64)
        self.coef = np.array(data["coef"], dtype=np.float64)
        self.intercept = float(data["intercept"])
        self.decision_threshold = float(data.get("decision_threshold", 0.32))
        self.w = self.coef.copy()
        logger.info("ARX charge (%s, dim=%d).", path, self.d)

    def load_weights(self) -> None:
        if not os.path.exists(WEIGHTS_FILE):
            return
        try:
            with open(WEIGHTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            w = np.array(data.get("w", self.w.tolist()))
            P = np.array(data.get("P", self.P.tolist()))
            if w.shape[0] == self.d and P.shape == (self.d, self.d):
                self.w = w
                self.P = P
                logger.info("Etat RLS local charge.")
        except Exception as e:
            logger.error("Echec chargement RLS local : %s", e)

    def save_weights(self) -> None:
        try:
            with open(WEIGHTS_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "w": self.w.tolist(),
                        "P": self.P.tolist(),
                        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    },
                    f,
                    indent=4,
                )
        except Exception as e:
            logger.error("Echec sauvegarde RLS : %s", e)

    def extract_features(self, snapshot, history=None):
        """Vecteur ARX 15D (11D base + transitions)."""
        try:
            features = snapshot.get("features", [])
            if len(features) >= 18:
                s_hour, c_hour, s_dow, c_dow = features[0], features[1], features[2], features[3]
                compat = float(features[17])
                outage_active = float(features[16])
            else:
                local_now = datetime.datetime.now()
                s_hour = np.sin(2 * np.pi * local_now.hour / 24.0)
                c_hour = np.cos(2 * np.pi * local_now.hour / 24.0)
                s_dow = np.sin(2 * np.pi * local_now.weekday() / 7.0)
                c_dow = np.cos(2 * np.pi * local_now.weekday() / 7.0)
                compat = float(snapshot.get("compat_score", 1.0))
                outage_active = 0.0 if snapshot.get("power_plugged", True) else 1.0

            cpu_percent = snapshot.get("cpu_percent", 0.0) / 100.0
            ram_percent = snapshot.get("ram_percent_used", 0.0) / 100.0
            power_plugged = 1.0 if snapshot.get("power_plugged", True) else 0.0
            is_connected = 1.0 if snapshot.get("is_connected", True) else 0.0
            idle_score = min(snapshot.get("idle_seconds", 0) / 3600.0, 1.0)

            hist = history or []
            gap_sec = 60.0
            if hist:
                try:
                    t_prev = datetime.datetime.fromisoformat(
                        str(hist[-1].get("ts_utc", "")).replace("Z", "")
                    )
                    t_now = datetime.datetime.fromisoformat(
                        str(snapshot.get("ts_utc", "")).replace("Z", "")
                    )
                    gap_sec = max(0.0, (t_now - t_prev).total_seconds())
                except Exception:
                    gap_sec = 60.0

            def _rate(snaps, key_fn, default=0.5):
                if not snaps:
                    return default
                vals = [float(key_fn(s)) for s in snaps]
                return float(np.mean(vals)) if vals else default

            h1 = hist[-60:] if hist else []
            h6 = hist[-360:] if hist else []
            avail_rate_1h = _rate(
                h1, lambda s: 1.0 if s.get("is_available", False) else 0.0, 0.5
            )
            avail_rate_6h = _rate(
                h6, lambda s: 1.0 if s.get("is_available", False) else 0.0, 0.5
            )
            outage_rate_6h = _rate(
                h6,
                lambda s: (
                    float(s["features"][16])
                    if len(s.get("features", [])) > 16
                    else (0.0 if s.get("power_plugged", True) else 1.0)
                ),
                float(outage_active),
            )

            x = np.array(
                [
                    s_hour,
                    c_hour,
                    s_dow,
                    c_dow,
                    cpu_percent,
                    ram_percent,
                    power_plugged,
                    is_connected,
                    idle_score,
                    compat,
                    power_plugged * cpu_percent,
                    np.log1p(gap_sec),
                    avail_rate_1h,
                    avail_rate_6h,
                    outage_rate_6h,
                ],
                dtype=np.float64,
            )
            return x[: self.d]
        except Exception as e:
            logger.error("Extraction features ARX echouee : %s", e)
            return np.zeros(self.d)

    def update(self, x, y) -> None:
        try:
            y_pred = np.dot(self.w, x)
            alpha = y - y_pred
            Px = np.dot(self.P, x)
            xPx = np.dot(x, Px)
            g = Px / (self.lambda_ + xPx)
            g_xt_P = np.outer(g, np.dot(x, self.P))
            self.P = (self.P - g_xt_P) / self.lambda_
            self.w = np.clip(self.w + alpha * g, -10.0, 10.0)
        except Exception as e:
            logger.error("RLS update echoue : %s", e)

    def predict(self, x) -> float:
        try:
            xs = (x - self.scaler_mean) / np.maximum(self.scaler_scale, 1e-8)
            logit = float(np.dot(self.coef, xs) + self.intercept)
            return float(1.0 / (1.0 + np.exp(-np.clip(logit, -30, 30))))
        except Exception as e:
            logger.error("Inference ARX echouee : %s", e)
            return 0.5


class SlidingWindowBuffer:
    def __init__(self):
        self.buffer = []
        self.load_buffer()

    def load_buffer(self):
        if os.path.exists(BUFFER_FILE):
            try:
                with open(BUFFER_FILE, "r", encoding="utf-8") as f:
                    self.buffer = json.load(f)
                logger.info("Buffer 72h : %d snapshots.", len(self.buffer))
            except Exception:
                self.buffer = []

    def save_buffer(self):
        try:
            with open(BUFFER_FILE, "w", encoding="utf-8") as f:
                json.dump(self.buffer, f)
        except Exception as e:
            logger.error("Ecriture buffer echouee : %s", e)

    def append(self, snapshot):
        self.buffer.append(snapshot)
        if len(self.buffer) > MINUTES_IN_72H:
            self.buffer = self.buffer[-MINUTES_IN_72H:]
        self.save_buffer()

    def get_all(self):
        return self.buffer

    def get_sequence(self, seq_len: int = 180) -> np.ndarray | None:
        if not self.buffer:
            return None
        rows = []
        for snap in self.buffer[-seq_len:]:
            feat = snap.get("features", [])
            if len(feat) >= 18:
                rows.append(np.array(feat[:18], dtype=np.float32))
        if not rows:
            return None
        if len(rows) < seq_len:
            pad = np.tile(rows[0], (seq_len - len(rows), 1))
            rows = [pad[i] for i in range(len(pad))] + rows
        return np.stack(rows[-seq_len:])


def _fuse_hybrid(
    p_lin: float,
    p_gru: float,
    x_arx: np.ndarray,
    alpha: float = HYBRID_ALPHA,
    *,
    require_ac: bool = False,
) -> float:
    """
    Porte reseau (toujours) + porte secteur seulement pour desktop.

    Laptop débranché : le score hybride n'est PAS forcé à 0 — l'autonomie batterie
    est normale pour la flotte VC-UY. Le modèle ARX voit encore power_plugged en soft feature.
    """
    # index 7 = is_connected
    if float(x_arx[7]) < 0.5:
        return 0.0
    # index 6 = power_plugged — hard gate desktop uniquement
    if require_ac and float(x_arx[6]) < 0.5:
        return 0.0
    return float(alpha * p_lin + (1.0 - alpha) * p_gru)


class HybridRuntimePredictor:
    """
    Modele final volontaire : hybride ARX + GRU (les deux obligatoires).
    """

    def __init__(self, launch_threshold: float | None = None):
        self.horizon_min = HORIZON_MIN
        self.hybrid_alpha = HYBRID_ALPHA
        self.rls = FrugalPredictor()
        self.launch_threshold = (
            float(launch_threshold)
            if launch_threshold is not None
            else float(self.rls.decision_threshold)
        )
        self.buffer = SlidingWindowBuffer()
        self.seq_len = 180
        self.h_idx = 0
        self.gru_model = None
        self.feature_mean = None
        self.feature_std = None
        self.gru_path = resolve_model_path(GRU_CHECKPOINT_NAME)
        self._load_gru(self.gru_path)
        if self.gru_model is None:
            raise RuntimeError(
                "GRU obligatoire mais non charge. "
                f"Verifiez {self.gru_path} et l'installation de torch."
            )
        logger.info(
            "Hybride ARX+GRU pret (alpha=%.2f, seuil=%.3f).",
            self.hybrid_alpha,
            self.launch_threshold,
        )

    def _load_gru(self, ckpt_path: str) -> None:
        try:
            import torch
            import torch.nn as nn
        except ImportError as e:
            raise RuntimeError(
                "PyTorch est obligatoire pour le hybride ARX+GRU. "
                "Installez : pip install torch --index-url https://download.pytorch.org/whl/cpu"
            ) from e

        class _GRU(nn.Module):
            def __init__(self, hidden_dim=128, num_layers=2, dropout=0.2, n_out=1):
                super().__init__()
                self.gru = nn.GRU(
                    18,
                    hidden_dim,
                    num_layers,
                    batch_first=True,
                    dropout=dropout if num_layers > 1 else 0.0,
                )
                self.drop = nn.Dropout(dropout)
                self.head = nn.Linear(hidden_dim, n_out)

            def forward(self, x):
                out, _ = self.gru(x)
                return self.head(self.drop(out[:, -1, :]))

        ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        self.seq_len = int(ckpt.get("seq_len", 180))
        n_out = int(ckpt["model_state"]["head.weight"].shape[0])
        model = _GRU(
            hidden_dim=int(ckpt["hidden_dim"]),
            num_layers=int(ckpt.get("num_layers", 2)),
            dropout=float(ckpt.get("dropout", 0.2)),
            n_out=n_out,
        )
        model.load_state_dict(ckpt["model_state"])
        model.eval()
        self.gru_model = model
        if ckpt.get("feature_mean"):
            self.feature_mean = np.array(ckpt["feature_mean"], dtype=np.float32)
            self.feature_std = np.array(ckpt["feature_std"], dtype=np.float32)
        logger.info("GRU charge (%s, seq_len=%d).", ckpt_path, self.seq_len)

    def _gru_proba(self, seq: np.ndarray) -> float:
        import torch

        x = seq.copy()
        if self.feature_mean is not None and self.feature_std is not None:
            x = (x - self.feature_mean) / np.maximum(self.feature_std, 1e-6)
        with torch.no_grad():
            logits = self.gru_model(torch.from_numpy(x).unsqueeze(0))
            return float(torch.sigmoid(logits[0, self.h_idx]).item())

    def _resource_summary(self, snapshot: dict, minutes: int = 15) -> dict:
        n_recent = max(1, minutes)
        recent = self.buffer.get_all()[-n_recent:]
        cpu_vals = [float(s["cpu_percent"]) for s in recent if s.get("cpu_percent") is not None]
        ram_vals = [
            float(s["ram_percent_used"]) for s in recent if s.get("ram_percent_used") is not None
        ]
        cpu_avg = float(np.mean(cpu_vals)) if cpu_vals else float(snapshot.get("cpu_percent", 0.0))
        ram_avg = (
            float(np.mean(ram_vals)) if ram_vals else float(snapshot.get("ram_percent_used", 0.0))
        )
        return {
            "cpu_percent_current": float(snapshot.get("cpu_percent", cpu_avg)),
            "ram_percent_used_current": float(snapshot.get("ram_percent_used", ram_avg)),
            "cpu_percent_avg_15m": cpu_avg,
            "ram_percent_used_avg_15m": ram_avg,
            "samples_15m": int(len(recent)),
        }

    def predict_from_snapshot(self, snapshot: dict) -> dict:
        hist = self.buffer.get_all()
        x_arx = self.rls.extract_features(snapshot, history=hist)
        p_lin = self.rls.predict(x_arx)

        seq = self.buffer.get_sequence(self.seq_len)
        if seq is None:
            # Demarrage a froid : pad avec le snapshot courant (GRU toujours evalue)
            feat = snapshot.get("features", [])
            if len(feat) >= 18:
                row = np.array(feat[:18], dtype=np.float32)
                seq = np.tile(row, (self.seq_len, 1))
            else:
                seq = np.zeros((self.seq_len, 18), dtype=np.float32)
        p_gru = self._gru_proba(seq)
        # Desktop only : require AC. Laptop (has_battery / chassis=laptop) : autonomie OK.
        chassis = str(snapshot.get("chassis") or "").lower()
        has_battery = snapshot.get("has_battery")
        if has_battery is None:
            # Heuristique si snapshot ancien : power_plugged=False + pas de chassis → laptop
            require_ac = chassis == "desktop"
        else:
            require_ac = bool(snapshot.get("require_ac", chassis == "desktop" or not has_battery))
        # Env override explicite (tests / lab)
        env_ac = os.getenv("VC_REQUIRE_AC")
        if env_ac is not None:
            require_ac = env_ac.strip() in ("1", "true", "True", "yes")

        p_hybrid = _fuse_hybrid(
            p_lin, p_gru, x_arx, alpha=self.hybrid_alpha, require_ac=require_ac
        )
        res = self._resource_summary(snapshot, minutes=15)

        return {
            "linear": p_lin,
            "gru": p_gru,
            "hybrid": p_hybrid,
            "launch": p_hybrid >= self.launch_threshold,
            "horizon_min": self.horizon_min,
            "launch_threshold": self.launch_threshold,
            "hybrid_alpha": self.hybrid_alpha,
            "model": "hybrid_arx_gru",
            "arx_weights": self.rls.weights_path,
            "gru_checkpoint": self.gru_path,
            "label": "stay_soft_15m",
            "require_ac": require_ac,
            "chassis": chassis or ("laptop" if has_battery else "desktop"),
            **res,
        }

    def observe(self, snapshot: dict, y_current: float) -> None:
        self.buffer.append(snapshot)
        if os.getenv("VC_ENABLE_RLS", "0") == "1":
            x = self.rls.extract_features(snapshot, history=self.buffer.get_all()[:-1])
            self.rls.update(x, y_current)
            self.rls.save_weights()
