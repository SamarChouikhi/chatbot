"""Calibrator for gaz — identical logic to water calibrator (domain-agnostic)."""
from water.calibrator import (   # noqa: F401  re-export
    DeviceProfile,
    DeviceProfileStore,
    build_profile,
    check_drift,
)
