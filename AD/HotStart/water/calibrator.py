from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from common.logger import get_logger

_log = get_logger(__name__)

_MIN_ERRORS_FOR_PROFILE = 20
_MIN_ERRORS_FOR_DRIFT   = 50


@dataclass
class DeviceProfile:
    device_id:         str
    n_errors:          int
    mean_err:          float
    std_err:           float
    p95:               float
    p99:               float
    calibrated_at:     str
    calibration_hours: int


class DeviceProfileStore:
    """Persists per-device error-distribution profiles to device_profiles.json."""

    def __init__(self, path: Path) -> None:
        self._path     = Path(path)
        self._profiles: dict[str, DeviceProfile] = {}

    def load(self) -> bool:
        """Load profiles from disk. Returns True if the file existed."""
        if not self._path.exists():
            return False
        with self._path.open(encoding="utf-8") as fh:
            raw = json.load(fh)
        self._profiles = {k: DeviceProfile(**v) for k, v in raw.items()}
        _log.info("Profils chargés : %d device(s) ← %s", len(self._profiles), self._path)
        return True

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as fh:
            json.dump(
                {k: asdict(v) for k, v in self._profiles.items()},
                fh, indent=2, ensure_ascii=False,
            )
        _log.info("Profils sauvegardés : %d device(s) → %s", len(self._profiles), self._path)

    def has(self, device_id: str) -> bool:
        return str(device_id) in self._profiles

    def get(self, device_id: str) -> DeviceProfile | None:
        return self._profiles.get(str(device_id))

    def put(self, profile: DeviceProfile) -> None:
        self._profiles[profile.device_id] = profile

    def ids(self) -> list[str]:
        return list(self._profiles.keys())


def build_profile(
    errors:            np.ndarray,
    device_id:         str,
    calibration_hours: int,
) -> DeviceProfile:
    """Build a DeviceProfile from an array of absolute prediction errors."""
    errors = errors[np.isfinite(errors) & (errors >= 0)]
    n = len(errors)
    if n < _MIN_ERRORS_FOR_PROFILE:
        _log.warning(
            "[%s] calibration : seulement %d erreurs valides (min=%d) — profil peu fiable",
            device_id, n, _MIN_ERRORS_FOR_PROFILE,
        )
    return DeviceProfile(
        device_id         = str(device_id),
        n_errors          = n,
        mean_err          = float(np.mean(errors))             if n > 0 else 0.0,
        std_err           = float(np.std(errors, ddof=1))      if n >= 2 else 0.0,
        p95               = float(np.percentile(errors, 95))   if n > 0 else 0.0,
        p99               = float(np.percentile(errors, 99))   if n > 0 else 0.0,
        calibrated_at     = datetime.now(timezone.utc).isoformat(),
        calibration_hours = calibration_hours,
    )


def check_drift(
    profile:       DeviceProfile,
    recent_errors: np.ndarray,
    z_threshold:   float = 3.0,
) -> bool:
    """
    One-tailed z-test : drift si la moyenne des erreurs récentes dépasse
    la moyenne de calibration de z_threshold écarts-types.
    """
    recent = recent_errors[np.isfinite(recent_errors) & (recent_errors >= 0)]
    n = len(recent)
    if n < _MIN_ERRORS_FOR_DRIFT or profile.n_errors == 0 or profile.std_err < 1e-9:
        return False

    z = (float(np.mean(recent)) - profile.mean_err) / (profile.std_err / np.sqrt(n))
    if z > z_threshold:
        _log.info(
            "[%s] drift détecté — z=%.2f > %.1f  "
            "(µ_récent=%.4f vs µ_profil=%.4f, p99_profil=%.4f)",
            profile.device_id, z, z_threshold,
            float(np.mean(recent)), profile.mean_err, profile.p99,
        )
        return True
    return False
