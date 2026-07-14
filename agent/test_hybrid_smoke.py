#!/usr/bin/env python3
"""Smoke test : hybride ARX+GRU obligatoire demarre et predit."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from predictor import HybridRuntimePredictor


def main() -> None:
    p = HybridRuntimePredictor()
    assert p.gru_model is not None, "GRU manquant"
    assert p.rls.coef is not None, "ARX manquant"
    snap = {
        "ts_utc": "2026-07-13T18:00:00+00:00",
        "features": [
            0.1, 0.2, 0.3, 0.4, 0.0, 1.0, 0.0, 1.0,
            50.0, 55.0, 60.0, 5.0,
            70.0, 2048.0, 1.0,
            0.0, 0.0, 1.0,
        ],
        "cpu_percent": 20.0,
        "ram_percent_used": 40.0,
        "power_plugged": True,
        "is_connected": True,
        "compat_score": 1.0,
        "is_available": True,
        "idle_seconds": 100,
    }
    out = p.predict_from_snapshot(snap)
    assert out["model"] == "hybrid_arx_gru"
    assert "linear" in out and "gru" in out and "hybrid" in out
    print("OK hybride ARX+GRU")
    print(f"  ARX  : {out['arx_weights']}")
    print(f"  GRU  : {out['gru_checkpoint']}")
    print(
        f"  scores linear={out['linear']:.4f} gru={out['gru']:.4f} "
        f"hybrid={out['hybrid']:.4f} launch={out['launch']}"
    )


if __name__ == "__main__":
    main()
