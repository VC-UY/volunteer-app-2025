#!/usr/bin/env python3
"""Smoke test : hybride ARX+GRU + laptop débranché reste prédictible."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from predictor import HybridRuntimePredictor


def _base_snap(**extra):
    snap = {
        "ts_utc": "2026-07-13T18:00:00+00:00",
        "features": [
            0.1, 0.2, 0.3, 0.4, 0.0, 1.0, 0.0, 1.0,
            50.0, 55.0, 60.0, 5.0,
            70.0, 2048.0, 1.0,
            0.0, 0.0, 1.0,  # outage_active=0 (pas batterie critique)
        ],
        "cpu_percent": 20.0,
        "ram_percent_used": 40.0,
        "power_plugged": True,
        "is_connected": True,
        "compat_score": 1.0,
        "is_available": True,
        "idle_seconds": 100,
        "has_battery": True,
        "chassis": "laptop",
        "require_ac": False,
        "battery_percent": 80.0,
    }
    snap.update(extra)
    return snap


def main() -> None:
    p = HybridRuntimePredictor()
    assert p.gru_model is not None, "GRU manquant"
    assert p.rls.coef is not None, "ARX manquant"

    out = p.predict_from_snapshot(_base_snap())
    assert out["model"] == "hybrid_arx_gru"
    assert "linear" in out and "gru" in out and "hybrid" in out
    print("OK hybride ARX+GRU")
    print(f"  ARX  : {out['arx_weights']}")
    print(f"  GRU  : {out['gru_checkpoint']}")
    print(
        f"  scores linear={out['linear']:.4f} gru={out['gru']:.4f} "
        f"hybrid={out['hybrid']:.4f} launch={out['launch']}"
    )

    # Laptop débranché avec bonne autonomie → hybrid NON forcé à 0
    unplugged = p.predict_from_snapshot(
        _base_snap(
            power_plugged=False,
            has_battery=True,
            chassis="laptop",
            require_ac=False,
            battery_percent=62.0,
            features=[
                0.1, 0.2, 0.3, 0.4, 0.0, 1.0, 0.0, 1.0,
                50.0, 55.0, 60.0, 5.0,
                70.0, 2048.0, 1.0,
                0.0, 0.0, 1.0,
            ],
        )
    )
    assert unplugged["hybrid"] > 0.0, "laptop débranché ne doit pas forcer hybrid=0"
    print(
        f"OK laptop débranché hybrid={unplugged['hybrid']:.4f} "
        f"launch={unplugged['launch']} require_ac={unplugged['require_ac']}"
    )

    # Desktop sans secteur → porte AC (score 0)
    desktop = p.predict_from_snapshot(
        _base_snap(
            power_plugged=False,
            has_battery=False,
            chassis="desktop",
            require_ac=True,
            battery_percent=None,
        )
    )
    assert desktop["hybrid"] == 0.0, "desktop débranché doit garder porte secteur"
    print(f"OK desktop débranché hybrid={desktop['hybrid']:.4f} (porte AC)")


if __name__ == "__main__":
    main()
